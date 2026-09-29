"""One finite watcher, no model calls, no steering, no runtime replacement."""

import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import uuid
import math

from . import protection
from .rollout import Rollout, threshold
from .state import (RelayError, lock, locked, marker_path, process_identity,
                    read_json, runtime_dir, thread_id, verify_ancestor, write_json)


UNVERIFIED = "experimental-unprotected"
PROTECTED = "protected"
ACTIVE = ("watching", "warning-pending", "warning-emitted-unverified", "warning-emitted", "starting")
CLOSEOUT = (
    "research-relay: Begin closeout. Stop opening new directions or delegating new research; "
    "finish the current operation safely. Collect completed or partial subagent results and stop the agents. "
    "Distinguish unsolicited human input from answers to questions and option selections. "
    "Keep originals only in Git-ignored artifacts/private/human-inputs/<main-session-id>.md. "
    "Check that separate agent annotations locate the question, code state, and results referred to. "
    "Update RESEARCH.md's current understanding, affected connections, decision summaries, "
    "private source citations, and unfinished investigation locations. Commit only reviewed shareable notes, "
    "never private originals, then end this turn. Do not compact or automatically create or continue sessions."
)


def queue_notice(runtime, identity, reason):
    """Must be called under control.lock. One notice per cause per activation."""
    path = marker_path(runtime, identity)
    marker = read_json(path)
    if marker is None:
        raise RelayError("Scoped guard marker is missing.")
    notices = marker.setdefault("notices", {})
    key = "closeout" if reason.startswith("threshold") else "failure"
    if key not in notices:
        notices[key] = {"reason": reason, "text": CLOSEOUT, "emitted": False,
                        "created_at": time.time()}
        write_json(path, marker)


def status(repo, identity=None):
    runtime = runtime_dir(repo)
    if not runtime.exists():
        return {"status": "inactive", "protected": False}
    live = locked(runtime / "watcher.lock")
    value = read_json(runtime / "watcher.json", {})
    value["live"] = live
    value["protected"] = False
    value.setdefault("status", "inactive")
    if not live and value.get("status") in ACTIVE:
        value["status"] = "failed"
        value["reason"] = "watcher exited without cleanup; inspect pending notes and hooks"
    if live and value.get("status") in ACTIVE and value.get("mode") == PROTECTED:
        try:
            if identity and value.get("thread_id") != thread_id(identity):
                raise RelayError("Repository watcher belongs to another thread.")
            request = read_json(runtime / "stop.json", {})
            if request.get("nonce") == value.get("nonce"):
                raise RelayError("Watcher stop has been requested.")
            protection.check_runtime(runtime, value)
            if process_identity(value["host_pid"]) != value["host_identity"]:
                raise RelayError("Desktop host identity changed.")
            reader = Rollout(value["rollout"]).bind(repo, value["thread_id"])
            if reader.turn != value["turn_id"]:
                raise RelayError("Watcher belongs to a previous main turn.")
            value["protected"] = True
        except (RelayError, OSError, ValueError, KeyError) as exc:
            value["status"], value["reason"] = "failed", str(exc)
    value["research_start"] = ("closeout" if value["status"].startswith("warning-") else "protected") if value["protected"] else "blocked"
    return value


def start_probe(repo, identity, rollout, host_pid, compact_limit, poll=1.0):
    return _start(repo, identity, rollout, host_pid, compact_limit, poll)


def start(repo, identity, home, poll=1.0):
    reader, checked = protection.environment(repo, identity, home)
    try:
        protection.check_delivery(repo, reader)
    except RelayError:
        from . import probes
        return {**probes.arm(repo, identity, home), "status": "awaiting-native-delivery",
                "research_start": "blocked"}
    if not reader.usage:
        raise RelayError("Waiting for the first main-turn usage record; retry at the next tool boundary.")
    return _start(repo, identity, reader.path, checked["host_pid"], checked["compact_limit"],
                  poll, capabilities=checked["capabilities"])


def _start(repo, identity, rollout, host_pid, compact_limit, poll=1.0, capabilities=None):
    repo = Path(repo).resolve()
    identity = thread_id(identity)
    actual_thread = os.environ.get("CODEX_THREAD_ID")
    if actual_thread and actual_thread != identity:
        raise RelayError("Requested thread differs from this execution's CODEX_THREAD_ID.")
    if not math.isfinite(poll) or not 0.05 <= poll <= 60:
        raise RelayError("Invalid polling interval.")
    runtime = runtime_dir(repo)
    mode = PROTECTED if capabilities else UNVERIFIED
    with lock(runtime / "start.lock"):
        reader = Rollout(rollout).bind(repo, identity)
        if locked(runtime / "watcher.lock"):
            value = read_json(runtime / "watcher.json", {})
            if (value.get("thread_id") == identity and
                    value.get("rollout") == str(Path(rollout).resolve()) and
                    value.get("host_pid") == host_pid and
                    value.get("compact_limit") == compact_limit and
                    value.get("turn_id") == reader.turn and value.get("mode") == mode):
                result = status(repo, identity)
                if result["status"] == "failed":
                    raise RelayError(result["reason"])
                return {**result, "already_running": True}
            raise RelayError(f"Repository occupied by thread {value.get('thread_id', 'unknown')}; no takeover.")
        host_identity = process_identity(host_pid)
        if actual_thread:
            if not host_identity.endswith("/codex"):
                raise RelayError("Host must be the actual Desktop Codex execution process.")
            verify_ancestor(host_pid)
        threshold(reader.usage["window"] if reader.usage else compact_limit, compact_limit)
        nonce = uuid.uuid4().hex
        config = {"repo": str(Path(repo).resolve()), "thread_id": identity,
                  "turn_id": reader.turn, "rollout": str(reader.path),
                  "host_pid": host_pid, "host_identity": host_identity,
                  "compact_limit": compact_limit, "poll": poll,
                  "nonce": nonce, "mode": mode, "protected": False,
                  **({"capabilities": capabilities} if capabilities else {})}
        with lock(runtime / "control.lock"):
            old = read_json(marker_path(runtime, identity))
            if old and old.get("rollout") != config["rollout"]:
                raise RelayError("Existing guard marker has a different binding; inspect it first.")
            write_json(marker_path(runtime, identity), {
                **(old or {}), "thread_id": identity, "rollout": config["rollout"],
                "guard_requested": True, "protected": False, "mode": mode,
                # A new watcher must be able to warn again. Idempotent starts
                # return above; the thread's guard and hook receipts survive.
                "notices": {},
            })
            write_json(runtime / "launch.json", config)
        log = (runtime / "watcher.log").open("ab")
        try:
            child = subprocess.Popen(
                [sys.executable, "-m", "research_relay", "_watch", "--repo", str(repo), "--nonce", nonce],
                cwd=Path(__file__).resolve().parent.parent,
                stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True,
            )
            # Reap if the launcher is long-lived (tests/library use); CLI launchers may
            # exit first and let the OS adopt the detached child. No restart logic.
            threading.Thread(target=child.wait, daemon=True).start()
        finally:
            log.close()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            value = read_json(runtime / "watcher.json", {})
            if value.get("nonce") == nonce:
                if value.get("status") == "failed":
                    raise RelayError(value.get("reason", "Watcher startup failed."))
                result = status(repo, identity)
                if mode == PROTECTED and not result["protected"]:
                    raise RelayError(result.get("reason", "Watcher did not become protected."))
                return result
            if child.poll() is not None:
                raise RelayError(f"Watcher failed to start; see {runtime / 'watcher.log'}")
            time.sleep(0.05)
        # Request a scoped exit, never signal an unverified PID or kill the host.
        write_json(runtime / "stop.json", {"nonce": nonce, "thread_id": identity})
        raise RelayError("Watcher readiness timed out; stop requested; inspect status/log.")


def stop(repo, identity):
    runtime = runtime_dir(repo)
    with lock(runtime / "control.lock"):
        value = read_json(runtime / "watcher.json", {})
        if not locked(runtime / "watcher.lock"):
            return {"status": "inactive", "protected": False, "guard_marker_retained": True}
        if value.get("thread_id") != thread_id(identity):
            raise RelayError("This watcher belongs to another thread; refusing to stop it.")
        write_json(runtime / "stop.json", {"nonce": value["nonce"], "thread_id": identity})
    return {"status": "stop-requested", "protected": False, "guard_marker_retained": True}


def watch(repo, nonce):
    runtime = runtime_dir(repo)
    with lock(runtime / "watcher.lock", blocking=False):
        config = read_json(runtime / "launch.json")
        if not config or config["nonce"] != nonce:
            raise RelayError("Launch was superseded; refusing stale launch.")
        value = {**config, "pid": os.getpid(), "status": "starting"}
        terminated = []
        for signum in (signal.SIGTERM, signal.SIGINT):
            signal.signal(signum, lambda sig, frame: terminated.append(sig))
        reason, failed = "stopped", False
        reader = Rollout(config["rollout"])
        try:
            reader.bind(repo, config["thread_id"])
            if reader.turn != config["turn_id"]:
                raise RelayError("Main turn changed during startup.")
            value["status"] = "watching"
            while True:
                if terminated:
                    reason = "watcher-signal"
                    break
                # Native lifecycle hooks can request shutdown while the app moves
                # the transcript into its archive. Honor that request before I/O.
                with lock(runtime / "control.lock"):
                    request = read_json(runtime / "stop.json", {})
                    if request.get("nonce") == nonce:
                        reason = "stop-requested"
                        break
                if process_identity(config["host_pid"]) != config["host_identity"]:
                    raise RelayError("Host identity changed; refusing reused PID.")
                reader.poll()
                if reader.compacted:
                    raise RelayError("Compaction observed: guard did not protect this thread.")
                if reader.ended or reader.turn != config["turn_id"]:
                    reason = "main-turn-ended"
                    break
                if config["mode"] == PROTECTED:
                    protection.check_runtime(runtime, config)
                    value["protected"] = True
                with lock(runtime / "control.lock"):
                    request = read_json(runtime / "stop.json", {})
                    if request.get("nonce") == nonce:
                        reason = "stop-requested"
                        break
                    if reader.usage:
                        limit = threshold(reader.usage["window"], config["compact_limit"])
                        value["usage"] = {**reader.usage, "warn_at": limit,
                                          "source": "last_token_usage.total_tokens",
                                          "observed_at": reader.usage_timestamp}
                        if reader.usage["used"] >= limit:
                            queue_notice(runtime, config["thread_id"], "threshold reached")
                            value["status"] = "warning-pending"
                    marker = read_json(marker_path(runtime, config["thread_id"]), {})
                    notice = marker.get("notices", {}).get("closeout")
                    if notice and notice["emitted"]:
                        value["status"] = "warning-emitted" if config["mode"] == PROTECTED else "warning-emitted-unverified"
                    value["heartbeat_at"] = time.time()
                    write_json(runtime / "watcher.json", value)
                time.sleep(config["poll"])
        except (RelayError, OSError, ValueError) as exc:
            reason, failed = str(exc), True
            print(f"research-relay UNPROTECTED: {reason}", file=sys.stderr, flush=True)
            try:
                with lock(runtime / "control.lock"):
                    queue_notice(runtime, config["thread_id"], reason)
            except (RelayError, OSError) as notice_error:
                print(f"research-relay could not queue failure: {notice_error}", file=sys.stderr, flush=True)
        finally:
            with lock(runtime / "control.lock"):
                write_json(runtime / "watcher.json", {**value,
                    "status": "failed" if failed else "stopped", "reason": reason,
                    "protected": False, "ended_at": time.time()})
        return 2 if failed else 0
