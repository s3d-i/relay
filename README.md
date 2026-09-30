# relay

relay keeps a long research session going without context compaction. It is a small Python
tool (3.10+, stdlib only) that hooks into Claude Code or Codex Desktop and keeps research
notes on a separate Git branch. It is a personal tool, not a release.

It does five things:

1. **Bans compaction.** A PreCompact hook blocks compaction in the main thread and in its
   subagents.
2. **One main thread.** The main thread waits for your instructions. Subagents do the real work.
3. **Handoff before the wall.** When context usage crosses a threshold, a hook tells the main
   agent to close out: write notes, stop workers, end the turn. It does not compact.
4. **Fresh-context subagents, enforced.** A PreToolUse hook denies spawning a subagent that
   inherits the parent conversation.
5. **A `<user>/relay-notes` branch.** A separate worktree and a branch named after the Git
   user hold `RESEARCH.md` (the entry
   point), linked materials, and Git-ignored private human inputs. A fresh session reads it
   and continues.

## How it works

`relay on` writes a policy for the repository to `<git-common-dir>/research-relay/policy.json`.
Every hook call reads it. If the policy is absent or `active: false`, the hook returns `{}` and
the agent behaves as usual. Per-session state (last usage, closeout emitted) sits next to it.

| Event | What relay does | Enforced? |
|---|---|---|
| PreCompact | Blocks compaction, manual or automatic. Subagent events carry the parent session id and are blocked the same way. Fails closed: an internal error still blocks. | Hook |
| SessionStart | On startup, resume and clear: injects a short note that relay is active, that `RESEARCH.md` on `relay-notes` is the entry point, and the delegation policy. On `compact`: says compaction should not have happened. | Injection by hook; the policy text is instruction-only |
| UserPromptSubmit | First prompt of a session: the human-feedback provenance guidance. Later prompts: nothing. | Instruction-only |
| PreToolUse, matcher `Agent` | Denies a spawn that would inherit the conversation (Claude Code: `subagent_type: "fork"`; Codex: `fork_turns` other than `"none"`). Everything else is allowed. | Hook |
| PostToolUse | Reads the tail of the transcript (last 256 KiB) to estimate context usage. Once per session, when usage reaches the threshold, injects the closeout reminder. | Delivery by hook; acting on it is instruction-only |

The closeout reminder fires at `warn_fraction` of the context window (default 0.6). Codex
reports the window in its transcript; Claude Code does not, so the policy holds it (default
200000, `--window N`, which also overrides a transcript value). With `--compact-limit N` the
reminder fires no later than 0.8 times the lower of window and limit, so closeout has room
before the app would try to compact.

relay does not create agents, check handoff quality, or verify that the main thread waits.
That discipline lives in the skill text and in the SessionStart note.

## Install and run

Clone relay anywhere. Commands run as `python3 <relay-checkout>/skills/research-relay/scripts/relay.py ...`
or, from the checkout, `python3 -m research_relay ...`. Below, `relay` stands for either.

```sh
relay install --repo /path/to/project --agent claude   # or --agent codex
relay on      --repo /path/to/project
relay status  --repo /path/to/project
relay off     --repo /path/to/project
```

`install` symlinks the skill into the project, adds `.gitignore` rules for the symlink, the
hooks file and `/artifacts/private/`, and writes or merges the hooks file. It never removes
hooks it did not write. `--print` only prints the hooks JSON. `--uninstall` removes the link only;
the hooks file, ignore rules, notes and policy stay. `on` takes `--agent`, `--window N`, `--warn-fraction F`,
`--compact-limit N`. `status` prints the policy, whether the hooks file is present and
matches, last usage and closeout state per session, and the notes worktree; exit 0 when
active, 2 when not.

The runtime does not verify the host. Correctness rests on the pinned versions below and on
you having trusted the hooks once. If you upgrade either app, re-check the facts in the
reference docs.

### Claude Code, pinned 2.1.285

- Skill link: `<project>/.claude/skills/research-relay`. Invoke with `/research-relay`.
- Hooks: merged into `<project>/.claude/settings.local.json`; other keys are kept. No trust prompt.
- Command: `python3 "$CLAUDE_PROJECT_DIR/.claude/skills/research-relay/scripts/relay.py" hook --agent claude`.
  No absolute paths, so the file works on both machines.
- `install` also sets `"autoCompactEnabled": false` there. The PreCompact block still catches `/compact`.
- Details: [references/claude-code.md](skills/research-relay/references/claude-code.md).

### Codex Desktop, pinned ChatGPT.app 26.924.22138 (bundled codex-cli 0.158.0-alpha.2.1)

- Skill link: `<project>/.agents/skills/research-relay`. Invoke with `$research-relay`.
- Hooks: `<project>/.codex/hooks.json`. Run `install` on the machine that runs Codex; the
  command holds absolute paths because Codex sets no project env var.
- Trust the hooks once in the app through `/hooks`. relay does not check trust.
- Details: [references/codex.md](skills/research-relay/references/codex.md).

Then open a fresh chat in the project and invoke the skill ([SKILL.md](skills/research-relay/SKILL.md)):
it reads the notes, aligns with you, checks `relay status`, and delegates.

## Notes workflow

```sh
relay notes init   --repo /path/to/project                 # [--from <ref> | --fresh]
relay notes status --repo /path/to/project
relay notes links  --repo /path/to/project --path RESEARCH.md
relay notes commit --repo /path/to/project --path RESEARCH.md --path artifacts/x.md -m "..."
```

`init` creates the branch `<user>/relay-notes`, where `<user>` is `git config user.name` made
ref-safe (bare `relay-notes` when no name is set). If other notes branches exist, local or
remote-tracking, named `relay-notes` or `*/relay-notes`, it stops and lists them: you decide
between `--from <ref>`, which starts your branch at that commit, and `--fresh`, which starts
from an empty tree. With no candidates it starts empty. It then adds a worktree at
`<git-common-dir>/research-relay/notes`, appends `/artifacts/private/` to `info/exclude`, and
writes a template `RESEARCH.md` only if none exists. `status` shows the worktree, uncommitted
changes, `private_inputs_ignored` and `tracked_private_artifacts`. `links` lists one file's
outgoing links and backlinks. `commit` commits explicit paths only, rejects `artifacts/private/`,
refuses when unrelated files are staged, and never pushes.

Original human wording (prompts, answers, option selections) stays in
`artifacts/private/human-inputs/<session-id>.md` in the notes worktree, which Git ignores.
Shareable notes carry the decision, the agent's interpretation and a citation. The aim is
epistemic durability: a fresh agent should understand what we are asking, why we got here,
and which grounds deserve another look. Conventions: [convention.md](skills/research-relay/references/convention.md).

## Limits

- Enforced by hooks: the compaction block, the fresh-context deny, delivery of the closeout
  reminder. Instruction-only: delegation discipline (main thread waits, one worker at a time,
  self-contained handoffs), provenance rules, and acting on the reminder.
- Usage is read at hook boundaries. The reminder arrives at the first PostToolUse after the
  threshold, not mid-thought. A long tool-free stretch gets no reminder.
- Claude Code: whether PostToolUse fires for tool calls inside a subagent is undocumented. If
  it does, the transcript is the parent's, so the estimate is still the main thread's.
  Subagent context is not monitored on either agent.
- Codex: the `Agent` tool_input fields (`fork_turns`) are observed, not documented.
- A hook that is not loaded or not trusted is silent. `relay status` checks the file, not the app.
- Notes are committed to your notes branch, never pushed. Private inputs are not in Git; back them up yourself.

Development: `python3 -m unittest discover -s tests` and `python3 scripts/check_skill.py`.
