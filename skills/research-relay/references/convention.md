# Research material convention

Preserve what helps the next reader understand: the current question, the grounds for a judgment, human intervention, and connections worth pursuing. The measure is epistemic durability. Markdown, Git, and links serve that purpose. The reader is a capable fresh agent who can reinterpret materials; this convention does not try to anticipate and mechanically check every document defect.

## Entry point

`RESEARCH.md` is where a human or a fresh agent recovers the research status and chooses what to read next. It holds five sections and nothing else. Materials behind it keep their free form; only the entry point has a fixed shape.

| Section | What it answers | What it holds |
| --- | --- | --- |
| Vision | What is this work for? | The experiences or capabilities we want to exist, in the human's terms, with the standing constraints. An open problem has a direction, not a finish line, so this is a vision and not a goal. |
| Position | How far are we toward the vision? | One line per capability the vision asks for: what is implemented and verified today, the kind of evidence, and a link. Work that was tried but not verified is not position. "Nothing verified" and a verified failure are valid lines. |
| Problem map | What must be understood or solved? | The abstract decomposition, independent of any implementation. One line per node: a stable id, a one-sentence statement, the nodes it needs, a status, and a link to the best current understanding. |
| Current movement | What is being pushed now? | The nodes in focus, the question asked of each, why now, what result would redirect the work, and any work still running. |
| Views | How else can the materials be read? | Links to view files, one line each. |

Position and the problem map differ in kind. Position is concrete and measured against the vision: it changes only when something is built and checked. The map is abstract: it would read the same if the current code were thrown away. A node can be settled in understanding while the position line it serves is still empty, and the reverse.

The map is a dependency graph. `needs` means a node cannot be settled or evaluated before the node it names. Keep the edges acyclic: when two nodes need each other, either they are one node or their coupling is a node of its own. Statuses are `open` (no supported answer), `held` (a working answer is in use and revisable) and `parked` (set aside; the link says why and what would reopen it). Keep the map to about a dozen nodes. A node that needs its own decomposition gets a sub-map in the material it links to.

### What stays in the entry point

The entry point holds what a reader needs to choose where to go: claims in one line, statuses, ids and links. Grounds live behind the links: numbers, run and checkpoint identities, narratives, variants and their tradeoffs, history, and anything about human wording. Two tests help. If a line needs evidence to be believed, the entry point states the claim and links the grounds. If removing a sentence would not change where a reader goes next, it belongs in a material.

Rewrite sections in place as understanding changes. The entry point keeps no change log and no session summaries: Git history of `RESEARCH.md` records what changed, and a material records why an earlier account was superseded. Aim for a file that reads in a few minutes.

### Anchors

Give a stable anchor to each statement other materials will need to cite: a problem-map node, an observation, a hypothesis, a decision. Write it as `<a id="..."></a>` before the statement, since heading text changes and explicit ids do not. Ids are lowercase kebab-case, never reused and never renamed; when a claim is superseded, keep its anchor and say what replaced it. Lead an anchored claim with what it is, how it stands and when that was judged, for example `**Hypothesis, open, 2026-09-29.**`. The words are free; no fixed vocabulary of kinds or statuses applies outside the problem map. Cite claims by anchor, not by file, so a reader lands on the statement and its grounds.

### Views

A view is a thin file that reads the same materials along one axis: formulation versus implementation, training versus inference, a use case, the history of the path. It lists links, each with a line saying why that source matters on this axis. A view owns nothing: a material may appear in many views, views may overlap, and a view made for one question can be deleted when the question passes. Add a view when readers keep assembling the same slice by hand. Views are not a taxonomy, and a material needs no view to be valid.

### Review

Evidence can overturn a scientific judgment; vision, priorities and authorization belong to the human. Each entry-point section therefore has its own rule for what an agent may change alone.

| Section | An agent may change alone | Needs human review |
| --- | --- | --- |
| Vision | Nothing. It may propose. | Every change. |
| Position | Add or downgrade a line, with a link to the evidence. | Upgrading a line that rests on human judgment, such as playability or quality; removing a line. |
| Problem map | Add a node or an edge; change `open` and `held` with grounds; update links. | Removing, merging or parking a node; removing an edge. |
| Current movement | Report progress, results and running work inside the chosen focus. | Changing which nodes are in focus. |
| Views | Everything. | Nothing. |

Every section except Views ends with a review line: the date of the last human review and a "private, local" link to the human's raw comment, or a statement that the section is an agent draft. Review is something the human said about that section in a session, recorded per [human feedback](#human-feedback); silence, a commit and a passing check are not review. A change that needs review and has none is written as a proposal, marked `(proposed)` at the change, and named in the review line. It stays marked until the human responds. Proposals may be committed; they may not be acted on as decisions. List pending proposals in the closeout report.

## Connections

Follow the current question from the entry point into whatever detail is needed, then onward to another material, code, experimental results, counterexamples, or human feedback. There is no fixed depth, and materials need not link directly from the entry point. Directories locate files without determining which connections can occur. Document kinds, a fixed relation vocabulary, a global taxonomy, and a graph database are unnecessary. A reader can form temporary categories and views for the question at hand.

A connection should explain **why this source is worth reading here**. A difference in experimental conditions might weaken another account's attribution; a failure might change the next experiment's design; a human scope decision might explain why a result was not pursued. State the relationship near the judgment it affects and link to the passage or file that develops the grounds. Link labels and surrounding prose carry the explanation together. A link's presence does not establish that its evidence has been checked.

Connect related materials directly when useful, without adding edges just to fill out a graph or requiring every edge to be reciprocated. A counterexample may first appear in a material the entry point does not mention. Look for other materials that cite the current judgment, then revise the judgment and affected entry point when they conflict. `notes links --path <file>` can reveal explicit outgoing links and backlinks. It offers reading leads, not inferred semantic relationships, anchor verification, or proof of completeness. Direct reading and search remain useful. Follow cycles only as far as the current judgment requires.

The query currently extracts ordinary single-line inline/reference Markdown links from the notes worktree. It skips private and ignored sources and does not parse every Markdown extension. The main agent can read necessary private originals directly through their source citations. An omitted edge does not establish that no relationship exists. Reading may also uncover a connection not yet written down: when it changes understanding or opens a worthwhile question, explain its basis and preserve the connection without first inventing a relation type.

Retain important earlier explanations and the reasons they were superseded in relevant materials. New materials may require changing the map or abandoning a route. Do not remove disagreement to keep the entry point tidy.

## Materials and evidence

A material may combine experimental observations, failure explanations, human decisions, and possible next steps. Keep their sources and degrees of confidence distinguishable while preserving the relationships that explain the inquiry. `artifacts/` is a convenient initial location; nested directories and existing locations are also usable. Files develop around worthwhile questions. One experiment may have several materials, and one material may span sessions. Template headings are writing prompts.

Make it possible to return to the grounds. As the question requires, identify experiments or datasets, code commits, execution conditions, original results, and specific logs or figures. HEAD alone does not identify uncommitted code: retain the relevant diff or snapshot and explain how it relates to the observation. Reference external code and large results where they live instead of moving or copying them to satisfy a layout.

Resolve relative links from the file containing them. Notes and code live in different worktrees. Cite committed code and documents as `<commit>:<path>`, which `git show` resolves in any clone, or by a path in a named checkout together with the commit. Checkpoints, receipts and other local results live on one machine: cite them by their absolute path there and name the machine, so the citation points at the artifact itself. A reader on another machine then knows where the evidence is and that it is not at hand. Anchors can locate passages; check affected citations when moving files or rewriting sections. When a source needed for the current question is unavailable, explain which judgment that limits. Repository-wide link repair is not a prerequisite for research.

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

Maintain materials on a separate notes branch and worktree. The branch is `<git user>/relay-notes`, so each author's account stays distinct and another author's branch can be read or continued without being overwritten. When notes branches already exist, locally or on a remote, the human decides whether to continue one or start a new account; an agent does not pick. This preserves room for provisional, revisable explanations without assigning them lower value. An account does not automatically become a mainline project commitment because it is tidy, passes checks, or was committed by an agent. Select conclusions explicitly before incorporating them into formal documentation, preserving their scope and grounds.

Keep the code checkout's existing structure. Read existing materials where they are, and migrate only within an agreed scope. Notes tools locate materials, protect private files from commits, and commit explicit paths. They do not determine document kinds, link topology, or scientific value.

## Continuation and closeout

Preserve consequential observations and turns in understanding as they happen. Closeout checks that record instead of reconstructing the whole investigation. State the next question worth checking, concrete code/log locations, and unresolved counterexamples. A previous agent's suggestion remains available for reassessment rather than becoming an instruction by default.

For independent training, record task identity, machine/service, directory, outputs, check methods, and whether it may continue. Check a PID together with start time or other identifying details. If subagents were used, preserve results or partial results and verify whether they have stopped. Research understanding should not depend on processes from the previous session staying alive.

Review the files and connections involved in the current work, confirm that private inputs were saved locally, and commit only reviewed shareable files with `notes commit --path ...`. Handoff does not require attaching every material to the entry point, standardizing formats, or cleaning the whole repository. On failure, retain drafts and the index, report their locations, and make them discoverable through status next time. Do not push by default or reset drafts.

Git commits do not back up ignored private files; preserve necessary originals separately before cleaning up a worktree. A handoff should distinguish shareable notes, sources available only locally, work still running, and unfinished judgments.

## Reading with fresh context

Without reading the old transcript, start from `RESEARCH.md` and the connections needed for this question. The reader should be able to explain what we are asking, why we arrived here, how strongly the evidence supports a judgment, what human intervention changed, what remains open to challenge, and why the next step is worthwhile. If necessary originals are missing, the reader should also be able to explain which understanding cannot be recovered.

When that is not possible, supply the missing explanation, source, or connection, then align with the human. File counts, fixed depth, a complete taxonomy, or lint cleanliness cannot establish that understanding.
