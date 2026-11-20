# Antigravity

Pinned: Antigravity CLI 1.5.12 (`agy --version`). relay does not check the build at runtime.
After an upgrade, re-verify the facts below against Antigravity's hooks and customization docs.

## Install

Run on the machine that runs Antigravity; the hooks file holds absolute paths.

```sh
python3 -m research_relay install --repo /path/to/project --agent antigravity
python3 -m research_relay on      --repo /path/to/project --mode autoresearch --agent antigravity --window 1000000
```

`install`:

- installs the skill at `<project>/.agent/skills/research-relay` as a real directory with a copy
  of `SKILL.md` and symlinks to `agents`, `assets`, `references`, and `scripts` (Antigravity's
  skill scanner skips symlinked skill directories and symlinked `SKILL.md` files, and using
  `.agent/skills` avoids colliding with Codex's symlink in `.agents/skills`);
- merges relay's `"research-relay"` entry into `<project>/.agents/hooks.json`, keeping foreign
  named hooks and refusing to overwrite an unreadable or non-JSON file;
- adds `.gitignore` rules for `/.agent/skills/research-relay`, `/.agents/hooks.json`, and
  `/artifacts/private/`.

The command is `python3 <abs-relay-checkout>/skills/research-relay/scripts/relay.py hook --agent antigravity --repo <abs-project>`.
Hooks run with their process cwd set to `<project>/.agents` and no project env var, so paths are
absolute and `--repo` names the project the hooks belong to. Timeout 5 s. Events: `SessionStart`,
`PreInvocation`. `install --print` shows the JSON without writing; `install --uninstall` removes
relay's skill directory and hook entries, deleting `.agents/hooks.json` only when nothing else is
left in it.

`--window`: Antigravity transcripts log token counts per `PLANNER_RESPONSE` step, not the model's
context window, so the policy supplies it. Without `--window` there are no context reminders and
`--mode autoresearch` refuses to start.

`--compact-limit`: only when Antigravity's own compaction ceiling sits below `--window`.

## Verified facts (1.5.12)

Checked against Antigravity's built-in `agy-customizations` docs (`docs/hooks.md`, `docs/skills.md`)
and live headless sessions (`agy -p`) whose hooks logged their payloads and transcripts.

- Hook payloads on stdin use camelCase (`hookEventName`, `conversationId`, `cwd`,
  `workspacePaths`, `transcriptPath`, `modelName`, `lastUserInput`, `invocationNum`,
  `initialNumSteps`).
- `SessionStart` and `PreInvocation` accept
  `{"injectSteps": [{"systemMessage": {"systemMessage": "..."}}]}` on stdout and deliver the text
  to the model as `SYSTEM_MESSAGE` steps. `PostToolUse` expects `{}` and cannot inject context.
- `PreInvocation` fires before every model call (`invocationNum` 0, 1, ...), including after tool
  calls and on tool-free turns. relay emits the human-feedback provenance guidance once on the
  first `PreInvocation` and checks context usage on every `PreInvocation`.
- Usage: the last `PLANNER_RESPONSE` line in `transcriptPath` (`transcript_full.jsonl` in CLI
  sessions). `used = input_tokens + cache_read_tokens + output_tokens`, `window = None`,
  `observed_at = created_at`. `input_tokens` counts uncached input tokens only, so adding
  `cache_read_tokens` gives the full prompt size. If a large tool output pushes the last
  `PLANNER_RESPONSE` past the 256 KiB tail of `transcript_full.jsonl`, relay falls back to the
  sibling compact `transcript.jsonl`. Both files are flushed before the next `PreInvocation`.
- Antigravity has no `PreCompact` hook: in `autoresearch` mode compaction cannot be blocked by
  hook (`relay on` and `relay status` warn about this). To compensate, `--agent antigravity`
  defaults `--warn-fraction` to `0.5` (500,000 tokens on a 1M window; use `--warn-fraction 0.6`
  for 600,000), `SessionStart` states that compaction is not hook-blocked, and a sharp drop in
  observed usage (>= 25% of ceiling and < 50% of prior usage) injects a suspected-compaction
  recovery and closeout notice.
- Antigravity hook payloads carry no `agent_id` field. Subagents run as separate conversations
  with their own `conversationId` and `transcriptPath`, so they fire hooks independently and keep
  separate session state without overwriting the main thread's state.
- `.agents/hooks.json` and real skill directories under `.agent/skills/` are loaded even when
  listed in `.gitignore`.

## Instructions for the main thread

- Reminders arrive before model invocations as injected system messages. Follow
  [SKILL.md, Context reminders](../SKILL.md#4-context-reminders).
- In auto-research mode: spawn every subagent with fresh context (`invoke_subagent` without
  inheriting conversation history, or `swarm` `add` without `fork`); do not run `/compact`
  (compaction is not hook-blocked on Antigravity); follow [auto-research](autoresearch.md).
