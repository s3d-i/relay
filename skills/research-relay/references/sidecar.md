# Experimental context reminders

The sidecar reads usage from the current Desktop rollout and queues a reminder while context still has room, delivered through native `PostToolUse.additionalContext`. It does not call a model, interpret materials, or keep a research session alive. The material workflow works independently.

Complete protection remains unverified. `start` and `doctor` return exit code `2` / `protected: false`. `probe-start` is always an integration diagnostic; a live watcher, passing tests, or a guard marker cannot establish a no-compaction guarantee. The CLI's `BLOCKERS` lists outstanding verification, including auto PreCompact, active-work interruption/SessionEnd cleanup, and continuous health checks.

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

There is one watcher per Git common directory. Repeated activation with the same binding is idempotent; do not take a lock occupied by another session. A normal main-turn end, host exit, or matching stop request causes the watcher to exit, but real-app lifecycle verification still has gaps. Guard requests survive independently; neither research nor sessions restart automatically.

Stale usage, parse failures, and unconsumed reminders are recorded as failures. A later runnable hook may display the failure. Without a hook, inspect `status` and `<git-common-dir>/research-relay/watcher.log`. Report the failure and save notes; do not silently continue sustained research as if protection were established.

After stopping, verify `live: false`. Do not delete the entire runtime directory to recover a watcher: it may contain the notes worktree and drafts. Before removing hooks, save materials and retire the old research sessions that rely on them. Do not claim protection after disabling their hooks. Preserve private inputs separately.
