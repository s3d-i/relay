"""Per-repository policy file, per-session state, and the texts hooks deliver."""

from datetime import datetime, timezone
from pathlib import Path
import re

from .state import RelayError, read_json, runtime_dir, write_json


DEFAULT_WINDOW = 200_000
DEFAULT_WARN_FRACTION = 0.6

PRECOMPACT = (
    "research-relay forbids compaction in this repository. Close out instead: update RESEARCH.md "
    "on relay-notes, stop workers, end the turn. The human opens a fresh session that reads the notes."
)

CLOSEOUT = (
    "research-relay: context usage crossed the closeout threshold. Begin closeout now. "
    "Do not open new directions or delegate new research; finish the current operation at a safe boundary. "
    "Collect completed or partial subagent results, stop the agents and verify they stopped writing. "
    "Keep original human inputs only in Git-ignored artifacts/private/human-inputs/<session-id>.md. "
    "Update RESEARCH.md on relay-notes: current understanding, affected connections, decision summaries, "
    "private source citations, and where unfinished investigation stands. Commit only reviewed shareable "
    "notes (relay notes commit --path ...), never private originals. Report briefly and end this turn. "
    "Do not compact; the human opens the next fresh session."
)

FEEDBACK = (
    "research-relay human feedback: Distinguish unsolicited human input from answers to agent questions "
    "and option selections; option wording is the agent's, and UserPromptSubmit alone does not establish "
    "provenance. Preserve originals only in Git-ignored artifacts/private/human-inputs/<session-id>.md, "
    "one file per main session, with separately labelled agent context annotations (question, proposal, "
    "code state, results). Interpret a selection within the question and options presented; never expand "
    "authorization through a summary. Shareable notes hold decisions, interpretations and private "
    "citations, not copies. Apply explicit stops immediately; a new idea does not by itself interrupt "
    "active work. Briefly state your understanding and what you will do."
)

SESSION_START = (
    "research-relay is active for this repository: compaction is blocked by hook, and when context usage "
    "crosses the threshold you will be told to close out. Entry point: RESEARCH.md on the relay-notes "
    "branch (relay notes status). Read the research-relay skill ($research-relay) and follow it. "
    "Delegation: the main thread aligns with the human, delegates bounded work to fresh-context "
    "subagents (never ones that inherit this conversation), reviews returned evidence and maintains the "
    "notes; it does not carry out substantive research itself."
)

COMPACTED = (
    "research-relay: this session continued after a compaction that should have been blocked. "
    "Do not continue sustained research on compacted context. Recover understanding from RESEARCH.md on "
    "relay-notes, report the compaction to the human, and close out; the human opens a fresh session."
)

FRESH_CONTEXT_DENIED = "research-relay: every subagent must start with fresh context. {fix}"


def locate(cwd):
    """Runtime dir for a hook payload's cwd, or None outside any repository (hooks stay silent there)."""
    try:
        return runtime_dir(cwd)
    except (RelayError, OSError):
        return None


def load(runtime):
    return read_json(Path(runtime) / "policy.json")


def enable(runtime, agent=None, window=None, warn_fraction=None, compact_limit=None):
    fraction = DEFAULT_WARN_FRACTION if warn_fraction is None else warn_fraction
    if not 0.1 <= fraction <= 0.95:
        raise RelayError("--warn-fraction must be between 0.1 and 0.95.")
    if any(n is not None and n <= 0 for n in (window, compact_limit)):
        raise RelayError("--window and --compact-limit must be positive.")
    value = {"active": True, "agent": agent, "context_window": window, "warn_fraction": fraction,
             "compact_limit": compact_limit, "since": now()}
    write_json(Path(runtime) / "policy.json", value)
    return value


def disable(runtime):
    value = {**(load(runtime) or {}), "active": False, "until": now()}
    write_json(Path(runtime) / "policy.json", value)
    return value


def threshold(policy, window=None):
    """An explicit policy window wins; else the transcript's; else the default."""
    window = policy.get("context_window") or window or DEFAULT_WINDOW
    value = int(window * policy.get("warn_fraction", DEFAULT_WARN_FRACTION))
    limit = policy.get("compact_limit")
    if limit:
        # Stay a fifth below the compaction ceiling: closeout needs room to write notes.
        value = min(value, int(min(window, limit) * 0.8))
    return value


def session_path(runtime, session_id):
    name = re.sub(r"[^\w.-]", "_", str(session_id or "unknown"))[:128]
    return Path(runtime) / "sessions" / f"{name}.json"


def session(runtime, session_id):
    return read_json(session_path(runtime, session_id), {})


def save_session(runtime, session_id, state):
    write_json(session_path(runtime, session_id), state)


def sessions(runtime):
    folder = Path(runtime) / "sessions"
    if not folder.is_dir():
        return {}
    return {p.stem: read_json(p, {}) for p in sorted(folder.glob("*.json"))}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
