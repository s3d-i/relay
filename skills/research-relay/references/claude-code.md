# Claude Code

Pinned: Claude Code 2.1.285 (`claude --version`). relay does not check the version at
runtime. After an upgrade, re-verify the facts below against
https://code.claude.com/docs/en/hooks.md and the sub-agents documentation.

## Install

From the relay checkout:

```sh
python3 -m research_relay install --repo /path/to/project --agent claude
python3 -m research_relay on      --repo /path/to/project --agent claude
```

`install`:

- symlinks `skills/research-relay` to `<project>/.claude/skills/research-relay` (invoke with `/research-relay`);
- merges into `<project>/.claude/settings.local.json`: relay's entries under `hooks` (entries whose
  command contains `research-relay` are replaced, others kept) and `"autoCompactEnabled": false`;
- adds `.gitignore` rules for the symlink, the settings file, and `/artifacts/private/`.

`settings.local.json` hooks need no workspace trust prompt. The command for every event is

```
python3 "$CLAUDE_PROJECT_DIR/.claude/skills/research-relay/scripts/relay.py" hook --agent claude
```

`CLAUDE_PROJECT_DIR` is set for hook commands, so the file holds no absolute paths and syncs
between machines. Timeout 5 s. Events: SessionStart, UserPromptSubmit, PreToolUse (matcher
`Agent`), PostToolUse, PreCompact. `install --print` shows the JSON without writing.

Optional extra: `DISABLE_AUTO_COMPACT=1` in the environment (or under `env` in settings) also
turns off auto-compaction. Not required; `autoCompactEnabled: false` plus the PreCompact block
already cover it.

## Verified facts (2.1.285)

- PreCompact block output is `{"decision": "block", "reason": ...}`. Claude Code discards
  `continue` and `systemMessage` on PreCompact. The hook fires for `manual` (`/compact`) and `auto`.
- Transcript: `~/.claude/projects/<slug>/<session_id>.jsonl`. Assistant entries carry
  `message.usage` with `input_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens`,
  `output_tokens`. relay sums the four from the last assistant line. The context window is not
  in the transcript, so it comes from the policy (`--window N`, default 200000).
- Subagent hook events carry the parent's `session_id`; subagents have their own transcripts
  under a `subagents/` folder, and SubagentStart/Stop carry `agent_id`. Whether PostToolUse
  fires for tool calls inside a subagent is undocumented. If it does, `transcript_path` is the
  parent's, so the usage estimate stays the main thread's.
- `Agent` tool input fields: `prompt`, `description`, `subagent_type`, `model`.
  `subagent_type: "fork"` inherits the conversation; relay denies it. Any other value, or none,
  starts a fresh context.
- SessionStart `source` is one of startup, resume, clear, compact, fork.

## Instructions for the main thread

- Use the `Agent` tool for all substantive work. Never pass `subagent_type: "fork"`; the hook
  denies it and the deny reason says why. Use the default general-purpose agent or a named one.
- Do not run `/compact`. It is blocked; the block message is expected.
- The closeout reminder arrives as additional context after a tool call. Follow
  [SKILL.md, Close out](../SKILL.md#5-close-out).
