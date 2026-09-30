import json
import subprocess
import unittest

from base import ROOT, RepoCase
from research_relay.backends import claude, codex
from research_relay.install import LAUNCHER


SKILL = ROOT / "skills/research-relay"


class InstallTests(RepoCase):
    def is_ignored(self, path):
        result = subprocess.run(["git", "-C", str(self.repo), "check-ignore", "--quiet", "--no-index", "--", path],
                                capture_output=True, text=True)
        self.assertIn(result.returncode, (0, 1), result.stderr)
        return result.returncode == 0

    def test_claude_install_merges_settings_and_is_idempotent(self):
        settings = self.repo / ".claude/settings.local.json"
        settings.parent.mkdir()
        foreign = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo foreign"}]}
        settings.write_text(json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "autoCompactEnabled": False,
                                        "hooks": {"PreToolUse": [foreign]}}))
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude")
        self.assertEqual(code, 0, value)
        self.assertTrue(value["installed"] and value["hooks_changed"])
        after = json.loads(settings.read_text())
        self.assertEqual(after["permissions"], {"allow": ["Bash(ls)"]})
        # relay no longer writes this key and cannot tell whose it is: kept and reported.
        self.assertIs(after["autoCompactEnabled"], False)
        self.assertIn("autoCompactEnabled", value["warnings"][0])
        self.assertEqual(after["hooks"]["PreToolUse"][0], foreign)
        ours = after["hooks"]["PreToolUse"][1]
        self.assertEqual(ours["matcher"], "Agent")
        self.assertEqual(ours["hooks"][0]["command"], claude.hook_command(LAUNCHER))
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
                                          "hooks": {"Stop": [stale], "PreCompact": [stale]}}))
        code, value = self.cli("install", "--repo", self.repo, "--agent", "codex")
        self.assertEqual(code, 0, value)
        self.assertIn("/hooks", value["next"])
        written = json.loads(hooks_file.read_text())
        self.assertEqual(written["description"], codex.DESCRIPTION)
        hooks = written["hooks"]
        self.assertEqual(len(hooks), 5)  # the stale Stop entry from an older relay is gone
        self.assertNotIn("Stop", hooks)
        self.assertEqual(len(hooks["PreCompact"]), 1)
        self.assertEqual(hooks["PreToolUse"][0]["matcher"], "Agent")
        command = hooks["PreCompact"][0]["hooks"][0]["command"]
        self.assertEqual(command, codex.hook_command(LAUNCHER))
        self.assertIn(str(LAUNCHER), command)
        self.assertTrue(command.endswith("hook --agent codex"))
        self.assertEqual((self.repo / ".agents/skills/research-relay").resolve(), SKILL)
        self.assertTrue(self.is_ignored(".codex/hooks.json"))
        hooks_file.write_text("local hooks, not JSON")
        code, value = self.cli("install", "--repo", self.repo, "--agent", "codex")
        self.assertEqual(code, 2)
        self.assertIn("Invalid JSON", value["error"])
        self.assertEqual(hooks_file.read_text(), "local hooks, not JSON")

    def test_print_and_uninstall(self):
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude", "--print")
        self.assertEqual((code, value), (0, claude.render_hooks(claude.hook_command(LAUNCHER))))
        self.assertFalse((self.repo / ".claude").exists())
        self.cli("install", "--repo", self.repo, "--agent", "claude")
        ignore = (self.repo / ".gitignore").read_bytes()
        code, value = self.cli("install", "--repo", self.repo, "--agent", "claude", "--uninstall")
        self.assertEqual((code, value["installed"]), (0, False))
        self.assertFalse((self.repo / ".claude/skills/research-relay").is_symlink())
        self.assertTrue((self.repo / ".claude/settings.local.json").is_file())
        self.assertEqual((self.repo / ".gitignore").read_bytes(), ignore)


if __name__ == "__main__":
    unittest.main()
