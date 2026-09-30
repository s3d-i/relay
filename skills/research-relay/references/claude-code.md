# Claude Code

Pinned: Claude Code 2.1.285 (`claude --version`). relay does not check the version at
runtime. After an upgrade, re-verify the facts below against
https://code.claude.com/docs/en/hooks.md and the sub-agents documentation.

## Install

From the relay checkout:

```sh
python3 -m research_relay install --repo /path/to/project --agent claude
python3 -m research_relay on      --repo /path/to/project --agent claude --window 1000000
```

`install`:

- symlinks `skills/research-relay` to `<project>/.claude/skills/research-relay` (invoke with `/research-relay`);
- merges relay's entries into `hooks` in `<project>/.claude/settings.local.json` (entries whose
  command contains `research-relay` are replaced, others kept);
- adds `.gitignore` rules for the symlink, the settings file, and `/artifacts/private/`.

`settings.local.json` hooks need no workspace trust prompt. The command for every event is

```
python3 "$CLAUDE_PROJECT_DIR/.claude/skills/research-relay/scripts/relay.py" hook --agent claude
```

`CLAUDE_PROJECT_DIR` is set for hook commands, so the file holds no absolute paths. Timeout
5 s. Events: SessionStart, UserPromptSubmit, PreToolUse (matcher `Agent`), PostToolUse,
PreCompact. `install --print` shows the JSON without writing.

`--window`: Claude Code reports its context window neither in the transcript nor in hook
payloads, so the policy supplies it. Without it there are no context reminders, and
`--mode autoresearch` refuses to start. Fable and Sonnet 5 models run with 1,000,000.

`--compact-limit`: only when Claude Code's own auto-compaction threshold (`autoCompactWindow`,
`CLAUDE_CODE_AUTO_COMPACT_WINDOW`) was lowered below the window.

Older relay versions wrote `"autoCompactEnabled": false` into `settings.local.json`. relay no
longer writes or requires it and does not remove it; `relay status` warns while it is there.
Delete the key to let Claude Code compact in trajectory mode.

## Verified facts (2.1.285)

- PreCompact block output is `{"decision": "block", "reason": ...}`. Claude Code discards
  `continue` and `systemMessage` on PreCompact. The hook fires for `manual` (`/compact`) and `auto`.
- Transcript: `~/.claude/projects/<slug>/<session_id>.jsonl`. Assistant entries carry
  `message.usage` with `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`,
  `output_tokens`. relay sums the four from the last assistant line that is not a sidechain.
- Hooks also run inside subagents. Tool events there carry `agent_id` and `agent_type`, and
  the parent's `session_id` (hooks reference, "Common input fields"). relay gives an event with
  `agent_id` enforcement only: no reminder, no session state.
- `Agent` tool input fields: `prompt`, `description`, `subagent_type`, `model`.
  `subagent_type: "fork"` inherits the conversation; auto-research mode denies it. Any other
  value, or none, starts a fresh context.
- SessionStart `source` is one of startup, resume, clear, compact, fork. `additionalContext`
  from SessionStart, UserPromptSubmit and PostToolUse reaches the model; `systemMessage`
  reaches only the human.

Not yet captured from a live session: the SessionStart that follows a real compaction, and
whether the session id survives one. relay treats `source: compact` as the confirmation and
starts over with empty state under a new session id, so either answer works.

## Instructions for the main thread

- Reminders arrive as additional context after a tool call. Follow
  [SKILL.md, Context reminders](../SKILL.md#4-context-reminders).
- In auto-research mode: use the `Agent` tool for all substantive work and never pass
  `subagent_type: "fork"`; do not run `/compact`; follow [auto-research](autoresearch.md).
