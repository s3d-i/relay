"""Per-repository policy file and per-session state."""

from datetime import datetime, timezone
from pathlib import Path
import re

from . import context
from .state import RelayError, read_json, runtime_dir, write_json


MODES = ("trajectory", "autoresearch")


def locate(cwd):
    """Runtime dir for a hook payload's cwd, or None outside any repository (hooks stay silent there)."""
    try:
        return runtime_dir(cwd)
    except (RelayError, OSError):
        return None


def load(runtime):
    return read_json(Path(runtime) / "policy.json")


def mode(policy):
    # A file written before modes existed meant what autoresearch means now.
    value = policy.get("mode", "autoresearch")
    if value not in MODES:
        raise RelayError(f"Unknown mode in policy.json: {value!r}")
    return value


def enable(runtime, mode="trajectory", agent=None, window=None, warn_fraction=None, reserve=None,
           compact_limit=None, checkpoint_fraction=None):
    if mode not in MODES:
        raise RelayError(f"--mode must be one of {', '.join(MODES)}.")
    fraction = context.WARN_FRACTION if warn_fraction is None else warn_fraction
    if not 0.1 <= fraction <= 0.95:
        raise RelayError("--warn-fraction must be between 0.1 and 0.95.")
    step = context.CHECKPOINT_FRACTION if checkpoint_fraction is None else checkpoint_fraction
    if not 0 <= step < 1:
        raise RelayError("--checkpoint-fraction must be at least 0 and below 1.")
    reserve = context.RESERVE if reserve is None else reserve
    if reserve < 0 or any(n is not None and n <= 0 for n in (window, compact_limit)):
        raise RelayError("--window and --compact-limit must be positive, --reserve not negative.")
    if mode == "autoresearch" and (agent is None or agent == "claude" and not window):
        # A mode that blocks compaction must be able to deliver its closeout reminder.
        raise RelayError("--mode autoresearch needs --agent, and --window with --agent claude: "
                         "Claude Code does not report its context window.")
    value = {"version": 2, "active": True, "mode": mode, "agent": agent, "context_window": window,
             "compact_limit": compact_limit, "warn_fraction": fraction, "reserve": reserve,
             "checkpoint_fraction": step, "since": now()}
    if window and context.thresholds(value) is None:
        raise RelayError("Nothing is left below the window after --reserve; lower --reserve.")
    write_json(Path(runtime) / "policy.json", value)
    return value


def disable(runtime):
    value = {**(load(runtime) or {}), "active": False, "until": now()}
    write_json(Path(runtime) / "policy.json", value)
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
