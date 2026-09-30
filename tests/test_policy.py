import json
import unittest

from base import RepoCase
from research_relay import hooks, policy
from research_relay.backends import claude
from test_hooks import claude_lines


class PolicyTests(RepoCase):
    def test_on_status_off_cycle(self):
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((code, value["policy"], value["active"]), (2, None, False))
        code, value = self.cli("on", "--repo", self.repo, "--agent", "claude", "--window", 150000)
        self.assertEqual(code, 0)
        self.assertEqual((value["active"], value["agent"], value["context_window"]), (True, "claude", 150000))
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual(code, 0)
        self.assertTrue(value["active"])
        self.assertEqual(set(value["hooks"]), {"codex", "claude"})
        self.assertFalse(value["hooks"]["claude"]["installed"])
        self.assertIsNone(value["notes"]["notes"])
        code, value = self.cli("off", "--repo", self.repo)
        self.assertEqual((code, value["active"], value["context_window"]), (0, False, 150000))
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual((code, value["active"]), (2, False))
        self.assertFalse(value["policy"]["active"])

    def test_threshold_rules(self):
        self.assertEqual(policy.threshold({"warn_fraction": 0.6}), 120000)
        self.assertEqual(policy.threshold({"warn_fraction": 0.6}, 100000), 60000)
        # An explicit policy window beats the transcript's.
        self.assertEqual(policy.threshold({"context_window": 50000, "warn_fraction": 0.5}, 100000), 25000)
        self.assertEqual(policy.threshold({"warn_fraction": 0.6, "compact_limit": 100000}, 200000), 80000)

    def test_invalid_options_rejected(self):
        for args in (("--warn-fraction", 0.99), ("--window", 0), ("--compact-limit", -1)):
            with self.subTest(args=args):
                self.assertEqual(self.cli("on", "--repo", self.repo, *args)[0], 2)
        self.assertFalse((self.runtime / "policy.json").exists())

    def test_status_reports_session_usage_and_threshold(self):
        policy.enable(self.runtime)
        transcript = self.repo.parent / "t.jsonl"
        transcript.write_text("".join(json.dumps(line) + "\n" for line in claude_lines(1000)))
        hooks.handle({"hook_event_name": "PostToolUse", "session_id": "s1", "cwd": str(self.repo),
                      "transcript_path": str(transcript)}, claude)
        code, value = self.cli("status", "--repo", self.repo)
        self.assertEqual(code, 0)
        session = value["sessions"]["s1"]
        self.assertEqual((session["last_usage"]["used"], session["last_usage"]["threshold"]), (1000, 120000))
        self.assertNotIn("closeout_emitted_at", session)


if __name__ == "__main__":
    unittest.main()
