import argparse
import json
import os
from pathlib import Path
import plistlib
import subprocess
import sys

from . import hooks, notes, probes, watcher
from .rollout import Rollout, locate
from .state import RelayError, thread_id


ROOT = Path(__file__).resolve().parent.parent
BLOCKERS = [
    "Desktop PostToolUse additionalContext delivery has not been verified",
    "Desktop trusted PreCompact blocking (manual AND auto) has not been verified",
    "Desktop Stop/Interrupt/SessionEnd execution has not been verified",
]


def doctor(repo, identity=None, home=None):
    value = {"protected": False, "research_start": "blocked", "blockers": BLOCKERS,
             "available": ["portable notes workflow", "experimental rollout + native-hook probe"],
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
    if identity:
        try:
            reader = Rollout(locate(home, thread_id(identity))).bind(repo, identity)
            value["binding"] = {"thread_id": identity, "turn_id": reader.turn,
                                "rollout": str(reader.path), "meta": reader.meta,
                                "latest_request_estimate": reader.usage}
            value["hook_delivery"] = probes.inspect(repo, identity)
        except (RelayError, OSError) as exc:
            value["binding_error"] = str(exc)
    return value


def parser():
    p = argparse.ArgumentParser(description="Research notes and an experimental Codex context sidecar; no LLM calls.")
    sub = p.add_subparsers(dest="cmd", required=True)
    for command in ("doctor", "start", "probe-start", "status", "stop", "_watch", "notes", "hooks"):
        q = sub.add_parser(command)
        q.add_argument("--repo", default=".")
        if command in ("doctor", "start", "probe-start", "stop", "hooks"):
            q.add_argument("--thread-id", default=os.environ.get("CODEX_THREAD_ID"))
        if command in ("doctor", "probe-start", "hooks"):
            q.add_argument("--codex-home", default=os.environ.get("CODEX_HOME", str(Path.home() / ".codex")))
        if command == "probe-start":
            q.add_argument("--rollout", type=Path)
            q.add_argument("--host-pid", type=int, required=True)
            q.add_argument("--compact-limit", type=int, required=True,
                           help="effective main-thread compaction ceiling; do not guess from model capacity")
            q.add_argument("--poll", type=float, default=1.0)
            q.add_argument("--stale", type=float, default=180.0)
        if command == "_watch":
            q.add_argument("--nonce", required=True)
        if command == "notes":
            q.add_argument("action", choices=("init", "status", "commit"))
            q.add_argument("--path", action="append", default=[])
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
            code = 2
        elif args.cmd == "start":
            raise RelayError("Protected research start is unavailable in V1. Use notes independently; probe-start is diagnostic ONLY. " + "; ".join(BLOCKERS))
        elif args.cmd == "probe-start":
            identity = thread_id(args.thread_id)
            path = args.rollout or locate(args.codex_home, identity)
            value = watcher.start_probe(args.repo, identity, path, args.host_pid,
                                        args.compact_limit, args.poll, args.stale)
        elif args.cmd == "status":
            value = watcher.status(args.repo)
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
