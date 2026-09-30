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
    usage = {"input_tokens": 10, "cache_read_input_tokens": used - 30,
             "cache_creation_input_tokens": 10, "output_tokens": 10}
    return [
        {"type": "user", "message": {"role": "user", "content": "hi"}},
        {"type": "assistant", "timestamp": "2026-09-30T00:00:01Z",
         "message": {"role": "assistant", "usage": usage}},
        # A subagent's record in the same file is not the main thread's usage.
        {"type": "assistant", "isSidechain": True, "message": {"role": "assistant", "usage": {"input_tokens": 7}}},
        {"type": "progress", "data": {}},
    ]


CASES = {"codex": (codex, codex_lines), "claude": (claude, claude_lines)}
# With a 100000 window and a 10000 reserve: final reminder at 75000, a checkpoint every 20000.
WINDOW, RESERVE, FINAL, STEP = 100000, 10000, 75000, 20000


class HookCase(RepoCase):
    def setUp(self):
        super().setUp()
        self.on("rhizome")
        self.transcript = self.repo.parent / "transcript.jsonl"

    def on(self, mode, **kw):
        return policy.enable(self.runtime, mode, "claude", WINDOW, reserve=RESERVE, **kw)

    def write(self, lines):
        self.transcript.write_text("".join(json.dumps(line) + "\n" for line in lines))

    def hook(self, backend, event, **kw):
        return hooks.handle({"hook_event_name": event, "session_id": "s1", "cwd": str(self.repo),
                             "transcript_path": str(self.transcript), **kw}, backend)

    def text(self, backend, event, **kw):
        out = self.hook(backend, event, **kw)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], event)
        return out["additionalContext"]

    def start(self, backend, session_id, source="startup"):
        return self.text(backend, "SessionStart", session_id=session_id, source=source)


class HookTests(HookCase):
    def test_precompact_allowed_in_rhizome_blocked_in_autoresearch(self):
        for backend in (codex, claude):
            self.assertEqual(self.hook(backend, "PreCompact", trigger="auto"), {})
        self.on("autoresearch")
        for trigger in ("auto", "manual"):
            result = self.hook(codex, "PreCompact", trigger=trigger)
            self.assertFalse(result["continue"])
            self.assertIn("blocks compaction", result["stopReason"])
            result = self.hook(claude, "PreCompact", trigger=trigger, agent_id="worker-1")
            self.assertEqual(result["decision"], "block")
            self.assertNotIn("continue", result)
        self.assertFalse((self.runtime / "sessions").exists())  # enforcement keeps no state

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
        self.on("autoresearch")
        policy.disable(self.runtime)
        for backend in (codex, claude):
            self.assertEqual(self.hook(backend, "PreCompact", trigger="auto"), {})
            self.assertEqual(self.hook(backend, "UserPromptSubmit"), {})
        self.assertFalse((self.runtime / "sessions").exists())

    def test_rhizome_reminders(self):
        for name, (backend, lines) in CASES.items():
            with self.subTest(agent=name):
                self.start(backend, name)

                def at(used):
                    self.write(lines(used))
                    return self.hook(backend, "PostToolUse", session_id=name)

                self.assertEqual(at(10000), {})
                self.assertEqual(at(29999), {})
                checkpoint = at(30000)["hookSpecificOutput"]["additionalContext"]
                self.assertIn("checkpoint: context has grown by about 20000 tokens", checkpoint)
                self.assertEqual(self.hook(backend, "PostToolUse", session_id=name), {})  # same record again
                final = at(FINAL)["hookSpecificOutput"]["additionalContext"]
                self.assertIn(f"{FINAL} of {WINDOW} tokens, past the final reminder threshold", final)
                self.assertNotIn("closeout", final)
                self.assertEqual(at(FINAL + 1), {})
                self.assertIn("checkpoint", at(FINAL + STEP)["hookSpecificOutput"]["additionalContext"])
                state = policy.session(self.runtime, name)
                self.assertEqual(state["last_usage"], {
                    "used": FINAL + STEP, "window": WINDOW if name == "codex" else None,
                    "observed_at": "2026-09-30T00:00:01Z", "ceiling": WINDOW, "final": FINAL, "step": STEP})
                self.assertEqual((state["baseline"], state["final_sent"]), (FINAL + STEP, True))

    def test_autoresearch_final_reminder_is_a_closeout_that_wraps_the_notes_update(self):
        self.on("autoresearch")
        for name, (backend, lines) in CASES.items():
            with self.subTest(agent=name):
                self.start(backend, name)
                self.write(lines(FINAL))
                text = self.text(backend, "PostToolUse", session_id=name)
                order = [text.index(part) for part in ("Begin closeout", "collect completed or partial worker",
                                                       "past the final reminder threshold", "end the turn")]
                self.assertEqual(order, sorted(order))
                self.assertEqual(self.hook(backend, "PostToolUse", session_id=name), {})
                self.write(lines(FINAL + STEP))  # still working a step later: the closeout again
                self.assertIn("Begin closeout", self.text(backend, "PostToolUse", session_id=name))

    def test_subagent_events_get_no_reminder_and_leave_no_state(self):
        self.write(claude_lines(FINAL))
        for event in ("PostToolUse", "UserPromptSubmit", "SessionStart"):
            self.assertEqual(self.hook(claude, event, agent_id="worker-1", agent_type="Explore"), {})
        self.assertFalse((self.runtime / "sessions").exists())
        self.start(claude, "s1")
        self.assertIn("past the final reminder threshold", self.text(claude, "PostToolUse"))

    def test_compaction_or_clear_rearms_and_compaction_gets_recovery_text(self):
        self.write(claude_lines(FINAL))
        self.start(claude, "s1")
        self.assertIn("final reminder", self.text(claude, "PostToolUse"))
        recovery = self.start(claude, "s1", "compact")
        self.assertIn("continued after a compaction", recovery)
        self.assertNotIn("should have been blocked", recovery)
        self.assertNotIn("last_usage", policy.session(self.runtime, "s1"))
        self.assertIn("final reminder", self.text(claude, "PostToolUse"))
        self.assertIn("RESEARCH.md", self.start(claude, "s1", "clear"))
        self.assertIn("final reminder", self.text(claude, "PostToolUse"))
        self.on("autoresearch")
        self.assertIn("should have been blocked", self.start(codex, "s2", "compact"))

    def test_no_reminder_without_usage_or_window(self):
        self.start(claude, "s1")
        self.assertEqual(self.hook(claude, "PostToolUse", transcript_path=None), {})
        self.assertEqual(self.hook(claude, "PostToolUse", transcript_path=str(self.repo / "absent.jsonl")), {})
        policy.enable(self.runtime)  # a bare `on`: rhizome mode, no window
        self.write(claude_lines(FINAL))
        told = self.start(claude, "s2")
        self.assertIn("cannot monitor context usage", told)
        self.assertEqual(self.hook(claude, "PostToolUse", session_id="s2"), {})
        self.assertEqual(policy.session(self.runtime, "s2")["last_usage"]["used"], FINAL)
        # Codex reports its window in the rollout, so the same policy monitors it.
        self.write(codex_lines(FINAL, 80000))
        self.assertNotIn("cannot monitor", self.start(codex, "s3"))
        self.assertEqual(self.hook(codex, "PostToolUse", session_id="s3"), {})  # no room above the 100K reserve
        self.write(codex_lines(750000, 1000000))
        self.assertIn("750000 of 1000000", self.text(codex, "PostToolUse", session_id="s3"))

    def test_tail_read_finds_last_usage_in_large_transcript(self):
        padding = {"type": "event_msg", "payload": {"type": "agent_message", "message": "x" * 1000}}
        for name, (backend, lines) in CASES.items():
            with self.subTest(agent=name):
                self.write([padding] * 400 + lines(FINAL) + [padding] * 3)
                self.assertGreater(self.transcript.stat().st_size, 256 * 1024)
                self.assertEqual(backend.read_usage(self.transcript)["used"], FINAL)
                self.assertIn("hookSpecificOutput", self.hook(backend, "PostToolUse", session_id=name))

    def test_feedback_guidance_only_on_first_prompt(self):
        self.start(claude, "s1")
        first = self.text(claude, "UserPromptSubmit", prompt="go")
        self.assertTrue(first.startswith("research-relay human feedback"))
        self.assertIn("provenance", first)
        self.assertEqual(self.hook(claude, "UserPromptSubmit", prompt="more"), {})

    def test_open_session_is_told_when_the_policy_changes(self):
        # A session that was open before relay was switched on gets the session text at its next event.
        late = self.text(codex, "UserPromptSubmit", session_id="late")
        self.assertTrue(late.startswith("research-relay: this repository is now in rhizome mode."))
        self.assertNotIn("no longer apply", late)
        self.assertIn("RESEARCH.md", late)
        self.assertIn("provenance", late)
        self.write(claude_lines(1000))
        self.start(claude, "s1")
        self.assertEqual(self.hook(claude, "PostToolUse"), {})
        self.on("autoresearch")
        text = self.text(claude, "PostToolUse")
        self.assertIn("now in auto-research mode", text)
        self.assertIn("Compaction is blocked by hook", text)
        self.assertEqual(self.hook(claude, "PostToolUse"), {})
        self.on("rhizome")
        text = self.text(claude, "PostToolUse")
        self.assertIn("now in rhizome mode. The auto-research restrictions no longer apply", text)
        self.assertNotIn("Compaction is blocked by hook", text)

    def test_pretooluse_denies_inherited_context_only_in_autoresearch(self):
        denied = [(claude, "Agent", {"subagent_type": "fork", "prompt": "x"}),
                  (codex, "Agent", {"prompt": "x"}),
                  (codex, "Agent", {"fork_turns": "all", "prompt": "x"})]
        allowed = [(claude, "Agent", {"subagent_type": "Explore", "prompt": "x"}),
                   (claude, "Agent", {"prompt": "x"}), (claude, "Bash", {"command": "ls"}),
                   (codex, "Agent", {"fork_turns": "none", "prompt": "x"}), (codex, "Shell", {})]
        for backend, tool, tool_input in denied + allowed:
            self.assertEqual(self.hook(backend, "PreToolUse", tool_name=tool, tool_input=tool_input), {})
        self.on("autoresearch")
        for backend, tool, tool_input in denied:
            with self.subTest(agent=backend.NAME, tool_input=tool_input):
                out = self.hook(backend, "PreToolUse", tool_name=tool, tool_input=tool_input,
                                agent_id="worker-1")["hookSpecificOutput"]
                self.assertEqual(out["hookEventName"], "PreToolUse")
                self.assertEqual(out["permissionDecision"], "deny")
                self.assertIn("fresh context", out["permissionDecisionReason"])
        for backend, tool, tool_input in allowed:
            with self.subTest(agent=backend.NAME, tool_input=tool_input):
                self.assertEqual(self.hook(backend, "PreToolUse", tool_name=tool, tool_input=tool_input), {})

    def test_session_start_context_per_mode(self):
        text = self.start(claude, "s1")
        self.assertIn("RESEARCH.md", text)
        self.assertNotIn("auto-research", text)
        self.assertNotIn("cannot monitor", text)
        self.on("autoresearch")
        text = self.start(claude, "s2", "resume")
        self.assertLess(text.index("RESEARCH.md"), text.index("This repository is in auto-research mode"))

    def test_policy_from_before_modes_is_autoresearch(self):
        (self.runtime / "policy.json").write_text(json.dumps(
            {"active": True, "agent": "claude", "context_window": 1000000, "warn_fraction": 0.6,
             "compact_limit": None, "since": "2026-09-30T07:58:00Z"}))
        self.assertEqual(self.hook(claude, "PreCompact")["decision"], "block")
        self.write(claude_lines(600000))
        self.start(claude, "s1")
        self.assertIn("Begin closeout", self.text(claude, "PostToolUse"))

    def test_garbage_never_raises_and_precompact_fails_closed(self):
        self.assertIn("systemMessage", hooks.handle(["nonsense"], claude))
        self.assertEqual(self.hook(codex, "SubagentStop"), {})
        self.assertIn("systemMessage", self.hook(claude, "PostToolUse", transcript_path=42))
        for broken in ("{broken", json.dumps({"active": True, "mode": "bogus"})):
            (self.runtime / "policy.json").write_text(broken)
            self.assertFalse(self.hook(codex, "PreCompact")["continue"])
            self.assertEqual(self.hook(claude, "PreCompact")["decision"], "block")
            self.assertIn("systemMessage", self.hook(claude, "PostToolUse"))

    def test_parallel_tool_calls_get_one_reminder(self):
        self.write(claude_lines(FINAL))
        self.start(claude, "s1")
        payload = json.dumps({"hook_event_name": "PostToolUse", "session_id": "s1", "cwd": str(self.repo),
                              "transcript_path": str(self.transcript)})
        procs = [subprocess.Popen([sys.executable, "-m", "research_relay", "hook", "--agent", "claude"],
                                  stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, cwd=ROOT)
                 for _ in range(6)]
        outputs = [json.loads(proc.communicate(payload, timeout=30)[0]) for proc in procs]
        self.assertEqual(sum(1 for out in outputs if out), 1)

    def test_cli_hook_prints_one_json_object_and_exits_zero(self):
        def run(stdin):
            result = subprocess.run([sys.executable, "-m", "research_relay", "hook", "--agent", "codex"],
                                    input=stdin, capture_output=True, text=True, cwd=ROOT, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            return json.loads(result.stdout)
        self.assertIn("systemMessage", run("not json"))
        self.on("autoresearch")
        payload = {"hook_event_name": "PreCompact", "session_id": "s1", "cwd": str(self.repo), "trigger": "auto"}
        self.assertFalse(run(json.dumps(payload))["continue"])


if __name__ == "__main__":
    unittest.main()
