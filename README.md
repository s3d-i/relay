# research-relay

以研究文档为中心的工作约定，加一个自动提醒收尾的临时 sidecar。持久化的是研究资产、路径、人类反馈和当前理解；会话由人手动开启和结束。

**V1 状态：文档流程与 notes 工具可用；原生送达、Stop 与 manual PreCompact 已实测，完整自动保护验收仍未完成。** `start` 和 `doctor` 返回退出码 `2` / `protected: false`。可运行的 `probe-start` 只用于集成诊断，绝不是受保护研究。没有用 prompt、mock 或 watcher 存活来冒充完整 no-compaction 保护。

本轮核验的桌面程序为 `/Applications/ChatGPT.app`（Codex 桌面能力），版本 `26.924.22138`、build `11645`，实际内嵌运行组件 `codex-cli 0.158.0-alpha.2.1`。PATH 中另一个 `0.155.1` CLI 不是该 app 的执行实例。环境证据、采用路径与未通过项见 [Codex 集成记录](docs/codex-integration.md)。

## 工作方式

人类手动打开未继承旧历史的 fresh 会话，invoke `$research-relay`。主 agent 读 `RESEARCH.md` 和必要证据，简述当前理解并与人对齐；主 agent 接待反馈、维护研究理解，具体调查与实验交给按需 subagent，默认串行。不是自动 `/goal` continuation，也不是永不退出的调度控制台。

新想法先作为研究资产保存，区分怀疑、优先级决定和停止要求。主 agent 决定在什么边界传给执行者、继续现有有界调查，或收回 partial result 后停止。明确停止立即采用；含糊而会改变方向的意见先澄清。这个约定减少不必要地 steer 执行研究的 subagent，**不改写或保证 Codex 原生输入框的中断语义**。

Continuation 保留在研究层：主 agent 审查一个有界任务的结果、及时补 notes，在方向仍明确且保护健康时继续下一个问题，不要求人每一步重新批准，也不因一个 subagent 结束就创建新会话。人类的 custom steer 先由主 agent 给出简短回执——怎样理解、当前执行到哪里、准备采取什么动作——然后将原话保存到主会话的私密 artifact，并决定如何传给执行者。新想法不自动覆盖原目标；明确的立即停止优先。跨会话仍由人手动 fresh，notes 是继续理解的依据。

完整 expected UX：

1. 人手动 fresh 会话 → `$research-relay`。
2. 读总文档，检查必要 artifacts、真实代码与结果、未提交草稿和活动实验；不是照搬上次 TODO。
3. 简述理解、提出影响行动的问题，取得明确方向；已有明确反馈不重复确认。此时 watcher 未运行。
4. 检查并启用保护 → 正常研究、按需委派、持续记笔记。
5. watcher 提前提醒 → 不再开启新方向，安全结束当前操作。
6. 核查 subagents 已结束或保存 partial result 后明确停止；登记可跨会话的训练。
7. 更新两层材料，只提交本次 notes，停止主 turn；watcher 自行退出。
8. 下一次仍由人手动 fresh，会重新理解和评估，不自动接管生命周期。

**本版在第 4 步诚实停在能力门槛。** 可以独立阅读、对齐、整理、提交 notes；不能将未验证保护的长研究伪装成这条完整流程。首次无笔记先明确意图，再建立入口。已有材料永不被模板覆盖。

## 为什么只有两层研究资产

一篇可独立理解的总 Markdown 承担解释，linked artifacts 承担细节和核查。总文档讲清目标、观察能支持多强的判断、hypothesis/confounder、路线转折、人的反馈和当前停留处；它不是目录、流水账或 session summaries 的拼接。

Artifacts 围绕问题、实验、审计、失败路径或有价值的讨论组织，可以有子目录，也可以引用原有代码 commit、结果目录和图表。修改分析不修改原始结果；被否定的路线保留“不再相信它的理由”。一个 artifact 可以跨会话完善，一次会话也可涉及多个问题。

影响研究的人类输入按来源分开：**主动输入 / steer** 才称为人类原始 prompt；**Codex 提问的回答 / 选项选择** 关联问题、给出的选项和实际选择，用户另行输入的文字单列，不能把 Codex 写的选项称作人类原创。这个区分不能仅凭 `role=user` 或 hook 事件名推定。

所有原始输入与回答都作为私密内容，默认一个主 Codex session 共用一个 `artifacts/private/human-inputs/<主会话ID>.md`，跨 turn 继续追加，内部按来源分段。先确认 Git 忽略已生效且没有已跟踪/暂存文件，再保存原文。`RESEARCH.md`、问题 artifacts、`docs/`、README 和提交说明只保留必要的决定摘要、agent 解释及私密来源路径/锚点。原文不因没有密钥或已经脱敏就变成可提交内容。

私密引用应注明“私密、本地”。其他克隆不会有这些文件，缺失时明确标注来源不可用；可共享正文仍须独立解释当前决定。Git 提交成功不代表私密输入已备份，清理 worktree 前须另行保全需要的本地原件。

详见 [convention](skills/research-relay/references/convention.md)、[总文档模板](skills/research-relay/assets/RESEARCH.md)、[artifact 模板](skills/research-relay/assets/artifact.md)与[私密输入模板](skills/research-relay/assets/private-human-inputs.md)。[ensomi-model 风格示例](examples/ensomi-model/RESEARCH.md) 全部为教学虚构，不包含真实研究成果。

不建立 Run/Generation、研究状态版本、event-sourcing、任务 DAG、调度数据库或 graph database。Git history 和普通实验 ID 足够。长期会话 continuation 保留对话状态；某些 fresh-context loops 自动创建下一轮；本项目选择人手动 fresh、从资产重新理解，不承诺更聪明、无损记忆或更省 token。

## 安装与开发

需要 Git 和 Python **3.10+**，macOS 为目标平台；实现只用 Python 标准库，POSIX 锁也可在 Linux 跑测试。没有模型 SDK、LLM 请求、服务端、数据库或前端。选择标准库是为了让安装、hook 启动和排错成本小。

```sh
cd /absolute/path/relay
make check
python3 -m research_relay --help
python3 scripts/install_skill.py --repo /absolute/path/research-project
```

安装器只创建研究仓库的 `.agents/skills/research-relay` 本地 symlink，指向此 checkout 的 skill；保留冲突目标，不改全局配置、AGENTS.md 或 hooks。保持 relay checkout 路径稳定。链接会作为该研究仓库的未跟踪文件出现；按项目习惯忽略它，不将机器专属路径盲目提交。多个代码 worktrees 要在实际使用的 checkout 安装 skill，watcher 唯一性仍按 Git common directory 计算。

在 app 中手动打开该项目的新会话，选择/输入 `$research-relay`。新 skill 通常自动发现；若菜单未更新，重启 app。这只安装了 skill，**不会自动信任 hooks 或自动启动研究**。本仓库也可用同一命令 `--repo .` 安装作本地开发。

从任意工作目录调用工具：

```sh
python3 /absolute/path/relay/skills/research-relay/scripts/relay.py notes --repo /absolute/path/research-project status
python3 /absolute/path/relay/skills/research-relay/scripts/relay.py doctor --repo /absolute/path/research-project
```

`make check` 包含真实子进程测试，会使用 `ps` 只读验证进程身份。当前 Codex sandbox 禁止 `ps`；在普通终端运行，或由宿主审批测试命令。不要因此扩大 Codex 的全局审批或 sandbox 权限。静态检查另可用 `python3 scripts/check_skill.py`。

## Notes branch 的真实使用

先对齐研究意图，再运行：

```sh
python3 -m research_relay notes --repo /absolute/path/research-project init
python3 -m research_relay notes --repo /absolute/path/research-project status
```

返回独立 worktree 的绝对路径。默认位于 `<git-common-dir>/research-relay/notes`，branch 为 `relay-notes`。已有此 branch 的 worktree 就复用；否则创建一个不含代码历史文件的独立 notes branch/worktree。初始空提交只是建立 branch，不是研究版本。代码工作区的分支、索引和未提交改动保持原样；即便代码仓库尚无提交也可建立 notes。创建需要 Git 提交身份，未配置时会报错，不擅自写全局身份。

`notes init` 同时在仓库本地 `info/exclude` 中追加 `/artifacts/private/`，保留其他规则，供所有关联 worktrees 使用。独立 notes branch 不继承代码分支的 `.gitignore`，所以不能只依赖后者。返回的 `private_inputs` 给出私密输入目录；`private_inputs_ignored` 必须为 true，`tracked_private_artifacts` 必须为空。重复 init 会保留 notes 和私密文件。status 只报告路径及保护状态，不输出原文。忽略规则若被覆盖，init/commit 会报错；已有跟踪或强制暂存的私密文件也会阻止操作，需要保留本地原件后人工清理索引，工具不自动删除或改写历史。

在返回的 notes 路径写材料、查看 `git diff`。收尾示例：

```sh
python3 -m research_relay notes --repo /absolute/path/research-project commit \
  --path RESEARCH.md --path artifacts/normalization-audit.md \
  -m 'Explain comparison confound and remaining checks'
```

必须显式列出审查过的可共享文件；工具拒绝 `artifacts/private/`，以及路径逃逸、symlink、隐藏/敏感文件名、部分密钥特征和超过 1 MiB 的文件，不接收目录或通配 pathspec。不相关的已暂存改动会阻止提交，未暂存的其他草稿保持原样。被忽略的私密输入不出现在普通 status/remaining 中，需单独核对已保存。这些基本检查不能识别被复制到其他文件的所有原文，仍须审查文档和提交说明。大结果留原处引用；默认不 push、无 reset。删除已跟踪 notes 也必须显式指定该路径并审查。

提交失败保留工作区和暂存区，`notes status` 下次能看到。只有返回 commit 后才称为提交成功；总文档和当前停止说明不能谎称 handoff 完成。不要删除整个 runtime 目录恢复 watcher——其中有 notes worktree 和未提交草稿。

## Sidecar：一条实验性路径

实现为：**当前 Desktop rollout 只读 tail → 本地一次性提醒 → 原生 `PostToolUse.additionalContext`**。没有 App Server adapter 列表，没有另起 Codex 执行实例，不调用 LLM、不做科学判断、不整理研究结论。

当前 app 的 App Server 使用私有 stdio 连接，未发现可附接监听端点；另起 `codex app-server`、共享同一个 Codex home，都不能证明连接到了它。故 V1 不调用 `thread/inject_items`。只读 rollout 的私有格式依赖集中在 `research_relay/rollout.py`；升级 app 后必须重新核验字段和行为，解析错误会停止监测。

用量取 `last_token_usage.total_tokens`：最近一次模型请求的输入加输出估计。**不取累计 `total_token_usage`**；cached input 已在 input 中，reasoning 已在 output 中，不再相加。这不是逐时刻精确的剩余 context：最后一个响应之后的新输入/工具结果可能还未计入，推理 token 的留存语义也可能不同。更新延迟包括 runtime 写盘延迟、默认 1 秒轮询和下一个可运行 hook 的工具边界；长推理/长工具期间不能保证马上提醒。

提醒阈值为：`min(0.60 × window, min(window, compact_limit) − max(32768, 0.20 × min(window, compact_limit)))`。既为笔记/核查/提交留空间，也考虑可能早于 window 的 compaction ceiling。`--compact-limit` 必须来自当前执行环境有效配置，不能把配置文件的值无条件当成当前 thread 的实际值。时间只用于检测观测失效，不冒充 token 用量。

同一个 Git common directory 用 `flock` 保证唯一 watcher；同主会话同绑定重复启动返回同一个 PID，另会话报告占用，不抢占、不 kill。锁文件不删除；进程崩溃由 OS 释放锁。绑定核对明确 UUID、rollout metadata、repo、主 turn、Desktop source，排除 subagent 文件。在 Codex 内还校验 `CODEX_THREAD_ID` 和执行进程祖先；外部终端指定 host PID 时只能核验该进程身份，需要人确认它是实际 app 实例。PID 加启动时间/可执行路径用于发现复用。

提醒每个 opted-in thread 对 closeout 去重一次，故障再至多提醒一次。hook 返回只记为 **emitted**，不是模型已接收的 ack。30 秒未取走提醒或 180 秒无新用量，会置失败状态、保留待提醒原因并退出；下一次可运行 hook 才有机会显示失败。若 hook 从未运行，无法承诺立即出现在聊天中，须看 `status`/本地日志。因此所有诊断始终 `protected: false`。

正常主 turn 结束、用户中断、host 退出、SIGTERM/SIGINT 或显式 `stop` 都使 watcher 释放锁退出。它监测已绑定文件的 `task_complete`/`turn_aborted`，原生 `Stop`/`Interrupt`/`SessionEnd` 是另一条同一路径内的清理边界。`Stop` 只表示一个 turn 结束，不表示研究完成或永久关闭会话。子任务 hook 使用 parent session ID，代码还检查 transcript 和 turn，不把 `SubagentStop` 当成主会话结束。不会自动重启 watcher/研究，不清理训练或整个工作区进程。

## Hook 配置与 no-compaction 边界

不需要臆造 `[features]` 开关，也不提高 `model_auto_compact_token_limit`。唯一需要的可选原生配置样例是 [hooks.example.json](integrations/codex/hooks.example.json)：

```sh
python3 -m research_relay render-hooks > /tmp/research-relay-hooks.json
```

生成包含实际 Python 和脚本绝对路径的待审查配置。也可执行 `python3 -m research_relay hooks prepare --repo /absolute/path/research-project`，直接准备项目 `.codex/hooks.json`；已有不同配置时拒绝覆盖，需人工合并，绝不自动信任。这个本地文件含机器路径，本仓库将其忽略。确保项目配置层被信任，再在**当前 app** 的 Hooks 设置中审查/信任具体定义。仅 project trusted 或 JSON 存在不等于 hook trusted。

已核验当前 app 的原生信任路径是 `hooks/list` 获取定义 hash，再用 `config/batchWrite` 保存并刷新该 app 管理的会话；不是绕过信任。另起进程写相同配置不意味着现有 app 会话已刷新。因此没有控制 socket **并不阻止原生 hook 路径**，也不需要自建 runtime；当前仍需在 app 实际完成审查/信任和送达验收。源码边界见[集成记录](docs/codex-integration.md)。

安装/信任后，用当前主会话做一次送达握手（仅诊断）：

**配置应在 fresh 会话创建前准备好。** 已实测：本机版本的旧会话若启动时还没有 `.codex/`，之后信任 hooks 也可能继续使用旧的项目层集合，完全不启动 handler。新建同项目的 fresh 测试聊天后，原生送达与 Stop 路径成功；不要反复改信任或扩大权限来修复旧层缓存。

```sh
python3 -m research_relay hooks probe --repo /absolute/path/research-project
# 在同一 app turn 执行一个普通工具。原生 PostToolUse 应送入一次性标记。
python3 -m research_relay hooks status --repo /absolute/path/research-project
# 只有主 agent 真正从 hook context 收到标记，才按其提示执行 hooks ack --token ...。
```

probe 的启动输出和 status 都不暴露标记；禁止从 marker 文件读它冒充收到消息。回执绑定主 thread/turn/transcript，记录各 hook 的最后一次报告，未保存聊天或工具正文；`UserPromptSubmit` 只给主 agent 一个静态反馈处理提示，不调用 LLM、判断语义或自动 steer subagent。`acknowledged-by-caller` 仍不等于 PreCompact 验收成功，`protected` 保持 false。下一 turn 需重新 arm 诊断，不能用旧标记证明新 turn 的送达。直接执行 hook 或测试 fixture 都仍是模拟。

`hooks probe` 另开启五分钟的 handler 入口诊断，只记录最后一次调用的事件、thread/turn、cwd 和 transcript 路径，不保存正文。`last_entry: null` 表示没有观察到脚本入口；有入口而无匹配回执则检查绑定。此诊断自动过期，不启动 watcher，也不算保护证据。在默认 workspace sandbox 中，初始化 `.git` 下的 runtime 状态可能需要该命令的正常审批；native hook trust 不代替文件访问审批。

诊断启动为该 **repo + 主 thread ID** 留下一个持久的 `guard_requested` 标记，后续匹配的 `PreCompact` 对 auto/manual 都返回 `continue: false`。标记独立于 watcher，Stop/崩溃/重新开 app 后仍保留，不影响其他 thread。子会话有不同 transcript，不给它冒充主会话保护；本版没有证明子 agent 的 compaction 防护，研究启动门槛也未放开。

这只是代码中的保护请求。只有 hook 被当前 app 加载、信任、执行，且实际阻止 compaction，才构成 runtime 保护；hook 被禁用、路径移动、信任失效、配置层没加载、读写失败时不能保证它阻断。**本版没有任何命令能把状态切成 `protected: true`**，也没有“人工填一个 verified=true”来绕过验收。保留文档流程，不接受 compaction 作为隐藏 fallback。

## 诊断启用、停止与恢复

普通研究使用 `start`，当前会拒绝。明确进行集成诊断时，才使用：

```sh
python3 -m research_relay probe-start --repo /absolute/path/research-project \
  --thread-id ACTUAL-CODEX-THREAD-UUID --host-pid ACTUAL-APP-SERVER-PID \
  --compact-limit ACTUAL-EFFECTIVE-LIMIT
python3 -m research_relay status --repo /absolute/path/research-project
python3 -m research_relay stop --repo /absolute/path/research-project \
  --thread-id ACTUAL-CODEX-THREAD-UUID
```

在当前 Codex shell 内 UUID 默认取 `CODEX_THREAD_ID`；其他 shell 必须明确给出。只通过 UUID 查唯一 rollout，找不到或不唯一就报错，可传 `--rollout /exact/file.jsonl`，仍核对 metadata，绝不选“最新文件”。host PID 用进程只读检查确认，不启动第二个 App Server。`stop` 是仅针对该 thread/启动 nonce 的退出请求；随后 `status` 应显示 `live: false`。不允许停止别人的 watcher。

常见恢复：

| 情况 | 处理 |
| --- | --- |
| 另一主会话占用 | 报告占用 UUID；让对应会话正常结束/停止，不能抢锁或批量 kill。 |
| watcher 崩溃，状态仍像 active | `status` 以 OS 锁检测存活并报告失败；确认原工作后重做诊断。不删除锁文件抢占。 |
| 已 trusted 但无 handler entry | 若 `.codex` 是在会话启动后新增，手动 fresh 同项目测试聊天，再 arm 探针；旧会话继续视为未保护。 |
| 用量陈旧/格式变化/提醒未送达 | 看 `<git-common-dir>/research-relay/watcher.log` 和 status，保存 notes 后停止；更新集成证据后再谈保护。 |
| `ps` 或 runtime 写入被 sandbox 拒绝 | 如实报告不可用，按宿主审批具体命令或在普通终端做诊断；不改全局审批。 |
| notes 提交失败 | `notes status` 定位草稿、暂存区与 Git 错误，修复后显式重提，不 reset、不覆盖。 |
| 旧会话已有 compaction | `probe-start` 拒绝；手动 fresh，从研究材料接续。 |
| 仍有训练或 subagent | 先核查身份和实际状态，保存结果/partial result；停止 agent 并核实，独立训练按人的决定保留与登记。 |

卸载 skill：`python3 scripts/install_skill.py --repo /absolute/path/research-project --uninstall`。先停止 watcher。notes branch、worktree 和 scoped guard 标记都保留，其他 skill/config 不变。若要卸载 hooks，先永久停用这些旧研究会话、保存 drafts，再审查删除仅 research-relay 的配置条目；旧 thread 将不再有 no-compaction 保护，**不要再恢复它们研究**。不要盲目删除 `.git/research-relay`。notes worktree 的清理由人确认已保存资产后按普通 Git/worktree 流程完成。

## 验证和边界

`make check`：真实临时 Git 仓库 + 真正 watcher 子进程，覆盖跨 worktree 竞争启动、绑定、阈值与去重、Stop/中断/host 退出、失效、独立保护标记、精确提交和失败草稿。`make demo`：模拟 token 事件→独立 watcher→直接调用 hook→Stop 的可运行演示，输出明确写明 **SIMULATION ONLY**。

真实 app 已验证：精确版本/进程/stdio、用量观察、用户信任的六个 hooks，以及 fresh 测试聊天中的原生 PostToolUse 送达、确认和 Stop 退出。一次未干扰的测试中，watcher 在 turn 结束后约 0.6 秒退出，锁释放，guard marker 保留。它的退出原因是 `main-turn-ended`，同时存在匹配 nonce 的原生 Stop 请求；不把这写成只靠 Stop hook 才退出的证明。此后用户触发 native Compact，manual PreCompact 在 watcher 已退出时仍阻断：compact turn 被中断，没有 compacted-history 记录。auto PreCompact、用户主动中断时的清理、SessionEnd 与持续保护健康检查仍待验收。独立材料阅读/反馈试用不能替代平台验证。详见 [集成记录](docs/codex-integration.md)。

本项目不自建模型调用链、工具执行器、sandbox、审批系统、聊天 UI、训练平台或通用 adapter framework。没有自动 push，没有私有数据库写入，没有 GUI 自动点击，没有常驻 LLM supervisor。
