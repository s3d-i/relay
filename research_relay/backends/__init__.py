"""Agent backends and the helpers they share."""

import importlib
import json
from pathlib import Path

from ..state import RelayError, write_json


NAMES = ("codex", "claude")
HOOK_EVENTS = ("SessionStart", "UserPromptSubmit", "PostToolUse", "PreCompact")
TIMEOUT = 5
TAIL = 256 * 1024
WHOLE = 4 * 1024 * 1024


def get(name):
    if name not in NAMES:
        raise RelayError(f"Unknown agent {name!r}; choose one of {', '.join(NAMES)}.")
    return importlib.import_module("." + name, __name__)


def hook_map(command):
    """The hooks fragment both agents accept."""
    return {event: [{"hooks": [{"type": "command", "command": command, "timeout": TIMEOUT}]}]
            for event in HOOK_EVENTS}


def _our_hook(hook):
    return isinstance(hook, dict) and "research-relay" in str(hook.get("command", ""))


def ours(entry):
    return isinstance(entry, dict) and isinstance(entry.get("hooks"), list) and any(map(_our_hook, entry["hooks"]))


def _without_ours(entry):
    """The entry with relay's hooks taken out; None when nothing else was in it."""
    if not ours(entry):
        return entry
    rest = [hook for hook in entry["hooks"] if not _our_hook(hook)]
    return {**entry, "hooks": rest} if rest else None


def merge_hooks(hooks, fragment):
    """Replace our hooks, keep foreign ones, also inside a group shared with ours. True when anything changed."""
    if not isinstance(hooks, dict):
        raise RelayError("Existing 'hooks' is not an object; refusing to overwrite it.")
    changed = False
    for event in set(hooks) | set(fragment):
        current = hooks.get(event, [])
        if not isinstance(current, list):
            if event in fragment:
                raise RelayError(f"Existing hooks.{event} is not a list; refusing to overwrite it.")
            continue  # someone else's, whatever its shape
        # Stale entries from earlier relay versions (other events, old commands) go too.
        kept = [entry for entry in map(_without_ours, current) if entry is not None] + fragment.get(event, [])
        if hooks.get(event) != kept:
            if kept:
                hooks[event] = kept
            else:
                del hooks[event]
            changed = True
    return changed


def strip_hooks(path, current, changed=False):
    """Remove our entries from a parsed hooks file and save it; a file left empty is deleted.

    Foreign hooks and keys stay. `changed` says the caller already removed something of ours.
    """
    hooks = current.get("hooks", {})
    changed = merge_hooks(hooks, {}) or changed
    if not changed:
        return {"hooks_file": str(path), "hooks_changed": False}
    if not hooks:
        current.pop("hooks", None)
    if not current:
        Path(path).unlink()
        return {"hooks_file": str(path), "hooks_changed": True, "hooks_file_removed": True}
    write_json(path, current)
    return {"hooks_file": str(path), "hooks_changed": True}


def present(hooks):
    """Any relay entry at all, whatever its command or event."""
    return isinstance(hooks, dict) and any(ours(entry) for entries in hooks.values() if isinstance(entries, list)
                                           for entry in entries)


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
