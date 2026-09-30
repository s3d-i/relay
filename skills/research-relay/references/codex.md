# Codex Desktop

Pinned: Codex Desktop ChatGPT.app 26.924.22138 (bundled codex-cli 0.158.0-alpha.2.1). relay does not check the build at runtime.
After an app update, re-verify the facts below against https://learn.chatgpt.com/docs/hooks.

## Install

Run on the machine that runs Codex; the hooks file holds absolute paths.

```sh
python3 -m research_relay install --repo /path/to/project --agent codex
python3 -m research_relay on      --repo /path/to/project --agent codex
```

`install`:

- symlinks `skills/research-relay` to `<project>/.agents/skills/research-relay` (invoke with
  `$research-relay`; skill metadata is in `agents/openai.yaml`);
- writes `<project>/.codex/hooks.json` with relay's five events, merging them into an existing
  file and refusing to overwrite a foreign file it cannot merge;
- adds `.gitignore` rules for the symlink, `/.codex/hooks.json`, and `/artifacts/private/`.

The command is `python3 <abs-relay-checkout>/skills/research-relay/scripts/relay.py hook --agent codex`.
Hooks run with the session cwd and Codex sets no project env var, so the paths are absolute.
Timeout 5 s. Events: SessionStart, UserPromptSubmit, PreToolUse (matcher `Agent`), PostToolUse,
PreCompact. `install --print` shows the JSON without writing.

Trust: open the project in the app and trust the hooks once through `/hooks`. relay does not
check or grant trust. A session opened before the hooks file existed may not have loaded it;
open a fresh one.

`model_auto_compact_token_limit`: Codex has its own auto-compaction ceiling in its config. The
PreCompact hook blocks the attempt whichever trigger fires, but if that ceiling sits below
relay's threshold, the blocked attempt comes before the closeout reminder. Pass
`--compact-limit N` to `relay on` with that value so the threshold is computed against it, or
raise the ceiling in the Codex config.

## Verified facts

- Hook event names and output shapes match Claude Code's, except PreCompact blocking, which
  uses `{"continue": false, "stopReason": reason, "systemMessage": reason}`.
- Usage: the last `event_msg` in the rollout with `payload.type == "token_count"` and a non-null
  `payload.info`. `used = info.last_token_usage.total_tokens`,
  `window = info.model_context_window`. relay reads the last 256 KiB of the file.
- The PreToolUse matcher for `spawn_agent` is `Agent`. `tool_input.fork_turns` is observed,
  not documented: any value other than `"none"` (including omission) inherits history and is
  denied.
- Worker events carry the parent `session_id`; their compaction is blocked under the same policy.

## Instructions for the main thread

- Spawn every worker with `spawn_agent` and `fork_turns: "none"`. Omission defaults to inherited
  history and is denied. New agent per independent task.
- Do not run `/compact`. It is blocked; the block message is expected.
- The closeout reminder arrives as additional context after a tool call. Follow
  [SKILL.md, Close out](../SKILL.md#5-close-out).
