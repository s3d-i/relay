from datetime import datetime, timezone
import contextlib
import io
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from research_relay import hooks, notes, watcher
from research_relay.__main__ import main
from research_relay.rollout import Rollout, threshold
from research_relay.state import (RelayError, git, locked, marker_path, read_json,
                                 runtime_dir, write_json)


T1 = "11111111-1111-1111-1111-111111111111"
T2 = "22222222-2222-2222-2222-222222222222"


def eventually(predicate, timeout=5):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(0.025)
    raise AssertionError("condition did not become true")


class RepositoryCase(unittest.TestCase):
    def setUp(self):
        self.original_thread = os.environ.pop("CODEX_THREAD_ID", None)
        self.tmp = tempfile.TemporaryDirectory(prefix="relay-test-")
        self.repo = Path(self.tmp.name).resolve() / "code with spaces"
        self.repo.mkdir()
        git(self.repo, "init", "-b", "main")
        git(self.repo, "config", "user.name", "Relay Test")
        git(self.repo, "config", "user.email", "relay-test@example.invalid")
        git(self.repo, "commit", "--allow-empty", "-m", "code baseline")
        self.runtime = runtime_dir(self.repo)
        self.rollout = self.repo / "example.jsonl"
        self.write_rollout()

    def tearDown(self):
        self.tmp.cleanup()
        if self.original_thread is not None:
            os.environ["CODEX_THREAD_ID"] = self.original_thread

    def append(self, payload, kind="event_msg"):
        with self.rollout.open("a") as out:
            out.write(json.dumps({"type": kind, "timestamp": datetime.now(timezone.utc).isoformat(),
                                  "payload": payload}) + "\n")

    def write_rollout(self, identity=T1, source="vscode"):
        self.rollout.write_text("")
        self.append({"id": identity, "cwd": str(self.repo), "source": source,
                     "originator": "Codex Desktop", "cli_version": "test-fixture"}, "session_meta")
        self.append({"type": "task_started", "turn_id": "turn-1"})
        self.usage(1000)

    def usage(self, used, total=10000000, window=100000):
        self.append({"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": used - 1, "output_tokens": 1,
                                  "total_tokens": used, "cached_input_tokens": used - 2,
                                  "reasoning_output_tokens": 1},
            "total_token_usage": {"total_tokens": total}, "model_context_window": window}})

    def marker(self):
        write_json(marker_path(self.runtime, T1), {"thread_id": T1, "rollout": str(self.rollout),
                                                  "guard_requested": True, "protected": False})
        write_json(self.runtime / "watcher.json", {"thread_id": T1, "turn_id": "turn-1", "nonce": "test",
                                                   "status": "stopped"})

    def hook(self, event, **kw):
        return hooks.handle({"hook_event_name": event, "session_id": T1, "turn_id": "turn-1",
                             "cwd": str(self.repo), "transcript_path": str(self.rollout), **kw})


class RolloutTests(RepositoryCase):
    def test_recent_usage_not_cumulative_or_double_counted(self):
        reader = Rollout(self.rollout).bind(self.repo, T1)
        self.assertEqual(reader.usage["used"], 1000)
        self.assertEqual(reader.usage["input"], 999)

    def test_partial_record_is_retried(self):
        reader = Rollout(self.rollout).bind(self.repo, T1)
        with self.rollout.open("a") as out:
            out.write('{"type":"event_msg","payload":')
        self.assertEqual(reader.poll(), [])
        with self.rollout.open("a") as out:
            out.write('{"type":"task_complete","turn_id":"turn-1"}}\n')
        reader.poll()
        self.assertTrue(reader.ended)

    def test_wrong_thread(self):
        with self.assertRaises(RelayError):
            Rollout(self.rollout).bind(self.repo, T2)

    def test_subagent_source_rejected(self):
        self.write_rollout(source={"subagent": {"thread_spawn": {"parent_thread_id": T1}}})
        with self.assertRaises(RelayError):
            Rollout(self.rollout).bind(self.repo, T1)

    def test_other_repo_rejected(self):
        other = self.repo.parent / "other"
        other.mkdir()
        git(other, "init")
        with self.assertRaises(RelayError):
            Rollout(self.rollout).bind(other, T1)

    def test_rotation_fails_visibly(self):
        reader = Rollout(self.rollout).bind(self.repo, T1)
        self.rollout.rename(self.rollout.with_suffix(".old"))
        self.write_rollout()
        with self.assertRaises(RelayError):
            reader.poll()

    def test_unknown_usage_no_fallback(self):
        self.append({"type": "token_count", "info": {"total_token_usage": {"total_tokens": 100000}}})
        with self.assertRaises(RelayError):
            Rollout(self.rollout).bind(self.repo, T1)

    def test_usage_without_timestamp_is_not_fresh(self):
        record = {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "last_token_usage": {"input_tokens": 100, "output_tokens": 1, "total_tokens": 101},
            "model_context_window": 100000}}}
        with self.rollout.open("a") as out:
            out.write(json.dumps(record) + "\n")
        with self.assertRaises(RelayError):
            Rollout(self.rollout).bind(self.repo, T1)

    def test_compacted_thread_rejected(self):
        self.append({}, "compacted")
        with self.assertRaises(RelayError):
            Rollout(self.rollout).bind(self.repo, T1)

    def test_idle_turn_rejected(self):
        self.append({"type": "task_complete", "turn_id": "turn-1"})
        with self.assertRaises(RelayError):
            Rollout(self.rollout).bind(self.repo, T1)

    def test_budget_uses_compaction_ceiling_and_reserve(self):
        self.assertEqual(threshold(760000, 600000), 456000)
        self.assertEqual(threshold(80000, 70000), 37232)
        with self.assertRaises(RelayError):
            threshold(30000, 30000)


class HookTests(RepositoryCase):
    def setUp(self):
        super().setUp()
        self.marker()

    def test_precompact_survives_watcher_exit_and_new_turn(self):
        for trigger in ("auto", "manual"):
            result = self.hook("PreCompact", trigger=trigger, turn_id="turn-2")
            self.assertFalse(result["continue"])
        self.assertTrue(marker_path(self.runtime, T1).exists())

    def test_unrelated_thread_untouched(self):
        self.assertEqual(self.hook("PreCompact", session_id=T2), {})

    def test_shared_parent_id_does_not_stop_or_notify_child(self):
        for event in ("SubagentStop", "Stop", "PostToolUse", "PreCompact"):
            self.assertEqual(self.hook(event, transcript_path=str(self.repo / "child.jsonl")), {})
        self.assertFalse((self.runtime / "stop.json").exists())

    def test_subagent_stop_never_main_stop(self):
        self.assertEqual(self.hook("SubagentStop", agent_id=T2), {})
        self.assertFalse((self.runtime / "stop.json").exists())

    def test_wrong_turn_cannot_stop_main(self):
        self.hook("Stop", turn_id="old-turn")
        self.assertFalse((self.runtime / "stop.json").exists())

    def test_lifecycle_only_requests_exit_never_continuation(self):
        for event in ("Stop", "Interrupt", "SessionEnd"):
            result = self.hook(event)
            if event == "Stop":
                self.assertFalse(result["continue"])
            else:
                self.assertEqual(result, {})
            self.assertNotIn("decision", result)
            self.assertEqual(read_json(self.runtime / "stop.json")["nonce"], "test")

    def test_notice_deduplicated_and_emitted_not_acknowledged(self):
        watcher.queue_notice(self.runtime, T1, "threshold reached")
        watcher.queue_notice(self.runtime, T1, "threshold reached again")
        result = self.hook("PostToolUse")
        self.assertIn("进入收尾", result["hookSpecificOutput"]["additionalContext"])
        self.assertEqual(self.hook("PostToolUse"), {})
        marker = read_json(marker_path(self.runtime, T1))
        self.assertEqual(len(marker["notices"]), 1)
        self.assertFalse(marker["protected"])

    def test_corrupt_scoped_marker_blocks_compact(self):
        for data in ("{broken", "[]", "null"):
            marker_path(self.runtime, T1).write_text(data)
            self.assertFalse(self.hook("PreCompact")["continue"])

    def test_missing_transcript_cannot_deliver_but_blocks_scoped_compact(self):
        watcher.queue_notice(self.runtime, T1, "threshold reached")
        self.assertNotIn("hookSpecificOutput", self.hook("PostToolUse", transcript_path=None))
        self.assertFalse(self.hook("PreCompact", transcript_path=None)["continue"])

    def test_guard_works_from_another_worktree(self):
        other = self.repo.parent / "linked"
        git(self.repo, "worktree", "add", "--detach", str(other), "HEAD")
        self.assertEqual(runtime_dir(other), self.runtime)
        self.assertFalse(self.hook("PreCompact", cwd=str(other))["continue"])

    def test_no_protected_start_even_with_guard_marker(self):
        output = io.StringIO()
        with contextlib.redirect_stderr(output):
            code = main(["start", "--repo", str(self.repo), "--thread-id", T1])
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(output.getvalue())["protected"])


class NotesTests(RepositoryCase):
    def test_inactive_status_does_not_create_runtime(self):
        self.assertEqual(watcher.status(self.repo)["status"], "inactive")
        self.assertFalse(self.runtime.exists())

    def test_isolated_branch_preserves_code_and_existing_notes(self):
        (self.repo / "code.txt").write_text("uncommitted code")
        initial = git(self.repo, "status", "--porcelain")
        result = notes.init(self.repo)
        path = Path(result["notes"])
        self.assertEqual(git(self.repo, "status", "--porcelain"), initial)
        self.assertEqual(git(self.repo, "branch", "--show-current"), "main")
        self.assertEqual(git(path, "branch", "--show-current"), "relay-notes")
        self.assertFalse((path / "code.txt").exists())
        (path / "RESEARCH.md").write_text("Existing understanding")
        self.assertFalse(notes.init(self.repo)["entry_created"])
        self.assertEqual((path / "RESEARCH.md").read_text(), "Existing understanding")

    def test_commit_only_reviewed_files(self):
        path = Path(notes.init(self.repo)["notes"])
        (path / "other.md").write_text("Someone else's draft")
        result = notes.commit(self.repo, ["RESEARCH.md"], "Record question")
        self.assertFalse(result["pushed"])
        self.assertIn("other.md", result["remaining"])
        self.assertEqual(git(path, "show", "--format=", "--name-only", "HEAD"), "RESEARCH.md")

    def test_private_inputs_ignored_in_notes_and_code_worktrees(self):
        exclude = self.runtime.parent / "info/exclude"
        existing = exclude.read_text() + "\n# keep this local rule\nlocal-output/"
        exclude.write_text(existing)
        result = notes.init(self.repo)
        path = Path(result["notes"])
        private = Path(result["private_inputs"]) / f"{T1}.md"
        private.parent.mkdir(parents=True)
        private.write_text("Synthetic private prompt and option answer")
        self.assertTrue(result["private_inputs_ignored"])
        self.assertEqual(result["tracked_private_artifacts"], [])
        relative = str(private.relative_to(path))
        for checkout in (path, self.repo):
            ignored = subprocess.run(["git", "-C", str(checkout), "check-ignore", "--", relative],
                                     capture_output=True, text=True, check=True)
            self.assertEqual(ignored.stdout.strip(), relative)
        git(path, "add", "-A")
        self.assertEqual(git(path, "diff", "--cached", "--name-only"), "RESEARCH.md")
        self.assertNotIn("Synthetic", json.dumps(notes.inspect(self.repo)))
        self.assertNotIn("private/", notes.inspect(self.repo)["status"])
        notes.init(self.repo)
        self.assertEqual(exclude.read_text(), existing + "\n/artifacts/private/\n")
        self.assertEqual(private.read_text(), "Synthetic private prompt and option answer")
        notes.commit(self.repo, ["RESEARCH.md"], "Record public summary")
        self.assertEqual(git(path, "ls-tree", "-r", "--name-only", "HEAD"), "RESEARCH.md")

    def test_explicit_private_paths_rejected_even_when_ignores_were_removed(self):
        path = Path(notes.init(self.repo)["notes"])
        private = path / notes.PRIVATE_INPUTS / f"{T1}.md"
        private.parent.mkdir(parents=True)
        private.write_text("Synthetic private input")
        exclude = self.runtime.parent / "info/exclude"
        exclude.write_text(exclude.read_text().replace("/artifacts/private/\n", ""))
        self.assertFalse(notes.inspect(self.repo)["private_inputs_ignored"])
        with self.assertRaisesRegex(RelayError, "must never be committed"):
            notes.commit(self.repo, [str(private.relative_to(path))], "Reject private file")
        self.assertTrue(notes.inspect(self.repo)["private_inputs_ignored"])
        self.assertEqual(git(path, "diff", "--cached", "--name-only"), "")
        self.assertEqual(private.read_text(), "Synthetic private input")

    def test_forced_private_index_entries_block_init_and_commit_without_reset(self):
        path = Path(notes.init(self.repo)["notes"])
        private = path / notes.PRIVATE_INPUTS / f"{T1}.md"
        private.parent.mkdir(parents=True)
        private.write_text("Synthetic forced private input")
        relative = str(private.relative_to(path))
        git(path, "add", "-f", "--", relative)
        head = git(path, "rev-parse", "HEAD")
        self.assertEqual(notes.inspect(self.repo)["tracked_private_artifacts"], [relative])
        with self.assertRaisesRegex(RelayError, "already tracked or staged"):
            notes.init(self.repo)
        for chosen in (["RESEARCH.md"], [relative]):
            with self.subTest(chosen=chosen), self.assertRaisesRegex(RelayError, "already tracked or staged"):
                notes.commit(self.repo, chosen, "Reject staged private input")
        self.assertEqual(git(path, "rev-parse", "HEAD"), head)
        self.assertEqual(git(path, "diff", "--cached", "--name-only"), relative)
        self.assertEqual(private.read_text(), "Synthetic forced private input")

    def test_already_committed_private_file_is_not_protected_by_ignore(self):
        path = Path(notes.init(self.repo)["notes"])
        private = path / notes.PRIVATE_INPUTS / f"{T1}.md"
        private.parent.mkdir(parents=True)
        private.write_text("Synthetic historical private input")
        git(path, "add", "-f", "--", str(private.relative_to(path)))
        git(path, "commit", "-m", "Simulate prior privacy failure")
        with self.assertRaisesRegex(RelayError, "already tracked or staged"):
            notes.commit(self.repo, ["RESEARCH.md"], "Do not perpetuate tracked private inputs")
        self.assertEqual(private.read_text(), "Synthetic historical private input")

    def test_worktree_ignore_override_rejected_before_saving_inputs(self):
        path = Path(notes.init(self.repo)["notes"])
        (path / ".gitignore").write_text("!artifacts/private/\n!artifacts/private/**\n")
        self.assertFalse(notes.inspect(self.repo)["private_inputs_ignored"])
        with self.assertRaisesRegex(RelayError, "override private input protection"):
            notes.init(self.repo)
        with self.assertRaisesRegex(RelayError, "override private input protection"):
            notes.commit(self.repo, ["RESEARCH.md"], "Reject broken ignores")
        self.assertEqual(git(path, "diff", "--cached", "--name-only"), "")

    def test_unrelated_staged_changes_rejected(self):
        path = Path(notes.init(self.repo)["notes"])
        (path / "other.md").write_text("staged by somebody")
        git(path, "add", "other.md")
        with self.assertRaises(RelayError):
            notes.commit(self.repo, ["RESEARCH.md"], "no")
        self.assertEqual(git(path, "diff", "--cached", "--name-only"), "other.md")

    def test_commit_failure_preserves_discoverable_draft(self):
        path = Path(notes.init(self.repo)["notes"])
        hook_path = self.runtime.parent / "hooks" / "pre-commit"
        hook_path.parent.mkdir(exist_ok=True)
        hook_path.write_text("#!/bin/sh\nexit 1\n")
        hook_path.chmod(0o755)
        with self.assertRaises(RelayError):
            notes.commit(self.repo, ["RESEARCH.md"], "will fail")
        self.assertIn("RESEARCH.md", notes.inspect(self.repo)["status"])
        self.assertTrue((path / "RESEARCH.md").exists())

    def test_sensitive_big_and_pathspec_inputs_rejected(self):
        path = Path(notes.init(self.repo)["notes"])
        (path / "large.json").write_text("x" * (1024 * 1024 + 1))
        (path / "secret.md").write_text("not allowed by filename")
        (path / "key.md").write_text("-----BEGIN PRIVATE KEY-----")
        (path / "link.md").symlink_to(path / "RESEARCH.md")
        for name in ("large.json", "secret.md", "key.md", "link.md", ".", "../outside.md", ":(glob)*"):
            with self.subTest(name=name), self.assertRaises(RelayError):
                notes.commit(self.repo, [name], "reject")

    def test_empty_repository_supported(self):
        repo = self.repo.parent / "empty"
        repo.mkdir()
        git(repo, "init", "-b", "main")
        git(repo, "config", "user.name", "Relay Test")
        git(repo, "config", "user.email", "test@example.invalid")
        self.assertTrue(notes.init(repo)["entry_created"])
        self.assertEqual(git(repo, "symbolic-ref", "HEAD"), "refs/heads/main")


class ProcessTests(RepositoryCase):
    def setUp(self):
        super().setUp()
        self.host = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        self.children = []

    def tearDown(self):
        try:
            if locked(self.runtime / "watcher.lock"):
                state = read_json(self.runtime / "watcher.json", {})
                watcher.stop(self.repo, state.get("thread_id", T1))
                eventually(lambda: not locked(self.runtime / "watcher.lock"))
            for child in self.children:
                child.wait(timeout=5)
        finally:
            self.host.terminate()
            self.host.wait(timeout=5)
            super().tearDown()

    def start(self, repo=None, identity=T1, stale=5):
        return watcher.start_probe(repo or self.repo, identity, self.rollout,
                                   self.host.pid, 100000, poll=0.05, stale=stale)

    def test_idempotent_across_worktrees_and_other_thread_busy(self):
        first = self.start()
        linked = self.repo.parent / "linked"
        git(self.repo, "worktree", "add", "--detach", str(linked), "HEAD")
        second = self.start(linked)
        self.assertEqual(first["pid"], second["pid"])
        self.assertTrue(second["already_running"])
        with self.assertRaises(RelayError):
            self.start(linked, T2)
        with self.assertRaises(RelayError):
            watcher.stop(linked, T2)
        self.assertIsNone(self.host.poll())

    def test_two_concurrent_launchers_only_one_watcher(self):
        command = [sys.executable, "-m", "research_relay", "probe-start", "--repo", str(self.repo),
                   "--thread-id", T1, "--rollout", str(self.rollout), "--host-pid", str(self.host.pid),
                   "--compact-limit", "100000", "--poll", "0.05"]
        processes = [subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
        self.children.extend(processes)
        responses = []
        for process in processes:
            out, err = process.communicate(timeout=8)
            self.assertEqual(process.returncode, 0, err)
            responses.append(json.loads(out))
        self.assertEqual(responses[0]["pid"], responses[1]["pid"])

    def test_threshold_hook_and_stop_process_loop(self):
        self.start()
        self.usage(65000)
        eventually(lambda: watcher.status(self.repo).get("status") == "warning-pending")
        first = self.hook("PostToolUse")
        self.assertIn("hookSpecificOutput", first)
        self.assertEqual(self.hook("PostToolUse"), {})
        self.hook("SubagentStop", agent_id=T2)
        self.assertTrue(locked(self.runtime / "watcher.lock"))
        self.hook("Stop")
        eventually(lambda: not locked(self.runtime / "watcher.lock"))
        self.assertIsNone(self.host.poll())
        self.assertFalse(self.hook("PreCompact")["continue"])

    def test_main_turn_completion_exits_without_hook(self):
        self.start()
        self.append({"type": "task_complete", "turn_id": "turn-1"})
        eventually(lambda: not locked(self.runtime / "watcher.lock"))
        self.assertEqual(watcher.status(self.repo)["reason"], "main-turn-ended")

    def test_user_interruption_exits_without_restart(self):
        self.start()
        self.append({"type": "turn_aborted", "turn_id": "turn-1"})
        eventually(lambda: not locked(self.runtime / "watcher.lock"))
        self.assertIsNone(self.host.poll())

    def test_host_exit_exits_watcher(self):
        self.start()
        self.host.terminate()
        self.host.wait()
        eventually(lambda: not locked(self.runtime / "watcher.lock"))
        self.assertFalse(watcher.status(self.repo)["protected"])

    def test_stale_source_fails_visibly(self):
        self.start(stale=0.5)
        eventually(lambda: not locked(self.runtime / "watcher.lock"))
        result = watcher.status(self.repo)
        self.assertEqual(result["status"], "failed")
        self.assertIn("stale", result["reason"])
        self.assertIn("hookSpecificOutput", self.hook("PostToolUse"))

    def test_guard_lives_after_explicit_stop(self):
        self.start()
        watcher.stop(self.repo, T1)
        eventually(lambda: not locked(self.runtime / "watcher.lock"))
        self.assertTrue(marker_path(self.runtime, T1).exists())
        self.assertFalse(self.hook("PreCompact", turn_id="future-turn")["continue"])

    def test_missing_hook_delivery_fails_visibly(self):
        self.start()
        self.usage(65000)
        eventually(lambda: watcher.status(self.repo).get("status") == "warning-pending")
        from research_relay.state import lock
        with lock(self.runtime / "control.lock"):
            marker = read_json(marker_path(self.runtime, T1))
            marker["notices"]["closeout"]["created_at"] = time.time() - 31
            write_json(marker_path(self.runtime, T1), marker)
        eventually(lambda: not locked(self.runtime / "watcher.lock"))
        self.assertIn("delivery unavailable", watcher.status(self.repo)["reason"])

    def test_dead_watcher_lock_released_and_guard_retained(self):
        first = self.start()
        os.kill(first["pid"], signal.SIGKILL)  # Only this test's spawned watcher.
        eventually(lambda: not locked(self.runtime / "watcher.lock"))
        self.assertEqual(watcher.status(self.repo)["status"], "failed")
        self.assertFalse(self.hook("PreCompact")["continue"])
        second = self.start()
        self.assertNotEqual(first["nonce"], second["nonce"])

    def test_environment_thread_binding_cannot_be_overridden(self):
        os.environ["CODEX_THREAD_ID"] = T2
        try:
            with self.assertRaises(RelayError):
                self.start(identity=T1)
        finally:
            os.environ.pop("CODEX_THREAD_ID", None)


if __name__ == "__main__":
    unittest.main()
