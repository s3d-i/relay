"""Install a repo-local skill symlink and ignore local Relay files in .gitignore."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_relay.state import RelayError, git


IGNORE_RULES = (
    "/.agents/skills/research-relay",
    "/.codex/hooks.json",
    "/artifacts/private/",
)


def patch_gitignore(repo):
    path = repo / ".gitignore"
    if path.is_symlink():
        raise RelayError("Refusing to edit a symlinked .gitignore; existing file preserved.")
    existing = path.read_bytes() if path.exists() else b""
    lines = existing.splitlines()
    # These patterns contain slashes, so the existing unprefixed forms are also
    # relative to the root .gitignore. Keep them instead of adding duplicates.
    missing = [rule.encode() for rule in IGNORE_RULES
               if rule.encode() not in lines and rule.lstrip("/").encode() not in lines]
    if not missing:
        return False
    newline = b"\r\n" if b"\r\n" in existing else b"\n"
    prefix = newline if existing and not existing.endswith(b"\n") else b""
    with path.open("ab") as out:
        out.write(prefix + b"# research-relay local files" + newline
                  + newline.join(missing) + newline)
    return True


p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--repo", type=Path, required=True)
p.add_argument("--uninstall", action="store_true")
args = p.parse_args()
source = Path(__file__).resolve().parents[1] / "skills/research-relay"
try:
    repo = Path(git(args.repo, "rev-parse", "--show-toplevel")).resolve()
    target = repo / ".agents/skills/research-relay"
    installed = target.is_symlink() and target.resolve() == source
    if not installed and (target.exists() or target.is_symlink()):
        raise RelayError(f"Existing skill preserved; inspect manually: {target}")
    if args.uninstall:
        if installed:
            target.unlink()
            print("Skill symlink removed. Ignore rules, notes, hooks and scoped guard markers retained.")
        else:
            print("Skill is not installed here. No changes.")
    else:
        # Write ignores before creating the link, including on repeat installs.
        if patch_gitignore(repo):
            print("Updated project .gitignore for Relay-local files.")
        if installed:
            print(f"Already installed: {target}")
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.symlink_to(source, target_is_directory=True)
            print(f"Installed {target} -> {source}")
        if git(repo, "ls-files", "-z", "--", *(rule.strip("/") for rule in IGNORE_RULES)):
            print("Warning: Relay-local files are already tracked; .gitignore does not untrack them.",
                  file=sys.stderr)
except (RelayError, OSError) as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(2)
