# Context protection and reminders

The sidecar reads usage from the current Desktop rollout and queues a reminder while context still has room, delivered through native `PostToolUse.additionalContext`. It does not call a model, interpret materials, or keep a research session alive. The material workflow works independently.

Desktop verification on 2026-09-29 covers live usage observation, native delivery, manual PreCompact blocking, normal Stop, and archive-triggered Interrupt/SessionEnd cleanup. Fault tests also verified native warnings after unexpected watcher death. Lifecycle shutdown now checks its stop request before reading a transcript that the app may have moved; each new watcher activation can deliver fresh warnings while retaining the thread's compaction guard.

Compaction refusal is established for the installed Desktop app by the live user test and the [documented PreCompact contract](https://learn.chatgpt.com/docs/hooks): a matching `continue: false` stops compaction before it runs. Another compaction or archive test is not an activation prerequisite. The watcher retains its latest observation while no new usage record arrives and keeps reminders pending until a native hook delivers them. Neither condition has a failure deadline.

## Normal activation

Run through this skill's `scripts/relay.py` inside the actual Desktop main chat:

```sh
python3 /path/to/skill/scripts/relay.py start --repo /path/to/research-project
python3 /path/to/skill/scripts/relay.py doctor --repo /path/to/research-project
```

`start` requires this execution's `CODEX_THREAD_ID`. It binds the unique main rollout and active turn, finds the actual Desktop ancestor process, and reproduces its supported launch overrides in a short-lived configuration reader. That reader uses only `initialize`, `config/read`, `hooks/list`, and `configRequirements/read`; it does not attach to the running host, create a chat, invoke a model, or change configuration. Its disk/configuration checks are combined with native delivery evidence from the actual chat, rather than treated as live-host delivery evidence.

The effective configuration must expose an explicit `model_auto_compact_token_limit`. All six Relay project hooks must match the launcher, be synchronous, enabled, trusted, and unfiltered. Unknown launch options, disabled hooks, configuration read errors, and incomplete bindings fail with a concrete reason. The tool never guesses a limit from model capacity or grants hook trust.

On `awaiting-native-delivery` (exit 2), the command has armed a delivery check but has not started monitoring. Receive the native hook context and run its acknowledgment command, then rerun `start`. The acknowledgment is scoped to this thread, active turn, and hook configuration. Successful activation returns `mode: protected`, `live: true`, and `protected: true`; repeated starts with the same active binding reuse the watcher. `doctor` returns exit 0 for `ready` or `protected`, and exit 2 for `blocked` or `closeout`. `ready` means the checks pass but a watcher still needs starting. A closeout reminder takes precedence over new research even though the compaction guard is healthy.

Protected `start` and `status` results also expose an output-only `delegation_policy`: every new subagent uses fresh context (`spawn_agent` with `fork_turns: "none"`), each independent task gets a new agent and self-contained handoff, and subagents perform substantive research, experiments, coding, and verification. The main coordinates, reviews evidence, maintains notes/lifecycle, and spends most research execution time in event-based waits; while a worker runs, the main starts no other substantive investigation or worker implementation. Follow the [skill's delegation instructions](../SKILL.md#human-feedback-and-delegation) for handoff contents and unavailable fresh spawning. The policy is instruction-only and compliance is unverified: the sidecar neither creates agents nor checks spawn arguments, handoff quality, or time spent waiting. `protected: true` verifies main-thread protection only. Inactive, failed, stopped, diagnostic (`doctor`/probe), awaiting-delivery, and closeout results omit the active policy, even when a closeout result retains a healthy compaction guard.

After requesting a stop, verify that monitoring has ended. The next main turn needs another delivery check and activation; nothing automatically restarts a chat or watcher.

For a project without hooks, use `hooks prepare` and the native trust workflow below. An unavailable or blocked activation still permits the independent material workflow.

## When explicitly testing integration

Run these commands through the skill's `scripts/relay.py`, or use `python3 -m research_relay` from the relay checkout. Replace the placeholder paths and identities with actual values:

```sh
python3 /path/to/skill/scripts/relay.py doctor --repo /path/to/research-project
python3 /path/to/skill/scripts/relay.py hooks prepare --repo /path/to/research-project
```

`hooks prepare` creates project `.codex/hooks.json`, refuses to overwrite a different configuration, and does not grant trust. Review and trust the specific definitions through the current app's native settings. An existing configuration or a trusted project does not prove hooks were loaded. Prepare configuration before manually opening a fresh test session; an older session may not have loaded a project configuration layer added afterward. Do not change global approval settings or bypass trust.

```sh
python3 /path/to/skill/scripts/relay.py hooks probe --repo /path/to/research-project
# Run an ordinary tool in the same app turn and check for native hook context.
python3 /path/to/skill/scripts/relay.py hooks status --repo /path/to/research-project
```

Acknowledge the token as instructed only after actually receiving it through hook context. Do not read the marker file to simulate delivery. Direct handler calls and test fixtures remain simulations. The probe leaves `guard_requested` for that repository and main thread. Matching PreCompact events request that automatic or manual compaction be blocked; actual prevention still depends on the current app loading, trusting, and executing the hook. One acknowledgment does not establish complete protection.

```sh
python3 /path/to/skill/scripts/relay.py probe-start --repo /path/to/research-project \
  --thread-id ACTUAL-MAIN-THREAD-UUID --host-pid ACTUAL-APP-HOST-PID \
  --compact-limit ACTUAL-EFFECTIVE-LIMIT
python3 /path/to/skill/scripts/relay.py status --repo /path/to/research-project
python3 /path/to/skill/scripts/relay.py stop --repo /path/to/research-project \
  --thread-id ACTUAL-MAIN-THREAD-UUID
```

In a Codex shell, the thread ID defaults to `CODEX_THREAD_ID`; supply it explicitly elsewhere. The tool checks a unique rollout's metadata, repository, main turn, and process identity instead of choosing the newest file. Do not infer the effective compaction threshold solely from the model window. Starting another App Server does not connect to the current app's execution instance.

## Limits and recovery

Usage comes from the latest model request's `last_token_usage.total_tokens`, not cumulative totals. Cached inputs and reasoning are not added twice. The reminder threshold is `min(0.60 * window, min(window, compact_limit) - max(32768, 0.20 * min(window, compact_limit)))`. Disk writes, polling, and the next hook boundary all introduce delay; immediate delivery during long reasoning or tool calls is not guaranteed.

There is one watcher per Git common directory. Repeated activation with the same thread, turn, and mode is idempotent; do not take a lock occupied by another session or promote a diagnostic watcher in place. A normal main-turn end, host exit, or matching stop request causes the watcher to exit. Guard requests survive independently; neither research nor sessions restart automatically.

Read, parse, binding, and protection-input errors are recorded as failures. Usage silence retains the last estimate; unconsumed reminders remain pending. A later runnable hook may display a failure. Without a hook, inspect `status` and `<git-common-dir>/research-relay/watcher.log`. Protection depends on the app continuing to honor its hook contract; disk checks cannot observe every in-memory or remote policy change. The private rollout format also remains an experimental adapter. Report a detected failure and save notes; do not silently continue sustained research as if protection were established.

After stopping, verify `live: false`. Do not delete the entire runtime directory to recover a watcher: it may contain the notes worktree and drafts. Before removing hooks, save materials and retire the old research sessions that rely on them. Do not claim protection after disabling their hooks. Preserve private inputs separately.
