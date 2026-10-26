"""Hook boundary: read the policy and payload, let the two layers answer, return hook output. Never raises."""

import copy
import os

from . import autoresearch, context, notes, policy, rhizome
from .state import RelayError, lock


def handle(payload, backend, repo=None):
    """`repo` is the repository the hook was installed in; without it (older hook commands) the payload cwd."""
    event = payload.get("hook_event_name") if isinstance(payload, dict) else None
    try:
        return _handle(payload, backend, event, repo)
    except Exception as exc:  # noqa: BLE001  the runner needs one JSON object whatever broke
        message = f"research-relay hook failed: {exc}"
        if event == "PreCompact":
            # Fail closed on compaction only. A policy read as rhizome has already answered by now.
            return backend.block_compaction(message)
        return {"systemMessage": message}


def _handle(payload, backend, event, repo):
    if not isinstance(payload, dict):
        raise RelayError("hook input must be a JSON object")
    if event not in backend.HOOK_EVENTS:
        return {}
    # The cwd follows the session's cd into other repositories; the installed repository does not.
    runtime = policy.locate(repo) if repo else None
    if runtime is None:
        repo = None  # not given, or no longer a repository (moved, renamed): the cwd, as hooks did before
        runtime = policy.locate(payload.get("cwd") or os.getcwd())
    active = policy.load(runtime) if runtime else None
    if not active or not active.get("active"):
        return {}  # unrelated repositories and switched-off ones see nothing
    auto = policy.mode(active) == "autoresearch"
    # Enforcement comes from the mode alone and applies to subagents too.
    if event == "PreCompact":
        return backend.block_compaction(autoresearch.PRECOMPACT) if auto else {}
    if payload.get("agent_id"):
        return {}  # a subagent's event: reminders and session state belong to the main thread
    session_id = payload.get("session_id")
    project = repo or payload.get("cwd") or os.getcwd()
    try:
        where = notes.where(runtime)  # no Git here: hooks stay cheap
    except (RelayError, OSError) as exc:  # an unreadable home must not cost the session its reminders
        where = {"error": str(exc)}
    # Parallel tool calls fire this hook concurrently; one reminder must reach one of them.
    with lock(policy.session_path(runtime, session_id).with_suffix(".lock")):
        state = policy.session(runtime, session_id)
        before = copy.deepcopy(state)
        parts = _main_thread(payload, backend, event, active, auto, state, project, where)
        if state != before:
            policy.save_session(runtime, session_id, state)
    return _context(event, "\n\n".join(parts)) if parts else {}


def _main_thread(payload, backend, event, active, auto, state, project, where):
    mode = "autoresearch" if auto else "rhizome"
    told, current = state.get("told"), {"mode": mode, "since": active.get("since")}
    if where:  # only with a pointer, so sessions told before pointers existed hear nothing new
        current["notes"] = {key: where[key] for key in ("home", "branch", "error") if key in where}
    state["told"] = current
    if event == "SessionStart":
        source = payload.get("source")
        if source in ("compact", "clear"):
            context.replaced(state)
        if source == "compact":
            return [rhizome.COMPACTED] + _located(where, project) + ([autoresearch.COMPACTED] if auto else [])
        return _session_text(backend, active, auto, project, where)
    parts = []
    if told != current:
        if told and {**told, "notes": None} == {**current, "notes": None}:
            parts = [rhizome.moved(where, project)]  # same policy, the notes live elsewhere now
        else:
            # The policy changed under an open session, or relay was switched on after it started.
            parts = [rhizome.changed(mode, told)] + _session_text(backend, active, auto, project, where)
    if event == "UserPromptSubmit":
        if not state.get("feedback_emitted"):
            state["feedback_emitted"] = True
            parts.append(rhizome.FEEDBACK)
        return parts
    return parts + _reminder(payload, backend, active, auto, state)


def _located(where, project):
    return [rhizome.located(where, project)] if where else []


def _session_text(backend, active, auto, project, where):
    parts = [rhizome.session(project)] + _located(where, project)
    if not (active.get("context_window") or backend.REPORTS_WINDOW):
        parts.append(rhizome.UNMONITORED)
    if auto:
        parts.append(autoresearch.SESSION)
    return parts


def _reminder(payload, backend, active, auto, state):
    usage = backend.read_usage(payload.get("transcript_path"))
    if not usage:
        return []
    limits = context.thresholds(active, usage.get("window"))
    if not limits:
        state["last_usage"] = usage
        return []
    result = context.observe(state, usage["used"], limits)
    state["last_usage"] = {**usage, **limits}
    if not result:
        return []
    final = rhizome.final(usage["used"], limits["ceiling"])
    if auto and usage["used"] >= limits["final"]:
        return [autoresearch.closeout(final)]  # every reminder past the threshold is the closeout
    return [final if result[0] == "final" else rhizome.checkpoint(result[1])]


def _context(event, text):
    return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}
