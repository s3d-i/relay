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

Open a fresh session manually and invoke `$research-relay`. Read and align before creating or updating notes. The installer creates a project-local skill symlink; it does not change global settings or trust hooks. Subsequent sessions remain a human choice.

- [Skill](skills/research-relay/SKILL.md): resume research, respond to human intervention, and close out.
- [Material convention](skills/research-relay/references/convention.md): preserve understanding, provenance, and useful connections.
- [Sidecar](skills/research-relay/references/sidecar.md): experimental context reminders and their current limits.

`notes init/status/links/commit` operates on the separate notes worktree. `links --path <file>` shows outgoing links and backlinks on demand, without storing a graph or judging research claims. Original human inputs stay in Git-ignored `artifacts/private/`; committing notes does not back them up.

Automatic protection is unfinished: `start` and `doctor` return exit code `2` and `protected: false`. The material workflow can be used independently; `probe-start` is only for integration diagnostics. Run `make check` for development checks. Passing tests does not establish protection in the real app.
