"""The optional mode on top of the rhizome: compaction blocked, fresh-context subagents, closeout at the final reminder."""

SESSION = (
    "This repository is in auto-research mode. Compaction is blocked by hook, every subagent must start "
    "with fresh context (never one that inherits this conversation), and the final context reminder asks "
    "you to close out instead of continuing. The main thread aligns with the human, delegates bounded "
    "work, reviews returned evidence and maintains the notes; it does not carry out substantive research "
    "itself. Follow references/autoresearch.md in the skill."
)

CLOSEOUT_BEFORE = (
    "Begin closeout. Open no new directions and start no new workers. Finish the current operation at a "
    "safe boundary, collect completed or partial worker results, and stop the remaining workers. Verify "
    "that they stopped writing and report anything you cannot confirm. Then bring the notes up to "
    "date, including those results."
)

CLOSEOUT_AFTER = (
    "Report saved notes or retained drafts and unfinished work, then end the turn. Do not compact; the "
    "human opens the next fresh session."
)

COMPACTED = (
    "Compaction is not allowed in auto-research mode and should have been blocked. Tell the human it "
    "happened, then close out instead of continuing sustained work."
)

PRECOMPACT = (
    "research-relay blocks compaction in auto-research mode. Close out instead: stop workers, bring "
    "the notes up to date, end the turn; the human opens a fresh session that reads the notes. "
    "relay on --mode rhizome allows compaction."
)

FRESH_CONTEXT_DENIED = "research-relay: every subagent must start with fresh context. {fix}"


def closeout(core):
    """Workers are collected before the notes are completed, so the mode wraps the core's text."""
    return "\n\n".join((CLOSEOUT_BEFORE, core, CLOSEOUT_AFTER))
