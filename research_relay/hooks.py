"""Native hook boundary. This module never performs research or restarts a turn."""

from pathlib import Path
import os
import shlex
import sys
import time

from .state import (RelayError, lock, locked, marker_path, read_json,
                    runtime_dir, write_json)


def record_probe_entry(payload):
    """Opt-in, five-minute metadata trace distinguishes no launch from bad binding."""
    try:
        runtime = runtime_dir(payload.get("cwd") or os.getcwd())
        path = runtime / "hook-entry-probe.json"
        if not path.exists():
            return
        with lock(runtime / "control.lock"):
            trace = read_json(path)
            if not trace or trace["expires_at"] < time.time():
                return
            trace["last_entry"] = {k: payload.get(k) for k in (
                "hook_event_name", "session_id", "turn_id", "cwd", "transcript_path")}
            trace["last_entry"]["reported_at"] = time.time()
            write_json(path, trace)
    except (RelayError, OSError, KeyError, TypeError):
        # Diagnostic failure must never change a hook's normal stop/delivery decision.
        return


def handle(payload):
    if not isinstance(payload, dict):
        raise RelayError("Hook input must be an object; no protection can be asserted.")
    record_probe_entry(payload)
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
            # A bounded last-receipt per event, never a transcript/event database.
            if transcript:
                marker.setdefault("hook_receipts", {})[event] = {
                    "turn_id": payload.get("turn_id"), "reported_at": time.time(),
                    **({"trigger": payload.get("trigger")} if event == "PreCompact" else {})}
                write_json(marker_file, marker)
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
            probe = marker.get("delivery_probe")
            if (event == "PostToolUse" and probe and not probe["emitted"] and
                    probe["turn_id"] == payload.get("turn_id")):
                probe.update(emitted=True, emitted_at=time.time())
                write_json(marker_file, marker)
                script = Path(__file__).resolve().parents[1] / "skills/research-relay/scripts/relay.py"
                ack_command = shlex.join([sys.executable, str(script), "hooks", "ack",
                                          "--repo", payload["cwd"], "--thread-id", payload["session_id"],
                                          "--token", probe["token"]])
                return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": (
                    "research-relay native delivery diagnostic. This is only a delivery check, not a research task. "
                    f"The delivery token is {probe['token']}. "
                    "If you actually received this text through the native hook, acknowledge it with:\n"
                    f"{ack_command}\n"
                    "Do not acknowledge by reading the marker file. This does not establish no-compaction protection.")}}
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
                feedback_context = (
                    "research-relay 人类反馈：区分主动输入/steer 与 Codex 提问的回答/选项；"
                    "选项文案由 Codex 提供，不能标成人类原创 prompt，不能仅凭 UserPromptSubmit 事件判断。"
                    "原文仅存 Git 已忽略的 artifacts/private/human-inputs/<主会话ID>.md，"
                    "同一主会话复用一个文件；回答关联问题、选项与另行输入的文字。"
                    "可提交 notes 只写决定、解释和私密来源引用，不复制原文。"
                    "先区分待验证想法、明确改向与立即停止；普通新想法不自动中断或重排正在执行的研究。"
                    "明确停止立即处理；否则结合 subagent 实际进度选择继续、边界交接或澄清。"
                    "向人简述理解和本次动作，不把新反馈悄悄变成替代原目标的任务。"
                )
                if not owner or not locked(runtime / "watcher.lock"):
                    feedback_context += " watcher 未运行；本 turn 未受保护，重新检查启用条件；旧会话 PreCompact 标记仍保留。"
                return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": feedback_context}}
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
