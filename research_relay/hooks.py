"""Native hook boundary. This module never performs research or restarts a turn."""

from pathlib import Path
import time

from .state import (RelayError, lock, locked, marker_path, read_json,
                    runtime_dir, write_json)


def handle(payload):
    if not isinstance(payload, dict):
        raise RelayError("Hook input must be an object; no protection can be asserted.")
    event = payload.get("hook_event_name")
    # Codex subagent hooks carry the PARENT session_id. Do not treat these as Stop.
    if event not in ("PostToolUse", "PreCompact", "Stop", "Interrupt", "SessionEnd", "UserPromptSubmit"):
        return {}
    try:
        runtime = runtime_dir(payload["cwd"])
        marker_file = marker_path(runtime, payload["session_id"])
    except (KeyError, RelayError):
        return {}
    if not marker_file.exists():
        return {}  # Unrelated sessions have no relay policy.
    try:
        with lock(runtime / "control.lock"):
            marker = read_json(marker_file)
            transcript = payload.get("transcript_path")
            if transcript and str(Path(transcript).resolve()) != marker["rollout"]:
                return {}  # A child can share session_id and cwd; its transcript differs.
            if event == "PreCompact":
                # Deliberately survives watcher exit, turn changes and application restarts.
                # Missing transcript is ambiguous inside this opted-in scope: stop safely.
                marker["last_precompact"] = {"trigger": payload.get("trigger"), "at": time.time()}
                write_json(marker_file, marker)
                return {"continue": False, "stopReason": "research-relay forbids compaction in this opted-in thread",
                        "systemMessage": "research-relay：已请求在 compaction 前停止；请手动新建 fresh 会话读取 notes。"}
            # Delivery/cleanup requires exact transcript binding, not only a parent id.
            if not transcript:
                return {"systemMessage": "research-relay：缺少主会话 transcript 绑定；自动提醒不可用。"}
            value = read_json(runtime / "watcher.json", {})
            owner = value.get("thread_id") == payload["session_id"]
            same_turn = payload.get("turn_id") == value.get("turn_id")
            if event in ("Stop", "Interrupt", "SessionEnd"):
                if owner and (same_turn or event == "SessionEnd"):
                    write_json(runtime / "stop.json", {"nonce": value["nonce"], "thread_id": payload["session_id"]})
                    if event == "Stop":
                        return {"continue": False, "stopReason": "research-relay main turn is finished"}
                return {}  # Never decision:block, never a continuation prompt.
            if event == "UserPromptSubmit":
                if not owner or not locked(runtime / "watcher.lock"):
                    return {"hookSpecificOutput": {"hookEventName": event,
                            "additionalContext": "research-relay watcher 未运行；不要把本 turn 当作受保护研究。重新执行 skill 的启用检查；旧会话的 PreCompact 标记仍保留。"}}
                return {}
            if not owner or not same_turn:
                return {}
            if not locked(runtime / "watcher.lock") and value.get("status") not in ("stopped", "failed"):
                marker.setdefault("notices", {}).setdefault("failure", {
                    "reason": "watcher disappeared", "text": "research-relay watcher 意外退出；监测不可用，请保存当前工作并停止。",
                    "emitted": False, "created_at": time.time()})
            pending = [n for n in marker.get("notices", {}).values() if not n["emitted"]]
            if not pending:
                return {}
            for notice in pending:
                notice["emitted"] = True
                notice["emitted_at"] = time.time()
            write_json(marker_file, marker)
            # Emitted means returned to the hook runner, NOT acknowledged by the model.
            return {"systemMessage": "research-relay：实验性提醒已交给 hook runner；保护尚未验证。",
                    "hookSpecificOutput": {"hookEventName": "PostToolUse",
                    "additionalContext": "\n".join(n["reason"] + "：" + n["text"] for n in pending)}}
    except (RelayError, OSError, KeyError, TypeError) as exc:
        message = f"research-relay scoped hook failed; monitoring is NOT protected: {exc}"
        if event == "PreCompact":
            return {"continue": False, "stopReason": message, "systemMessage": message}
        return {"systemMessage": message}


def configuration(python, script):
    import shlex
    command = shlex.join([str(python), str(script), "hook"])
    events = ("PostToolUse", "PreCompact", "Stop", "Interrupt", "SessionEnd", "UserPromptSubmit")
    return {"description": "research-relay experimental hooks; manual review/trust required; no verified protection",
            "hooks": {event: [{"hooks": [{"type": "command", "command": command,
                        "timeout": 3 if event in ("Interrupt", "SessionEnd") else 5,
                        **({"additionalContextLimit": 1500} if event in ("PostToolUse", "UserPromptSubmit") else {})}]}]
                      for event in events}}
