# 当前 Codex 集成决策与验证记录

核验日期：2026-09-29。本文记录 research-relay 实现环境，不是 ensomi-model 研究笔记。README 说明操作，本文保留证据层级和未解决项。

## 产品解释已对齐

职责边界来自一次 Codex 澄清提问后的选项选择，见[私密、本地选择记录](../artifacts/private/human-inputs/01a0eb31-2655-78b1-967a-bbaee34f7c31.md#answer-1)。选项措辞不归为人类原创 prompt。

因此主 agent 维护理解、处理人类反馈与交接；具体调查和实验按需委派。主 agent 收尾后停止，不变成常驻调度台。不承诺改变原生输入框的中断行为。

## 证据分层

用户给出的官方入口现重定向到 ChatGPT Learn。已实际打开 [Skills](https://learn.chatgpt.com/docs/build-skills)、[Hooks](https://learn.chatgpt.com/docs/hooks)、[App Server](https://learn.chatgpt.com/docs/app-server)。下面将文档描述、安装环境中的定义和真实行为分开；源码/schema 出现一个名字不等于本会话已接入它。

| 能力 | 官方文档 / 安装组件证据 | 当前 app 实际验证 | V1 决定 |
| --- | --- | --- | --- |
| skill discovery、显式 invoke、脚本 | 文档支持 `.agents/skills`、symlink、`SKILL.md`、`agents/openai.yaml`；脚本显式执行 | 本工程已安装 repo-local symlink，launcher 与官方 skill 校验通过；本次上下文未重新加载新 skill catalog | 显式 `$research-relay`，不隐式启用 |
| `thread/tokenUsage/updated` | 内嵌 CLI 生成 schema 含 `threadId`、`turnId`、`tokenUsage.last/total/modelContextWindow`；app bundle 有事件处理代码 | 当前 App Server 是 app 私有 stdio，无发现可附接监听端点 | 不启动第二个 runtime；不用此 RPC 作 V1 接入 |
| `thread/inject_items` | 内嵌 schema 含 `threadId` 和原始 `items` | 未附接原执行实例，未向主会话实际注入 | 不实现 RPC adapter |
| `PostToolUse.additionalContext` | 官方定义可加 developer context；code-mode 有具体工具覆盖限制 | 安装包有 hooks settings；未安装/信任/实际触发本项目 hook | 仅候选原生通知边界，代码与配置可测试 |
| `PreCompact` | 官方定义 `continue:false` 在 auto/manual compaction 前停止；内嵌枚举存在 | 未验证信任、实际触发及无 compact 结果 | 会话 marker + hook handler；不宣称保护 |
| `Stop` | 是 turn 结束边界，可被其他 Stop hook 继续；`continue:false` 优先 | 只完成程序级模拟 | scoped handler 请求退出并返回 continue:false，不续跑 |
| `Interrupt`、`SessionEnd` | 官方定义主线程中断/结束，不用于 subagents，短 timeout | 只完成程序级模拟 | 原生 hook 写 scoped stop 请求；无 restart |
| `SubagentStop` | 不是主 turn 结束，且子任务 hook 的 session_id 可为 parent ID | 已测试模拟相同 parent ID 不会误停主 watcher | 不挂此 hook 作 cleanup；由主 agent 核查执行者 |

## 后续核验：原生 hook 握手不需要附接 socket

本次后续核验以最初实现为基线。主动输入要求继续推进研究，并保留人类反馈、notes 交接和手动 fresh 的边界；见[私密、本地主动输入记录](../artifacts/private/human-inputs/01a0eb31-2655-78b1-967a-bbaee34f7c31.md#prompt-1)。

因此把“研究问题继续推进”与“旧执行身份继续存活”分开：一个 subagent 结束后，主 agent 可以审查结果、更新 notes 并继续下一个有界问题；人类反馈先由主 agent 保存、澄清与决定如何交给执行者。上下文接近边界时整体收尾，下一次由人手动 fresh。没有新增自动会话循环或反馈调度数据库。

进一步只读核验定位到安装版精确源码 tag `rust-v0.158.0-alpha.2.1`，commit `0d9c7cbfa6cf1489f55a8a9542b75ddd2c061807`：

- [配置 schema](https://github.com/openai/codex/blob/0d9c7cbfa6cf1489f55a8a9542b75ddd2c061807/codex-rs/core/config.schema.json#L2045) 支持 `hooks.state.<key>.trusted_hash`；[信任来源规则](https://github.com/openai/codex/blob/0d9c7cbfa6cf1489f55a8a9542b75ddd2c061807/codex-rs/hooks/src/config_rules.rs#L8) 只接受 user/sessionFlags，项目不能自我信任。安装 app 的 `app-initial-d817715f10a0.js` 中 `dGa/uGa` 使用 `hooks/list` 的 key/currentHash，调用 `config/batchWrite` 写 trusted_hash 并传 `reloadUserConfig:true`。这是一条原生信任路径，不是 bypass。
- [config_processor.rs](https://github.com/openai/codex/blob/0d9c7cbfa6cf1489f55a8a9542b75ddd2c061807/codex-rs/app-server/src/request_processors/config_processor.rs#L356) 只刷新**当前处理进程**持有的线程；[session/mod.rs](https://github.com/openai/codex/blob/0d9c7cbfa6cf1489f55a8a9542b75ddd2c061807/codex-rs/core/src/session/mod.rs#L2060) 重建并替换 hooks。普通工具使用已加载 hooks，未证明每 turn/tool 自动重读磁盘。另一个管理进程写用户配置，不能证明 app 里的旧 thread 已更新。
- 设置页 “Reload hooks” 只重新发现；[catalog_processor.rs](https://github.com/openai/codex/blob/0d9c7cbfa6cf1489f55a8a9542b75ddd2c061807/codex-rs/app-server/src/request_processors/catalog_processor.rs#L614) 不刷新活动线程。没有在有限安装包检查中证实外部配置改动会自动传播到当前 app。信任定义的 hash [不包含脚本内容](https://github.com/openai/codex/blob/0d9c7cbfa6cf1489f55a8a9542b75ddd2c061807/codex-rs/hooks/src/engine/discovery.rs#L766)，因此列表显示 trusted 也不是脚本健康证据。
- [hook_runtime.rs](https://github.com/openai/codex/blob/0d9c7cbfa6cf1489f55a8a9542b75ddd2c061807/codex-rs/core/src/hook_runtime.rs#L392) 区分主线程 Stop 与 ThreadSpawn 的 SubagentStop，Interrupt hook 跳过子代理。没有在核心 interrupt 路径看到后代遍历，app 更高层是否级联仍未证实；主 turn 停止不能替代对子任务的实际停止检查。

本轮已用 `hooks prepare` 创建当前仓库的本地配置（不提交机器路径），并用**内嵌二进制的一次独立只读配置查询**执行 `initialize`、`hooks/list`：六个项目 hook 均 enabled、untrusted，无配置错误/警告。没有调用 thread/start/resume、turn/start、模型或配置写接口，该管理进程已退出。此结果只证明配置可发现，不冒充当前 app 的真实 hook 执行。

已增加 `hooks probe/status/ack`：随机标记只通过匹配主 thread/turn/transcript 的 PostToolUse 返回，主 agent 实际收到后确认；本地 status 不输出标记，回执不保存 prompt/工具正文。它把“handler 报告执行”“模型确认收到”“PreCompact 真正阻断”分开，任何一项都不能替代下一项。人工直接调用 hook 仍是模拟，确认也不会放开 `start`。项目缺少 socket 已从必须阻塞项移除；当前阻塞是 app 内的原生信任/加载和实际保护验收。

## 本地只读核验

本机 app：`/Applications/ChatGPT.app`，Info.plist 的 `CFBundleShortVersionString=26.924.22138`、`CFBundleVersion=11645`。运行的 Codex 二进制为 app 内的 `Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex`，`--version` 为 `0.158.0-alpha.2.1`。PATH 上 `/opt/homebrew/bin/codex` 指向 `0.155.1`，未作为桌面能力依据。

通过只读 `ps` 查到 app 的子进程运行 `codex ... app-server --analytics-default-enabled ...`，没有 `--listen`。`lsof` 显示 fd 0/1 为连接到 app 的无命名 Unix stdio 通道，没有观察到该进程的可附接 Unix listener；未扫描或改写私有数据库。`app-server --help` 虽提供 proxy、daemon、socket 参数，也不能证明已运行 app 使用了可连接 daemon。放开具体命令权限后重试内嵌 CLI 的 `app-server daemon version`，仍返回 `app-server-control.sock: No such file or directory`，不是网络/文件权限错误。没有为核验启动另一条研究执行实例。

从当前会话的确切 `CODEX_THREAD_ID` 定位 rollout，只提取 metadata、event 类型与 token 字段，不输出/复制聊天正文。metadata 与当前 repo 对应，originator=`Codex Desktop`，source=`vscode`，cli_version 与运行组件一致。发现 `task_started` 带 turn_id；token 记录同时含最近请求和累计值。某次实际采样的最近请求总量为 80,277，累计为 385,022；后续采样还会变化，数字仅证明不是同一个量，不作为固定窗口预算。

只读安装包的 ASAR 文件，发现 hooks settings、`PreCompact` 文案、trustStatus 模型和 app 对 `thread/tokenUsage/updated` 的处理。它说明 app 含相应 UI/处理代码，**没有证明 hooks 已被加载、信任或执行**。未操作 GUI、未写私有配置/数据库、未 bypass trust。

使用**内嵌二进制**执行离线 schema 生成（不是启动 app-server）：

```sh
/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex \
  app-server generate-json-schema --experimental --out /tmp/research-relay-schema
```

生成的 schema 支持候选方法与 hook 枚举，留存以下 SHA-256 供复核，未把大份生成 schema vendoring 进项目：

| 文件（`v2/` 下） | SHA-256 |
| --- | --- |
| `ThreadTokenUsageUpdatedNotification.json` | `aba4f6c7e4a19b2b842c08ee793b57000c07dafd57b922ad0d8e7c76609108c2` |
| `ThreadInjectItemsParams.json` | `8d7e754402a2bb71bd817882076d2f8ac4cd75d4573306db082a83b841aa3532` |
| `HooksListResponse.json` | `891dd10ef7f78e59631fce05fff2becddb8004b3c0338dbbbd6b4f17ef1fa64f` |

## 选定路径及维护代价

只实现 `rollout.py` 中的 Desktop JSONL 只读解析、独立 watcher、原生 hook mailbox；未构建多 harness adapter。最近请求 footprint 是估计量，不精确等于下一次调用 context；额外输入/工具输出与写盘延迟都可能让它滞后。阈值和失效策略见 README，不使用费用、时间或累计 tokens 代替。

代价是每次 app/runtime 更新要重验 JSONL 格式、主/子线程标识和结束事件；格式不匹配会报错退出。hook 通知等到工具边界，不能中断长模型推理。即便 hook 返回已 emitted，模型实际看到还要额外验收；不能凭本地文件中的标记制造成功证据。

No-compaction marker 位于 Git common directory 内，按 thread 隔离，watcher 退出不清除。未来仍需证明老 thread 在后续 turn、watcher 退出甚至 app 重启后都经过同一个已信任的 PreCompact 路径。保护 marker 不是研究生命周期对象，也不是安全边界本身。

## 基线已执行验证

- 最终 `make check`：**40 项 unittest 全部通过**（5.013 秒），另有静态 skill 检查。使用临时真实 Git 仓库与独立进程；token 事件和 hook stdin 是 fixture。包括独立 notes branch、代码工作区保留、显式文件提交、真实失败 pre-commit 保留草稿、跨 worktree 唯一性、并发幂等、绑定拒绝、提醒去重、提醒超时、watcher 崩溃与退出、损坏 guard 状态及生产启动门槛。
- `make demo` 的模拟闭环通过：独立 watcher 进程处理 fixture token 事件，直接调用 hook 后停止；输出明确标为 SIMULATION ONLY。
- 当前 Codex sandbox 禁止 `ps`，首次进程用例明确失败；经宿主批准具体测试命令后，进程用例通过。没有修改全局权限。
- `scripts/check_skill.py`：静态 frontmatter、入口脚本与 Markdown 链接校验；不等于行为验收。
- 官方 `skill-creator/scripts/quick_validate.py` 返回 `Skill is valid!`。系统 Python 缺少 PyYAML，验证器通过 `/tmp` 内的临时 uv 依赖环境运行，没有增加本项目运行依赖。
- `doctor` 真实绑定当前 app 会话并读取最近请求估计，仍返回 `protected:false` 和阻塞项。
- **真实 app 只读监测实测**：当前主 thread 中启用诊断 watcher，验证 host 为实际 app-server 进程且是本执行环境祖先；启动命令返回后 watcher 继续独立运行，`ps` 显示 PPID 1。它自行将最近请求估计从 145,879 更新至 149,838，最终样本 151,532（window 760,000）。再次启用返回相同 PID/nonce。随后显式停止，status 为 stopped/live=false，进程检查确认诊断 PID 已不存在。测试没有模拟 token 输入、没有注入 prompt、没有启用任何 hook，状态全程 `experimental-unprotected`。这证明观察链路；不证明提醒/保护链路。
- 独立 subagent 只读 SKILL.md、convention、ensomi 示例及三个 artifacts，未读旧 transcript/实现源码，能正确说出目标、比较条件反例、容量路径暂缓理由、反馈中怀疑/决定的区别和待回答问题。没有训练、watcher、写文件或再次委派，且明确区分教学样例与真实证据。这是独立材料理解试用，不是 app 中新建 fresh 主会话的验收。

上述结果均为本轮实际执行；任何 mock 通过均不升级平台支持状态。skill 试用 subagent 已结束，诊断 watcher 已退出，没有留下本轮训练任务。

## 放开受保护研究前必须补齐

在一次由人手动创建的**专门测试会话**中，审查项目 hooks 并用 app 原生入口完成 exact-definition trust；保持代码/notes 与真实研究隔离。验收需要同时留存：

1. 当前 app 会话的主 thread/turn 身份与 hook 输入对应，且另 repo/thread/子任务不会误绑定。
2. 自动用量更新使 watcher 过阈值，提醒在**同一主会话**实际进入模型上下文；不调用 turn/start、fork/resume、steer，也不是终端日志假冒通知。
3. 在丢弃用测试会话分别触发 manual 和 auto PreCompact，验证停止发生在 compaction 之前，且没有 compact item/压缩后继续。不得在真实研究会话中做此破坏性风险试验。
4. watcher 退出后的同一旧 thread 仍被阻止 compaction；其他 thread 正常；改变/撤销 hook trust、删除脚本或失去用量时明确失败，不保留“受保护”状态。
5. 主 turn Stop、用户 Interrupt、执行环境退出都清理 watcher；SubagentStop 不误停它，人类停止不被自动 continuation 覆盖。
6. 人手动 fresh，新 agent 不读 transcript，只读两层材料，能发现未提交草稿、过期结论、活动训练和新反馈，并先对齐方向。

当前没有可调用的宿主 hook trust/会话注入接口，也没有已连接到 app-owned stdio 的受支持通道；不能自动代替人信任 hook。故 V1 的生产 `start` 硬性拒绝，不提供填写“verified=true”的开关。只有补齐真实证据并实现可持续检测保护失效的机制，才能修改这个门槛；不以单次成功或设置更大 context 代替。

本次后续验证补充：新握手和配置准备测试覆盖同线程幂等、旧 turn/子线程拒绝、标记不出现在 status、收到回执不等于保护、现有配置保留、项目配置 symlink 防逃逸和 prompt/工具正文不被诊断记录采集；完整测试与官方 skill 校验通过。新增的配置管理查询已退出，没有启动研究或 watcher。独立行为试用确认“loss 新想法但先别打断”不改写当前任务，“马上停”则优先停止并诚实核查 partial result；这仍是只读演练，不是实际训练停止验证。
