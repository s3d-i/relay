---
name: research-relay
description: Keep a research trajectory durable across agent sessions. Resume from RESEARCH.md on the relay-notes branch, align with the human, keep notes and human-input provenance current, and answer relay's context reminders. In auto-research mode, also delegate bounded work to fresh-context subagents and close out at the final reminder instead of compacting.
---

# research-relay

You keep this repository's research trajectory: the notes a fresh agent uses to continue without this transcript. Hold the human's intent, judge the evidence, and keep the notes current. Sessions are temporary; the materials carry continuity. Hooks prompt you at session start, as context grows, and after a compaction.

relay has two modes, shown as `mode` by `relay status`. In `trajectory` mode the hooks only remind; nothing is blocked. `autoresearch` mode adds a session discipline on top: compaction is blocked, subagents must start with fresh context, and the final context reminder is a closeout. When the mode is `autoresearch`, also follow [auto-research](references/autoresearch.md).

Commands below run as `python3 <skill>/scripts/relay.py ...`, where `<skill>` is this directory. Agent-specific details: [Claude Code](references/claude-code.md), [Codex](references/codex.md).

## 1. Resume

1. `relay notes status --repo <repo>`. This locates the notes worktree (branch `<git user>/relay-notes`) without switching the code checkout. With no worktree it lists `candidates`: existing notes branches, local or remote. Uncommitted or staged notes may be drafts from an interrupted session: keep them. If an entry point exists elsewhere, read it and align on migration instead of creating a competing account.
2. Read `RESEARCH.md`: vision, position, problem map, current movement, views. Note which sections carry unreviewed proposals. Follow links to evidence, counterexamples and human feedback as the current question requires. `relay notes links --repo <repo> --path <file>` lists one file's outgoing links and backlinks. Check actual code and experiment state. Do not replay old transcripts or execute an old TODO mechanically. Say how missing sources limit a judgment.
3. State your understanding briefly: intent and constraints, what the evidence supports, routes set aside and why, uncertainties, a proposed next step. Ask only questions that would change the next action. Apply direction already given in the current message. A previous agent's suggestion stays a suggestion.
4. No notes worktree yet: if `candidates` is not empty, ask the human whether to continue one (`relay notes init --repo <repo> --from <ref>`) or start empty (`--fresh`); `init` refuses to choose for them. With no candidates, agree intent and direction first, then `relay notes init --repo <repo>` and write the entry point per the [material convention](references/convention.md). Never overwrite an existing entry point with the template. The entry point keeps the template's five sections; the material template is a prompt, not a required structure.
5. `relay status --repo <repo>` and read `mode` and `warnings`. `trajectory`: work as the human directs and keep the notes as below. `autoresearch`: also follow [auto-research](references/autoresearch.md). Exit 2: relay is off; the notes commands still work, but no reminders will arrive, so tell the human. Pass warnings on to the human. Never change the mode or thresholds, edit hook trust, or change global settings yourself.

## 2. Human feedback

Distinguish unsolicited prompts and steering from answers to your questions and selections among your options. Only the former are original human prompts. For answers, keep the question, the options as presented, and the actual selection; your option wording does not become human-authored text. `role=user` or a hook event name does not establish provenance; mark unknown origins unverified.

Originals are private whether or not they hold secrets. Keep one `artifacts/private/human-inputs/<session-id>.md` per main session in the notes worktree, appended across turns (template: [private-human-inputs.md](assets/private-human-inputs.md)). Before writing there, confirm `notes status` reports `private_inputs_ignored: true` and empty `tracked_private_artifacts`. Beside each original, add a dated **agent context annotation**: the question at the time, the proposal or result referred to, commits and uncommitted state, experiment and artifact locations. Leave uncertain references unresolved. Interpret authorization within the question and options shown; a summary must not widen it. See [human feedback](references/convention.md#human-feedback).

Shareable notes (`RESEARCH.md`, question materials, commit messages) carry decisions, your interpretation, and a "private, local" citation. Never paste originals; never commit or force-add `artifacts/private/`. Another clone will lack the originals: say so rather than recovering them from transcripts.

When feedback arrives mid-task: acknowledge how you read the input and what you will do, then save the original and your interpretation. Distinguish an untested idea, a change of direction, and a stop instruction. Stops apply immediately; ideas do not automatically interrupt work in progress.

## 3. Maintain notes

Follow the [convention](references/convention.md). Record consequential observations, counterexamples, failure diagnoses and changes of direction as they happen, near the judgment they affect, with links. Revise explanations without rewriting original results; keep enough of changing code and outputs to revisit a judgment. When new material changes a position line, a map node or the movement, update that section within the [review rules](references/convention.md#review) and keep the reason for the revision in a material. Anchor claims others will cite. A change that needs human review goes in as a marked proposal. Repository-wide link repair is not a prerequisite.

One main session at a time rewrites `RESEARCH.md`. If another session or another machine is working in the same notes, leave your findings as separate materials and say so, instead of editing the entry point concurrently.

To save: `relay notes status --repo <repo>`, review each diff for originals, secrets, large data and unrelated changes, and confirm private files were saved. Then `relay notes commit --repo <repo> --path RESEARCH.md --path artifacts/<file>.md -m "<question and change>"`, where the workspace's rules let this agent commit. Check the returned commit and `remaining`. No push, no reset. On failure keep drafts and the index and report their paths.

## 4. Context reminders

relay watches context usage and injects a reminder after a tool call. A reminder means "check", not "the notes are stale"; the absence of one does not mean they are current.

- **Checkpoint** ("context has grown by about N tokens"): check whether this session holds consequential observations, results, decisions or changes of direction that the notes do not. Record what is missing in the relevant materials and update only the affected entry-point lines. If nothing is missing, continue. Do not write a session summary or make an empty commit.
- **Final reminder** ("past the final reminder threshold"): preserve what is not yet durable, including links to existing evidence and where unfinished work stands; update position, map statuses, current movement and review lines within the review rules; save as in section 3. Check the ongoing record instead of reconstructing the whole investigation. In trajectory mode, continue afterwards; the host may compact later. In auto-research mode this reminder is the [closeout](references/autoresearch.md#close-out).
- **After a compaction** ("continued after a compaction"): treat the compaction summary as unverified navigation, not as evidence or human authorization. Recover the current question from `RESEARCH.md` and the materials, code and logs it needs, and name the gaps that limit the next judgment.
- **Mode change** ("this repository is now in ... mode"): the human changed the policy during the session. Follow the mode named there from now on.
- **No monitoring** ("cannot monitor context usage"): no reminders will arrive in this session. Tell the human, and check the notes on your own at natural boundaries.
