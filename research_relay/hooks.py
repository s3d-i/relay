"""Hook boundary: read the policy and payload, estimate usage, return hook output. Never raises."""

import os

from . import policy
from .state import RelayError


def handle(payload, backend):
    event = payload.get("hook_event_name") if isinstance(payload, dict) else None
    try:
        return _handle(payload, backend, event)
    except Exception as exc:  # noqa: BLE001  the runner needs one JSON object whatever broke
        message = f"research-relay hook failed: {exc}"
        if event == "PreCompact":
            return backend.block_compaction(message)  # fail closed on compaction only
        return {"systemMessage": message}


def _handle(payload, backend, event):
    if not isinstance(payload, dict):
        raise RelayError("hook input must be a JSON object")
    if event not in backend.HOOK_EVENTS:
        return {}
    runtime = policy.locate(payload.get("cwd") or os.getcwd())
    active = policy.load(runtime) if runtime else None
    if not active or not active.get("active"):
        return {}  # unrelated repositories and switched-off ones see nothing
    if event == "SessionStart":
        return _context(event, policy.COMPACTED if payload.get("source") == "compact" else policy.SESSION_START)
    if event == "PreToolUse":
        return _pre_tool_use(payload, backend)
    session_id = payload.get("session_id")
    state = policy.session(runtime, session_id)
    if event == "PreCompact":
        state.setdefault("precompact_blocked", []).append(
            {"trigger": payload.get("trigger"), "at": policy.now()})
        policy.save_session(runtime, session_id, state)
        return backend.block_compaction(policy.PRECOMPACT)
    if event == "UserPromptSubmit":
        if state.get("feedback_emitted"):
            return {}
        state["feedback_emitted"] = True
        policy.save_session(runtime, session_id, state)
        return _context(event, policy.FEEDBACK)
    return _post_tool_use(payload, backend, active, runtime, session_id, state)


def _pre_tool_use(payload, backend):
    tool_input = payload.get("tool_input")
    reason = backend.fresh_context_violation(
        payload.get("tool_name"), tool_input if isinstance(tool_input, dict) else {})
    if not reason:
        return {}
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": reason}}


def _post_tool_use(payload, backend, active, runtime, session_id, state):
    usage = backend.read_usage(payload.get("transcript_path"))
    if not usage:
        return {}
    limit = policy.threshold(active, usage.get("window"))
    state["last_usage"] = {**usage, "threshold": limit}
    emit = usage["used"] >= limit and not state.get("closeout_emitted_at")
    if emit:
        state["closeout_emitted_at"] = policy.now()
    policy.save_session(runtime, session_id, state)
    return _context("PostToolUse", policy.CLOSEOUT) if emit else {}


def _context(event, text):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
