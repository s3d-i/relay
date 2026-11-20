"""Antigravity: .agents/hooks.json, .agent/skills/research-relay, transcript PLANNER_RESPONSE tokens."""

import os
from pathlib import Path
import shlex
import shutil
import sys

from . import TIMEOUT, _our_hook, last_value
from ..state import RelayError, read_json, write_json


NAME = "antigravity"
SKILL_DIR = ".agent/skills"
HOOKS_FILE = ".agents/hooks.json"
HOOK_NAME = "research-relay"
HOOK_EVENTS = ("SessionStart", "PreInvocation")
REPORTS_WINDOW = False  # transcripts log token counts but not the context window; the policy supplies it
DEFAULT_WARN_FRACTION = 0.6  # no PreCompact hook: fire closeout earlier (600K on a 1M window) before auto-compaction
USAGE_KEYS = ("input_tokens", "cache_read_tokens", "output_tokens")


def hooks_file(repo):
    return Path(repo) / HOOKS_FILE


def hook_command(launcher, repo):
    # Hooks run with cwd set to .agents/ and no project env var: absolute paths only.
    return shlex.join([sys.executable, str(Path(launcher).resolve()), "hook", "--agent", NAME,
                       "--repo", str(Path(repo).resolve())])


def project_dir(environ):
    return None  # Antigravity sets no project env var; the command carries --repo


def _event_map(command):
    return {event: [{"type": "command", "command": command, "timeout": TIMEOUT}] for event in HOOK_EVENTS}


def render_hooks(command):
    return {HOOK_NAME: _event_map(command)}


def _is_our_entry(entry):
    if _our_hook(entry):
        return True
    return isinstance(entry, dict) and isinstance(entry.get("hooks"), list) and any(map(_our_hook, entry["hooks"]))


def _without_ours(entry):
    if _our_hook(entry):
        return None
    if isinstance(entry, dict) and isinstance(entry.get("hooks"), list) and any(map(_our_hook, entry["hooks"])):
        rest = [hook for hook in entry["hooks"] if not _our_hook(hook)]
        return {**entry, "hooks": rest} if rest else None
    return entry


def _has_ours(spec):
    return isinstance(spec, dict) and any(
        _is_our_entry(entry) for entries in spec.values() if isinstance(entries, list) for entry in entries
    )


def _strip_spec(spec):
    """Remove relay's entries from one named hook spec. Returns (new_spec_or_None, changed)."""
    if not isinstance(spec, dict):
        return spec, False
    updated = dict(spec)
    changed = False
    for event, entries in list(updated.items()):
        if not isinstance(entries, list):
            continue
        kept = [entry for entry in map(_without_ours, entries) if entry is not None]
        if kept != entries:
            changed = True
            if kept:
                updated[event] = kept
            else:
                del updated[event]
    if changed and not any(isinstance(v, list) for v in updated.values()):
        return None, True
    return updated, changed


def install_hooks(repo, command):
    path = hooks_file(repo)
    current = read_json(path, {})
    fragment = _event_map(command)
    changed = False
    for name in list(current):
        if name == HOOK_NAME:
            continue
        cleaned, item_changed = _strip_spec(current[name])
        if item_changed:
            changed = True
            if cleaned is None:
                del current[name]
            else:
                current[name] = cleaned
    existing = current.get(HOOK_NAME)
    if existing is not None and not isinstance(existing, dict):
        raise RelayError(f"Existing hooks.{HOOK_NAME} is not an object; refusing to overwrite it.")
    spec = dict(existing or {})
    for event in set(spec) | set(fragment):
        entries = spec.get(event, [])
        if event in fragment and not isinstance(entries, list):
            raise RelayError(f"Existing hooks.{HOOK_NAME}.{event} is not a list; refusing to overwrite it.")
        if not isinstance(entries, list):
            continue
        kept = [entry for entry in map(_without_ours, entries) if entry is not None] + fragment.get(event, [])
        if spec.get(event) != kept:
            if kept:
                spec[event] = kept
            else:
                del spec[event]
            changed = True
    if current.get(HOOK_NAME) != spec:
        current[HOOK_NAME] = spec
        changed = True
    if changed:
        write_json(path, current)
    return {"hooks_file": str(path), "hooks_changed": changed}


def uninstall_hooks(repo):
    path = hooks_file(repo)
    current = read_json(path)
    if current is None:
        return {"hooks_file": str(path), "hooks_changed": False}
    changed = False
    for name in list(current):
        cleaned, item_changed = _strip_spec(current[name])
        if item_changed:
            changed = True
            if cleaned is None:
                del current[name]
            else:
                current[name] = cleaned
    if not changed:
        return {"hooks_file": str(path), "hooks_changed": False}
    if not current:
        path.unlink()
        return {"hooks_file": str(path), "hooks_changed": True, "hooks_file_removed": True}
    write_json(path, current)
    return {"hooks_file": str(path), "hooks_changed": True}


def hooks_present(repo):
    try:
        current = read_json(hooks_file(repo), {})
    except RelayError:
        return False
    return any(_has_ours(spec) for spec in current.values())


def hooks_installed(repo, command):
    try:
        current = read_json(hooks_file(repo), {})
    except RelayError:
        return False
    spec = current.get(HOOK_NAME)
    if not isinstance(spec, dict) or spec.get("enabled") is False:
        return False
    fragment = _event_map(command)
    return all(isinstance(spec.get(event), list) and all(entry in spec[event] for entry in entries)
               for event, entries in fragment.items())


def _is_our_skill_dir(target, skill_src):
    if not target.is_dir() or target.is_symlink():
        return False
    scripts = target / "scripts"
    if not scripts.is_symlink():
        return False
    return (scripts.resolve() == skill_src / "scripts"
            or os.readlink(scripts).rstrip("/").endswith("skills/research-relay/scripts"))


def install_skill(repo, skill_src):
    """Install a real skill directory: Antigravity's scanner skips symlinked skill directories and SKILL.md."""
    target = Path(repo) / SKILL_DIR / "research-relay"
    if target.exists() or target.is_symlink():
        if not _is_our_skill_dir(target, skill_src):
            raise RelayError(f"Existing skill preserved; inspect manually: {target}")
    target.mkdir(parents=True, exist_ok=True)
    skill_md = target / "SKILL.md"
    src_bytes = (skill_src / "SKILL.md").read_bytes()
    if skill_md.is_symlink() or not skill_md.exists() or skill_md.read_bytes() != src_bytes:
        if skill_md.is_symlink():
            skill_md.unlink()
        skill_md.write_bytes(src_bytes)
    for child in sorted(skill_src.iterdir()):
        if child.name == "SKILL.md":
            continue
        link = target / child.name
        if link.is_symlink() and link.resolve() == child:
            continue
        if link.is_symlink():
            link.unlink()
        elif link.exists():
            raise RelayError(f"Existing skill preserved; inspect manually: {link}")
        link.symlink_to(child, target_is_directory=child.is_dir())
    return target


def uninstall_skill(repo, skill_src):
    target = Path(repo) / SKILL_DIR / "research-relay"
    if _is_our_skill_dir(target, skill_src):
        shutil.rmtree(target)
        return target, None
    if target.exists() or target.is_symlink():
        return target, "not relay's skill directory; left in place"
    return target, None


def parse_payload(payload):
    workspaces = payload.get("workspacePaths")
    fallback_cwd = workspaces[0] if isinstance(workspaces, list) and workspaces else None
    return {
        "event": payload.get("hookEventName"),
        "session_id": payload.get("conversationId"),
        "cwd": payload.get("cwd") or fallback_cwd,
        "transcript_path": payload.get("transcriptPath"),
        "agent_id": None,
        "source": None,
    }


def format_context(event, text):
    return {"injectSteps": [{"systemMessage": {"systemMessage": text}}]}


def format_error(event, message):
    return {"injectSteps": [{"systemMessage": {"systemMessage": message}}]}


def warnings(repo, policy):
    if policy and policy.get("active") and policy.get("agent") == NAME and policy.get("mode") == "autoresearch":
        notes = ["Antigravity has no PreCompact hook: compaction cannot be blocked by hook in auto-research mode "
                 "(closeout reminders still arrive, and sharp token drops trigger a suspected-compaction closeout)."]
        fraction = policy.get("warn_fraction", DEFAULT_WARN_FRACTION)
        if fraction > 0.65:
            notes.append(f"warn_fraction is {fraction} on Antigravity without a PreCompact hook; "
                         "0.5-0.6 (500K-600K on a 1M window) is recommended so closeout arrives before auto-compaction.")
        return notes
    return []


def read_usage(transcript_path):
    if not transcript_path:
        return None
    usage = last_value(transcript_path, _usage)
    if usage is None and Path(transcript_path).name == "transcript_full.jsonl":
        # A large tool result in transcript_full.jsonl can push PLANNER_RESPONSE past the 256 KiB tail.
        return last_value(Path(transcript_path).with_name("transcript.jsonl"), _usage)
    return usage


def _usage(item):
    if item.get("type") != "PLANNER_RESPONSE":
        return None
    if not any(item.get(key) is not None for key in USAGE_KEYS):
        return None
    return {"used": sum(int(item.get(key) or 0) for key in USAGE_KEYS),
            "window": None, "observed_at": item.get("created_at")}
