"""Native hook boundary. This module never performs research or restarts a turn."""

from pathlib import Path
import os
import shlex
import sys
import time

from .state import (RelayError, lock, locked, marker_path, read_json,
                    runtime_dir, write_json)


def record_probe_entry(payload):
    """Opt-in, five-minute metadata trace distinguishes no launch from bad binding."""
    try:
        runtime = runtime_dir(payload.get("cwd") or os.getcwd())
        path = runtime / "hook-entry-probe.json"
        if not path.exists():
            return
        with lock(runtime / "control.lock"):
            trace = read_json(path)
            if not trace or trace["expires_at"] < time.time():
                return
            trace["last_entry"] = {k: payload.get(k) for k in (
                "hook_event_name", "session_id", "turn_id", "cwd", "transcript_path")}
            trace["last_entry"]["reported_at"] = time.time()
            write_json(path, trace)
    except (RelayError, OSError, KeyError, TypeError):
        # Diagnostic failure must never change a hook's normal stop/delivery decision.
        return


def handle(payload):
    if not isinstance(payload, dict):
        raise RelayError("Hook input must be an object; no protection can be asserted.")
    record_probe_entry(payload)
    event = payload.get("hook_event_name")
    # Codex subagent hooks carry the PARENT session_id. Do not treat these as Stop.
    if event not in ("PostToolUse", "PreCompact", "Stop", "Interrupt", "SessionEnd", "UserPromptSubmit"):
        return {}
    try:
        runtime = runtime_dir(payload["cwd"])
        marker_file = marker_path(runtime, payload["session_id"])
    except (KeyError, RelayError):
        return {}
    if not marker_file.exists():
        return {}  # Unrelated sessions have no relay policy.
    try:
        with lock(runtime / "control.lock"):
            marker = read_json(marker_file)
            transcript = payload.get("transcript_path")
            if transcript and str(Path(transcript).resolve()) != marker["rollout"]:
                return {}  # A child can share session_id and cwd; its transcript differs.
            # A bounded last-receipt per event, never a transcript/event database.
            if transcript:
                marker.setdefault("hook_receipts", {})[event] = {
                    "turn_id": payload.get("turn_id"), "reported_at": time.time(),
                    **({"trigger": payload.get("trigger")} if event == "PreCompact" else {})}
                write_json(marker_file, marker)
            if event == "PreCompact":
                # Deliberately survives watcher exit, turn changes and application restarts.
                # Missing transcript is ambiguous inside this opted-in scope: stop safely.
                marker["last_precompact"] = {"trigger": payload.get("trigger"), "at": time.time()}
                write_json(marker_file, marker)
                return {"continue": False, "stopReason": "research-relay forbids compaction in this opted-in thread",
                        "systemMessage": "research-relay: Requested a stop before compaction. Manually open a fresh session to read notes."}
            # Delivery/cleanup requires exact transcript binding, not only a parent id.
            if not transcript:
                return {"systemMessage": "research-relay: Main-session transcript binding is missing; automatic reminders are unavailable."}
            probe = marker.get("delivery_probe")
            if (event == "PostToolUse" and probe and not probe["emitted"] and
                    probe["turn_id"] == payload.get("turn_id")):
                probe.update(emitted=True, emitted_at=time.time())
                write_json(marker_file, marker)
                script = Path(__file__).resolve().parents[1] / "skills/research-relay/scripts/relay.py"
                ack_command = shlex.join([sys.executable, str(script), "hooks", "ack",
                                          "--repo", payload["cwd"], "--thread-id", payload["session_id"],
                                          "--token", probe["token"]])
                return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": (
                    "research-relay native delivery diagnostic. This is only a delivery check, not a research task. "
                    f"The delivery token is {probe['token']}. "
                    "If you actually received this text through the native hook, acknowledge it with:\n"
                    f"{ack_command}\n"
                    "Do not acknowledge by reading the marker file. This does not establish no-compaction protection.")}}
            value = read_json(runtime / "watcher.json", {})
            owner = value.get("thread_id") == payload["session_id"]
            same_turn = payload.get("turn_id") == value.get("turn_id")
            if event in ("Stop", "Interrupt", "SessionEnd"):
                if owner and (same_turn or event == "SessionEnd"):
                    write_json(runtime / "stop.json", {"nonce": value["nonce"], "thread_id": payload["session_id"]})
                    if event == "Stop":
                        return {"continue": False, "stopReason": "research-relay main turn is finished"}
                return {}  # Never decision:block, never a continuation prompt.
            if event == "UserPromptSubmit":
                feedback_context = (
                    "research-relay human feedback: Distinguish unsolicited input/steering from answers to Codex "
                    "questions and option selections. Option wording belongs to Codex, not an original human prompt; "
                    "UserPromptSubmit alone does not establish provenance. Preserve originals only in Git-ignored "
                    "artifacts/private/human-inputs/<main-session-id>.md, reusing one file per main session. "
                    "Associate answers with their questions, options, and any additional human text. "
                    "Add separate agent context annotations locating the question, proposal, code state, and results; "
                    "leave uncertain references unresolved. Interpret selections and authorization within the question "
                    "and options presented at the time. Do not attribute model wording to original human intent "
                    "or expand authorization through a summary. Shareable notes contain decisions, interpretations, "
                    "and private source citations, without copying originals. Distinguish an untested idea, an explicit "
                    "change of direction, and an immediate stop request. New ideas do not automatically interrupt "
                    "or reorder active research. Apply explicit stops immediately; otherwise check subagent progress "
                    "and choose continuation, a handoff at a suitable boundary, or clarification. Briefly explain "
                    "your understanding and action without silently replacing the original goal."
                )
                if not owner or not locked(runtime / "watcher.lock"):
                    feedback_context += " The watcher is not running; this turn is unprotected. Recheck activation conditions. The existing thread's PreCompact marker remains."
                return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": feedback_context}}
            if not owner or not same_turn:
                return {}
            if not locked(runtime / "watcher.lock") and value.get("status") not in ("stopped", "failed"):
                marker.setdefault("notices", {}).setdefault("failure", {
                    "reason": "watcher disappeared", "text": "research-relay watcher exited unexpectedly; monitoring is unavailable. Save current work and stop.",
                    "emitted": False, "created_at": time.time()})
            pending = [n for n in marker.get("notices", {}).values() if not n["emitted"]]
            if not pending:
                return {}
            for notice in pending:
                notice["emitted"] = True
                notice["emitted_at"] = time.time()
            write_json(marker_file, marker)
            # Emitted means returned to the hook runner, NOT acknowledged by the model.
            return {"systemMessage": "research-relay: Experimental reminder emitted to the hook runner; protection remains unverified.",
                    "hookSpecificOutput": {"hookEventName": "PostToolUse",
                    "additionalContext": "\n".join(n["reason"] + ": " + n["text"] for n in pending)}}
    except (RelayError, OSError, KeyError, TypeError) as exc:
        message = f"research-relay scoped hook failed; monitoring is NOT protected: {exc}"
        if event == "PreCompact":
            return {"continue": False, "stopReason": message, "systemMessage": message}
        return {"systemMessage": message}


def configuration(python, script):
    import shlex
    command = shlex.join([str(python), str(script), "hook"])
    events = ("PostToolUse", "PreCompact", "Stop", "Interrupt", "SessionEnd", "UserPromptSubmit")
    return {"description": "research-relay experimental hooks; manual review/trust required; no verified protection",
            "hooks": {event: [{"hooks": [{"type": "command", "command": command,
                        "timeout": 3 if event in ("Interrupt", "SessionEnd") else 5,
                        **({"additionalContextLimit": 1500} if event in ("PostToolUse", "UserPromptSubmit") else {})}]}]
                      for event in events}}
