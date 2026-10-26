import json
import shlex
import subprocess
import unittest
from unittest.mock import patch

from base import ROOT, RepoCase
from research_relay.backends import claude, codex
from research_relay.install import LAUNCHER
from research_relay import install


SKILL = ROOT / "skills/research-relay"
OLD_CODEX_COMMAND = "/usr/local/bin/python3 /opt/old-relay/skills/research-relay/scripts/relay.py hook --agent codex"


class InstallTests(RepoCase):
    def test_status_preserves_inaccessible_agent_settings(self):
        with patch.object(codex, "hooks_installed", side_effect=PermissionError):
            value = install.hooks_status(self.repo)
        self.assertIsNone(value["codex"]["installed"])
        self.assertIn("not readable", value["codex"]["error"])
        self.assertFalse(value["claude"]["installed"])
        with patch.object(claude, "warnings", side_effect=PermissionError):
            self.assertIn("not readable", install.warnings(self.repo)[0])

    def is_ignored(self, path):
        result = subprocess.run(["git", "-C", str(self.repo), "check-ignore", "--quiet", "--no-index", "--", path],
                                capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_claude_install_merges_settings_and_is_idempotent(self):
        settings = self.repo / ".claude/settings.local.json"
        settings.parent.mkdir()
        foreign = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo foreign"}]}
        # An older relay registered a PreToolUse entry; install drops it and keeps the foreign one.
        old = {"matcher": "Agent", "hooks": [{"type": "command", "command": claude.hook_command(LAUNCHER, self.repo)}]}
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "autoCompactEnabled": False,
                                        "hooks": {"PreToolUse": [foreign, old]}}))
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude")
        self.assertEqual(code, 0, value)
        self.assertTrue(value["installed"] and value["hooks_changed"])
        after = json.loads(settings.read_text())
        self.assertEqual(after["permissions"], {"allow": ["Bash(ls)"]})
        # relay no longer writes this key and cannot tell whose it is: kept and reported.
        self.assertIs(after["autoCompactEnabled"], False)
        self.assertIn("autoCompactEnabled", value["warnings"][0])
        self.assertEqual(after["hooks"]["PreToolUse"], [foreign])
        self.assertEqual(after["hooks"]["PostToolUse"][0]["hooks"][0]["command"], claude.hook_command(LAUNCHER, self.repo))
        self.assertEqual(set(after["hooks"]), {"SessionStart", "UserPromptSubmit", "PreToolUse",
                                               "PostToolUse", "PreCompact"})
        target = self.repo / ".claude/skills/research-relay"
        self.assertEqual(target.resolve(), SKILL)
        for path in (".claude/skills/research-relay", ".claude/settings.local.json",
                     "artifacts/private/human-inputs/s.md"):
            self.assertTrue(self.is_ignored(path), path)
        self.assertFalse(self.is_ignored(".claude/settings.json"))
        before = (settings.read_bytes(), (self.repo / ".gitignore").read_bytes())
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude")
        self.assertEqual((code, value["hooks_changed"], value["gitignore_changed"]), (0, False, False))
        self.assertEqual((settings.read_bytes(), (self.repo / ".gitignore").read_bytes()), before)
        self.assertTrue(self.cli("status", "--repo", self.repo)[1]["hooks"]["claude"]["installed"])

    def test_codex_install_writes_hooks_and_refuses_foreign_file(self):
        hooks_file = self.repo / ".codex/hooks.json"
        hooks_file.parent.mkdir()
        stale = {"hooks": [{"type": "command", "command": "python3 /old/research-relay/scripts/relay.py hook"}]}
        hooks_file.write_text(json.dumps({"description": "research-relay experimental hooks",
                                          "hooks": {"Stop": [stale], "PreToolUse": [{"matcher": "Agent", **stale}],
                                                    "PreCompact": [stale]}}))
        code, value = self.cli("install", "--repo", self.repo, "--agent", "codex")
        self.assertEqual(code, 0, value)
        self.assertIn("/hooks", value["next"])
        written = json.loads(hooks_file.read_text())
        self.assertEqual(written["description"], codex.DESCRIPTION)
        hooks = written["hooks"]
        # The stale Stop and PreToolUse entries from an older relay are gone.
        self.assertEqual(set(hooks), {"SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact"})
        self.assertEqual(len(hooks["PreCompact"]), 1)
        command = hooks["PreCompact"][0]["hooks"][0]["command"]
        self.assertEqual(command, codex.hook_command(LAUNCHER, self.repo))
        self.assertIn(str(LAUNCHER), command)
        self.assertEqual(shlex.split(command)[-5:], ["hook", "--agent", "codex", "--repo", str(self.repo)])
        self.assertEqual((self.repo / ".agents/skills/research-relay").resolve(), SKILL)
        self.assertTrue(self.is_ignored(".codex/hooks.json"))
        hooks_file.write_text("local hooks, not JSON")
        code, value = self.cli("install", "--repo", self.repo, "--agent", "codex")
        self.assertEqual(code, 2)
        self.assertIn("Invalid JSON", value["error"])
        self.assertEqual(hooks_file.read_text(), "local hooks, not JSON")

    def test_print_and_uninstall(self):
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude", "--print")
        self.assertEqual((code, value), (0, claude.render_hooks(claude.hook_command(LAUNCHER, self.repo))))
        self.assertFalse((self.repo / ".claude").exists())
        self.cli("install", "--repo", self.repo, "--agent", "claude")
        ignore = (self.repo / ".gitignore").read_bytes()
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude", "--uninstall")
        self.assertEqual((code, value["installed"], value["hooks_changed"]), (0, False, True))
        self.assertFalse((self.repo / ".claude/skills/research-relay").is_symlink())
        # The file held relay's hooks and nothing else.
        self.assertTrue(value["hooks_file_removed"])
        self.assertFalse((self.repo / ".claude/settings.local.json").exists())
        self.assertEqual((self.repo / ".gitignore").read_bytes(), ignore)
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude", "--uninstall")
        self.assertEqual((code, value["hooks_changed"]), (0, False))

    def test_uninstall_keeps_foreign_hooks_and_keys(self):
        foreign = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo foreign"}]}
        settings = self.repo / ".claude/settings.local.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"PreToolUse": [foreign]}}))
        self.cli("install", "--repo", self.repo, "--agent", "claude")
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude", "--uninstall")
        self.assertEqual((code, value["hooks_changed"]), (0, True))
        self.assertNotIn("hooks_file_removed", value)
        self.assertEqual(json.loads(settings.read_text()),
                         {"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"PreToolUse": [foreign]}})
        hooks_file = self.repo / ".codex/hooks.json"
        hooks_file.parent.mkdir()
        hooks_file.write_text(json.dumps({"description": "team hooks", "hooks": {"Stop": [foreign]}}))
        self.cli("install", "--repo", self.repo, "--agent", "codex")
        code, value = self.cli("install", "--repo", self.repo, "--agent", "codex", "--uninstall")
        self.assertEqual((code, value["hooks_changed"]), (0, True))
        self.assertEqual(json.loads(hooks_file.read_text()), {"description": "team hooks", "hooks": {"Stop": [foreign]}})

    def test_status_tells_old_and_idle_hooks_apart(self):
        hooks_file = self.repo / ".codex/hooks.json"
        hooks_file.parent.mkdir()
        stale = [{"hooks": [{"type": "command", "command": OLD_CODEX_COMMAND}]}]
        hooks_file.write_text(json.dumps({"hooks": {"PostToolUse": stale}}))
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual(value["hooks"]["codex"], {"file": str(hooks_file), "installed": True, "current": False})
        self.assertEqual(value["hooks"]["claude"]["installed"], False)
        text = " ".join(value["warnings"])
        self.assertIn("different command than this relay writes", text)
        self.assertIn("run install --agent codex again", text)
        self.assertIn("installed but relay is off here", text)
        self.cli("install", "--repo", self.repo, "--agent", "codex")
        self.cli("on", "--repo", self.repo, "--agent", "codex", "--compact-limit", 600000)
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((value["hooks"]["codex"]["current"], value["warnings"]), (True, []))

    def test_uninstall_keeps_a_foreign_skill_and_names_other_agents_hooks(self):
        self.cli("install", "--repo", self.repo, "--agent", "codex")
        foreign = self.repo / ".claude/skills/research-relay"
        foreign.mkdir(parents=True)
        (foreign / "SKILL.md").write_text("someone else's skill")
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude", "--uninstall")
        self.assertEqual((code, value["other_agents_hooks"]), (0, ["codex"]))
        self.assertIn("left in place", value["skill_kept"])
        self.assertEqual((foreign / "SKILL.md").read_text(), "someone else's skill")

    def test_foreign_hooks_in_a_group_with_ours_survive_install_and_uninstall(self):
        mine = {"type": "command", "command": "echo my-own-formatter"}
        settings = self.repo / ".claude/settings.local.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"hooks": {
            "PostToolUse": [{"hooks": [{"type": "command", "command": OLD_CODEX_COMMAND}, mine]}],
            "Stop": "echo malformed but someone's"}}))
        self.cli("install", "--repo", self.repo, "--agent", "claude")
        after = json.loads(settings.read_text())["hooks"]
        self.assertEqual(after["PostToolUse"][0], {"hooks": [mine]})
        self.assertEqual(after["Stop"], "echo malformed but someone's")
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude", "--uninstall")
        self.assertEqual((code, value["hooks_changed"]), (0, True))
        self.assertEqual(json.loads(settings.read_text())["hooks"],
                         {"PostToolUse": [{"hooks": [mine]}], "Stop": "echo malformed but someone's"})

    def test_uninstall_removes_a_link_from_another_relay_checkout_and_print_needs_no_repo(self):
        link = self.repo / ".agents/skills/research-relay"
        link.parent.mkdir(parents=True)
        link.symlink_to(self.repo.parent / "other-relay/skills/research-relay")  # dangling: that checkout is gone
        code, value = self.cli("install", "--repo", self.repo, "--agent", "codex", "--uninstall")
        self.assertEqual(code, 0, value)
        self.assertNotIn("skill_kept", value)
        self.assertFalse(link.is_symlink())
        plain = self.repo.parent / "not a repository"
        plain.mkdir()
        code, value = self.cli("install", "--repo", plain, "--agent", "codex", "--print")
        self.assertEqual(code, 0, value)
        self.assertIn(str(plain), value["hooks"]["PreCompact"][0]["hooks"][0]["command"])

    def test_uninstall_removes_a_stale_codex_hooks_file(self):
        # What an earlier relay left in a repository the notes had moved away from.
        stale = [{"hooks": [{"type": "command", "command": OLD_CODEX_COMMAND, "timeout": 5}]}]
        hooks_file = self.repo / ".codex/hooks.json"
        hooks_file.parent.mkdir()
        hooks_file.write_text(json.dumps({
            "description": "research-relay: no compaction, fresh-context subagents, closeout before the context wall.",
            "hooks": {"PostToolUse": stale, "PreCompact": stale, "PreToolUse": [{"matcher": "Agent", **stale[0]}]}}))
        code, value = self.cli("install", "--repo", self.repo, "--agent", "codex", "--uninstall")
        self.assertEqual((code, value["hooks_changed"], value["hooks_file_removed"]), (0, True, True))
        self.assertFalse(hooks_file.exists())
        hooks_file.write_text("not JSON")
        code, value = self.cli("install", "--repo", self.repo, "--agent", "codex", "--uninstall")
        self.assertEqual(code, 2)
        self.assertEqual(hooks_file.read_text(), "not JSON")


if __name__ == "__main__":
    unittest.main()
