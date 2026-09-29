import json
from pathlib import Path
import re
import shlex

from test_relay import RepositoryCase, T1, T2
from research_relay import hooks, probes
from research_relay.state import RelayError, read_json, write_json


class NativeProbeTests(RepositoryCase):
    def setUp(self):
        super().setUp()
        self.home = self.repo.parent / "codex-home"
        (self.home / "sessions").mkdir(parents=True)
        self.rollout = self.home / "sessions" / f"rollout-{T1}.jsonl"
        self.write_rollout()

    def test_prepare_is_idempotent_and_never_trusts(self):
        first = probes.prepare(self.repo)
        before = Path(first["path"]).read_bytes()
        second = probes.prepare(self.repo)
        self.assertEqual(second["status"], "already-prepared")
        self.assertEqual(Path(first["path"]).read_bytes(), before)
        self.assertEqual(second["trusted"], "unknown")
        self.assertNotIn("state", json.loads(before)["hooks"])

    def test_foreign_hook_config_is_preserved(self):
        path = self.repo / ".codex/hooks.json"
        path.parent.mkdir()
        foreign = {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": "true"}]}]}}
        write_json(path, foreign)
        with self.assertRaises(RelayError):
            probes.prepare(self.repo)
        self.assertEqual(read_json(path), foreign)

    def test_prepare_cannot_write_through_project_config_symlink(self):
        outside = self.repo.parent / "user-config"
        outside.mkdir()
        (self.repo / ".codex").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(RelayError):
            probes.prepare(self.repo)
        self.assertFalse((outside / "hooks.json").exists())

    def test_probe_requires_correct_main_thread(self):
        with self.assertRaises(RelayError):
            probes.arm(self.repo, T2, self.home)

    def test_delivery_is_separate_from_protection_and_tokens_are_not_listed(self):
        first = probes.arm(self.repo, T1, self.home)
        again = probes.arm(self.repo, T1, self.home)
        self.assertNotIn("token", first)
        self.assertEqual(again["status"], "already-armed")
        self.assertNotIn("token", probes.inspect(self.repo, T1)["delivery_probe"])
        with self.assertRaises(RelayError):
            probes.acknowledge(self.repo, T1, "invented")
        # Direct handler calls are simulated delivery, never claimed to be native.
        result = self.hook("PostToolUse")
        content = result["hookSpecificOutput"]["additionalContext"]
        token = re.search(r"delivery token is ([0-9a-f]+)", content)[1]
        self.assertEqual(self.hook("PostToolUse"), {})
        ack = probes.acknowledge(self.repo, T1, token)
        self.assertFalse(ack["protected"])
        state = probes.inspect(self.repo, T1)
        self.assertTrue(state["delivery_probe"]["acknowledged"])
        self.assertFalse(state["protected"])

    def test_other_turn_or_child_cannot_consume_probe(self):
        probes.arm(self.repo, T1, self.home)
        self.assertEqual(self.hook("PostToolUse", turn_id="unrelated-turn"), {})
        self.assertEqual(self.hook("PostToolUse", transcript_path=str(self.repo / "child.jsonl")), {})
        self.assertFalse(probes.inspect(self.repo, T1)["delivery_probe"]["emitted"])

    def test_ack_command_quotes_working_directory_as_one_argument(self):
        probes.arm(self.repo, T1, self.home)
        cwd = self.repo / "quote' $(echo should-not-run)"
        cwd.mkdir()
        content = self.hook("PostToolUse", cwd=str(cwd))["hookSpecificOutput"]["additionalContext"]
        command = shlex.split(content.splitlines()[1])
        self.assertEqual(command[command.index("--repo") + 1], str(cwd))
        self.assertEqual(command[command.index("--thread-id") + 1], T1)

    def test_old_turn_token_is_not_accepted(self):
        probes.arm(self.repo, T1, self.home)
        result = self.hook("PostToolUse")
        token = re.search(r"delivery token is ([0-9a-f]+)", result["hookSpecificOutput"]["additionalContext"])[1]
        self.append({"type": "task_started", "turn_id": "new-turn"})
        with self.assertRaises(RelayError):
            probes.acknowledge(self.repo, T1, token)

    def test_receipts_do_not_capture_prompts_or_tool_results(self):
        probes.arm(self.repo, T1, self.home)
        self.hook("UserPromptSubmit", prompt="PRIVATE HUMAN CONTENT", tool_response="PRIVATE TOOL RESULT")
        state = probes.inspect(self.repo, T1)
        self.assertIn("UserPromptSubmit", state["reported_hook_events"])
        self.assertNotIn("PRIVATE", json.dumps(state))
        self.assertFalse(state["protected"])

    def test_feedback_hint_does_not_emit_continuation_decisions(self):
        probes.arm(self.repo, T1, self.home)
        result = self.hook("UserPromptSubmit", prompt="我有一个想法")
        self.assertNotIn("decision", result)
        self.assertNotIn("continue", result)
        self.assertEqual(result["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
