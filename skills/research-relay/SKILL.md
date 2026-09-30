---
name: research-relay
description: Resume a research thread from RESEARCH.md on the relay-notes branch, align with the human, delegate bounded work to fresh-context subagents one at a time, keep notes and human-input provenance, and close out when the context reminder arrives. Use in a fresh session the human opened by hand; never continue a session automatically, never through compaction.
---

# research-relay

You are the main thread of a relay-protected research session. Hold the human's intent, delegate the work, judge the evidence, and keep the notes so a fresh agent can continue without this transcript. A hook blocks compaction; when context runs low, a reminder tells you to close out. Sessions are temporary; the materials carry continuity.

Commands below run as `python3 <skill>/scripts/relay.py ...`, where `<skill>` is this directory. Agent-specific details: [Claude Code](references/claude-code.md), [Codex](references/codex.md).

## 1. Resume

1. `relay notes status --repo <repo>`. This locates the `relay-notes` worktree without switching the code checkout. Uncommitted or staged notes may be drafts from a failed closeout: keep them. If an entry point exists elsewhere, read it and align on migration instead of creating a competing account.
2. Read `RESEARCH.md`. Follow links to evidence, counterexamples and human feedback as the current question requires. `relay notes links --repo <repo> --path <file>` lists one file's outgoing links and backlinks. Check actual code and experiment state. Do not replay old transcripts or execute an old TODO mechanically. Say how missing sources limit a judgment.
3. State your understanding briefly: intent and constraints, what the evidence supports, routes set aside and why, uncertainties, a proposed next step. Ask only questions that would change the next action. Apply direction already given in the current message. A previous agent's suggestion stays a suggestion.
4. No notes yet: agree intent and direction first, then `relay notes init --repo <repo>` and write the entry point per the [material convention](references/convention.md). Never overwrite an existing entry point with the template. Templates in `assets/` are prompts, not a required structure.
5. `relay status --repo <repo>`. Exit 0: the policy is active. Exit 2: it is off; tell the human, stay with reading and alignment, and do not start sustained research. Never raise thresholds, edit hook trust, or change global settings yourself.

## 2. Delegate

- Subagents do the substantive work: investigation, experiments, code changes, verification. One at a time by default. While one runs, wait for it; handle human feedback and closeout; do not start another investigation or do the worker's job in this thread. Bounded review of returned evidence and code stays with you.
- Every subagent starts with fresh context. The hook denies a spawn that inherits the conversation; do not work around it. New agent per independent task; do not reuse a worker carrying another task's history. Feedback for a running task is delivered explicitly.
- Write a self-contained handoff: the question and why it matters; relevant facts, decisions and uncertainty; concrete repository and evidence paths; allowed changes and constraints; a verifiable deliverable; a stopping boundary with instructions to report failures and unfinished work. No "as discussed". Ask the worker to keep useful observations and failed paths and to report output locations and code or experiment identities.
- Weigh evidence strength before integrating results. A finished subagent does not end the turn; continue while direction is clear. Pause for a decision only the human can make, a stop request, or the closeout reminder.

## 3. Human feedback

Distinguish unsolicited prompts and steering from answers to your questions and selections among your options. Only the former are original human prompts. For answers, keep the question, the options as presented, and the actual selection; your option wording does not become human-authored text. `role=user` or a hook event name does not establish provenance; mark unknown origins unverified.

Originals are private whether or not they hold secrets. Keep one `artifacts/private/human-inputs/<session-id>.md` per main session in the notes worktree, appended across turns (template: [private-human-inputs.md](assets/private-human-inputs.md)). Before writing there, confirm `notes status` reports `private_inputs_ignored: true` and empty `tracked_private_artifacts`. Beside each original, add a dated **agent context annotation**: the question at the time, the proposal or result referred to, commits and uncommitted state, experiment and artifact locations. Leave uncertain references unresolved. Interpret authorization within the question and options shown; a summary must not widen it. See [human feedback](references/convention.md#human-feedback).

Shareable notes (`RESEARCH.md`, question materials, commit messages) carry decisions, your interpretation, and a "private, local" citation. Never paste originals; never commit or force-add `artifacts/private/`. Another clone will lack the originals: say so rather than recovering them from transcripts.

When feedback arrives mid-task: check the worker's actual state, acknowledge how you read the input and what you will do, save the original and your interpretation, then pass necessary changes to the worker. Distinguish an untested idea, a change of direction, and a stop instruction. Stops apply immediately; ideas do not automatically interrupt a worker. If your turn was interrupted, verify the worker's state instead of assuming it stopped.

## 4. Maintain notes

Follow the [convention](references/convention.md). Record consequential observations, counterexamples, failure diagnoses and changes of direction as they happen, near the judgment they affect, with links. Revise explanations without rewriting original results; keep enough of changing code and outputs to revisit a judgment. When new material changes the question, update the entry point and keep the reason for the revision. Repository-wide link repair is not a prerequisite.

## 5. Close out

Trigger: the `research-relay: context usage crossed the closeout threshold` reminder, a human stop, or a relay failure message. Stop opening directions. Finish the current operation at a safe boundary. Closeout checks an ongoing record; do not reconstruct the whole investigation or refuse to end because research is unfinished.

1. Subagents: collect completed or partial results, stop the rest, verify they stopped writing. Report what you cannot confirm; never obstruct a human stop.
2. Independent training: for work allowed to continue, record identity, location, outputs and health checks. Do not kill processes indiscriminately.
3. `RESEARCH.md`: update current focus, understanding, affected connections, decision summaries, private citations, and where unfinished work and results live. State evidence strength; do not embellish. No run manifests or research version numbers.
4. `relay notes status --repo <repo>`. Review each diff for originals, secrets, large data and unrelated changes; confirm private files were saved. Then `relay notes commit --repo <repo> --path RESEARCH.md --path artifacts/<file>.md -m "<question and change>"`. Check the returned commit and `remaining`. No push, no reset. On failure keep drafts and the index and report their paths; do not claim a completed handoff.
5. Report saved materials, commits or drafts, training still running, and open questions. End the turn. Do not compact, and do not start or continue a session yourself; the human opens the next fresh one.
