import argparse
import json
import subprocess
import sys

from . import __version__, backends, hooks, install, links, notes, policy
from .state import RelayError, runtime_dir


def parser():
    p = argparse.ArgumentParser(
        prog="relay", description="Research notes on a <user>/relay-notes branch; hooks that ban compaction, "
        "force fresh-context subagents and ask for a handoff before the context wall.")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)
    agent = dict(choices=backends.NAMES, metavar="{codex,claude}")
    q = sub.add_parser("install", help="symlink the skill, add ignore rules, write the hooks file")
    q.add_argument("--repo", default=".")
    q.add_argument("--agent", required=True, **agent)
    q.add_argument("--uninstall", action="store_true", help="remove the skill symlink only")
    q.add_argument("--print", action="store_true", help="print the hooks JSON instead of installing")
    q = sub.add_parser("on", help="activate the policy for this repository")
    q.add_argument("--repo", default=".")
    q.add_argument("--agent", **agent)
    q.add_argument("--window", type=int, help="context window in tokens (default: transcript, else 200000)")
    q.add_argument("--warn-fraction", type=float, help="closeout at this fraction of the window (default 0.6)")
    q.add_argument("--compact-limit", type=int, help="the agent's own compaction ceiling, if lower")
    q = sub.add_parser("off", help="deactivate the policy (file kept)")
    q.add_argument("--repo", default=".")
    q = sub.add_parser("status", help="policy, hooks files, per-session usage, notes; exit 2 when inactive")
    q.add_argument("--repo", default=".")
    q = sub.add_parser("hook", help="hook entry point: payload JSON on stdin, output JSON on stdout")
    q.add_argument("--agent", required=True, **agent)
    q = sub.add_parser("notes", help="init | status | links | commit on the relay-notes worktree")
    q.add_argument("action", choices=("init", "status", "links", "commit"))
    q.add_argument("--repo", default=".")
    q.add_argument("--path", action="append", default=[],
                   help="reviewed file to commit, or one links query file (default RESEARCH.md)")
    q.add_argument("-m", "--message", default="")
    q.add_argument("--from", dest="source", metavar="REF",
                   help="init: continue this existing notes branch (e.g. origin/relay-notes) under your own name")
    q.add_argument("--fresh", action="store_true", help="init: start empty although notes branches exist")
    return p


def status(repo):
    runtime = runtime_dir(repo)
    current = policy.load(runtime)
    return {"policy": current, "active": bool(current and current.get("active")),
            "hooks": install.hooks_status(repo), "sessions": policy.sessions(runtime),
            "notes": notes.inspect(repo)}


def notes_command(args):
    if args.action == "init":
        return notes.init(args.repo, args.source, args.fresh)
    if args.action == "status":
        return notes.inspect(args.repo)
    if args.action == "links":
        path = notes.find(args.repo)
        if path is None:
            raise RelayError("No notes worktree. Run notes status/init first.")
        if len(args.path) > 1:
            raise RelayError("Query one notes file at a time with --path.")
        return links.neighborhood(path, args.path[0] if args.path else "RESEARCH.md")
    return notes.commit(args.repo, args.path, args.message)


def hook(agent):
    backend = backends.get(agent)
    try:
        payload = json.load(sys.stdin)
    except ValueError as exc:
        payload = f"unreadable payload: {exc}"  # handle() reports a non-object as a failure
    return hooks.handle(payload, backend)


def main(argv=None):
    args = parser().parse_args(argv)
    if args.cmd == "hook":
        print(json.dumps(hook(args.agent), ensure_ascii=False))
        return 0  # decisions travel in the JSON; a non-zero exit would mean "hook broken"
    code = 0
    try:
        if args.cmd == "install":
            backend = backends.get(args.agent)
            if args.print:
                value = backend.render_hooks(backend.hook_command(install.LAUNCHER))
            else:
                value = install.install(args.repo, args.agent, args.uninstall)
        elif args.cmd == "on":
            value = policy.enable(runtime_dir(args.repo), args.agent, args.window,
                                  args.warn_fraction, args.compact_limit)
        elif args.cmd == "off":
            value = policy.disable(runtime_dir(args.repo))
        elif args.cmd == "status":
            value = status(args.repo)
            code = 0 if value["active"] else 2
        else:
            value = notes_command(args)
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except (RelayError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
