"""An ordinary notes branch and isolated worktree, with explicit-path commits."""

from pathlib import Path
import re
import subprocess

from .state import RelayError, common_dir, git, lock, runtime_dir


SUFFIX = "relay-notes"
TEMPLATES = Path(__file__).resolve().parent.parent / "skills/research-relay/assets"
PRIVATE_ARTIFACTS = Path("artifacts/private")
PRIVATE_INPUTS = PRIVATE_ARTIFACTS / "human-inputs"
PRIVATE_IGNORE = "/artifacts/private/"


def is_private_artifact(name):
    return tuple(part.casefold() for part in Path(name).parts[:2]) == ("artifacts", "private")


def private_status(path):
    tracked = [name for name in git(path, "ls-files", "-z").split("\0")
               if name and is_private_artifact(name)]
    # check-ignore accepts literal filenames, but rejects git()'s pathspec magic.
    result = subprocess.run(
        ["git", "-C", str(path), "check-ignore", "--quiet", "--no-index", "--",
         str(PRIVATE_INPUTS / "session.md")], capture_output=True, text=True, timeout=30,
    )
    if result.returncode not in (0, 1):
        raise RelayError(result.stderr.strip() or "Cannot check private input ignore rules.")
    return {"private_inputs": str(path / PRIVATE_INPUTS),
            "private_inputs_ignored": result.returncode == 0, "tracked_private_artifacts": tracked}


def protect_private_inputs(repo, path):
    # The independent notes branch does not inherit the code branch's .gitignore.
    # info/exclude is local and shared by the repository's linked worktrees.
    exclude = common_dir(repo) / "info/exclude"
    existing = exclude.read_text() if exclude.exists() else ""
    if PRIVATE_IGNORE not in existing.splitlines():
        exclude.parent.mkdir(parents=True, exist_ok=True)
        with exclude.open("a") as out:
            out.write(("\n" if existing and not existing.endswith("\n") else "") + PRIVATE_IGNORE + "\n")
    status = private_status(path)
    if status["tracked_private_artifacts"]:
        raise RelayError("Private artifacts are already tracked or staged; preserve the local files and remove "
                         "them from the Git index before continuing. Ignore rules do not untrack files.")
    if not status["private_inputs_ignored"]:
        raise RelayError("Notes ignore rules override private input protection; fix artifacts/private/ "
                         "ignores before saving human input. Existing drafts are preserved.")
    return status


def branch_name(repo):
    """<git user.name>/relay-notes, so each author's notes stay apart; bare relay-notes without a usable name."""
    try:
        user = git(repo, "config", "user.name")
    except RelayError:
        user = ""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", user).strip("-.")
    name = f"{slug}/{SUFFIX}" if slug else SUFFIX
    try:
        git(repo, "check-ref-format", "--branch", name)
    except RelayError:
        return SUFFIX
    return name


def is_notes_branch(name):
    return name == SUFFIX or name.endswith("/" + SUFFIX)


def _exists(repo, ref):
    try:
        git(repo, "rev-parse", "--verify", "--quiet", ref)
    except RelayError:
        return False
    return True


def candidates(repo):
    """Local and remote-tracking notes branches other than this author's own local branch."""
    own = "refs/heads/" + branch_name(repo)
    raw = git(repo, "for-each-ref", "--format=%(refname)%00%(refname:short)%00%(objectname:short)%00"
              "%(committerdate:short)%00%(subject)", "refs/heads", "refs/remotes")
    found = []
    for line in raw.splitlines():
        ref, short, commit, date, subject = line.split("\0")
        if ref != own and is_notes_branch(short):
            found.append({"ref": short, "commit": commit, "date": date, "subject": subject})
    return found


def find(repo):
    # -z preserves spaces, newlines and non-ASCII names without Git path quoting.
    raw = git(repo, "worktree", "list", "--porcelain", "-z")
    own, current, found = branch_name(repo), None, {}
    for field in raw.split("\0"):
        if field.startswith("worktree "):
            current = Path(field[9:])
        elif field.startswith("branch refs/heads/") and is_notes_branch(field[18:]):
            found[field[18:]] = current
    if own in found or len(found) < 2:
        return found.get(own) or next(iter(found.values()), None)
    raise RelayError("Several notes worktrees and none on this author's branch; choose one: "
                     + ", ".join(f"{name} at {path}" for name, path in found.items()))


def init(repo, source=None, fresh=False):
    if source and fresh:
        raise RelayError("Pass --from or --fresh, not both.")
    runtime = runtime_dir(repo)
    with lock(runtime / "notes.lock"):
        path = find(repo)
        if path is None:
            path = runtime / "notes"
            if path.exists():
                raise RelayError(f"Unregistered notes directory exists; preserve and inspect it: {path}")
            branch = branch_name(repo)
            if not _exists(repo, "refs/heads/" + branch):
                found = candidates(repo)
                if source:
                    commit = git(repo, "rev-parse", "--verify", source + "^{commit}")
                elif found and not fresh:
                    # Continuing someone's notes or starting a competing account is the human's call.
                    raise RelayError(
                        "Notes branches already exist: "
                        + "; ".join(f"{c['ref']} ({c['commit']}, {c['date']}, {c['subject']})" for c in found)
                        + f". Ask the human, then run notes init --from <ref> to continue one as {branch}, "
                        "or notes init --fresh to start empty.")
                else:
                    tree = git(repo, "mktree", input="")
                    commit = git(repo, "commit-tree", tree, "-m", "Initialize independent research notes")
                # Compare-and-create: do not overwrite a concurrently created branch.
                git(repo, "update-ref", "refs/heads/" + branch, commit, "0" * len(commit))
                if source and _exists(repo, "refs/remotes/" + source):
                    try:  # tracking only reports divergence; relay never pushes
                        git(repo, "branch", "--set-upstream-to=" + source, branch)
                    except RelayError:
                        pass
            git(repo, "worktree", "add", str(path), branch)
        privacy = protect_private_inputs(repo, path)
        entry = path / "RESEARCH.md"
        created = not entry.exists()
        if created:
            # x mode refuses races and never replaces an existing research document.
            with entry.open("x") as out:
                out.write((TEMPLATES / "RESEARCH.md").read_text())
        return {"notes": str(path), "branch": git(path, "branch", "--show-current"), "entry_created": created,
                "status": git(path, "status", "--short"), "committed": False, **privacy}


def inspect(repo):
    path = find(repo)
    if path is None:
        return {"notes": None, "branch": branch_name(repo), "candidates": candidates(repo),
                "hint": "Align research intent before notes init. When candidates exist, the human decides "
                        "between notes init --from <ref> and notes init --fresh."}
    return {"notes": str(path), "branch": git(path, "branch", "--show-current"),
            "status": git(path, "status", "--short"),
            "head": git(path, "rev-parse", "HEAD"),
            "entry_exists": (path / "RESEARCH.md").is_file(), **private_status(path)}


def commit(repo, paths, message):
    path = find(repo)
    if path is None:
        raise RelayError("No notes worktree. Run notes status/init first.")
    if not paths or not message.strip():
        raise RelayError("Pass each reviewed notes file with --path and a commit message.")
    with lock(runtime_dir(repo) / "notes.lock"):
        if not is_notes_branch(git(path, "branch", "--show-current")):
            raise RelayError("Notes checkout changed branch; refusing to commit.")
        protect_private_inputs(repo, path)
        chosen = []
        for name in paths:
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or name.startswith(":") or rel.as_posix() == ".":
                raise RelayError("Notes paths must be explicit relative filenames.")
            if is_private_artifact(rel):
                raise RelayError("Private human input artifacts must never be committed; commit only summaries and references.")
            if not (path / rel).exists():
                git(path, "ls-files", "--error-unmatch", "--", str(rel))  # a deletion is a valid change
            chosen.append(str(rel))
        staged = set(git(path, "diff", "--cached", "--name-only", "-z").split("\0")) - {""}
        if staged - set(chosen):
            raise RelayError("Unrelated staged notes exist; inspect them. Nothing was reset or committed.")
        git(path, "add", "--", *chosen)
        staged_after = git(path, "diff", "--cached", "--name-only")
        if not staged_after:
            return {"status": "unchanged", "notes": str(path)}
        # A failed Git hook/identity check intentionally leaves the draft and index intact.
        git(path, "commit", "-m", message)
        return {"status": "committed", "notes": str(path), "commit": git(path, "rev-parse", "HEAD"),
                "remaining": git(path, "status", "--short"), "pushed": False}
