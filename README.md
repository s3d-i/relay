# relay

relay keeps a research trajectory durable across agent sessions. It is a small Python tool
(3.10+, stdlib only) that hooks into Claude Code or Codex Desktop and keeps research notes on
a separate Git branch. It is a personal tool, not a release.

It has a core and an optional mode:

- **Trajectory (the core).** A `<user>/relay-notes` branch in its own worktree holds
  `RESEARCH.md` (the entry point), linked materials, and Git-ignored private human inputs.
  Hooks turn moments in a session (start, first prompt, context growth, compaction) into
  prompts to read or update those notes. Nothing is blocked.
- **Auto-research (a mode on top).** A session discipline for long unattended work: compaction
  is blocked, subagents must start with fresh context, the main thread delegates and waits for
  the human, and the final context reminder is a closeout that ends the session before the
  wall.

## How it works

`relay on` writes a policy for the repository to `<git-common-dir>/research-relay/policy.json`.
Every hook call reads it. If the policy is absent or `active: false`, the hook returns `{}` and
the agent behaves as usual. Per-session state (what the session was told, last usage, reminder
state) sits next to it.

| Event | Trajectory | Auto-research adds | Enforced? |
|---|---|---|---|
| SessionStart | Injects where the notes are and that reminders will come. After `compact`: how to recover from the notes. `compact` and `clear` restart the reminder state. | The mode's rules. After `compact`: it should have been blocked; tell the human and close out. | Injection by hook; acting on it is instruction-only |
| UserPromptSubmit | First prompt of a session: the human-feedback provenance guidance. | | Instruction-only |
| PostToolUse | Reads the tail of the transcript (last 256 KiB) for context usage and injects a checkpoint or the final reminder. | At or past the final threshold the reminder is the closeout: collect and stop workers, preserve the notes, end the turn. | Delivery by hook; acting on it is instruction-only |
| PreToolUse, matcher `Agent` | | Denies a spawn that would inherit the conversation (Claude Code: `subagent_type: "fork"`; Codex: `fork_turns` other than `"none"`). | Hook |
| PreCompact | | Blocks compaction, manual or automatic, also in subagents. Fails closed: an unreadable policy or an internal error still blocks. | Hook |

An event that comes from a subagent (its payload carries `agent_id`) gets the two enforcement
rows and nothing else: reminders and session state belong to the main thread. A session that
was already open when the policy was switched on or changed is told at its next prompt or tool
call.

### Context reminders

The ceiling is the context window, or the agent's own compaction limit when that is lower
(`--compact-limit`). Against it:

```
final reminder = min(0.75 * ceiling, ceiling - 100000)     --warn-fraction, --reserve
checkpoint     = every 0.2 * ceiling tokens of growth      --checkpoint-fraction, 0 turns them off
```

| Ceiling | Final reminder | Checkpoint every |
|---|---|---|
| 1,000,000 | 750,000 | 200,000 |
| 760,000 | 570,000 | 152,000 |
| 600,000 | 450,000 | 120,000 |
| 200,000 | 100,000 | 40,000 |

A checkpoint asks the agent to record what the notes do not yet hold and to continue. The
final reminder fires once; after it a reminder repeats at every further checkpoint step. A
compaction or `/clear` starts the count over, and so does a drop in usage of more than a tenth
of the ceiling below the final threshold (a rewind). A ceiling of 100,000 or less leaves no
room above the default reserve: lower `--reserve`.

The window comes from `--window`, else from the transcript. Codex reports it; Claude Code does
not, so without `--window` a Claude Code session gets no reminders and is told so.

relay does not create agents, check handoff quality, or verify that the notes are current. That
discipline lives in the skill text and in the injected reminders.

## Install and run

Clone relay anywhere. Commands run as `python3 <relay-checkout>/skills/research-relay/scripts/relay.py ...`
or, from the checkout, `python3 -m research_relay ...`. Below, `relay` stands for either.

```sh
relay install --repo /path/to/project --agent claude   # or --agent codex
relay on      --repo /path/to/project --agent claude --window 1000000
relay on      --repo /path/to/project --agent claude --window 1000000 --mode autoresearch
relay status  --repo /path/to/project
relay off     --repo /path/to/project
```

`install` symlinks the skill into the project, adds `.gitignore` rules for the symlink, the
hooks file and `/artifacts/private/`, and writes or merges the hooks file. It never removes
hooks it did not write. `--print` only prints the hooks JSON. `--uninstall` removes the link only;
the hooks file, ignore rules, notes and policy stay.

`on` replaces the policy: omitted options return to their defaults, and a bare `on` means
`--mode trajectory`. It takes `--mode`, `--agent`, `--window N`, `--compact-limit N`,
`--warn-fraction F`, `--reserve N`, `--checkpoint-fraction F`, and prints `previous_mode` when
the mode changed. `--mode autoresearch` needs `--agent`, and `--window` with `--agent claude`:
a mode that blocks compaction must be able to deliver its closeout. A policy file written
before modes existed is read as `autoresearch` until `on` is run again.

`status` prints the policy, the mode, warnings, whether the hooks file is present and matches,
per-session state (last usage with the thresholds it was judged against, `baseline`,
`final_sent`), and the notes worktree; exit 0 when active, 2 when not.

The runtime does not verify the host. Correctness rests on the pinned versions below and on
you having trusted the hooks once. If you upgrade either app, re-check the facts in the
reference docs.

### Claude Code, pinned 2.1.285

- Skill link: `<project>/.claude/skills/research-relay`. Invoke with `/research-relay`.
- Hooks: merged into `<project>/.claude/settings.local.json`; other keys are kept. No trust prompt.
- Command: `python3 "$CLAUDE_PROJECT_DIR/.claude/skills/research-relay/scripts/relay.py" hook --agent claude`.
  No absolute paths, so the file works on both machines.
- Pass `--window`; Claude Code does not report it.
- Upgrading from an older relay: `install` used to write `"autoCompactEnabled": false` into
  that file. relay no longer writes or removes it; `status` warns while it is there. Delete it
  to let Claude Code compact in trajectory mode.
- Details: [references/claude-code.md](skills/research-relay/references/claude-code.md).

### Codex Desktop, pinned ChatGPT.app 26.924.22138 (bundled codex-cli 0.158.0-alpha.2.1)

- Skill link: `<project>/.agents/skills/research-relay`. Invoke with `$research-relay`.
- Hooks: `<project>/.codex/hooks.json`. Run `install` on the machine that runs Codex; the
  command holds absolute paths because Codex sets no project env var.
- Trust the hooks once in the app through `/hooks`. relay does not check trust.
- Pass `--compact-limit` with Codex's `model_auto_compact_token_limit` when that is below the
  window; relay does not read Codex's configuration and warns while the limit is missing.
- Details: [references/codex.md](skills/research-relay/references/codex.md).

Then open a fresh chat in the project and invoke the skill ([SKILL.md](skills/research-relay/SKILL.md)):
it reads the notes, aligns with you, and checks `relay status` for the mode. The auto-research
discipline is in [references/autoresearch.md](skills/research-relay/references/autoresearch.md).

## Notes workflow

```sh
relay notes init   --repo /path/to/project                 # [--from <ref> | --fresh]
relay notes status --repo /path/to/project
relay notes links  --repo /path/to/project --path RESEARCH.md
relay notes commit --repo /path/to/project --path RESEARCH.md --path artifacts/x.md -m "..."
```

The notes commands work whether relay is on or off.

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

- Enforced by hooks, in auto-research mode only: the compaction block and the fresh-context
  deny. Delivered by hooks: the reminders. Instruction-only: keeping the notes current,
  delegation discipline, provenance rules, and acting on a reminder.
- Usage is read at hook boundaries. A reminder arrives at the first PostToolUse after its
  threshold, not mid-thought; a long tool-free stretch gets none. On Codex the reading can lag
  by one model request.
- One policy per repository and machine, written for one agent. `--window` and
  `--compact-limit` apply to every hook call in the repository, so two different agents in one
  repository on one machine are not supported.
- The reminder state assumes the thresholds stay put during a session. After `relay on` changes
  the window mid-session, the final reminder may not fire again until the context is compacted
  or cleared.
- `relay off` is silent: an open session is not told that the rules stopped applying.
- Notes are shared by every session in the repository and relay does not arbitrate between
  writers; the skill asks for one writer of `RESEARCH.md` at a time.
- Not yet captured from live sessions: worker payloads and the post-compaction SessionStart on
  the pinned Codex build, and the post-compaction SessionStart on Claude Code. See the
  reference docs for what each would change.
- A hook that is not loaded, not trusted, times out or receives unparseable input enforces
  nothing, the compaction block included. `relay status` checks the file, not the app.
- Notes are committed to your notes branch, never pushed. Private inputs are not in Git; back them up yourself.

Development: `python3 -m unittest discover -s tests` and `python3 scripts/check_skill.py`.
