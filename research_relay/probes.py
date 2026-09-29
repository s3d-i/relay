"""Bounded native-hook setup and delivery diagnostics; never grants protection.

These receipts say what our handler reported. They are not a trust store, and
directly invoking the handler is only a simulation of Desktop delivery.
"""

import json
import os
from pathlib import Path
import secrets
import sys
import time

from . import hooks
from .rollout import Rollout, locate
from .state import RelayError, git, lock, marker_path, read_json, runtime_dir, thread_id, write_json


def prepare(repo):
    root = Path(git(repo, "rev-parse", "--show-toplevel"))
    path = root / ".codex/hooks.json"
    if path.is_symlink() or not path.parent.resolve().is_relative_to(root.resolve()):
        raise RelayError("Refusing a hooks path redirected outside this project; inspect it manually.")
    script = Path(__file__).resolve().parents[1] / "skills/research-relay/scripts/relay.py"
    expected = hooks.configuration(sys.executable, script)
    existing = read_json(path)
    if existing is not None:
        # Do not rewrite/retrust somebody else's hooks, or merge duplicates blindly.
        if existing != expected:
            raise RelayError(f"Existing hooks preserved. Merge the render-hooks output manually: {path}")
        return {"path": str(path), "status": "already-prepared", "trusted": "unknown", "protected": False}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x") as out:
        json.dump(expected, out, ensure_ascii=False, indent=2)
        out.write("\n")
    return {"path": str(path), "status": "prepared", "trusted": "unknown", "protected": False,
            "next": "Review these exact commands and trust them through Codex's native hook settings."}


def checked_identity(identity):
    identity = thread_id(identity)
    actual = os.environ.get("CODEX_THREAD_ID")
    if actual and actual != identity:
        raise RelayError("Cannot operate on another thread from this Codex execution.")
    return identity


def arm(repo, identity, home):
    identity = checked_identity(identity)
    reader = Rollout(locate(home, identity)).bind(repo, identity)
    runtime = runtime_dir(repo)
    with lock(runtime / "control.lock"):
        path = marker_path(runtime, identity)
        marker = read_json(path, {})
        if marker.get("rollout", str(reader.path)) != str(reader.path):
            raise RelayError("Existing marker has another rollout binding.")
        probe = marker.get("delivery_probe")
        if probe and probe["turn_id"] == reader.turn:
            return {"status": "already-armed", "thread_id": identity, "protected": False}
        marker.update({"thread_id": identity, "rollout": str(reader.path),
                       "guard_requested": True, "protected": False,
                       "delivery_probe": {"token": secrets.token_hex(16), "turn_id": reader.turn,
                                          "created_at": time.time(), "emitted": False, "acknowledged": False}})
        write_json(path, marker)
    # The token is deliberately not printed here. It must arrive through the hook.
    return {"status": "armed", "thread_id": identity, "turn_id": reader.turn, "protected": False,
            "next": "Run an ordinary tool in this Desktop turn; only acknowledge a token actually received in hook context."}


def acknowledge(repo, identity, token):
    identity = checked_identity(identity)
    runtime = runtime_dir(repo)
    with lock(runtime / "control.lock"):
        path = marker_path(runtime, identity)
        marker = read_json(path, {})
        probe = marker.get("delivery_probe")
        if not probe or not probe["emitted"] or not secrets.compare_digest(probe["token"], token):
            raise RelayError("No matching emitted delivery probe; protection cannot be asserted.")
        # An old turn's token cannot attest delivery in a new turn.
        reader = Rollout(marker["rollout"]).bind(repo, identity)
        if reader.turn != probe["turn_id"]:
            raise RelayError("Delivery probe belongs to a previous turn.")
        probe.update(acknowledged=True, acknowledged_at=time.time())
        write_json(path, marker)
    return {"delivery": "acknowledged-by-caller", "protected": False,
            "limitation": "An acknowledgement is not proof of trust, nor of PreCompact blocking."}


def inspect(repo, identity):
    identity = checked_identity(identity)
    marker = read_json(marker_path(runtime_dir(repo), identity), {})
    probe = marker.get("delivery_probe", {})
    return {"thread_id": identity, "protected": False,
            "guard_requested": marker.get("guard_requested", False),
            "reported_hook_events": marker.get("hook_receipts", {}),
            "delivery_probe": {k: v for k, v in probe.items() if k != "token"},
            "limitation": "Handler receipts and caller ack require native-host evidence; manual hook calls are simulations."}
