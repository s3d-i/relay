import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

from . import hooks, links, notes, probes, protection, watcher
from .rollout import locate, threshold
from .state import RelayError, thread_id


ROOT = Path(__file__).resolve().parent.parent


def doctor(repo, identity=None, home=None):
    value = {"protected": False, "research_start": "blocked", "blockers": [],
             "available": ["portable notes workflow", "protected Desktop sidecar", "native-hook probe"],
             "notes": notes.inspect(repo)}
    for app in (Path("/Applications/ChatGPT.app"), Path("/Applications/Codex.app")):
        plist = app / "Contents/Info.plist"
        binary = app / "Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex"
        if plist.exists():
            data = plistlib.loads(plist.read_bytes())
            value["installed_app"] = {"path": str(app), "version": data.get("CFBundleShortVersionString"),
                                      "build": data.get("CFBundleVersion")}
            if binary.exists():
                result = subprocess.run([str(binary), "--version"], capture_output=True, text=True, timeout=10)
                value["installed_app"]["bundled_cli"] = result.stdout.strip()
            break
    try:
        reader, checked = protection.environment(repo, identity, home)
        value["binding"] = {"thread_id": identity, "turn_id": reader.turn,
                            "rollout": str(reader.path), "meta": reader.meta,
                            "latest_request_estimate": reader.usage}
        value["compact_limit"] = checked["compact_limit"]
        value["host_pid"] = checked["host_pid"]
        value["verified_hooks"] = list(checked["capabilities"]["hooks"])
        value["hook_delivery"] = probes.inspect(repo, identity)
        protection.check_delivery(repo, reader)
        if not reader.usage:
            raise RelayError("Waiting for the first main-turn usage record.")
        value["watcher"] = watcher.status(repo, identity)
        # Activation/status expose delegation instructions; this diagnostic can
        # independently discover closeout from usage newer than watcher state.
        value["watcher"].pop("delegation_policy", None)
        active = value["watcher"]
        if active.get("live") and not active["protected"]:
            raise RelayError(active.get("reason", "An unprotected watcher occupies the repository; stop its owning turn first."))
        value["protected"] = active["protected"]
        value["research_start"] = "protected" if active["protected"] else "ready"
        value["warn_at"] = threshold(reader.usage["window"], checked["compact_limit"])
        if reader.usage["used"] >= value["warn_at"] or active.get("status", "").startswith("warning-"):
            value["research_start"] = "closeout"
    except (RelayError, OSError, ValueError, subprocess.SubprocessError) as exc:
        value["blockers"].append(str(exc))
    return value


def parser():
    p = argparse.ArgumentParser(description="Research notes and a scoped Codex context sidecar; no LLM calls.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for command in ("doctor", "start", "probe-start", "status", "stop", "_watch", "notes", "hooks"):
        q = sub.add_parser(command)
        q.add_argument("--repo", default=".")
        if command in ("doctor", "start", "probe-start", "status", "stop", "hooks"):
            q.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID"))
        if command in ("doctor", "start", "probe-start", "hooks"):
            q.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        if command == "probe-start":
            q.add_argument("--rollout", type=Path)
            q.add_argument("--host-pid", type=int, required=True)
            q.add_argument("--compact-limit", type=int, required=True,
                           help="effective main-thread compaction ceiling; do not guess from model capacity")
        if command in ("start", "probe-start"):
            q.add_argument("--poll", type=float, default=1.0)
        if command == "_watch":
            q.add_argument("--nonce", required=True)
        if command == "notes":
            q.add_argument("action", choices=("init", "status", "links", "commit"))
            q.add_argument("--path", action="append", default=[],
                           help="reviewed commit file, or one links query file (default: RESEARCH.md)")
            q.add_argument("-m", "--message", default="")
        if command == "hooks":
            q.add_argument("action", choices=("prepare", "probe", "ack", "status"))
            q.add_argument("--token", default="")
    sub.add_parser("hook")
    sub.add_parser("render-hooks")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    code = 0
    try:
        if args.cmd == "doctor":
            value = doctor(args.repo, args.thread_id, args.codex_home)
            code = 0 if value["research_start"] in ("ready", "protected") else 2
        elif args.cmd == "start":
            value = watcher.start(args.repo, args.thread_id, args.codex_home, args.poll)
            code = 0 if value["protected"] and value["research_start"] == "protected" else 2
        elif args.cmd == "probe-start":
            identity = thread_id(args.thread_id)
            path = args.rollout or locate(args.codex_home, identity)
            value = watcher.start_probe(args.repo, identity, path, args.host_pid,
                                        args.compact_limit, args.poll)
        elif args.cmd == "status":
            value = watcher.status(args.repo, args.thread_id)
        elif args.cmd == "stop":
            value = watcher.stop(args.repo, args.thread_id)
        elif args.cmd == "_watch":
            return watcher.watch(args.repo, args.nonce)
        elif args.cmd == "hook":
            value = hooks.handle(json.load(sys.stdin))
        elif args.cmd == "render-hooks":
            value = hooks.configuration(sys.executable, ROOT / "skills/research-relay/scripts/relay.py")
        elif args.cmd == "hooks":
            if args.action == "prepare":
                value = probes.prepare(args.repo)
            elif args.action == "probe":
                value = probes.arm(args.repo, args.thread_id, args.codex_home)
            elif args.action == "ack":
                value = probes.acknowledge(args.repo, args.thread_id, args.token)
            else:
                value = probes.inspect(args.repo, args.thread_id)
        elif args.cmd == "notes":
            if args.action == "init":
                value = notes.init(args.repo)
            elif args.action == "status":
                value = notes.inspect(args.repo)
            elif args.action == "links":
                path = notes.find(args.repo)
                if path is None:
                    raise RelayError("No notes worktree. Run notes status/init first.")
                if len(args.path) > 1:
                    raise RelayError("Query one notes file at a time with --path.")
                value = links.neighborhood(path, args.path[0] if args.path else "RESEARCH.md")
            else:
                value = notes.commit(args.repo, args.path, args.message)
        print(json.dumps(value, ensure_ascii=False, indent=2))
    except (RelayError, OSError, ValueError, subprocess.SubprocessError) as exc:
        if args.cmd == "hook":
            print(json.dumps({"systemMessage": f"research-relay hook failed; NOT protected: {exc}"}))
        else:
            print(json.dumps({"error": str(exc), "protected": False}, ensure_ascii=False), file=sys.stderr)
        return 2
    return code


if __name__ == "__main__":
    sys.exit(main())
