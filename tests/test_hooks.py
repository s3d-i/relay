import json
import subprocess
import sys
import unittest

from base import ROOT, RepoCase
from research_relay import hooks, policy
from research_relay.backends import claude, codex


def codex_lines(used, window=100000):
    return [
        {"type": "session_meta", "payload": {"id": "t1", "cwd": "/x"}},
        {"type": "event_msg", "timestamp": "2026-09-30T00:00:00Z",
         "payload": {"type": "token_count", "info": None}},
        {"type": "event_msg", "timestamp": "2026-09-30T00:00:01Z", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": used - 1, "output_tokens": 1, "total_tokens": used},
            "total_token_usage": {"total_tokens": used * 9}, "model_context_window": window}}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "done"}},
    ]


def claude_lines(used):
    return [
        {"type": "user", "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "timestamp": "2026-09-30T00:00:01Z", "message": {"role": "assistant", "usage": {
            "input_tokens": 10, "cache_read_input_tokens": used - 30,
            "cache_creation_input_tokens": 10, "output_tokens": 10}}},
        {"type": "progress", "data": {}},
    ]


# (backend, fixture, a usage exactly at the default threshold)
CASES = {"codex": (codex, codex_lines, 60000), "claude": (claude, claude_lines, 120000)}


class HookCase(RepoCase):
    def setUp(self):
        super().setUp()
        policy.enable(self.runtime)
        self.transcript = self.repo.parent / "transcript.jsonl"

    def write(self, lines):
        self.transcript.write_text("".join(json.dumps(line) + "\n" for line in lines))

    def hook(self, backend, event, **kw):
        return hooks.handle({"hook_event_name": event, "session_id": "s1", "cwd": str(self.repo),
                             "transcript_path": str(self.transcript), **kw}, backend)


class HookTests(HookCase):
    def test_precompact_blocked_for_both_backends(self):
        for trigger in ("auto", "manual"):
            result = self.hook(codex, "PreCompact", trigger=trigger)
            self.assertFalse(result["continue"])
            self.assertIn("forbids compaction", result["stopReason"])
            result = self.hook(claude, "PreCompact", trigger=trigger)
            self.assertEqual(result["decision"], "block")
            self.assertNotIn("continue", result)
        blocked = policy.session(self.runtime, "s1")["precompact_blocked"]
        self.assertEqual([b["trigger"] for b in blocked], ["auto", "auto", "manual", "manual"])

    def test_unrelated_repo_and_missing_policy_return_empty(self):
        other = self.repo.parent / "other"
        other.mkdir()
        subprocess.run(["git", "init", "-q", str(other)], check=True)
        plain = self.repo.parent / "plain"
        plain.mkdir()
        for cwd in (other, plain):
            for backend in (codex, claude):
                self.assertEqual(self.hook(backend, "PreCompact", cwd=str(cwd)), {})
                self.assertEqual(self.hook(backend, "PostToolUse", cwd=str(cwd)), {})

    def test_policy_off_returns_empty(self):
        policy.disable(self.runtime)
        for backend in (codex, claude):
            self.assertEqual(self.hook(backend, "PreCompact", trigger="auto"), {})
            self.assertEqual(self.hook(backend, "UserPromptSubmit"), {})
        self.assertFalse((self.runtime / "sessions").exists())

    def test_closeout_emitted_once_at_threshold(self):
        for name, (backend, lines, used) in CASES.items():
            with self.subTest(agent=name):
                self.write(lines(used))
                first = self.hook(backend, "PostToolUse", session_id=name)
                self.assertEqual(first["hookSpecificOutput"]["hookEventName"], "PostToolUse")
                self.assertIn("Begin closeout", first["hookSpecificOutput"]["additionalContext"])
                self.assertEqual(self.hook(backend, "PostToolUse", session_id=name), {})
                state = policy.session(self.runtime, name)
                self.assertEqual(state["last_usage"]["used"], used)
                self.assertEqual(state["last_usage"]["threshold"], used)
                self.assertTrue(state["closeout_emitted_at"])

    def test_no_emission_below_threshold_or_without_transcript(self):
        for name, (backend, lines, used) in CASES.items():
            with self.subTest(agent=name):
                self.write(lines(used - 1))
                self.assertEqual(self.hook(backend, "PostToolUse", session_id=name), {})
                self.assertEqual(policy.session(self.runtime, name)["last_usage"]["used"], used - 1)
                self.assertEqual(self.hook(backend, "PostToolUse", transcript_path=None), {})
                self.assertEqual(self.hook(backend, "PostToolUse",
                                           transcript_path=str(self.repo / "absent.jsonl")), {})

    def test_tail_read_finds_last_usage_in_large_transcript(self):
        padding = {"type": "event_msg", "payload": {"type": "agent_message", "message": "x" * 1000}}
        for name, (backend, lines, used) in CASES.items():
            with self.subTest(agent=name):
                self.write([padding] * 400 + lines(used) + [padding] * 3)
                self.assertGreater(self.transcript.stat().st_size, 256 * 1024)
                self.assertEqual(backend.read_usage(self.transcript)["used"], used)
                self.assertIn("hookSpecificOutput", self.hook(backend, "PostToolUse", session_id=name))

    def test_feedback_guidance_only_on_first_prompt(self):
        first = self.hook(claude, "UserPromptSubmit", prompt="go")
        self.assertEqual(first["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")
        self.assertIn("provenance", first["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.hook(claude, "UserPromptSubmit", prompt="more"), {})
        self.assertIn("hookSpecificOutput", self.hook(codex, "UserPromptSubmit", session_id="s2"))

    def test_pretooluse_denies_inherited_context_only(self):
        denied = [(claude, "Agent", {"subagent_type": "fork", "prompt": "x"}),
                  (codex, "Agent", {"prompt": "x"}),
                  (codex, "Agent", {"fork_turns": "all", "prompt": "x"})]
        allowed = [(claude, "Agent", {"subagent_type": "Explore", "prompt": "x"}),
                   (claude, "Agent", {"prompt": "x"}), (claude, "Bash", {"command": "ls"}),
                   (codex, "Agent", {"fork_turns": "none", "prompt": "x"}), (codex, "Shell", {})]
        for backend, tool, tool_input in denied:
            with self.subTest(agent=backend.NAME, tool_input=tool_input):
                out = self.hook(backend, "PreToolUse", tool_name=tool, tool_input=tool_input)["hookSpecificOutput"]
                self.assertEqual(out["hookEventName"], "PreToolUse")
                self.assertEqual(out["permissionDecision"], "deny")
                self.assertIn("fresh context", out["permissionDecisionReason"])
        for backend, tool, tool_input in allowed:
            with self.subTest(agent=backend.NAME, tool_input=tool_input):
                self.assertEqual(self.hook(backend, "PreToolUse", tool_name=tool, tool_input=tool_input), {})

    def test_session_start_context(self):
        out = self.hook(claude, "SessionStart", source="startup")["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn("RESEARCH.md", out["additionalContext"])
        out = self.hook(codex, "SessionStart", source="compact")["hookSpecificOutput"]
        self.assertIn("should have been blocked", out["additionalContext"])

    def test_garbage_never_raises_and_precompact_fails_closed(self):
        self.assertIn("systemMessage", hooks.handle(["nonsense"], claude))
        self.assertEqual(self.hook(codex, "SubagentStop"), {})
        self.assertIn("systemMessage", self.hook(claude, "PostToolUse", transcript_path=42))
        (self.runtime / "policy.json").write_text("{broken")
        self.assertFalse(self.hook(codex, "PreCompact")["continue"])
        self.assertEqual(self.hook(claude, "PreCompact")["decision"], "block")
        self.assertIn("systemMessage", self.hook(claude, "PostToolUse"))

    def test_cli_hook_prints_one_json_object_and_exits_zero(self):
        def run(stdin):
            result = subprocess.run([sys.executable, "-m", "research_relay", "hook", "--agent", "codex"],
                                    input=stdin, capture_output=True, text=True, cwd=ROOT, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertIn("systemMessage", run("not json"))
        payload = {"hook_event_name": "PreCompact", "session_id": "s1", "cwd": str(self.repo), "trigger": "auto"}
        self.assertFalse(run(json.dumps(payload))["continue"])


if __name__ == "__main__":
    unittest.main()
