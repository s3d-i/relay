import json
import unittest

from base import RepoCase
from research_relay import hooks, policy
from research_relay.backends import claude
from test_hooks import claude_lines


class PolicyTests(RepoCase):
    def test_on_status_off_cycle(self):
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((code, value["policy"], value["active"], value["mode"]), (2, None, False, None))
        code, value = self.cli("on", "--repo", self.repo, "--agent", "claude", "--window", 150000)
        self.assertEqual(code, 0)
        self.assertEqual((value["active"], value["mode"], value["agent"], value["context_window"]),
                         (True, "trajectory", "claude", 150000))
        self.assertEqual((value["warn_fraction"], value["reserve"], value["checkpoint_fraction"]),
                         (0.75, 100000, 0.2))
        self.assertNotIn("previous_mode", value)
        stored = json.loads((self.runtime / "policy.json").read_text())
        self.assertEqual(stored["version"], 2)
        self.assertNotIn("warnings", stored)
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((code, value["active"], value["mode"], value["warnings"]), (0, True, "trajectory", []))
        self.assertEqual(set(value["hooks"]), {"codex", "claude"})
        self.assertFalse(value["hooks"]["claude"]["installed"])
        self.assertIsNone(value["notes"]["notes"])
        code, value = self.cli("off", "--repo", self.repo)
        self.assertEqual((code, value["active"], value["context_window"]), (0, False, 150000))
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((code, value["active"], value["mode"]), (2, False, None))
        self.assertFalse(value["policy"]["active"])

    def test_bare_on_is_trajectory_and_a_mode_change_is_printed(self):
        code, value = self.cli("on", "--repo", self.repo)
        self.assertEqual((code, value["mode"], value["agent"], value["context_window"]), (0, "trajectory", None, None))
        code, value = self.cli("on", "--repo", self.repo, "--mode", "autoresearch", "--agent", "codex")
        self.assertEqual((code, value["mode"], value["previous_mode"]), (0, "autoresearch", "trajectory"))
        self.assertIn("compaction ceiling", value["warnings"][0])
        code, value = self.cli("on", "--repo", self.repo, "--mode", "autoresearch", "--agent", "codex",
                               "--compact-limit", 600000)
        self.assertEqual((code, value["warnings"]), (0, []))
        self.assertNotIn("previous_mode", value)
        code, value = self.cli("on", "--repo", self.repo)
        self.assertEqual((value["mode"], value["previous_mode"]), ("trajectory", "autoresearch"))

    def test_invalid_options_rejected(self):
        cases = (("--warn-fraction", 0.99), ("--window", 0), ("--compact-limit", -1), ("--reserve", -1),
                 ("--checkpoint-fraction", 1), ("--window", 100000),  # nothing left above the default reserve
                 ("--mode", "autoresearch"), ("--mode", "autoresearch", "--agent", "claude"))
        for args in cases:
            with self.subTest(args=args):
                self.assertEqual(self.cli("on", "--repo", self.repo, *args)[0], 2)
        self.assertFalse((self.runtime / "policy.json").exists())
        self.assertEqual(self.cli("on", "--repo", self.repo, "--window", 100000, "--reserve", 20000)[0], 0)

    def test_status_reports_session_usage_thresholds_and_warnings(self):
        policy.enable(self.runtime, "autoresearch", "claude", 1000000)
        transcript = self.repo.parent / "t.jsonl"
        transcript.write_text("".join(json.dumps(line) + "\n" for line in claude_lines(1000)))
        hooks.handle({"hook_event_name": "PostToolUse", "session_id": "s1", "cwd": str(self.repo),
                      "transcript_path": str(transcript)}, claude)
        settings = self.repo / ".claude/settings.local.json"
        settings.parent.mkdir()
        settings.write_text(json.dumps({"autoCompactEnabled": False}))
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((code, value["mode"]), (0, "autoresearch"))
        session = value["sessions"]["s1"]
        self.assertEqual((session["last_usage"]["used"], session["last_usage"]["final"],
                          session["last_usage"]["step"]), (1000, 750000, 200000))
        self.assertEqual((session["baseline"], session["final_sent"]), (1000, False))
        self.assertEqual(session["told"]["mode"], "autoresearch")
        self.assertEqual(len(value["warnings"]), 1)
        self.assertIn("autoCompactEnabled", value["warnings"][0])

    def test_policy_from_before_modes_reads_as_autoresearch(self):
        (self.runtime).mkdir(parents=True, exist_ok=True)
        (self.runtime / "policy.json").write_text(json.dumps(
            {"active": True, "agent": "claude", "context_window": 1000000, "warn_fraction": 0.6}))
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((code, value["mode"]), (0, "autoresearch"))


if __name__ == "__main__":
    unittest.main()
