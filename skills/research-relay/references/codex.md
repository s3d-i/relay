# Codex Desktop

Pinned: Codex Desktop ChatGPT.app 26.1007.71326 (bundled codex-cli 0.162.0-alpha.17.2). relay does not check the build at runtime.
After an app update, re-verify the facts below against https://learn.chatgpt.com/docs/hooks.

## Install

Run on the machine that runs Codex; the hooks file holds absolute paths.

```sh
python3 -m research_relay install --repo /path/to/project --agent codex
python3 -m research_relay on      --repo /path/to/project --agent codex --compact-limit 600000
```

`install`:

- symlinks `skills/research-relay` to `<project>/.agents/skills/research-relay` (invoke with
  `$research-relay`; skill metadata is in `agents/openai.yaml`);
- writes `<project>/.codex/hooks.json` with relay's five events, merging them into an existing
  file and refusing to overwrite a foreign file it cannot merge;
- adds `.gitignore` rules for the symlink, `/.codex/hooks.json`, and `/artifacts/private/`.

The command is `python3 <abs-relay-checkout>/skills/research-relay/scripts/relay.py hook --agent codex`.
Hooks run with the session cwd and Codex sets no project env var, so the paths are absolute.
Timeout 5 s. Events: SessionStart, UserPromptSubmit, PostToolUse, PreCompact.
`install --print` shows the JSON without writing.

Trust: open the project in the app and trust the hooks once through `/hooks`. relay does not
check or grant trust. A session opened before the hooks file existed may not have loaded it;
open a fresh one.

`--compact-limit`: Codex compacts on its own at `model_auto_compact_token_limit`, which can
sit below the window the rollout reports (for example 600000 under a window of 760000). Pass
that value so the reminders are computed against it. relay does not read Codex's
configuration: the key can come from `-c`, a trusted project file, a profile file or the user
file, and a file reader cannot know which applied to a running session. `relay on` and
`relay status` warn while the policy names Codex and has no limit. The value assumes
`model_auto_compact_token_limit_scope` is `total`, the default; with `body_after_prefix` the
limit counts only growth after the carried prefix.

## Verified facts

Checked against https://learn.chatgpt.com/docs/hooks, the openai/codex release notes and source
for 0.158 to 0.162, the hook schemas and tool text embedded in the pinned build's binary, and
its rollouts.

- Hook event names and output shapes match Claude Code's, except PreCompact blocking, which
  uses `{"continue": false, "stopReason": reason, "systemMessage": reason}`.
- Usage: the last `event_msg` in the rollout with `payload.type == "token_count"` and a non-null
  `payload.info`. `used = info.last_token_usage.total_tokens`,
  `window = info.model_context_window` (760000 in the pinned build's sessions). relay reads the
  last 256 KiB of the file. The `token_count` for a model request is written after that
  request's tool output, so at PostToolUse the reading can lag by one request.
- A compaction writes a `compacted` record followed by a `token_count` with the reduced usage
  (seen on the pinned build: about 12000 to 13500 tokens after).
- `spawn_agent` in multi-agent V2, which the pinned build's sessions use, takes `message`,
  `task_name` and optional `agent_type`, `model`, `reasoning_effort`, `fork_turns`. The tool
  text says `fork_turns` defaults to `all`, `none` starts without parent history, and only
  those two are supported. Since 0.162 a positive integer string forks the full history instead
  of that many turns (openai/codex#51329); other values are rejected. `fork_turns` is not in
  the public docs. V1's `spawn_agent` takes a `fork_context` boolean instead; V2 rejects it.
- Worker events carry the parent `session_id`. The pinned build's PostToolUse, PreCompact and
  UserPromptSubmit input schemas include an optional `agent_id`; relay gives an event with
  `agent_id` enforcement only.
- The SessionStart input schema accepts `source` startup, resume, clear, compact and fork. The
  docs say the `compact` event runs before the next model request after a root compaction.

Not yet captured from a live session on the pinned build: whether worker payloads actually
carry `agent_id`, and the `SessionStart` with `source: compact` after a real compaction. If
`agent_id` is missing, a worker's tool call can receive a reminder meant for the main thread.
If the compact event is missing, the final reminder re-arms only after usage drops by a tenth
of the ceiling below its threshold.

## Instructions for the main thread

- Reminders arrive as additional context after a tool call. Follow
  [SKILL.md, Context reminders](../SKILL.md#4-context-reminders).
- In auto-research mode: spawn every worker with `spawn_agent` and `fork_turns: "none"`
  (omission inherits history); do not run `/compact`; follow
  [auto-research](autoresearch.md).
