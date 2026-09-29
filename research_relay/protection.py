"""Read-only Desktop capability checks; never changes configuration or hook trust.

The short-lived app server resolves disk configuration only. Native delivery must
separately be acknowledged in the actual main turn; it is not a second session.
"""

import hashlib
import json
import os
from pathlib import Path
import select
import shlex
import subprocess
import sys
import time

from .rollout import Rollout, locate, threshold
from .state import (RelayError, git, marker_path, read_json,
                    runtime_dir, thread_id, verify_ancestor)


EVENTS = ("postToolUse", "preCompact", "stop", "interrupt", "sessionEnd", "userPromptSubmit")
ROOT = Path(__file__).resolve().parents[1]


def fingerprint(path):
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except FileNotFoundError:
        return None


def hooks_path(repo):
    return Path(git(repo, "rev-parse", "--show-toplevel")) / ".codex/hooks.json"


def hook_fingerprint(repo):
    """Bind native delivery to Relay definitions, not the surrounding hook file."""
    config = read_json(hooks_path(repo))
    if config is None:
        return None
    command = [sys.executable, str(ROOT / "skills/research-relay/scripts/relay.py"), "hook"]
    definitions = {}
    for event in EVENTS:
        matches = []
        for group in config.get("hooks", {}).get(event[0].upper() + event[1:], []):
            for handler in group.get("hooks", []):
                if handler.get("type") != "command":
                    continue
                raw_command = handler.get("command")
                if not isinstance(raw_command, str):
                    continue
                try:
                    args = shlex.split(raw_command)
                except ValueError:
                    continue  # An unrelated command cannot attest Relay delivery.
                if args == command:
                    matcher = group.get("matcher")
                    matches.append({"matcher": "*" if matcher in (None, "", "*") else matcher,
                                    "handler": {**handler, "command": command}})
        definitions[event] = matches
    return hashlib.sha256(json.dumps(definitions, sort_keys=True).encode()).hexdigest()


def desktop_host():
    """Discover only this execution's ancestor, never the newest process/session."""
    pid = os.getpid()
    for _ in range(64):
        result = subprocess.run(["ps", "-p", str(pid), "-o", "ppid=", "-o", "comm="],
                                capture_output=True, text=True, timeout=3)
        fields = result.stdout.strip().split(None, 1)
        if len(fields) != 2:
            break
        parent, executable = fields
        if executable.endswith("/codex-cli/CodexCLI.app/Contents/MacOS/codex"):
            verify_ancestor(pid)
            return pid, executable
        pid = int(parent)
        if pid <= 1:
            break
    raise RelayError("No Desktop Codex ancestor found; run start inside the actual main chat.")


def host_overrides(pid, executable):
    result = subprocess.run(["ps", "-p", str(pid), "-o", "args="],
                            capture_output=True, text=True, timeout=3)
    args = result.stdout.strip()
    if not args.startswith(executable + " "):
        raise RelayError("Cannot inspect Desktop launch arguments.")
    args = shlex.split(args[len(executable):])
    overrides, index = [], 0
    while index < len(args):
        arg = args[index]
        if arg in ("-c", "--config", "--enable", "--disable") and index + 1 < len(args):
            overrides.extend(args[index:index + 2])
            index += 2
        elif arg in ("app-server", "--analytics-default-enabled", "--stdio"):
            index += 1
        elif arg == "--strict-config":
            overrides.append(arg)
            index += 1
        else:
            raise RelayError(f"Unsupported Desktop launch option {arg}; cannot reproduce configuration safely.")
    return overrides


def read_capabilities(repo, home, executable, overrides):
    """Bounded stdio JSON-RPC, using only initialize and three read methods."""
    env = {**os.environ, "CODEX_HOME": str(home)}
    child = subprocess.Popen([executable, *overrides, "app-server"], cwd=repo, env=env,
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL)
    buffer = b""
    deadline = time.monotonic() + 20

    def call(number, method, params):
        nonlocal buffer
        child.stdin.write((json.dumps({"id": number, "method": method, "params": params}) + "\n").encode())
        child.stdin.flush()
        while True:
            while b"\n" in buffer:
                line, buffer = buffer.split(b"\n", 1)
                response = json.loads(line)
                if response.get("id") == number:
                    if "error" in response:
                        raise RelayError(f"Desktop {method} readiness query failed.")
                    return response["result"]
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not select.select([child.stdout], [], [], remaining)[0]:
                raise RelayError("Desktop capability query timed out.")
            chunk = os.read(child.stdout.fileno(), 65536)
            if not chunk:
                raise RelayError("Desktop capability query exited without a response.")
            buffer += chunk
            if len(buffer) > 16 * 1024 * 1024:
                raise RelayError("Desktop capability response is too large.")

    try:
        call(1, "initialize", {"clientInfo": {"name": "relay-readiness", "version": "1"},
                               "capabilities": {"experimentalApi": True}})
        config = call(2, "config/read", {"cwd": str(repo), "includeLayers": True})
        hooks = call(3, "hooks/list", {"cwds": [str(repo)]})
        requirements = call(4, "configRequirements/read", {})
        return config, hooks, requirements
    finally:
        child.terminate()
        try:
            child.communicate(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.communicate()


def validate_capabilities(repo, config, listing, requirements):
    effective = config["config"]
    policy = requirements.get("requirements") or {}
    for source in (effective, policy):
        features = source.get("features") or {}
        if features.get("hooks", features.get("codex_hooks", True)) is False:
            raise RelayError("Codex hooks are disabled.")
        if source.get("allow_managed_hooks_only"):
            raise RelayError("Only managed hooks are allowed; project Relay hooks cannot run.")
    limit = effective.get("model_auto_compact_token_limit")
    if type(limit) is not int:
        raise RelayError("Need an explicit effective model_auto_compact_token_limit; model window is not a substitute.")
    threshold(limit, limit)
    path = hooks_path(repo)
    entries = [e for e in listing["data"] if Path(e["cwd"]).resolve() == Path(repo).resolve()]
    if len(entries) != 1 or entries[0]["errors"]:
        raise RelayError("Desktop cannot resolve this project's hooks cleanly.")
    command = [sys.executable, str(ROOT / "skills/research-relay/scripts/relay.py"), "hook"]
    verified = {}
    for event in EVENTS:
        matches = [h for h in entries[0]["hooks"] if h["eventName"] == event
                   and Path(h["sourcePath"]).resolve() == path.resolve()
                   and h.get("handlerType") == "command"
                   and shlex.split(h.get("command", "")) == command
                   and h.get("matcher") in (None, "", "*") and not h.get("async", False)
                   and h.get("enabled") and h.get("trustStatus") in ("trusted", "managed")]
        if len(matches) != 1:
            raise RelayError(f"Relay {event} hook is missing, disabled, changed or untrusted; review it in native hook settings.")
        verified[event] = matches[0]["currentHash"]
    return limit, verified


def capability_files(repo, home, config):
    # Fingerprints trigger a scoped capability recheck, not automatic revocation.
    # Keep private configuration contents and launch overrides out of state files.
    paths = {home / "config.toml", home / "hooks.json", home / "requirements.toml",
             Path("/etc/codex/requirements.toml"), hooks_path(repo)}
    for layer in config.get("layers") or []:
        name = layer["name"]
        if name.get("file"):
            path = Path(name["file"])
            paths.update((path, path.parent / "hooks.json"))
        if name.get("dotCodexFolder"):
            folder = Path(name["dotCodexFolder"])
            paths.update((folder / "config.toml", folder / "hooks.json"))
    return {str(p): fingerprint(p) for p in sorted(paths)}


def environment(repo, identity, home):
    identity = thread_id(identity)
    if os.environ.get("CODEX_THREAD_ID") != identity:
        raise RelayError("Protected start requires this execution's exact CODEX_THREAD_ID.")
    repo, home = Path(repo).resolve(), Path(home).resolve()
    reader = Rollout(locate(home, identity)).bind(repo, identity)
    pid, executable = desktop_host()
    overrides = host_overrides(pid, executable)
    config, listing, requirements = read_capabilities(repo, home, executable, overrides)
    limit, verified = validate_capabilities(repo, config, listing, requirements)
    snapshot = capability_files(repo, home, config)
    return reader, {"host_pid": pid, "compact_limit": limit,
                    "capabilities": {"files": snapshot, "hooks": verified,
                                     "hook_path": str(hooks_path(repo)),
                                     "hooks_fingerprint": hook_fingerprint(repo),
                                     "resolver": {"home": str(home), "executable": executable},
                                     "basis": "trusted definitions + native turn delivery + PreCompact contract"}}


def check_delivery(repo, reader):
    marker = read_json(marker_path(runtime_dir(repo), reader.meta["id"]), {})
    probe = marker.get("delivery_probe", {})
    if (marker.get("rollout") != str(reader.path) or not marker.get("guard_requested")
            or probe.get("turn_id") != reader.turn or not probe.get("emitted")
            or not probe.get("acknowledged")
            or probe.get("hooks_fingerprint") != hook_fingerprint(repo)):
        raise RelayError("Native delivery is not acknowledged for this turn and hook configuration. Run start, receive the native token, acknowledge it, then retry start.")


def recheck_configuration(value, observed):
    capabilities = value["capabilities"]
    resolver = capabilities.get("resolver")
    if not resolver:
        # Older activations lack the reader binding; never infer one from cwd.
        changed = next(path for path, digest in observed.items()
                       if digest != capabilities["files"][path])
        raise RelayError(f"Protection input changed: {changed}; recheck activation.")
    repo, home = Path(value["repo"]), Path(resolver["home"])
    executable = resolver["executable"]
    for _ in range(3):
        try:
            overrides = host_overrides(value["host_pid"], executable)
            config, listing, requirements = read_capabilities(repo, home, executable, overrides)
        except subprocess.SubprocessError as exc:
            raise RelayError("Cannot recheck this project's protection configuration.") from exc
        current = capability_files(repo, home, config)
        # Re-read if files changed during the query or a newly resolved layer was
        # not observed beforehand. Never bless a digest that the reader missed.
        if (any(path not in observed or observed[path] != digest
                for path, digest in current.items())
                or any(fingerprint(path) != digest for path, digest in observed.items())):
            observed = {path: fingerprint(path) for path in observed.keys() | current.keys()}
            continue
        if hook_fingerprint(repo) != capabilities["hooks_fingerprint"]:
            raise RelayError("Native Relay hook configuration changed; recheck activation and delivery.")
        limit, verified = validate_capabilities(repo, config, listing, requirements)
        if limit != value["compact_limit"]:
            raise RelayError("Protection compaction ceiling changed for this project; recheck activation.")
        if verified != capabilities["hooks"]:
            raise RelayError("Relay hook definitions changed for this project; recheck activation.")
        capabilities["files"] = current
        return
    raise RelayError("Protection inputs kept changing during the scoped capability recheck; retry activation.")


def check_runtime(runtime, value):
    capabilities = value.get("capabilities", {})
    if not capabilities.get("files"):
        raise RelayError("Protected activation has no capability snapshot.")
    marker = read_json(marker_path(runtime, value["thread_id"]), {})
    probe = marker.get("delivery_probe", {})
    if (not marker.get("guard_requested") or marker.get("rollout") != value["rollout"]
            or probe.get("turn_id") != value["turn_id"] or not probe.get("acknowledged")
            or not probe.get("emitted")
            or probe.get("hooks_fingerprint") != capabilities.get(
                "hooks_fingerprint", capabilities["files"].get(capabilities["hook_path"]))):
        raise RelayError("Scoped guard or native delivery evidence changed; protection unavailable.")
    observed = {path: fingerprint(path) for path in capabilities["files"]}
    if observed != capabilities["files"]:
        recheck_configuration(value, observed)
