# relay

relay is an evolving tool for personal research, not yet ready for a community release. Its aim is **epistemic durability**: a fresh agent should still understand what we are asking, why we arrived here, and which grounds for our understanding deserve another look.

`RESEARCH.md` is the entry point for the current focus. It explains enough to join the discussion, then connects to experiments, code, counterexamples, human feedback, and emerging questions. Materials can connect laterally, unfold into further detail, and revise the entry point itself. The early two-layer layout is only a starting point. No document kind is required; observations, explanations, and decisions can stay together when their relationship matters.

Human prompts, answers to agent questions, and selections among model-written options have distinct origins. Original wording stays in private local records. Agent annotations separately identify the question, code state, and results being referred to. Scientific judgments remain answerable to evidence; model summaries cannot replace a person's actual expression of goals, priorities, or authorization.

Research materials live on a separate `relay-notes` branch and worktree by default. They hold revisable working understanding. Moving conclusions into formal project documentation takes an explicit decision; the code repository need not be reorganized around relay's conventions.

Local use requires Git and Python 3.10+:

```sh
python3 scripts/install_skill.py --repo /absolute/path/research-project
python3 -m research_relay notes --repo /absolute/path/research-project status
```

Open a fresh session manually and invoke `$research-relay`. Read and align before creating or updating notes. The installer creates a project-local skill symlink and adds missing root `.gitignore` rules for `/.agents/skills/research-relay`, `/.codex/hooks.json`, and `/artifacts/private/`, preserving existing content. Rerunning it updates existing installations without duplicating rules. Already tracked local files are reported and remain tracked; uninstall removes the skill link and retains the ignore rules. The installer does not change global settings or trust hooks. Subsequent sessions remain a human choice.

- [Skill](skills/research-relay/SKILL.md): resume research, respond to human intervention, and close out.
- [Material convention](skills/research-relay/references/convention.md): preserve understanding, provenance, and useful connections.
- [Sidecar](skills/research-relay/references/sidecar.md): protected activation, context reminders, and their limits.

`notes init/status/links/commit` operates on the separate notes worktree. `links --path <file>` shows outgoing links and backlinks on demand, without storing a graph or judging research claims. Original human inputs stay in Git-ignored `artifacts/private/`; committing notes does not back them up.

To enable protection inside the actual Desktop main chat, run:

```sh
python3 -m research_relay start --repo /absolute/path/research-project
python3 -m research_relay doctor --repo /absolute/path/research-project
```

`start` discovers the current thread and Desktop host, resolves the explicit compaction ceiling, and checks that all six project Relay hooks are enabled and trusted. If native delivery has not been acknowledged in this turn, it arms a token check and returns `awaiting-native-delivery` (exit 2). Acknowledge only the token received through native hook context, then rerun `start`. Success reports `mode: protected`, `live: true`, and `protected: true`. Missing hook configuration can be prepared with `hooks prepare`; trust remains a native app setting.

While protected research is active, the main agent coordinates human intent and feedback, frames bounded work, reviews results, and maintains notes and lifecycle. Subagents perform substantive research, experiments, coding, and verification, one at a time by default; the main spends most execution time in event-based waits and starts no other substantive investigation or worker implementation while they run. Every new subagent must use `spawn_agent` with `fork_turns: "none"`, and every independent task gets a new agent with a self-contained handoff. Successful protected `start`/`status` results expose these instructions in `delegation_policy`, marked instruction-only with unverified compliance. The sidecar never creates agents or verifies delegation behavior; `protected: true` verifies main-thread protection only. Diagnostic output, results outside protected research, and closeout omit the active policy.

The shared PreCompact handler also rejects worker compaction when Codex delivers the event under the opted-in parent's session ID in the same Git repository. Worker events do not consume main-thread reminders or stop its watcher. This handler behavior has regression coverage; native worker hook delivery and worker context usage are not yet verified by `protected: true`.

`doctor` distinguishes blocked, ready, protected, and closeout. Configuration changes are checked against the current project's protection requirements; unrelated agent settings, other projects' trust records, and unrelated hooks do not end research. Changes to Relay's own definitions, trust, or effective compaction ceiling, binding errors, and loss of guard/delivery evidence revoke protection. Usage silence retains the last observation, and pending reminders wait for the next hook boundary without a deadline. Stop/Interrupt/SessionEnd end monitoring; the thread's compaction guard remains. Each new main turn needs its own activation and delivery check. `probe-start` stays diagnostic and never reports protection. Run `make check` for development checks.
