"""Claude Code: .claude/settings.local.json, Agent tool subagent_type, transcript message.usage."""

from pathlib import Path

from . import HOOK_EVENTS, hook_map, installed, last_value, merge_hooks
from ..autoresearch import FRESH_CONTEXT_DENIED
from ..state import RelayError, read_json, write_json


NAME = "claude"
SKILL_DIR = ".claude/skills"
HOOKS_FILE = ".claude/settings.local.json"
REPORTS_WINDOW = False  # neither the transcript nor hook payloads carry it; the policy supplies it
USAGE_KEYS = ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "output_tokens")


def hooks_file(repo):
    return Path(repo) / HOOKS_FILE


def hook_command(launcher):
    # CLAUDE_PROJECT_DIR is set for hook commands, so the same string works on every machine.
    return f'python3 "$CLAUDE_PROJECT_DIR/{SKILL_DIR}/research-relay/scripts/relay.py" hook --agent {NAME}'


def render_hooks(command):
    return {"hooks": hook_map(command)}


def install_hooks(repo, command):
    path = hooks_file(repo)
    current = read_json(path, {})  # foreign keys in settings.local.json survive untouched
    changed = merge_hooks(current.setdefault("hooks", {}), hook_map(command))
    if changed:
        write_json(path, current)
    return {"hooks_file": str(path), "hooks_changed": changed}


def hooks_installed(repo, command):
    try:
        current = read_json(hooks_file(repo), {})
    except RelayError:
        return False
    return installed(current.get("hooks"), hook_map(command))


def warnings(repo, policy):
    # Older relay versions wrote this key. relay cannot tell its own false from the human's, so it only reports.
    try:
        current = read_json(hooks_file(repo), {})
    except RelayError:
        return []
    if current.get("autoCompactEnabled") is False:
        return [f"{HOOKS_FILE} sets autoCompactEnabled: false; remove it to let Claude Code compact "
                "in trajectory mode."]
    return []


def block_compaction(reason):
    # Claude Code ignores continue/systemMessage on PreCompact; decision:block is the contract.
    return {"decision": "block", "reason": reason}


def read_usage(transcript_path):
    return last_value(transcript_path, _usage) if transcript_path else None


def _usage(item):
    if item["type"] != "assistant" or item.get("isSidechain"):
        return None
    usage = item["message"]["usage"]
    return {"used": sum(int(usage.get(key) or 0) for key in USAGE_KEYS),
            "window": None, "observed_at": item.get("timestamp")}


def fresh_context_violation(tool_name, tool_input):
    if tool_name == "Agent" and tool_input.get("subagent_type") == "fork":
        return FRESH_CONTEXT_DENIED.format(
            fix='Do not use subagent_type "fork"; every other Agent call starts a fresh context.')
    return None
