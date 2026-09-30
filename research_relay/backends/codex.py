"""Codex Desktop: .codex/hooks.json, spawn_agent fork_turns, rollout token_count records."""

from pathlib import Path
import shlex
import sys

from . import HOOK_EVENTS, hook_map, installed, last_value, merge_hooks
from ..policy import FRESH_CONTEXT_DENIED
from ..state import RelayError, read_json, write_json


NAME = "codex"
SKILL_DIR = ".agents/skills"
HOOKS_FILE = ".codex/hooks.json"
DEFAULT_WINDOW = None  # the rollout carries model_context_window
TRUST = "Open the project in Codex and trust the hooks with /hooks; untrusted hooks never run."
DESCRIPTION = "research-relay: no compaction, fresh-context subagents, closeout before the context wall."


def hooks_file(repo):
    return Path(repo) / HOOKS_FILE


def hook_command(launcher):
    # Hooks run with the session cwd and no project variable: absolute paths only.
    return shlex.join([sys.executable, str(Path(launcher).resolve()), "hook", "--agent", NAME])


def render_hooks(command):
    return {"description": DESCRIPTION, "hooks": hook_map(command)}


def install_hooks(repo, command):
    path = hooks_file(repo)
    current = read_json(path, {})  # a non-JSON file is foreign: RelayError, nothing written
    changed = merge_hooks(current.setdefault("hooks", {}), hook_map(command))
    if "description" not in current:
        current["description"], changed = DESCRIPTION, True
    if changed:
        write_json(path, current)
    return {"hooks_file": str(path), "hooks_changed": changed, "next": TRUST}


def hooks_installed(repo, command):
    try:
        current = read_json(hooks_file(repo), {})
    except RelayError:
        return False
    return installed(current.get("hooks"), hook_map(command))


def block_compaction(reason):
    return {"continue": False, "stopReason": reason, "systemMessage": reason}


def read_usage(transcript_path):
    return last_value(transcript_path, _usage) if transcript_path else None


def _usage(item):
    if item["type"] != "event_msg" or item["payload"]["type"] != "token_count":
        return None
    info = item["payload"]["info"]
    if info is None:
        return None
    # last_token_usage already includes cached input and reasoning; never sum totals.
    return {"used": int(info["last_token_usage"]["total_tokens"]),
            "window": info.get("model_context_window"), "observed_at": item.get("timestamp")}


def fresh_context_violation(tool_name, tool_input):
    if tool_name == "Agent" and tool_input.get("fork_turns") != "none":
        return FRESH_CONTEXT_DENIED.format(
            fix='Call spawn_agent with fork_turns: "none"; omitting it inherits the parent conversation.')
    return None
