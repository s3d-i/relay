# Auto-research mode

Applies when `relay status` reports `mode: autoresearch`. Everything in [SKILL.md](../SKILL.md) still holds; this mode adds a session discipline. You are the main thread: hold the human's intent, delegate the work, judge the evidence, keep the notes. Hooks enforce two rules and deliver one reminder:

- Compaction is blocked, manual or automatic, in the main thread and in subagents. Do not run `/compact`; the block message is expected.
- A subagent that would inherit this conversation is denied. Do not work around it.
- The final context reminder arrives as a closeout. Acting on it is up to you.

Use this mode in a fresh session the human opened by hand. Never continue a session automatically, and never through compaction.

## Delegate

- Subagents do the substantive work: investigation, experiments, code changes, verification. One at a time by default. While one runs, wait for it; handle human feedback and closeout; do not start another investigation or do the worker's job in this thread. Bounded review of returned evidence and code stays with you.
- Every subagent starts with fresh context. New agent per independent task; do not reuse a worker carrying another task's history. Feedback for a running task is delivered explicitly.
- Write a self-contained handoff: the question and why it matters; relevant facts, decisions and uncertainty; concrete repository and evidence paths; allowed changes and constraints; a verifiable deliverable; a stopping boundary with instructions to report failures and unfinished work. No "as discussed". Ask the worker to keep useful observations and failed paths and to report output locations and code or experiment identities.
- Weigh evidence strength before integrating results. A finished subagent does not end the turn; continue while direction is clear. Pause for a decision only the human can make, a stop request, or the closeout.
- When human feedback arrives while a worker runs: check the worker's actual state, save the input as in SKILL.md section 2, then pass necessary changes to the worker. Stops apply immediately; ideas do not automatically interrupt a worker. If your turn was interrupted, verify the worker's state instead of assuming it stopped.

## Close out

Trigger: a reminder that starts with `Begin closeout`, a human stop, or a relay failure message. Stop opening directions. Finish the current operation at a safe boundary. Closeout checks an ongoing record; do not reconstruct the whole investigation or refuse to end because research is unfinished.

1. Subagents: collect completed or partial results, stop the rest, verify they stopped writing. Report what you cannot confirm; never obstruct a human stop.
2. Independent training: for work allowed to continue, record identity, location, outputs and health checks. Do not kill processes indiscriminately.
3. `RESEARCH.md`: update position, map statuses and links, current movement, review lines and private citations, and where unfinished work and results live. State evidence strength; do not embellish. No run manifests or research version numbers.
4. Save the notes as in SKILL.md section 3. On failure keep drafts and the index and report their paths; do not claim a completed handoff.
5. Report saved materials, commits or drafts, training still running, proposals awaiting human review, and open questions. End the turn. Do not compact, and do not start or continue a session yourself; the human opens the next fresh one.

If the session goes on after a closeout reminder, the reminder repeats as context grows. If the session continued after a compaction anyway, tell the human, recover from the notes, and close out.
