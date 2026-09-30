"""Agent backends and the helpers they share."""

import importlib
import json
from pathlib import Path

from ..state import RelayError


NAMES = ("codex", "claude")
HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "PreCompact")
TIMEOUT = 5
TAIL = 256 * 1024
WHOLE = 4 * 1024 * 1024


def get(name):
    if name not in NAMES:
        raise RelayError(f"Unknown agent {name!r}; choose one of {', '.join(NAMES)}.")
    return importlib.import_module("." + name, __name__)


def hook_map(command):
    """The hooks fragment both agents accept: matcher only where the event is tool-specific."""
    value = {}
    for event in HOOK_EVENTS:
        entry = {"hooks": [{"type": "command", "command": command, "timeout": TIMEOUT}]}
        if event == "PreToolUse":
            entry = {"matcher": "Agent", **entry}
        value[event] = [entry]
    return value


def ours(entry):
    return any("research-relay" in str(hook.get("command", "")) for hook in entry.get("hooks", [])
               if isinstance(hook, dict)) if isinstance(entry, dict) else False


def merge_hooks(hooks, fragment):
    """Replace our entries, keep foreign ones. Returns True when anything changed."""
    if not isinstance(hooks, dict):
        raise RelayError("Existing 'hooks' is not an object; refusing to overwrite it.")
    changed = False
    for event in set(hooks) | set(fragment):
        # Stale entries from earlier relay versions (other events, old commands) go too.
        kept = [e for e in hooks.get(event, []) if not ours(e)] + fragment.get(event, [])
        if hooks.get(event) != kept:
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
            changed = True
    return changed


def installed(hooks, fragment):
    return isinstance(hooks, dict) and all(
        all(entry in hooks.get(event, []) for entry in entries) for event, entries in fragment.items())


def last_value(path, extract):
    """First non-None extract(record) scanning a JSONL file backwards; bounded read.

    The tail (256 KiB) is enough for a live transcript; the whole file is read only
    when the tail holds no match and the file is small, so a 50 MB transcript stays cheap.
    """
    path = Path(path)
    if not path.is_file():
        return None  # an absent transcript is "no estimate yet", not a failure
    size = path.stat().st_size
    starts = [max(0, size - TAIL)]
    if starts[0] and size <= WHOLE:
        starts.append(0)
    for start in starts:
        with path.open("rb") as src:
            src.seek(start)
            lines = src.read().split(b"\n")
        for raw in reversed(lines[1:] if start else lines):
            try:
                value = extract(json.loads(raw))
            except (ValueError, KeyError, TypeError, AttributeError):
                continue
            if value is not None:
                return value
    return None
