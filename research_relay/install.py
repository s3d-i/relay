"""Install the skill symlink, ignore rules and hooks file into a project, per agent."""

from pathlib import Path

from . import backends
from .state import RelayError, git


SKILL = Path(__file__).resolve().parent.parent / "skills/research-relay"
LAUNCHER = SKILL / "scripts/relay.py"


def ignore_rules(backend):
    # The hooks file is local-only for both agents: absolute paths (codex), local settings (claude).
    return (f"/{backend.SKILL_DIR}/research-relay", f"/{backend.HOOKS_FILE}", "/artifacts/private/")


def patch_gitignore(repo, rules):
    path = repo / ".gitignore"
    existing = path.read_bytes() if path.exists() else b""
    lines = existing.splitlines()
    # Slash-containing patterns are root-relative either way: an unprefixed form counts.
    missing = [rule.encode() for rule in rules
               if rule.encode() not in lines and rule.lstrip("/").encode() not in lines]
    if not missing:
        return False
    newline = b"\r\n" if b"\r\n" in existing else b"\n"
    prefix = newline if existing and not existing.endswith(b"\n") else b""
    with path.open("ab") as out:
        out.write(prefix + b"# research-relay local files" + newline + newline.join(missing) + newline)
    return True


def toplevel(repo):
    return Path(git(repo, "rev-parse", "--show-toplevel")).resolve()


def skill_link(repo, backend):
    target = repo / backend.SKILL_DIR / "research-relay"
    installed = target.is_symlink() and target.resolve() == SKILL
    if not installed and (target.exists() or target.is_symlink()):
        raise RelayError(f"Existing skill preserved; inspect manually: {target}")
    return target, installed


def install(repo, agent, uninstall=False):
    backend = backends.get(agent)
    repo = toplevel(repo)
    target, installed = skill_link(repo, backend)
    if uninstall:
        if installed:
            target.unlink()
        return {"agent": agent, "skill": str(target), "installed": False,
                "retained": "ignore rules, hooks file, notes and policy"}
    rules = ignore_rules(backend)
    gitignore_changed = patch_gitignore(repo, rules)
    if not installed:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(SKILL, target_is_directory=True)
    result = backend.install_hooks(repo, backend.hook_command(LAUNCHER))
    tracked = git(repo, "ls-files", "-z", "--", *(rule.strip("/") for rule in rules))
    return {"agent": agent, "skill": str(target), "installed": True, "gitignore_changed": gitignore_changed,
            **result, **({"warning": "relay-local files are tracked; .gitignore does not untrack them"}
                         if tracked else {})}


def hooks_status(repo):
    repo = toplevel(repo)
    return {name: {"file": str(backends.get(name).hooks_file(repo)),
                   "installed": backends.get(name).hooks_installed(
                       repo, backends.get(name).hook_command(LAUNCHER))}
            for name in backends.NAMES}
