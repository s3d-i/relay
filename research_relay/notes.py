"""An ordinary notes branch and isolated worktree, with explicit-path commits."""

from pathlib import Path
import subprocess

from .state import RelayError, common_dir, git, lock, runtime_dir


BRANCH = "relay-notes"
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


def find(repo):
    # -z preserves spaces, newlines and non-ASCII names without Git path quoting.
    raw = git(repo, "worktree", "list", "--porcelain", "-z")
    current = None
    for field in raw.split("\0"):
        if field.startswith("worktree "):
            current = Path(field[9:])
        elif field == "branch refs/heads/" + BRANCH:
            return current
    return None


def init(repo):
    runtime = runtime_dir(repo)
    with lock(runtime / "notes.lock"):
        path = find(repo)
        if path is None:
            path = runtime / "notes"
            if path.exists():
                raise RelayError(f"Unregistered notes directory exists; preserve and inspect it: {path}")
            try:
                git(repo, "rev-parse", "--verify", "refs/heads/" + BRANCH)
            except RelayError:
                tree = git(repo, "mktree", input="")
                commit = git(repo, "commit-tree", tree, "-m", "Initialize independent research notes")
                # Compare-and-create: do not overwrite a concurrently created branch.
                git(repo, "update-ref", "refs/heads/" + BRANCH, commit, "0" * len(commit))
            git(repo, "worktree", "add", str(path), BRANCH)
        privacy = protect_private_inputs(repo, path)
        entry = path / "RESEARCH.md"
        created = not entry.exists()
        if created:
            # x mode refuses races and never replaces an existing research document.
            with entry.open("x") as out:
                out.write((TEMPLATES / "RESEARCH.md").read_text())
        return {"notes": str(path), "branch": BRANCH, "entry_created": created,
                "status": git(path, "status", "--short"), "committed": False, **privacy}


def inspect(repo):
    path = find(repo)
    if path is None:
        return {"notes": None, "branch": BRANCH, "hint": "Align research intent before notes init."}
    return {"notes": str(path), "branch": BRANCH,
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
        if git(path, "branch", "--show-current") != BRANCH:
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
