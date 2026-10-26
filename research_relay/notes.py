"""An ordinary notes branch and isolated worktree, with explicit-path commits.

The notes live in a home repository: the project itself, or the repository and branch its
pointer names (`notes attach`). The worktree, its lock and the private-input exclude belong to
the home; the policy and session state stay with the project.
"""

import contextlib
import os
from pathlib import Path
import re
import shlex
import subprocess

from .policy import now
from .state import RelayError, common_dir, git, lock, read_json, runtime_dir, toplevel, write_json


SUFFIX = "relay-notes"
POINTER = "home.json"
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


def protect_private_inputs(path):
    # The independent notes branch does not inherit the code branch's .gitignore.
    # info/exclude is local and shared by the linked worktrees of the notes' own repository.
    exclude = common_dir(path) / "info/exclude"
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


def candidates(repo, own=None, exact=False):
    """Local and remote-tracking notes branches other than the local `own` (default: this author's).

    exact: only remote-tracking copies of `own`. A home that holds several notebooks keeps
    other notebooks' branches, which are not continuations of this one.
    """
    own = own or branch_name(repo)
    raw = git(repo, "for-each-ref", "--format=%(refname)%00%(refname:short)%00%(objectname:short)%00"
              "%(committerdate:short)%00%(subject)", "refs/heads", "refs/remotes")
    found = []
    for line in raw.splitlines():
        ref, short, commit, date, subject = line.split("\0")
        if ref == "refs/heads/" + own:
            continue
        if exact:
            keep = ref.startswith("refs/remotes/") and short.split("/", 1)[-1] == own
        else:
            keep = is_notes_branch(short)
        if keep:
            found.append({"ref": short, "commit": commit, "date": date, "subject": subject})
    return found


def _accessible(path, common):
    try:
        return path.is_dir() and common_dir(path).samefile(common)
    except (OSError, RelayError):
        return False


def _same(a, b):
    try:
        return Path(a).samefile(b)
    except OSError:
        return False


def _same_repo(a, b):
    try:
        return common_dir(a) == common_dir(b)
    except (RelayError, OSError):
        return False


def worktrees(repo):
    """{branch: path} of this repository's notes worktrees that this environment can reach."""
    # -z preserves spaces, newlines and non-ASCII names without Git path quoting.
    raw = git(repo, "worktree", "list", "--porcelain", "-z")
    current, found = None, {}
    common = common_dir(repo)
    for field in raw.split("\0"):
        if field.startswith("worktree "):
            current = Path(field[9:])
        elif field.startswith("branch refs/heads/") and is_notes_branch(field[18:]):
            if current is not None and _accessible(current, common):
                found[field[18:]] = current
    # A shared Git registration can name another host or mount namespace. The
    # conventional local checkout is usable only when it belongs to this repo.
    local = runtime_dir(repo) / "notes"
    if _accessible(local, common):
        branch = git(local, "branch", "--show-current")
        if is_notes_branch(branch):
            found.setdefault(branch, local)
    return found


def find(repo, branch=None):
    """The notes worktree of `branch` in this repository, or by discovery when no branch is chosen."""
    found = worktrees(repo)
    runtime = runtime_dir(repo)
    if branch is not None:
        local = runtime / "branches" / branch
        if branch not in found and _accessible(local, common_dir(repo)) \
                and git(local, "branch", "--show-current") == branch:
            return local  # registered under a path this environment cannot see
        return found.get(branch)
    own = branch_name(repo)
    if own in found or len(found) < 2:
        return found.get(own) or next(iter(found.values()), None)
    # A home with several notebooks: the conventional checkout holds this repository's own notes.
    for path in found.values():
        if _same(path, runtime / "notes"):
            return path
    raise RelayError("Several notes worktrees and none on this author's branch; choose one: "
                     + ", ".join(f"{name} at {path}" for name, path in found.items()))


def worktree_path(repo, branch):
    """Where init checks out `branch`: research-relay/notes for this author's branch, else branches/<branch>."""
    runtime = runtime_dir(repo)
    local = runtime / "notes"
    taken = any(_same(path, local) for name, path in worktrees(repo).items() if name != branch)
    if branch == branch_name(repo) and not taken:
        return local  # free, or something there (a stray directory, a detached checkout) that init refuses
    # Branch names never nest (git refuses a/relay-notes beside a/relay-notes/b), so neither do these.
    return runtime / "branches" / branch


def main_worktree(repo):
    """The repository's main checkout, so a pointer never names a linked worktree that may be removed."""
    common = common_dir(repo)
    return common.parent if common.name == ".git" else toplevel(repo)


@contextlib.contextmanager
def _notes_lock(repo):
    """The project's lock, then the home's: attach cannot slip between resolving the pointer and using it."""
    project = runtime_dir(repo)
    with lock(project / "notes.lock"):
        home, chosen = resolve(repo)
        runtime = runtime_dir(home)
        if runtime == project:  # one lock file: flock twice from one process would wait on itself
            yield home, chosen
        else:
            with lock(runtime / "notes.lock"):
                yield home, chosen


def pointer(runtime):
    """The project's notes pointer, or None when the project keeps its own notes."""
    path = Path(runtime) / POINTER
    value = read_json(path)
    if value is not None and not (isinstance(value.get("home"), str) and isinstance(value.get("branch"), str)):
        raise RelayError(f"Invalid notes pointer (preserved): {path}")
    return value


def home_path(runtime, value):
    # Relative to the project's git common dir, so the same pointer holds wherever the workspace is mounted.
    return (Path(runtime).parent / value["home"]).resolve()


def where(runtime):
    """The pointer's home and branch for hook texts, without running Git; None without a pointer."""
    value = pointer(runtime)
    if value is None:
        return None
    home = home_path(runtime, value)
    return {"home": str(home), "branch": value["branch"], "reachable": (home / ".git").exists()}


def resolve(repo):
    """(home, branch): where this project's notes live; branch is None when it keeps its own notes."""
    runtime = runtime_dir(repo)
    value = pointer(runtime)
    if value is None:
        return Path(repo), None
    home = home_path(runtime, value)
    try:
        common_dir(home)
    except (RelayError, OSError):
        raise RelayError(f"The notes home {home}, named by {runtime / POINTER}, is not a repository here. "
                         "Run notes attach again on this machine, or notes detach.") from None
    return home, value["branch"]


def locate(repo):
    home, branch = resolve(repo)
    return find(home, branch)


def init(repo, source=None, fresh=False):
    if source and fresh:
        raise RelayError("Pass --from or --fresh, not both.")
    with _notes_lock(repo) as (home, chosen):
        path = find(home, chosen)
        if path is None:
            branch = chosen or branch_name(home)
            path = worktree_path(home, branch)
            if path.exists():
                raise RelayError(f"Unregistered notes directory exists; preserve and inspect it: {path}")
            if not _exists(home, "refs/heads/" + branch):
                found = candidates(home, branch, exact=chosen is not None)
                if source:
                    commit = git(home, "rev-parse", "--verify", source + "^{commit}")
                elif found and not fresh:
                    # Continuing someone's notes or starting a competing account is the human's call.
                    raise RelayError(
                        "Notes branches already exist: "
                        + "; ".join(f"{c['ref']} ({c['commit']}, {c['date']}, {c['subject']})" for c in found)
                        + f". Ask the human, then run notes init --from <ref> to continue one as {branch}, "
                        "or notes init --fresh to start empty.")
                else:
                    tree = git(home, "mktree", input="")
                    commit = git(home, "commit-tree", tree, "-m", "Initialize independent research notes")
                # Compare-and-create: do not overwrite a concurrently created branch.
                git(home, "update-ref", "refs/heads/" + branch, commit, "0" * len(commit))
                if source and _exists(home, "refs/remotes/" + source):
                    try:  # tracking only reports divergence; relay never pushes
                        git(home, "branch", "--set-upstream-to=" + source, branch)
                    except RelayError:
                        pass
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            git(home, "worktree", "add", str(path), branch)
        privacy = protect_private_inputs(path)
        entry = path / "RESEARCH.md"
        created = not entry.exists()
        if created:
            # x mode refuses races and never replaces an existing research document.
            with entry.open("x") as out:
                out.write((TEMPLATES / "RESEARCH.md").read_text())
        return {"notes": str(path), "home": str(toplevel(home)), "attached": chosen is not None,
                "branch": git(path, "branch", "--show-current"), "entry_created": created,
                "status": git(path, "status", "--short"), "committed": False, **privacy}


def _tracking(path, branch):
    """The notes branch's upstream and that remote's URL. relay never pushes and cannot tell a public remote."""
    upstream, remote = git(path, "for-each-ref", "--format=%(upstream:short)%00%(upstream:remotename)",
                           "refs/heads/" + branch).partition("\0")[::2]
    if not upstream:
        return {"upstream": None, "remote_url": None}
    try:
        url = git(path, "remote", "get-url", remote) if remote else None
    except RelayError:
        url = None
    return {"upstream": upstream, "remote_url": url}


def inspect(repo):
    home, chosen = resolve(repo)
    place = {"home": str(toplevel(home)), "attached": chosen is not None}
    path = find(home, chosen)
    if path is None:
        branch = chosen or branch_name(home)
        return {"notes": None, **place, "branch": branch,
                "candidates": candidates(home, branch, exact=chosen is not None),
                "hint": "Align research intent before notes init. When candidates exist, the human decides "
                        "between notes init --from <ref> and notes init --fresh."}
    branch = git(path, "branch", "--show-current")
    return {"notes": str(path), **place, "branch": branch,
            "status": git(path, "status", "--short"),
            "head": git(path, "rev-parse", "HEAD"),
            "entry_exists": (path / "RESEARCH.md").is_file(), **_tracking(path, branch), **private_status(path)}


def commit(repo, paths, message):
    with _notes_lock(repo) as (home, chosen):
        path = find(home, chosen)
        if path is None:
            raise RelayError("No notes worktree. Run notes status/init first.")
        if not paths or not message.strip():
            raise RelayError("Pass each reviewed notes file with --path and a commit message.")
        current = git(path, "branch", "--show-current")
        if (current != chosen) if chosen else not is_notes_branch(current):
            raise RelayError("Notes checkout changed branch; refusing to commit.")
        protect_private_inputs(path)
        chosen_paths = []
        for name in paths:
            rel = Path(name)
            if rel.is_absolute() or ".." in rel.parts or name.startswith(":") or rel.as_posix() == ".":
                raise RelayError("Notes paths must be explicit relative filenames.")
            if is_private_artifact(rel):
                raise RelayError("Private human input artifacts must never be committed; commit only summaries and references.")
            if not (path / rel).exists():
                git(path, "ls-files", "--error-unmatch", "--", str(rel))  # a deletion is a valid change
            chosen_paths.append(str(rel))
        staged = set(git(path, "diff", "--cached", "--name-only", "-z").split("\0")) - {""}
        if staged - set(chosen_paths):
            raise RelayError("Unrelated staged notes exist; inspect them. Nothing was reset or committed.")
        git(path, "add", "--", *chosen_paths)
        staged_after = git(path, "diff", "--cached", "--name-only")
        if not staged_after:
            return {"status": "unchanged", "notes": str(path)}
        # A failed Git hook/identity check intentionally leaves the draft and index intact.
        git(path, "commit", "-m", message)
        return {"status": "committed", "notes": str(path), "commit": git(path, "rev-parse", "HEAD"),
                "remaining": git(path, "status", "--short"), "pushed": False}


def _contained(home, commit, branch):
    # A commit the home does not have is not contained; nothing is fetched to find out.
    result = subprocess.run(["git", "-C", str(home), "merge-base", "--is-ancestor", commit, "refs/heads/" + branch],
                            capture_output=True, text=True, timeout=30)
    return result.returncode == 0


def _remote_url(repo, ref):
    try:
        return git(repo, "remote", "get-url", ref.split("/", 1)[0])
    except RelayError:
        return None


def left_behind(project, home, branch):
    """What this project still holds of its own notes, judged against `branch` in `home`.

    worktrees and stranded (local notes branches, or their upstreams, with commits the home's
    branch lacks) would leave notes behind; contained and remote are only reported.
    """
    result = {"source": str(project), "worktrees": [], "stranded": [], "contained": [], "remote": []}
    for name, path in worktrees(project).items():
        private = path / PRIVATE_ARTIFACTS
        result["worktrees"].append({"path": str(path), "branch": name, "status": git(path, "status", "--short"),
                                    "private_files": sum(1 for p in private.rglob("*") if p.is_file())
                                    if private.is_dir() else 0})
    raw = git(project, "for-each-ref", "--format=%(refname)%00%(refname:short)%00%(objectname)%00%(upstream)",
              "refs/heads", "refs/remotes")
    rows = [line.split("\0") for line in raw.splitlines()]
    upstreams = {upstream for ref, short, _, upstream in rows if ref.startswith("refs/heads/") and
                 is_notes_branch(short) and upstream}
    for ref, short, commit, _ in rows:
        local, tracked = ref.startswith("refs/heads/"), ref in upstreams
        if not (is_notes_branch(short) and (local or ref.startswith("refs/remotes/")) or tracked):
            continue
        entry = {"ref": short, "commit": commit[:12]}
        if local or tracked:
            result["contained" if _contained(home, commit, branch) else "stranded"].append(entry)
        if not local:
            result["remote"].append({**entry, "url": _remote_url(project, short)})
    return result


def _left_text(left, home, branch):
    """One message per kind of leftover, for status warnings and attach refusals."""
    where = f"{branch} in {home}"
    texts = []
    if left.get("unreachable"):
        texts.append(f"The earlier notes home {left['unreachable']} is not a repository here, so relay cannot "
                     "check what its notes hold.")
    for tree in left["worktrees"]:
        changed = len(tree["status"].splitlines())
        texts.append(f"A notes worktree remains at {tree['path']} ({tree['branch']}; {changed} changed files, "
                     f"{tree['private_files']} private input files). Bring what it holds into {where}, copy "
                     "artifacts/private/ by hand, then remove it with git worktree remove, which deletes "
                     "ignored files: copy the private inputs first.")
    if left["stranded"]:
        source = shlex.quote(str(left["source"]))
        texts.append("Notes branches in " + str(left["source"]) + " hold commits that " + where + " lacks: "
                     + ", ".join(f"{e['ref']} ({e['commit']})" for e in left["stranded"])
                     + f". Bring them into {branch} first. If it does not exist yet, "
                     f"git -C {shlex.quote(str(home))} fetch {source} <ref>:{branch} creates it from one of them; "
                     f"otherwise, in a checkout of {branch}: git pull --no-rebase --allow-unrelated-histories "
                     f"{source} <ref> (notes branches start from separate roots).")
    if left["contained"]:
        texts.append(f"Notes branches in {left['source']} are already contained in {where}: "
                     + ", ".join(e["ref"] for e in left["contained"])
                     + ". Delete the local ones there with git branch -D once nothing else needs them.")
    if left["remote"]:
        texts.append("Remote notes branches remain: "
                     + ", ".join(f"{e['ref']} ({e['url'] or 'unknown URL'})" for e in left["remote"])
                     + ". relay cannot tell whether a remote is public; if one is, delete the branch there.")
    return texts


def _check_branch(repo, branch):
    try:
        git(repo, "check-ref-format", "--branch", branch)
    except RelayError:
        raise RelayError(f"Invalid branch name: {branch!r}") from None
    if not is_notes_branch(branch):
        raise RelayError("--branch must end in relay-notes, for example <user>/<topic>/relay-notes: notes branches "
                         "stay recognizable, and a code branch cannot be chosen by mistake.")


def _previous_left(runtime, previous, home, branch):
    """What moving from the pointer's earlier home and branch would leave behind there."""
    old, old_branch = home_path(runtime, previous), previous["branch"]
    result = {"source": str(old), "worktrees": [], "stranded": [], "contained": [], "remote": []}
    try:
        common_dir(old)
    except (RelayError, OSError):
        return {**result, "unreachable": str(old)}
    path = find(old, old_branch)
    if path is not None and git(path, "status", "--short"):
        private = path / PRIVATE_ARTIFACTS
        result["worktrees"].append({"path": str(path), "branch": old_branch, "status": git(path, "status", "--short"),
                                    "private_files": sum(1 for p in private.rglob("*") if p.is_file())
                                    if private.is_dir() else 0})
    if _exists(old, "refs/heads/" + old_branch):
        tip = git(old, "rev-parse", "refs/heads/" + old_branch)
        entry = {"ref": old_branch, "commit": tip[:12]}
        result["contained" if _contained(home, tip, branch) else "stranded"].append(entry)
    return result


def attach(repo, to=None, branch=None):
    """Keep this project's notes on `branch` of `to` (default: this repository). Policy and sessions stay here."""
    project = toplevel(repo)
    home = main_worktree(to) if to else main_worktree(project)
    same = common_dir(home) == common_dir(project)
    if same and branch is None:
        raise RelayError("Pass --to another repository, or --branch to keep the notes here on a chosen branch.")
    if branch is not None:
        _check_branch(home, branch)
    pinned = None if same else pointer(runtime_dir(home))
    if pinned is not None:
        if common_dir(home_path(runtime_dir(home), pinned)) != common_dir(home):
            raise RelayError(f"{home} keeps its notes in another repository (notes attach); attach to that one instead.")
        branch = branch or pinned["branch"]  # the home's own chosen branch is its notes
    branch = branch or branch_name(home)  # recorded, so a later user.name change does not move the notes
    runtime = runtime_dir(project)
    with lock(runtime / "notes.lock"):
        previous = pointer(runtime)
        old = home_path(runtime, previous) if previous else None
        # Moving from an earlier home: what its branch holds must reach the new one. A self-pin is
        # this repository's own notes, which left_behind already judges.
        moving = old is not None and (old, previous["branch"]) != (home, branch) and not _same_repo(old, project)
        parts = [part for part in (None if same else left_behind(project, home, branch),
                                   _previous_left(runtime, previous, home, branch) if moving else None) if part]
        blocking = [part for part in parts if part["worktrees"] or part["stranded"] or part.get("unreachable")]
        if blocking:
            texts = [text for part in blocking for text in _left_text({**part, "contained": [], "remote": []},
                                                                        home, branch)]
            raise RelayError(" ".join(texts) + " relay attaches only when notes would not be left behind; to "
                             "leave an earlier home's notes where they are, run notes detach first. "
                             "Nothing was changed.")
        write_json(runtime / POINTER, {"version": 1, "home": os.path.relpath(home, runtime.parent),
                                       "branch": branch, "since": now()})
    report = [text for part in parts for text in _left_text(part, home, branch)]
    return {"project": str(project), "home": str(home), "branch": branch, "pointer": str(runtime / POINTER),
            **({"previous": previous} if previous else {}), **({"left_behind": report} if report else {}),
            "notes": _quiet(inspect, project)}


def detach(repo):
    runtime = runtime_dir(repo)
    path = runtime / POINTER
    with lock(runtime / "notes.lock"):
        try:
            previous = pointer(runtime)
        except RelayError as exc:
            previous = {"invalid": str(exc)}  # detach is how a broken pointer goes away
        if path.exists():
            path.unlink()
    return {"detached": previous is not None, **({"previous": previous} if previous else {}),
            "notes": _quiet(inspect, repo)}


def warnings(repo):
    """Status warnings: a pointer that does not resolve, or notes left behind in a project attached elsewhere."""
    try:
        home, chosen = resolve(repo)
        if chosen is None or common_dir(home) == common_dir(repo):
            return []
        return _left_text(left_behind(repo, home, chosen), home, chosen)
    except RelayError as exc:
        return [str(exc)]


def _quiet(function, *args):
    try:
        return function(*args)
    except RelayError as exc:
        return {"error": str(exc)}
