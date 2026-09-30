"""Context thresholds and one session's reminder state. Pure functions: no files, no hook shapes."""

WARN_FRACTION = 0.75
RESERVE = 100_000
CHECKPOINT_FRACTION = 0.2
STATE_KEYS = ("baseline", "final_sent", "last_usage")


def thresholds(policy, window=None):
    """{"ceiling", "final", "step"}; None without a window or without room above the reserve.

    An explicit policy window wins over the transcript's. The ceiling is what a session can
    reach: the window, or the host's own compaction limit when that is lower. Both the
    fraction and the reserve are measured against it.
    """
    window = policy.get("context_window") or window
    if not window:
        return None
    limit = policy.get("compact_limit")
    ceiling = min(window, limit) if limit else window
    final = int(min(policy.get("warn_fraction", WARN_FRACTION) * ceiling,
                    ceiling - policy.get("reserve", RESERVE)))
    if final <= 0:
        return None
    step = int(policy.get("checkpoint_fraction", CHECKPOINT_FRACTION) * ceiling)
    return {"ceiling": ceiling, "final": final, "step": step}


def replaced(state):
    """The context was compacted or cleared: earlier usage says nothing about the new one."""
    for key in STATE_KEYS:
        state.pop(key, None)


def observe(state, used, limits):
    """Judge one usage observation and update `state`.

    Returns None, ("checkpoint", growth since the last reminder) or ("final", used). A final
    reminder replaces a checkpoint due at the same time; after it, a reminder comes every step.
    """
    baseline = state.get("baseline")
    if baseline is None or used < baseline:
        baseline = used  # first observation, or usage went down
    sent = state.get("final_sent", False)
    if sent and used < limits["final"] - limits["ceiling"] // 10:
        sent = False  # a large drop with no compaction event (a rewind, a missed event) re-arms
    result = None
    if used >= limits["final"] and not sent:
        sent, result = True, ("final", used)
    elif limits["step"] and used - baseline >= limits["step"]:
        result = ("checkpoint", used - baseline)
    if result:
        baseline = used
    state["baseline"], state["final_sent"] = baseline, sent
    return result
