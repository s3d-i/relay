"""The core layer: what each hook moment asks of the research notes. Texts only; it blocks nothing."""

MODE_NAMES = {"trajectory": "trajectory", "autoresearch": "auto-research"}

SESSION = (
    "research-relay keeps this repository's research trajectory. Run relay notes status to locate the "
    "notes worktree and branch, read its RESEARCH.md, and follow the research-relay skill "
    "($research-relay). If there are no notes yet, follow the skill's initialization guidance. Record "
    "consequential observations, results, decisions and changes of direction in the notes as they "
    "happen; context reminders will prompt a check."
)

UNMONITORED = (
    "research-relay cannot monitor context usage in this session: no context window is set for this "
    "agent (relay on --window N). No context reminders will arrive; tell the human."
)

FEEDBACK = (
    "research-relay human feedback: Distinguish unsolicited human input from answers to agent questions "
    "and option selections; option wording is the agent's, and UserPromptSubmit alone does not establish "
    "provenance. Preserve originals only in Git-ignored artifacts/private/human-inputs/<session-id>.md, "
    "one file per main session, with separately labelled agent context annotations (question, proposal, "
    "code state, results). Interpret a selection within the question and options presented; never expand "
    "authorization through a summary. Shareable notes hold decisions, interpretations and private "
    "citations, not copies. Apply explicit stops immediately; a new idea does not by itself interrupt "
    "active work. Briefly state your understanding and what you will do."
)

CHECKPOINT = (
    "research-relay checkpoint: context has grown by about {grown} tokens since the last reminder. "
    "Check for consequential observations, results, decisions or changes of direction that are not yet "
    "preserved. Record gaps in the relevant materials; update only the affected entry-point lines, "
    "within the review rules. Commit changed shareable files only after reviewing their diffs and where "
    "workspace rules permit. If nothing consequential is missing, continue without writing a summary "
    "or making a commit."
)

FINAL = (
    "research-relay: last observed context usage is {used} of {ceiling} tokens, past the final reminder "
    "threshold. Preserve consequential understanding that is not yet durable, including links to "
    "existing evidence and to unfinished work. Update the affected entry-point sections within the "
    "review rules; keep proposals marked. Check the ongoing record; do not reconstruct the whole "
    "investigation. Later context may be compacted."
)

COMPACTED = (
    "research-relay: this session continued after a compaction. Treat the compaction summary as "
    "unverified navigation, not as evidence or as human authorization. Recover the current question "
    "from RESEARCH.md and the materials, code and logs it needs. Name the gaps that limit the next "
    "judgment; do not invent missing originals or rebuild them from transcripts."
)

CHANGED = "research-relay: this repository is now in {mode} mode."

RELAXED = (
    "The auto-research restrictions no longer apply: compaction is allowed, subagents may inherit the "
    "conversation, and the final context reminder asks for a notes update, not a closeout."
)


def checkpoint(grown):
    return CHECKPOINT.format(grown=grown)


def final(used, ceiling):
    return FINAL.format(used=used, ceiling=ceiling)


def changed(mode, told):
    """The policy moved under an open session; `told` is what the session last heard, if anything."""
    text = CHANGED.format(mode=MODE_NAMES[mode])
    if mode == "trajectory" and told and told.get("mode") == "autoresearch":
        text += " " + RELAXED
    return text
