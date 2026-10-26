"""Install the skill symlink, ignore rules and hooks file into a project, per agent."""

import os
from pathlib import Path

from . import backends
from .state import RelayError, git, read_json, toplevel


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


def skill_link(repo, backend):
    target = repo / backend.SKILL_DIR / "research-relay"
    installed = target.is_symlink() and target.resolve() == SKILL
    if not installed and (target.exists() or target.is_symlink()):
        raise RelayError(f"Existing skill preserved; inspect manually: {target}")
    return target, installed


def install(repo, agent, uninstall=False):
    backend = backends.get(agent)
    repo = toplevel(repo)
    if uninstall:
        return _uninstall(repo, agent, backend)
    target, installed = skill_link(repo, backend)
    rules = ignore_rules(backend)
    gitignore_changed = patch_gitignore(repo, rules)
    if not installed:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(SKILL, target_is_directory=True)
    result = backend.install_hooks(repo, backend.hook_command(LAUNCHER, repo))
    tracked = git(repo, "ls-files", "-z", "--", *(rule.strip("/") for rule in rules))
    notes = backend.warnings(repo, None)
    if tracked:
        notes.append("relay-local files are tracked; .gitignore does not untrack them")
    return {"agent": agent, "skill": str(target), "installed": True, "gitignore_changed": gitignore_changed,
            **result, **({"warnings": notes} if notes else {})}


def _uninstall(repo, agent, backend):
    # Hooks first: an unreadable hooks file stops here with nothing changed.
    result = backend.uninstall_hooks(repo)
    target = repo / backend.SKILL_DIR / "research-relay"
    # relay's link from this or another relay checkout; a link only, so its target is never touched.
    if target.is_symlink() and (target.resolve() == SKILL
                                or os.readlink(target).rstrip("/").endswith("skills/research-relay")):
        target.unlink()
    elif target.exists() or target.is_symlink():
        result["skill_kept"] = "not relay's link; left in place"
    others = []
    for name in backends.NAMES:
        try:
            if name != agent and present(backends.get(name), repo):
                others.append(name)
        except PermissionError:
            pass
    return {"agent": agent, "skill": str(target), "installed": False, **result,
            **({"other_agents_hooks": others} if others else {}),
            "retained": "ignore rules, foreign hooks, notes and policy"}


def present(backend, repo):
    """Whether the hooks file holds any relay entry, current or from an older relay."""
    try:
        current = read_json(backend.hooks_file(repo), {})
    except RelayError:
        return False
    return backends.present(current.get("hooks"))


def warnings(repo, policy=None):
    repo = toplevel(repo)
    active = bool(policy and policy.get("active"))
    result = []
    for name in backends.NAMES:
        backend = backends.get(name)
        try:
            result.extend(backend.warnings(repo, policy))
            if not present(backend, repo):
                continue
            if not backend.hooks_installed(repo, backend.hook_command(LAUNCHER, repo)):
                result.append(f"relay's {name} hooks run a different command than this relay writes (an older "
                              f"relay, another checkout or another Python); run install --agent {name} again "
                              "unless that is intended.")
            if not active:
                result.append(f"relay's {name} hooks are installed but relay is off here. If the notes moved to "
                              f"another repository, remove them with install --uninstall --agent {name}.")
        except PermissionError:
            result.append(f"{name} hook settings are not readable in this environment.")
    return result


def hooks_status(repo):
    """installed: any relay entry; current: exactly the entries this relay writes."""
    repo = toplevel(repo)
    result = {}
    for name in backends.NAMES:
        backend = backends.get(name)
        value = {"file": str(backend.hooks_file(repo))}
        try:
            value["installed"] = present(backend, repo)
            value["current"] = backend.hooks_installed(repo, backend.hook_command(LAUNCHER, repo))
        except PermissionError:
            value.update(installed=None, current=None, error="Hook settings are not readable in this environment.")
        result[name] = value
    return result
