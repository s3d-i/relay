# Claude Code

Pinned: Claude Code 2.1.299 (`claude --version`). relay does not check the version at
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

Hooks in `settings.local.json` run once the folder has passed Claude Code's workspace trust
dialog; there is no separate hook trust step. The command for every event is

```
python3 "$CLAUDE_PROJECT_DIR/.claude/skills/research-relay/scripts/relay.py" hook --agent claude
```

`CLAUDE_PROJECT_DIR` is set for hook commands, so the file holds no absolute paths. The hook
also reads it as its repository: the payload's `cwd` follows every `cd` the session makes,
into other repositories too (seen in 2.1.299 transcripts), while `CLAUDE_PROJECT_DIR` stays
the project whose settings loaded the hook. Timeout 5 s. Events: SessionStart,
UserPromptSubmit, PostToolUse, PreCompact. `install --print` shows the JSON without writing;
`install --uninstall` removes the skill link and relay's entries, and deletes the settings
file only when nothing else is left in it.

`--window`: Claude Code reports its context window neither in the transcript nor in hook
payloads (only the status line payload carries it), so the policy supplies it. Without it
there are no context reminders, and `--mode autoresearch` refuses to start. Fable 5 and 5.1,
Sonnet 5 and later, Opus 4.7 and later and Haiku 5.5 run with 1,000,000 by default.

`--compact-limit`: only when Claude Code's own auto-compaction threshold (`autoCompactWindow`,
`/autocompact`, which saves it per model under `modelSettings`, `--autocompact`, or
`CLAUDE_CODE_AUTO_COMPACT_WINDOW`) was lowered below the window.

Older relay versions wrote `"autoCompactEnabled": false` into `settings.local.json`. relay no
longer writes or requires it and does not remove it; `relay status` warns while it is there.
Delete the key to let Claude Code compact in rhizome mode.

## Verified facts (2.1.299)

Checked against the hooks, sub-agents and settings documentation and the changelog through
2.1.299, and in a headless 2.1.299 session (`claude -p`, then `/compact`) whose hooks logged
their input.

- PreCompact block output is `{"decision": "block", "reason": ...}`; it blocked a manual
  `/compact` in that session. Claude Code discards `continue` and `systemMessage` on
  PreCompact. The hook fires for `manual` (`/compact`) and `auto`; idle compaction, new in
  2.1.299, also reports `auto`. Blocking a compaction started to recover from a context-limit
  error fails the current request.
- Transcript: `~/.claude/projects/<slug>/<session_id>.jsonl`. Assistant entries carry
  `message.usage` with `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`,
  `output_tokens`. relay sums the four from the last assistant line that is not a sidechain.
  Subagent records go to `<session_id>/subagents/agent-<id>.jsonl` with `isSidechain: true`.
- Hooks also run inside subagents. Their events carry `agent_id` and `agent_type`, and the
  parent's `session_id` and `transcript_path`. relay gives an event with `agent_id`
  enforcement only: no reminder, no session state.
- `Agent` tool input fields: `prompt`, `description`, `subagent_type`, and optional `model`,
  `effort`, `isolation` and `name`. `subagent_type: "fork"` inherits the conversation;
  any other value, or none, starts a fresh context.
- SessionStart `source` is one of startup, resume, clear, compact, fork. `additionalContext`
  from SessionStart, UserPromptSubmit and PostToolUse reaches the model; `systemMessage`
  reaches only the human.
- After a real compaction, SessionStart fires with `source: compact`, the same `session_id`
  and the same transcript. relay resets that session's context state on it.

## Instructions for the main thread

- Reminders arrive as additional context after a tool call. Follow
  [SKILL.md, Context reminders](../SKILL.md#4-context-reminders).
- In auto-research mode: use the `Agent` tool for all substantive work and never pass
  `subagent_type: "fork"`; do not run `/compact`; follow [auto-research](autoresearch.md).
