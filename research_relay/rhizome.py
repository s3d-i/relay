"""The core layer: the research notes as a rhizome, and what each hook moment asks of them.

The notes have no fixed hierarchy or reading order: RESEARCH.md is a way in, materials connect in
any direction, and a reader composes what the question at hand needs. The texts below prompt an
agent to enter that way and to connect what is new. Texts only; this layer blocks nothing.
"""

import shlex

MODE_NAMES = {"rhizome": "rhizome", "autoresearch": "auto-research"}

SESSION = (
    "research-relay keeps this repository's research notes as a rhizome: materials connected in any "
    "direction, with no fixed hierarchy or reading order. RESEARCH.md is the way in, not a summary to "
    "stop at. Run relay notes status --repo {project} to locate the notes worktree and branch, read RESEARCH.md, then "
    "follow only the connections the current question needs and compose your own reading; the "
    "research-relay skill ($research-relay) says how. If there are no notes yet, follow the skill's "
    "initialization guidance. As you work, connect what is new (observations, results, hypotheses, "
    "decisions, changes of direction) to the materials it supports, contradicts or reopens; context "
    "reminders will prompt a check. Bring each item under Open for the human in RESEARCH.md dated a day "
    "or more ago back to the human as a question that also offers to move it to the undecided bank."
)

LOCATED = (
    "research-relay: this repository's notes are on branch {branch} of {home}, chosen with relay notes "
    "attach. Read, write and commit them only there, through relay notes status and relay notes commit "
    "with --repo {project}; other notes branches or worktrees you may come across are not these notes."
)

UNREACHABLE = (
    "research-relay: this repository's notes are kept in {home}, which is not a repository on this "
    "machine. Tell the human: relay notes attach has to be run again here, or notes detach. Do not start "
    "notes anywhere else."
)

UNREADABLE = (
    "research-relay: this repository's notes pointer cannot be read ({error}). Tell the human; do not "
    "start notes anywhere else."
)

MOVED = (
    "research-relay: this repository's notes moved during this session. Stop writing notes where you "
    "have so far, and re-enter through RESEARCH.md at the new place."
)

OWN = "They are this repository's own notes again: run relay notes status --repo {project}."

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
    "Check for consequential observations, results, hypotheses, decisions or changes of direction that "
    "the notes do not yet hold. Write each where it bears on a judgment and link it to what it supports, "
    "contradicts or reopens; update only the affected entry-point lines, in place. Commit changed "
    "shareable files only after reviewing their diffs and where workspace rules permit. "
    "If nothing consequential is missing, continue without writing a summary or making a commit."
)

FINAL = (
    "research-relay: last observed context usage is {used} of {ceiling} tokens, past the final reminder "
    "threshold. Leave the notes so that a fresh reader can enter and continue: connect consequential "
    "understanding that is not yet durable, including links to existing evidence and to unfinished "
    "work, and update the affected entry-point sections in place. Check the ongoing record; do not "
    "reconstruct the whole investigation or write a session summary. Later context may be compacted."
)

COMPACTED = (
    "research-relay: this session continued after a compaction. Treat the compaction summary as "
    "unverified navigation, not as evidence or as human authorization. Re-enter through RESEARCH.md and "
    "follow the connections the current question needs into materials, code and logs. Name the gaps "
    "that limit the next judgment; do not invent missing originals or rebuild them from transcripts."
)

CHANGED = "research-relay: this repository is now in {mode} mode."

RELAXED = (
    "The auto-research restrictions no longer apply: compaction is allowed, subagents may inherit the "
    "conversation, and the final context reminder asks for a notes update, not a closeout."
)


def session(project):
    return SESSION.format(project=shlex.quote(str(project)))


def located(where, project):
    """Where an attached project's notes live; `where` comes from notes.where or names its error."""
    if where.get("error"):
        return UNREADABLE.format(error=where["error"])
    if not where.get("reachable"):
        return UNREACHABLE.format(home=where["home"])
    return LOCATED.format(branch=where["branch"], home=where["home"], project=shlex.quote(str(project)))


def moved(where, project):
    return MOVED + " " + (located(where, project) if where else OWN.format(project=shlex.quote(str(project))))


def checkpoint(grown):
    return CHECKPOINT.format(grown=grown)


def final(used, ceiling):
    return FINAL.format(used=used, ceiling=ceiling)


def changed(mode, told):
    """The policy moved under an open session; `told` is what the session last heard, if anything."""
    text = CHANGED.format(mode=MODE_NAMES[mode])
    if mode == "rhizome" and told and told.get("mode") == "autoresearch":
        text += " " + RELAXED
    return text
