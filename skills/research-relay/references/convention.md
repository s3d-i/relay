# Research material convention

Preserve what helps the next reader understand: the current question, the grounds for a judgment, human intervention, and connections worth pursuing. The measure is epistemic durability. Markdown, Git, and links serve that purpose. The reader is a capable fresh agent who can reinterpret materials; this convention does not try to anticipate and mechanically check every document defect.

## Entry point and connections

`RESEARCH.md` is a self-contained account of the current focus. Reading it should make participation possible: what we want to understand, why it matters now, how far the evidence reaches, what human constraints apply, and what remains uncertain. It need not contain all knowledge or serve as the root of every material's meaning or authority.

Follow the current question from the entry point into whatever detail is needed, then onward to another material, code, experimental results, counterexamples, or human feedback. There is no fixed depth, and materials need not link directly from the entry point. Directories locate files without determining which connections can occur. Document kinds, a fixed relation vocabulary, a global taxonomy, and a graph database are unnecessary. A reader can form temporary categories and views for the question at hand.

A connection should explain **why this source is worth reading here**. A difference in experimental conditions might weaken another account's attribution; a failure might change the next experiment's design; a human scope decision might explain why a result was not pursued. State the relationship near the judgment it affects and link to the passage or file that develops the grounds. Link labels and surrounding prose carry the explanation together. A link's presence does not establish that its evidence has been checked.

Connect related materials directly when useful, without adding edges just to fill out a graph or requiring every edge to be reciprocated. A counterexample may first appear in a material the entry point does not mention. Look for other materials that cite the current judgment, then revise the judgment and affected entry point when they conflict. `notes links --path <file>` can reveal explicit outgoing links and backlinks. It offers reading leads, not inferred semantic relationships, anchor verification, or proof of completeness. Direct reading and search remain useful. Follow cycles only as far as the current judgment requires.

The query currently extracts ordinary single-line inline/reference Markdown links from the notes worktree. It skips private and ignored sources and does not parse every Markdown extension. The main agent can read necessary private originals directly through their source citations. An omitted edge does not establish that no relationship exists. Reading may also uncover a connection not yet written down: when it changes understanding or opens a worthwhile question, explain its basis and preserve the connection without first inventing a relation type.

Rewrite the entry point as the focus changes. Retain important earlier explanations and the reasons they were superseded in relevant materials. New materials may require changing the question or abandoning a route. Avoid accumulating session summaries or removing disagreement to keep the entry point tidy.

## Materials and evidence

A material may combine experimental observations, failure explanations, human decisions, and possible next steps. Keep their sources and degrees of confidence distinguishable while preserving the relationships that explain the inquiry. `artifacts/` is a convenient initial location; nested directories and existing locations are also usable. Files develop around worthwhile questions. One experiment may have several materials, and one material may span sessions. Template headings are writing prompts.

Make it possible to return to the grounds. As the question requires, identify experiments or datasets, code commits, execution conditions, original results, and specific logs or figures. HEAD alone does not identify uncommitted code: retain the relevant diff or snapshot and explain how it relates to the observation. Reference external code and large results where they live instead of moving or copying them to satisfy a layout.

Resolve relative links from the file containing them. For code in another worktree or local results, identify the repository/machine, a usable path, and the relevant commit or experiment. Anchors can locate passages; check affected citations when moving files or rewriting sections. When a source needed for the current question is unavailable, explain which judgment that limits. Repository-wide link repair is not a prerequisite for research.

Distinguish observations, interpretations, and decisions, as well as absent evidence, contrary evidence, and confirmation. Mark sources that have not been checked. Revise judgments when their applicable code, data, or conditions change. Original results stay unchanged when explanations change; preserve the grounds and date of important analytical revisions. When deferring a route, explain why and what new evidence would make it worth revisiting.

## Human feedback

The human trajectory helps explain why research came this way. Evidence can overturn a scientific judgment. Goals, priorities, and authorization must respect the person's actual expression, which a more fluent agent summary cannot replace.

Preserve distinctions of provenance. These describe authorship and response, not document kinds:

| Source | Private record | Attribution |
| --- | --- | --- |
| Unsolicited human input / steering | Original wording of goals, additions, corrections, or stop requests | Original human prompt |
| Free-text answer to an agent question | The question and its source, plus the person's original answer | An answer to that question, not reclassified as an unsolicited prompt |
| Selection among agent options | The original question, options as presented, and actual selection; additional human text recorded separately | The agent wrote the options; the human selected. Interpret authorization within that content without expanding it or rewriting the proposal as human-authored |
| Unverified source | Known content and missing information | Do not infer provenance from tone, `role=user`, or a hook event name |

By default, reuse `artifacts/private/human-inputs/<main-session-id>.md` for a main session, appending across turns and questions with stable anchors. Preserve meaningful inputs and necessary context rather than dumping the entire conversation. See the [private input template](../assets/private-human-inputs.md). Original wording, agent interpretations, and human decisions must remain distinguishable. Preserve the original language of human input; any translation belongs in a separately labelled agent annotation.

Making an input understandable outside its session takes more than copying a sentence. For references such as "this proposal" or "the earlier result," add a separate **agent context annotation**: what was being discussed, where the referenced proposal or question is, how to find the relevant code state, experiment, and local artifacts, and which correspondences are verified or still inferred. Preserve the choices available at the time of a selection; a later revision of the proposal cannot substitute for them. Retain a recoverable diff or snapshot for uncommitted states and results that may be overwritten. A mutable path alone may not identify what was meant then.

Date annotations and identify their basis. Keep unresolved references uncertain, asking for clarification when they affect action. If a later reader finds that an agent misunderstood, add the correction and identify affected judgments while retaining original wording and important earlier interpretations for inspection. Enrich context without silently rewriting what the person said.

Original inputs, questions, and options stay in Git-ignored private storage, even when they contain no secrets. Before writing, confirm `private_inputs_ignored: true` and an empty `tracked_private_artifacts`. `notes init` appends `/artifacts/private/` to the Git common directory's `info/exclude`, covering the separate notes worktree. `notes commit` rejects private paths and private files forced into the index. For already tracked originals, preserve the local files before removing them from the index; the tool does not delete files or rewrite history automatically.

Shareable materials contain only the agent's necessary account of decisions, constraints, interpretations, and effects, without copying original wording or selected options. Label source citations "private, local," resolve paths from the citing file, and link to anchors. If another clone lacks the original, state that it is unavailable and which interpretations cannot be checked. Keep a decision summary that stands on its own; do not invent original wording or automatically recover it from old transcripts. Annotations in the private record may link back to the questions and evidence they affect.

Interpret source and action separately: an unsolicited input, free-text answer, or option selection can express a suspicion, a decision, or a stop request. An untested idea is neither a confirmed conclusion nor an automatic replacement for the current goal. Apply decisions already clear in the current input. Align when a conflict with an older constraint leaves the scope uncertain.

## Working understanding and project commitments

Maintain materials on a separate `relay-notes` branch/worktree by default. This preserves room for provisional, revisable explanations without assigning them lower value. An account does not automatically become a mainline project commitment because it is tidy, passes checks, or was committed by an agent. Select conclusions explicitly before incorporating them into formal documentation, preserving their scope and grounds.

Keep the code checkout's existing structure. Read existing materials where they are, and migrate only within an agreed scope. Notes tools locate materials, protect private files from commits, and commit explicit paths. They do not determine document kinds, link topology, or scientific value.

## Continuation and closeout

Preserve consequential observations and turns in understanding as they happen. Closeout checks that record instead of reconstructing the whole investigation. State the next question worth checking, concrete code/log locations, and unresolved counterexamples. A previous agent's suggestion remains available for reassessment rather than becoming an instruction by default.

For independent training, record task identity, machine/service, directory, outputs, check methods, and whether it may continue. Check a PID together with start time or other identifying details. If subagents were used, preserve results or partial results and verify whether they have stopped. Research understanding should not depend on processes from the previous session staying alive.

Review the files and connections involved in the current work, confirm that private inputs were saved locally, and commit only reviewed shareable files with `notes commit --path ...`. Handoff does not require attaching every material to the entry point, standardizing formats, or cleaning the whole repository. On failure, retain drafts and the index, report their locations, and make them discoverable through status next time. Do not push by default or reset drafts.

Git commits do not back up ignored private files; preserve necessary originals separately before cleaning up a worktree. A handoff should distinguish shareable notes, sources available only locally, work still running, and unfinished judgments.

## Reading with fresh context

Without reading the old transcript, start from `RESEARCH.md` and the connections needed for this question. The reader should be able to explain what we are asking, why we arrived here, how strongly the evidence supports a judgment, what human intervention changed, what remains open to challenge, and why the next step is worthwhile. If necessary originals are missing, the reader should also be able to explain which understanding cannot be recovered.

When that is not possible, supply the missing explanation, source, or connection, then align with the human. File counts, fixed depth, a complete taxonomy, or lint cleanliness cannot establish that understanding.
