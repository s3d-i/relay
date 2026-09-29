"""Install only a repo-local skill symlink; never edit hooks, trust, or global config."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research_relay.state import RelayError, git

p = argparse.ArgumentParser(description=__doc__)
p.add_argument("--repo", type=Path, required=True)
p.add_argument("--uninstall", action="store_true")
args = p.parse_args()
source = Path(__file__).resolve().parents[1] / "skills/research-relay"
try:
    repo = Path(git(args.repo, "rev-parse", "--show-toplevel")).resolve()
    target = repo / ".agents/skills/research-relay"
    if target.is_symlink() and target.resolve() == source:
        if args.uninstall:
            target.unlink()
            print("Skill symlink removed. Notes and scoped guard markers retained; hooks were not changed.")
        else:
            print(f"Already installed: {target}")
    elif target.exists() or target.is_symlink():
        raise RelayError(f"Existing skill preserved; inspect manually: {target}")
    elif args.uninstall:
        print("Skill is not installed here. No changes.")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.symlink_to(source, target_is_directory=True)
        print(f"Installed {target} -> {source}")
except (RelayError, OSError) as exc:
    print(str(exc), file=sys.stderr)
    sys.exit(2)
