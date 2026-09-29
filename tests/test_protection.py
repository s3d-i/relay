import copy
import json
import os
from pathlib import Path
import shlex
import sys
from unittest.mock import patch

from test_relay import RepositoryCase, T1
from research_relay import hooks, protection, watcher
from research_relay.state import RelayError, lock, marker_path, read_json, write_json


class ScopedProtectionTests(RepositoryCase):
    def setUp(self):
        super().setUp()
        self.home = self.repo.parent / "codex-home"
        self.home.mkdir()
        self.user_config = self.home / "config.toml"
        self.user_config.write_text("model_auto_compact_token_limit = 100000\n")
        self.hook_path = self.repo / ".codex/hooks.json"
        self.hook_path.parent.mkdir()
        write_json(self.hook_path, hooks.configuration(
            sys.executable, protection.ROOT / "skills/research-relay/scripts/relay.py"))
        self.config = {
            "config": {"model_auto_compact_token_limit": 100000, "features": {"hooks": True}},
            "layers": [{"name": {"file": str(self.user_config)}},
                       {"name": {"dotCodexFolder": str(self.hook_path.parent)}}],
        }
        command = shlex.join([sys.executable,
                              str(protection.ROOT / "skills/research-relay/scripts/relay.py"), "hook"])
        self.listing = {"data": [{"cwd": str(self.repo), "errors": [], "hooks": [
            {"eventName": event, "sourcePath": str(self.hook_path), "handlerType": "command",
             "command": command, "enabled": True, "trustStatus": "trusted",
             "currentHash": f"definition-{event}"} for event in protection.EVENTS]}]}
        self.requirements = {"requirements": None}
        self.overrides = ["-c", 'unrelated_private_setting="PRIVATE VALUE"']
        for target, kwargs in (
            ("host_overrides", {"return_value": self.overrides}),
            ("read_capabilities", {"side_effect": self.resolve}),
        ):
            patcher = patch.object(protection, target, **kwargs)
            mock = patcher.start()
            self.addCleanup(patcher.stop)
            if target == "read_capabilities":
                self.reader = mock
        with patch.dict(os.environ, {"CODEX_THREAD_ID": T1}), \
                patch.object(protection, "desktop_host", return_value=(123, "/fixture/codex")), \
                patch.object(protection, "locate", return_value=self.rollout):
            _, checked = protection.environment(self.repo, T1, self.home)
        self.value = {**checked, "repo": str(self.repo), "thread_id": T1, "turn_id": "turn-1",
                      "rollout": str(self.rollout), "host_identity": "fixture-host",
                      "mode": watcher.PROTECTED, "nonce": "fixture", "poll": 0.05,
                      "status": "watching"}
        write_json(marker_path(self.runtime, T1), {
            "rollout": str(self.rollout), "guard_requested": True,
            "delivery_probe": {"turn_id": "turn-1", "emitted": True, "acknowledged": True,
                               "hooks_fingerprint": protection.hook_fingerprint(self.repo)},
        })
        self.reader.reset_mock()

    def resolve(self, *args):
        return copy.deepcopy((self.config, self.listing, self.requirements))

    def edit_user_config(self, text="[agents.default]\nmodel = 'other-project-model'\n"):
        self.user_config.write_text(text)

    def check(self):
        protection.check_runtime(self.runtime, self.value)

    def test_unchanged_inputs_do_not_launch_reader_or_store_private_overrides(self):
        self.check()
        self.reader.assert_not_called()
        self.assertNotIn("PRIVATE VALUE", json.dumps(self.value))

    def test_other_project_agent_config_rechecks_this_repo_without_revoking(self):
        before = read_json(marker_path(self.runtime, T1))
        self.edit_user_config()
        self.check()
        self.reader.assert_called_once_with(self.repo, self.home, "/fixture/codex", self.overrides)
        self.assertEqual(self.value["capabilities"]["files"][str(self.user_config)],
                         protection.fingerprint(self.user_config))
        self.assertEqual(read_json(marker_path(self.runtime, T1)), before)
        self.check()
        self.assertEqual(self.reader.call_count, 1)

    def test_another_project_trust_entry_does_not_affect_current_hooks(self):
        self.edit_user_config("[hooks.state.'other-project:pre_compact:0:0']\nenabled = false\n")
        self.listing["data"].append({"cwd": str(self.repo.parent / "other-project"),
                                      "errors": ["untrusted hooks"], "hooks": []})
        self.check()
        self.reader.assert_called_once()

    def test_other_project_local_config_is_not_observed(self):
        other = self.repo.parent / "other-project/.codex/config.toml"
        other.parent.mkdir(parents=True)
        other.write_text("[agents.default]\nmodel = 'other-model'\n")
        self.check()
        self.reader.assert_not_called()

    def test_current_project_agent_config_and_shadowed_defaults_are_allowed(self):
        (self.hook_path.parent / "config.toml").write_text("[agents.worker]\nmodel = 'new-model'\n")
        # The project/host still resolves the original effective ceiling.
        self.edit_user_config("model_auto_compact_token_limit = 200000\n")
        self.check()
        self.reader.assert_called_once()

    def test_effective_compaction_ceiling_change_preserves_failed_snapshot(self):
        baseline = copy.deepcopy(self.value["capabilities"])
        self.edit_user_config("model_auto_compact_token_limit = 200000\n")
        self.config["config"]["model_auto_compact_token_limit"] = 200000
        with self.assertRaisesRegex(RelayError, "compaction ceiling changed for this project"):
            self.check()
        self.assertEqual(self.value["capabilities"], baseline)

    def test_current_hook_disabled_untrusted_or_changed_still_revokes(self):
        original = copy.deepcopy(self.listing)
        self.edit_user_config()
        for field, value in (("enabled", False), ("trustStatus", "untrusted"),
                             ("currentHash", "changed-definition")):
            with self.subTest(field=field):
                self.listing = copy.deepcopy(original)
                self.listing["data"][0]["hooks"][0][field] = value
                with self.assertRaisesRegex(RelayError, "Relay .*changed|Relay .*untrusted"):
                    self.check()

    def test_disabled_hooks_and_managed_only_policy_still_revoke(self):
        self.edit_user_config()
        self.config["config"]["features"]["hooks"] = False
        with self.assertRaisesRegex(RelayError, "hooks are disabled"):
            self.check()
        self.config["config"]["features"]["hooks"] = True
        self.requirements["requirements"] = {"allow_managed_hooks_only": True}
        with self.assertRaisesRegex(RelayError, "Only managed hooks"):
            self.check()

    def test_relay_hook_definition_change_requires_native_delivery_again(self):
        config = read_json(self.hook_path)
        config["hooks"]["PostToolUse"][0]["hooks"][0]["command"] = "changed-command"
        write_json(self.hook_path, config)
        with self.assertRaisesRegex(RelayError, "Native Relay hook configuration changed"):
            self.check()

    def test_unrelated_project_hooks_and_formatting_preserve_delivery(self):
        before = read_json(marker_path(self.runtime, T1))
        config = read_json(self.hook_path)
        config["description"] = "Updated description"
        config["hooks"]["PostToolUse"].append({"hooks": [{"type": "command", "command": "true"}]})
        self.hook_path.write_text(json.dumps(config, sort_keys=True))
        self.check()
        reader = protection.Rollout(self.rollout).bind(self.repo, T1)
        protection.check_delivery(self.repo, reader)
        self.assertEqual(read_json(marker_path(self.runtime, T1)), before)
        self.assertEqual(self.reader.call_count, 1)

    def test_lost_guard_is_not_hidden_by_unrelated_config_change(self):
        self.edit_user_config()
        marker = read_json(marker_path(self.runtime, T1))
        marker["guard_requested"] = False
        write_json(marker_path(self.runtime, T1), marker)
        with self.assertRaisesRegex(RelayError, "Scoped guard"):
            self.check()
        self.reader.assert_not_called()

    def test_reader_failure_does_not_accept_new_fingerprints(self):
        baseline = copy.deepcopy(self.value["capabilities"])
        self.edit_user_config()
        self.reader.side_effect = RelayError("Desktop config/read readiness query failed.")
        with self.assertRaisesRegex(RelayError, "readiness query failed"):
            self.check()
        self.assertEqual(self.value["capabilities"], baseline)

    def test_concurrent_configuration_change_is_reread(self):
        self.edit_user_config()

        def change_during_read(*args):
            result = self.resolve()
            if self.reader.call_count == 1:
                self.edit_user_config("model_auto_compact_token_limit = 200000\n")
                self.config["config"]["model_auto_compact_token_limit"] = 200000
            return result

        self.reader.side_effect = change_during_read
        with self.assertRaisesRegex(RelayError, "compaction ceiling changed"):
            self.check()
        self.assertEqual(self.reader.call_count, 2)

    def test_newly_resolved_layer_is_read_again_and_observed_later(self):
        layer = self.repo.parent / "profile.config.toml"
        layer.write_text("[agents.worker]\nmodel = 'profile-model'\n")
        self.config["layers"].append({"name": {"file": str(layer)}})
        self.edit_user_config()
        self.check()
        self.assertEqual(self.reader.call_count, 2)
        self.assertIn(str(layer), self.value["capabilities"]["files"])
        layer.write_text("model_auto_compact_token_limit = 200000\n")
        self.config["config"]["model_auto_compact_token_limit"] = 200000
        with self.assertRaisesRegex(RelayError, "compaction ceiling changed"):
            self.check()

    def test_legacy_activation_requires_reactivation_instead_of_guessing_reader(self):
        del self.value["capabilities"]["resolver"]
        self.edit_user_config()
        with self.assertRaisesRegex(RelayError, "Protection input changed"):
            self.check()
        self.reader.assert_not_called()

    def test_status_retains_live_protection_after_unrelated_change(self):
        write_json(self.runtime / "watcher.json", self.value)
        self.edit_user_config()
        with lock(self.runtime / "watcher.lock"), \
                patch.object(watcher, "process_identity", return_value="fixture-host"):
            result = watcher.status(self.repo, T1)
        self.assertTrue(result["live"])
        self.assertTrue(result["protected"])
        self.assertEqual(result["research_start"], "protected")

    def test_watcher_refreshes_snapshot_without_queuing_closeout(self):
        write_json(self.runtime / "launch.json", self.value)
        self.edit_user_config()
        observations = []

        def stop_after_poll(*args):
            observations.append(read_json(self.runtime / "watcher.json"))
            write_json(self.runtime / "stop.json", {"nonce": self.value["nonce"]})

        # Simulate one protected poll in a temporary repository, never a live host.
        with patch.object(watcher, "process_identity", return_value="fixture-host"), \
                patch.object(watcher.signal, "signal"), \
                patch.object(watcher.time, "sleep", side_effect=stop_after_poll):
            self.assertEqual(watcher.watch(self.repo, self.value["nonce"]), 0)
        self.assertTrue(observations[0]["protected"])
        self.assertEqual(observations[0]["status"], "watching")
        self.assertEqual(observations[0]["capabilities"]["files"][str(self.user_config)],
                         protection.fingerprint(self.user_config))
        self.assertFalse(read_json(marker_path(self.runtime, T1)).get("notices"))
