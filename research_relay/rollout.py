"""Experimental, read-only adapter for the observed Desktop JSONL format.

No transcript content is retained, emitted, or used as research continuity.
All dependence on the private rollout format lives here.
"""

import json
from datetime import datetime
from pathlib import Path

from .state import RelayError, common_dir


class Rollout:
    MAX_LINE = 16 * 1024 * 1024

    def __init__(self, path):
        self.path = Path(path).resolve()
        self.offset = 0
        self.inode = None
        self.meta = None
        self.turn = None
        self.ended = False
        self.compacted = False
        self.usage = None
        self.usage_timestamp = None

    def poll(self):
        stat = self.path.stat()
        identity = (stat.st_dev, stat.st_ino)
        if self.inode and (identity != self.inode or stat.st_size < self.offset):
            raise RelayError("Rollout rotated/truncated; binding is no longer reliable.")
        self.inode = identity
        events = []
        with self.path.open("rb") as src:
            src.seek(self.offset)
            while True:
                raw = src.readline(self.MAX_LINE + 1)
                if not raw:
                    break
                if len(raw) > self.MAX_LINE:
                    raise RelayError("Rollout record too large; parser stopped.")
                if not raw.endswith(b"\n"):
                    break  # Writer has not finished this line. Retry at the same offset.
                self.offset += len(raw)
                try:
                    item = json.loads(raw)
                    if not isinstance(item, dict):
                        raise ValueError("record is not an object")
                except (ValueError, UnicodeError) as exc:
                    raise RelayError("Malformed rollout record; monitoring stopped.") from exc
                event = self.consume(item)
                if event:
                    events.append(event)
        return events

    def consume(self, item):
        kind, payload = item.get("type"), item.get("payload", {})
        if not isinstance(payload, dict):
            return None
        if kind == "session_meta":
            if self.meta is not None:
                raise RelayError("Repeated session metadata; refusing ambiguous binding.")
            self.meta = {k: payload.get(k) for k in ("id", "cwd", "source", "originator", "cli_version")}
        elif kind == "compacted":
            self.compacted = True
            return {"kind": "compacted"}
        elif kind == "event_msg":
            event = payload.get("type")
            if event == "task_started":
                self.turn = payload.get("turn_id")
                self.ended = False
                self.usage = None
                self.usage_timestamp = None
                return {"kind": "started", "turn_id": self.turn}
            if event in ("task_complete", "turn_aborted"):
                # These records have no consistent turn_id across releases. This file
                # must already be bound to the main session, never a shared event bus.
                if payload.get("turn_id") not in (None, self.turn):
                    return None
                self.ended = True
                return {"kind": "ended", "turn_id": self.turn, "reason": event}
            if event == "token_count" and payload.get("info") is not None:
                info = payload["info"]
                try:
                    last = info["last_token_usage"]
                    used, window = last["total_tokens"], info["model_context_window"]
                    # Cached input is already included. Reasoning is included in output.
                    # Never add either a second time; never use total_token_usage here.
                    if any(type(n) is not int or n <= 0 for n in (used, window)):
                        raise ValueError("missing/invalid token estimate")
                    if type(last["input_tokens"]) is not int or last["input_tokens"] < 0:
                        raise ValueError("invalid input tokens")
                    if type(last["output_tokens"]) is not int or last["output_tokens"] < 0:
                        raise ValueError("invalid output tokens")
                    self.usage = {"used": used, "window": window,
                                  "input": last["input_tokens"], "output": last["output_tokens"]}
                except (KeyError, TypeError, ValueError) as exc:
                    raise RelayError("Unknown context-usage format; no cumulative-token fallback.") from exc
                try:
                    stamp = datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00"))
                    if stamp.tzinfo is None:
                        raise ValueError("timestamp requires timezone")
                except (KeyError, AttributeError, TypeError, ValueError) as exc:
                    raise RelayError("Unknown usage timestamp; staleness cannot be verified.") from exc
                self.usage_timestamp = item["timestamp"]
                return {"kind": "usage", **self.usage}
        return None

    def bind(self, repo, identity):
        self.poll()
        if not self.meta or self.meta.get("id") != identity:
            raise RelayError("Rollout does not belong to the exact requested thread.")
        if self.meta.get("originator") != "Codex Desktop" or self.meta.get("source") != "vscode":
            raise RelayError("Expected the observed Desktop main-thread format; refusing CLI/subagent source.")
        if common_dir(self.meta["cwd"]) != common_dir(repo):
            raise RelayError("Rollout cwd belongs to a different repository.")
        if self.compacted:
            raise RelayError("This thread has already compacted. Open a manual fresh chat.")
        if not self.turn or self.ended:
            raise RelayError("No active main turn in this rollout.")
        return self


def locate(home, identity):
    paths = list((Path(home) / "sessions").glob(f"**/*-{identity}.jsonl"))
    if len(paths) != 1:
        raise RelayError("Expected exactly one rollout for CODEX_THREAD_ID; pass --rollout explicitly.")
    return paths[0]


def threshold(window, compact_limit, fraction=0.60, reserve=32768):
    if not 0.1 <= fraction <= 0.75 or compact_limit <= reserve or reserve <= 0:
        raise RelayError("Invalid reserve/threshold policy.")
    # Budget against BOTH the model window and the configured compaction ceiling.
    ceiling = min(window, compact_limit)
    value = min(int(window * fraction), ceiling - max(reserve, int(ceiling * 0.20)))
    if value <= 0:
        raise RelayError("No context left after the closing reserve.")
    return value
