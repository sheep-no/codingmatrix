# Agent 子系统架构与市场同类产品对比报告

> 版本：v1.2 | 日期：2026-09-18 | 代码基线：master `9b7c820`
> 范围：仅 Web 端 Agent（Web 前端 + FastAPI 云端 Agent）。桌面端运行时与 VS Code Agent Host 属其他负责范围，仅作形态背景记录，不纳入对标与改进项。
> 本地事实来源：三路只读代码测绘（2026-09-18，行号基于当时工作树）
> 市场事实来源：各产品官方站点（2026-09-18 抓取），见「附录 B」
> 性质：只读调研。本报告不修改任何代码。

## 结论摘要

- 本仓库 Agent 子系统定位为平台内置的代码生成流水线。它的强项在生成前的计划冻结、跨文件契约校验、四级预算、产物原子提交与成功门禁；弱项在交互式 agent 循环、会话级可回放、插件化扩展与服务端执行隔离。
- 架构上存在两套运行时：`OrchestratorCore` 七阶段直线状态机（无 LLM 自主循环）与 `StateGraph` 通用图运行时（条件边/错误边处于休眠）。实际由 `StateGraph` 以单节点外壳承载 legacy/core 二选一。
- 已建成但未接线的能力相当集中：V0-V6 分层验证（`synthesis_validation.py`，714 行）、`MultiModelAgent`、`ContextAssembler` 的 memory/mcp 入参、`ModelGateway`、`workflow_ir` 投影、跨进程恢复工厂、`/modify` 的 core 分支。这些是「能力存在但零消费」，也是与主对标产品差距最集中的地方。
- 对外呈现与真实执行存在一处可复现分歧：`incremental=True` 且未显式指定 engine 时，端点横幅宣称 `engine="core"`，`run_workflow` 实际按 legacy 执行。
- 市场对照分两组。主对标是三个同为云端运行时的产品：OpenHands（Agent Canvas + Agent Server + Sandbox Server 分层，会话经 REST/WebSocket 持久化）、Claude Code on the web（隔离托管 VM + 多端同一引擎 + 子代理/并行会话 + MCP/skills/hooks）、Devin（云端自主 agent + 多 Devin 并行 + 读历史轨迹改进 + 深度集成）。本地形态的 DeepSeek Harness、ZCode、AutoClaw、MiMo Code 仅作背景，本地文件、终端与系统沙箱属形态差异，不计入能力差距。
- 与主对标相比，本仓库在「生成正确性门禁」上更接近工程严谨型，在「harness 内核抽象、会话级持久与恢复、服务端执行隔离、可观测轨迹」上明显落后。
- 最省成本的改进是给已完成的能力接线，并建立「声明能力必须有生产消费方」的验收门禁，防止未接线面继续累积。

## 一、范围与口径

纳入验收：Web 端 Agent，即 Web 前端（Agent 页、SSE 流式、会话与文件状态）与 FastAPI 云端 Agent（代码生成管线、工程师工具调用、MCP、Skills、模型路由、记忆与状态、云端验证）。

不纳入本轮：桌面端运行时与本地执行能力、VS Code Agent Host（属其他负责范围）；Flutter/Dart 客户端（属另一进程任务）；图表编辑器、能力中心独立页、PPT/绘画/工作流独立产物、超管面板。

市场对比口径：以官方公开能力描述为准，未对这些产品做黑盒实测；标注「官方」的条目直接引用官方站点，标注「搜索摘要」的条目来自搜索引擎结果摘要，标注「未核验/未明确」的条目表示本次未取得证据。对标分两组：主对标取同为云端运行时的 OpenHands、Claude Code on the web、Devin；本地运行时产品（DeepSeek Harness、ZCode、AutoClaw、MiMo Code）仅作背景。对比维度取与运行位置无关的编排与计划、生成正确性门禁、记忆与上下文、可观测与可恢复、模型路由、Skills 与扩展机制、服务端执行隔离。本地文件系统、终端与系统级沙箱作为形态背景记录，不计入能力评分。

## 二、本仓库 Agent 子系统架构基线

### 2.1 分层总览

| 层 | 主要模块 | 职责 |
| --- | --- | --- |
| 接入层 | `app/api/v1/ai_agent/orchestrate_endpoints.py`、`generate_endpoints.py`、`agent_host.py` | HTTP/SSE、引擎选择、取消、Agent Host 协议 |
| 编排内核 | `app/agent/orchestration/core.py`、`state_machine.py`、`generation_scheduler.py`、`artifact_committer.py` | 七阶段生命周期、拓扑调度、预算、产物提交 |
| 生成适配 | `app/agent/orchestration/adapters.py`、`orchestrator_generation/*` | traditional/spec-first/incremental 三种模式 |
| 能力层 | `tools.py`、`react_engine.py`、`mcp_client.py`、`skill_registry.py`、`code_validator.py`、`languages/`、`framework_profiles/` | 工具、MCP、Skills、验证、语言与框架画像 |
| 路由与记忆 | `dynamic_model_router.py`、`llm_client.py`、`memory.py`、`context_assembler.py`、`agent_memory_service.py` | 模型选择、并发、记忆、上下文 |
| 状态与持久化 | `app/agent/state/*`、`workflow_registry.py`、`services/agent_state_adapter.py` | State/Delta/reducer/checkpoint、JSON+DB 双写 |

### 2.2 编排内核

控制模型为固定七阶段的管道式编排，无 LLM 自主循环。阶段固定为 CREATED→PLANNING→SCHEDULING→GENERATING→PERSISTING→VALIDATING→FINALIZING（`orchestration/models.py:27`），合法迁移由 `ALLOWED_TRANSITIONS` 约束（`state_machine.py:19`）。事件按 `event_id` 幂等、按 `expected_revision` 做并发冲突检测（`state_machine.py:36`、`state_machine.py:38`）。

第二套运行时 `StateGraph` 具备通用图能力：`max_steps` 上限、节点错误与 `error_edges`、条件路由、`pending_actions` 暂停（`state/graph.py:50`、`graph.py:100`、`graph.py:128`）。但实际接线方式是 `build_legacy_workflow` 构建单节点图，节点内二选一执行 legacy 或 core（`workflow_registry.py:106`、`workflow_registry.py:116`）。条件边与错误边（`graph.py:161`、`graph.py:167`）全仓无调用点，多节点图能力处于休眠。

四级预算已实现并强制单调：`ExecutionBudget` 的 task/stage/file/model_call 必须满足 model_call ≤ file ≤ stage ≤ task，默认 900/600/180/120 秒（`budget.py:18`、`budget.py:30`、`models.py:20`）。但预算感知的模型调用网关 `ModelGateway`（`orchestration/model_gateway.py:28`）除包导出外零引用，预算目前只在调度层生效。

取消链路完整：端点侧 `_cancel_events` 注册、`_cancel_active_generation` 执行、断连监听，workflow 层按 session 取消落盘（`orchestrate_endpoints.py:238`、`:324`、`:367`；`workflow_registry.py:239`）。

### 2.3 三条生成管线

| 管线 | legacy 实现 | core 适配器 | 触发 | 备注 |
| --- | --- | --- | --- | --- |
| traditional | `orchestrator_generation/traditional_generate.py` | `TraditionalAdapter`（`adapters.py:187`） | 默认 | `/orchestrate` 与 `/orchestrate/stream` 可达 |
| spec-first | `spec_first_generate.py`（2689 行） | `SpecFirstAdapter`（`adapters.py:901`） | `spec_first=True` | 规划含拓扑调度（`spec_first_generate.py:1154`） |
| incremental | `incremental_modify.py` + `incremental_generate.py` | `IncrementalAdapter`（`adapters.py:1081`） | `incremental=True` | core 分支在 `/modify` 不可达 |

计划模型分两层：项目级 `GenerationPlan`/`PlanFile`（`generation_plan.py:41`、`generation_plan.py:27`）与 Core 级 `PlannedFile`/`build_file_plan`/`Policy=strict|extensible`（`orchestration/plan.py:18`、`plan.py:46`）。冻结计划后由 `ContractIndex.from_generation_plan` 生成不可变契约索引并写入 digest（`adapters.py:498`、`contract_index.py:38`）。写盘前 `ArtifactCommitter` 校验生成内容声明的 `contract_refs`，未知契约以 `operation_contract_missing` 阻止落盘。

产物提交是这套内核最扎实的部分：原子写（mkstemp→fsync→os.replace，`orchestration/store.py:41`）、磁盘回读、SHA-256、清单登记、成功门禁比较计划/事件/清单/磁盘四集合（`core.py:222`、`core.py:253`）。增量路径额外用 `IncrementalFileTransaction` 做 stage/commit/rollback，并检查未在变更计划内的文件是否被改动（`file_transaction.py:13`、`core.py:146`、`core.py:176`、`core.py:269`）。

### 2.4 能力层

工具体系：`SPECIALIST_TOOLS` 共 20 个（读/写/执行/Git/网络/删除六类，`tools.py:1230`），由 `ToolRegistry` 与 `EnhancedExecutor` 注册（`executor.py:84`、`executor.py:200`）。执行循环是统一 `ReActEngine`，simple 模式为 Thought→Tool→Result，full 模式增加 Reflection，并在 full 模式写入进程内 `AgentMemory`（`react_engine.py:449`、`react_engine.py:589`、`react_engine.py:798`）。安全边界包括写路径白名单、`_safe_join`、`run_command` 前缀白名单与 `shell=False`、`http_request` 的私网地址拒绝（`tools.py:18`、`tools.py:35`、`tools.py:629`、`tools.py:1134`）。

MCP：支持 stdio 与 http 两种 transport，全局配置文件 `data/mcp_servers.json`，工具名加 `mcp_{server}_{tool}` 前缀（`mcp_client.py:5`、`mcp_client.py:29`、`mcp_client.py:355`）。当前 4 个 server 全部 `enabled:false`，且 `EnhancedExecutor.load_mcp_tools` 全仓无调用点（`data/mcp_servers.json:4`；`executor.py:157`）。配置为全局单文件，无用户/工作区分区；管理接口要求超级管理员（`mcp_admin.py:75`）。结论：MCP 能力已实现，默认未加载。

Skills：三级命名空间 system/user/workspace，User Skills 按 `owner_user_id` 隔离，workspace 扫描 `.claude/skills`，配额 50/用户（`skill_registry.py:22`、`skill_registry.py:72`、`skill_registry.py:274`；`custom_skill_manager.py:32`、`custom_skill_manager.py:92`）。Skill 以 Markdown 内容注入角色 Prompt，可按需求关键词发现；Host 侧 `skill_runtime` 分派显式 `unsupported_capability`，即技能不可执行（`tool-dispatcher.ts:107`）。

沙箱：当前实际生效的是语法级门禁（Python `ast.parse`、JS/TS 走 `js_syntax`、HTML/CSS 走 `markup_syntax`，`utils.py:682`），Go/Rust 编译器验证在 bwrap 可用时执行、缺失时跳过并判过（`utils.py:801`、`utils.py:821`）。`execute_code` 工具是同机子进程加正则黑名单，`run_command` 在服务端进程内执行（`tools.py:508`、`react_engine.py:216`）。隔离现状与记忆中的沙箱决策一致（docker 整体移除、bwrap 近似废弃、只保留语法验证）：服务端执行工具是 Web 端 Agent 的主要安全边界。

Agent Host（跨范围，仅记录 Web 端出口侧事实）：协议完整。handshake 校验 capability 与 protocol version 1，默认策略 `local_execution_enabled=true`、`auto_approve=false`（`agent_host.py:239`、`agent_host.py:253`）；动作分发 GET actions/ack、结果回传 POST events 触发 `resume_workflow_from_local_result`、policy 乐观版本控制（`agent_host.py:338`、`agent_host.py:367`、`agent_host.py:445`）。Host 侧 `ValidationRunner` 用 `spawn(shell:false)` 执行、输出上限 64KB、超时 SIGTERM（`validation-runner.ts:74`）。宿主侧实现属 VS Code 插件负责范围。

验证体系：写入门禁在三条路径调用 `validate_file_in_sandbox`（`utils.py:159`、`utils.py:192`、`utils.py:230`）；云端报告 `ValidationReport` 固定 scope 为 `cloud_syntax`（`validation_report.py:70`、`orchestrator_files.py:2424`）；修复路由 `RepairBudget(per_category_limit=3, total_limit=5)` 已接入错误恢复（`repair_router.py:19`、`error_recovery.py:163`）。Core 的 VALIDATING 阶段是常量占位 `waiting_local_validation`，真实验证责任显式转交本地 Agent Host（`core.py:265`、`core.py:267`）。

### 2.5 模型路由、记忆与状态

模型路由：`DynamicModelRouter` 按成功率 50、延迟 30、队列深度 20 三因子评分，探索率 0.2，按 `consecutive_failures` 熔断，fallback 链来自配置（`dynamic_model_router.py:461`、`dynamic_model_router.py:336`、`dynamic_model_router.py:246`、`dynamic_model_router.py:526`）。性能表落 SQLite。分层角色路由 `LayeredModelRouter.get_assignment()` 由生成 mixin 调用（`orchestrator_generation/mixin.py:61`）。

LLM 调用：`app/agent/llm_client.py` 提供全局并发 6 与按模型并发（默认 2），并有按模型覆盖表 `MODEL_CONCURRENCY_LIMITS`（`llm_client.py:29`、`llm_client.py:30`、`llm_client.py:36`）；双信号量在 `get_global_semaphore`/`get_model_semaphore`（`llm_client.py:43`、`llm_client.py:67`）。底层统一走 `app/utils/aicloud/llm_caller.py` 与 httpx 共享客户端，429 重试 3 次、15-60s 冷却、300s 超时（`llm_caller.py:120`、`http_client.py:37`、`http_client.py:54`）。

记忆：进程内 `AgentMemory`（ConversationMemory/KnowledgeMemory/ReflectionMemory）按 session 隔离，语义检索阈值 0.65，`get_context_for_prompt(max_tokens=4000)` 被 full 模式 ReAct 消费（`memory.py:86`、`memory.py:469`、`react_engine.py:840`）。其 `save_to_storage`/`load_from_storage` 全仓无调用点，即进程内记忆没有持久化调用（`memory.py:525`、`memory.py:548`）。DB 记忆由 `AgentMemoryService` 按 user/session 隔离，经 knowledge 端点读写（`agent_memory_service.py:30`、`knowledge_endpoints.py:7`）。存在一处契约不一致：`add_knowledge` 无 `tags` 形参却被以 `tags=` 调用，运行期会抛 `TypeError`（`agent_memory_service.py:176`、`knowledge_endpoints.py:26`）。

上下文：`ContextAssembler.assemble()` 输出带来源/优先级/作用域/内容 hash 的 `ContextEnvelope`，含字符预算与密钥脱敏（`context_assembler.py:80`、`context_assembler.py:88`、`context_assembler.py:188`）。生产调用有 4 处，但均只喂部分参数；`memory_entries` 与 `mcp_tools` 两个入参无任何调用点，`SkillPolicy`/`MCPToolDescriptor` 无生产消费方（`context_assembler.py:96`、`context_assembler.py:97`、`context_assembler.py:51`、`context_assembler.py:63`）。即上下文工程框架已建，记忆与 MCP 维度尚未接入。

状态与持久化：State/StateDelta/reducer 具备 revision 校验与 event_id 幂等（`state/reducer.py:19`）；本地 checkpoint 原子 JSON 写入（`state/checkpoint.py:18`、`checkpoint.py:30`）；workflow 层同时写本地 JSON 与 DB，DB 失败仅记日志（`workflow_registry.py:178`、`workflow_registry.py:182`）。DB 侧 `checkpoints.task_id` 外键指向 `tasks(task_id)`，但 `app/models/task.py:44` 声明的 `task_id` 唯一性在实际 DB 中不存在（`PRAGMA index_list(tasks)` 为空），导致 `foreign_key_check` 报 `foreign key mismatch`，级联约束实际未生效；这也解释了 `persist_agent_state` 的失败。

多模型协同：`MultiModelAgent` 已实现（五角色路由 + 全局信号量，`multi_model_agent.py:48`、`multi_model_agent.py:82`），但唯一引用是导入语句与包导出，主链路未调用（`orchestrate_endpoints.py:28`、`agent/__init__.py:18`）。

评测：`evaluation_matrix.py` 定义 `EvaluationRecord` 的 compile/tests/startup/persistence 四项合取与分层判定 `core_passed`/`engineering_passed`/`stage_success`，`build_report()` 做缺失/重复/非法校验并输出分类失败与策略汇总（`evaluation_matrix.py:62`、`evaluation_matrix.py:71`、`evaluation_matrix.py:76`、`evaluation_matrix.py:87`、`evaluation_matrix.py:260`）。运行器为 `tests/manual/run_core_evaluation_matrix.py`（24 用例，带 checkpoint）。

### 2.6 实现状态三态清单

已实现且已接线（关键项）：

| 能力 | 证据 |
| --- | --- |
| Core 七阶段状态机与事件幂等 | `orchestration/models.py:27`、`state_machine.py:19` |
| 三适配器与 `execute_core_generation` | `adapters.py:187`、`adapters.py:901`、`adapters.py:1081`、`runtime.py:29` |
| 冻结计划与契约索引 | `adapters.py:489`、`contract_index.py:38` |
| 拓扑调度与四级预算 | `generation_scheduler.py:25`、`budget.py:18` |
| 原子提交与成功门禁 | `artifact_committer.py:31`、`core.py:253` |
| 增量文件事务 stage/commit/rollback | `file_transaction.py:13`、`core.py:146` |
| ReAct 工具循环（simple/full） | `react_engine.py:449`、`react_engine.py:589` |
| Skills 三级命名空间与按 owner 隔离 | `skill_registry.py:22`、`custom_skill_manager.py:92` |
| 云端语法门禁与写入门禁 | `utils.py:682`、`utils.py:159` |
| 修复路由与预算 | `repair_router.py:19`、`error_recovery.py:163` |
| Agent Host 协议与本地结果归并 | `agent_host.py:239`、`local_validation_adapter.py:22` |
| 动态模型路由与熔断 | `dynamic_model_router.py:461`、`dynamic_model_router.py:246` |
| 上下文装配（部分入参） | `context_assembler.py:88` |

已声明但未接线（能力存在、生产零消费）：

| 能力 | 证据 | 影响 |
| --- | --- | --- |
| V0-V6 分层候选验证全套 | `synthesis_validation.py:245`、`:332`、`:472`、`:506`、`:573` | 最完整的验证设计未参与生成 |
| `MultiModelAgent` 多角色协同 | `multi_model_agent.py:48` | 多模型协同停留在单文件分工 |
| `ContextAssembler` 的 memory/mcp 入参 | `context_assembler.py:96`、`:97` | 上下文缺记忆与工具描述 |
| `ModelGateway` 预算感知调用 | `orchestration/model_gateway.py:28` | 模型调用不受四级预算约束 |
| `WorkflowIR` 投影与读取 | `core.py:195`、`:210` | IR 写入 state metadata 后无读取方 |
| 跨进程恢复工厂注册 | `workflow_registry.py:49` | 重启恢复退化为异常路径 |
| StateGraph 条件边/错误边 | `state/graph.py:161`、`:167` | 图能力仅单节点外壳 |
| `/modify` 的 core 分支 | `orchestrate_endpoints.py:671` | 增量 core 不可达，恒走 legacy |
| `/generate` 的 core 语义 | `generate_endpoints.py:93` | core_handler 为透传 |
| `EnhancedExecutor.load_mcp_tools` | `executor.py:157` | MCP 无有效加载入口 |
| `AgentMemory` 持久化 | `memory.py:525`、`:548` | 记忆不跨进程 |
| `ValidationCoordinator.execute`/`to_report` | `validation_coordinator.py:82` | 仅 build_plan 被使用 |
| `stack_adapters` 注册表探测 | `stack_adapters/registry.py` | 官方脚手架路径运行时不可达 |
| framework_profiles 校验与 workspace 画像 | `framework_profiles/validation.py`、`workspace.py` | 仅测试引用 |

死代码/兼容残留（关键项）：`app/agent/nodes/*` 四个节点包装器、`orchestration/ir_projection.py:16 project_change_plan`、`engine_router.py` 的 `route_generation`/`compare_shadow_results`、`adapters/spec_first_adapter.py`/`event_adapter.py`/`session_adapter.py` 的导出符号、两份 `CodeValidator`（`code_validator.py:94` 与 `app/utils/agent_core.py:352`）。

已确认的行为分歧：`incremental=True` 且未显式指定 engine 时，`_pipeline_mode_payload` 对外宣称 `engine="core"`（`orchestrate_endpoints.py:56`），而 `run_workflow` 在无 `engine` 键时按 legacy 执行（`workflow_registry.py:158`、`routing.py:16`）。

## 三、市场同类产品基线

本章分两组。3.1 至 3.3 的运行时在云端，与本仓库部署形态一致，构成主对标；3.4 至 3.7 的运行时在本地（CLI 或桌面应用），其本地文件、终端与系统沙箱属部署形态差异，仅作背景记录，不参与能力对标。

### 3.1 OpenHands（官方）

定位是开源软件工程 agent 平台，提供 GUI、CLI、SDK 与企业控制面。组件分层清晰：Agent Canvas 是开源浏览器客户端与控制中心，可连接一个或多个 Agent Server 后端；Software Agent SDK 是可组合的 Python 库，同仓的 Agent Server 通过 REST 与 WebSocket API 暴露 agent 执行、会话、工具与工作区；Sandbox Server 是独立的 API 与沙箱控制面，创建并管理承载 Agent Server 的沙箱环境；Automation Server 负责定时与事件驱动的自动化生命周期（官方）。OpenHands Cloud 是托管商业服务，提供托管执行、集成、协作、访问控制、用量报表与预算管理（官方）。旧的 Docker 本地 GUI 已归档。

### 3.2 Claude Code on the web（官方）

云会话运行在云端基础设施上，关闭笔记本后仍在运行，可从任意设备查看与干预（官方）。同一引擎在终端、IDE、桌面与 Web 多端共用，仓库里的 `CLAUDE.md`、设置与 MCP server 在各端通用（官方）。云端能力面：云环境统一控制网络访问、环境变量与 setup 脚本；project 负责协调并行云会话；`--cloud` 与 `--teleport` 支持终端与云端单向交接；子代理按 `.claude/agents/` 自动加载，agent teams 为实验特性；skills、hooks、`/context`、`/compact` 与自动压缩可用；会话带 diff 审阅与行内评论，并支持 PR 自动修复，订阅 GitHub 事件以响应 CI 失败与 review 评论（官方）。

隔离层明确：每个会话运行在隔离的托管 VM 中，网络访问默认受限且可关闭，git 凭据与签名密钥留在沙箱之外、由代理以受限凭据代认证，API 凭据同样不进入沙箱（官方）。限制：会话在一段时间不活动后回收，重开时恢复对话历史，当时仍在运行的后台工作（子代理、shell 命令）不恢复（官方）。

### 3.3 Devin（官方）

云端 AI 软件工程师，通过 `app.devin.ai` 使用。能力面覆盖 PR 审阅与视觉 QA（含浏览器与桌面操作）、用 DeepWiki 自动生成文档与系统图、并行迁移多仓库、定时杂务、Issue 分诊（Datadog 告警、Slack 报告、CI 失败）、单元与 E2E 测试、浏览器任务自动化（官方）。协作层：学习代码库与团队隐性知识，支持多周多仓库项目，可为一个大型任务拉起一组 Devin，并通过阅读历史会话轨迹持续改进；集成 GitHub、Linear、Slack/Teams 等，并提供 Devin API 与 Devin Automations（官方）。每一步都提供完整可审计性（官方）。

### 3.4 背景：DeepSeek Harness（dsh，官方）

定位是开源 agent harness（MIT），「Agent = Model + Harness」。内核是 Cordis 插件系统，模型、工具、技能、会话、沙箱、存储、循环、调度与 UI 全部是可替换插件，通过配置组合而无需改源码（官方）。运行时在本地。

关键设计：每次运行的输入全部写入 append-only 会话日志，覆盖 system prompt、推理、工具调用与结果、子代理调度与每次上下文注入；Trajectory 视图按来源检查这些记录；resume、fork、search、replay 都基于同一事件流（官方）。运行时模式有 Standard（完整工具集）、Code（用模型生成代码编排多轮工具调用）、Minimal（仅 shell + 文件编辑器，用于基准测试）、Creator（运行时检视、内存中试插件、组合新模式）（官方）。安装为 `npx @deepseek-ai/dsh web`（官方）。

### 3.5 背景：智谱 ZCode（官方）

定位是 GLM-5.3 官方 Harness 与 Agentic Development Environment（ADE），Electron 桌面应用，覆盖 macOS/Windows/Linux（`zcode.z.ai`）。能力点是 Goals 长任务（持续规划、执行与验证）、多智能体协作、从微信/飞书/Telegram 远程操控（Bot control）、GLM-5.3 深度集成与 GLM-5.3-Flash 多模态（截图理解/图像分析）、Skills、终端与 Git 工具（官方）。产品界面展示任务分解、逐条 todo 进度、tokens 统计与 Undo/Changes 审阅（官方页面示例）。

### 3.6 背景：智谱 AutoClaw（澳龙，官方）

定位是面向办公的桌面 AI agent，把 AI 助手、办公自动化、浏览器自动化与 IM 协作放进一个桌面应用。核心能力是 50+ 内置技能（Word/Excel/PPT/报告/会议纪要/图表）、浏览器自动化（表单、截图、采集、定时任务）、网页产品构建（需求到可运行前端并浏览器预览）、IM 集成（Slack/Telegram/WhatsApp/Lark 内 @ 助手指派任务）与模型切换（GLM/DeepSeek）（官方）。安装即用，无需配置开发环境或命令行工具链（官方）。

### 3.7 背景：小米 MiMo / MiMo Code（官方 + 搜索摘要）

MiMo 是小米的模型与助手品牌，桌面客户端 MiMo Desktop 处于内测资格申请阶段（官方申请页）。旗舰模型 MiMo-V2.5-Pro 面向真实 agentic 负载，并与 OpenClaw 深度适配，支持多模态识别与语音（官方 Studio 页）。社区教程显示「MiMo Code」是面向普通用户（含非程序员）的桌面 AI 助手型编码工具（搜索摘要，未做实测）。

## 四、能力矩阵

图例：`已接线` 表示本仓库有生产消费方；`未接线` 表示已实现无消费；`无` 表示未发现；`官方` 表示对方官方公开；`未核验` 表示本次未取得官方或实测证据；`未明确` 表示官方未公开说明。

### 4.1 主对标：云端/Web 形态

与本仓库同为云端运行时，能力可直接对比。

| 维度 | 本仓库 Agent | OpenHands | Claude Code on the web | Devin |
| --- | --- | --- | --- | --- |
| 控制模型 | 固定七阶段管道，无 LLM 自主循环 | agent 循环 + SDK/Server 分层（官方） | agent 循环，多端共用同一引擎（官方） | 自主云 agent，覆盖多周多仓库项目（官方） |
| 计划与调度 | 冻结计划 + 拓扑调度 + 四级预算（已接线） | Automation Server 定时与事件驱动（官方） | plan mode；project 协调并行会话；Routines 云端定时/API/GitHub 触发（官方） | 计划并执行复杂任务；Automations 调度（官方） |
| 工具生态 | 20 内置 + ReAct（已接线） | SDK 工具 + 工作区，Canvas 为客户端（官方） | 完整 CLI 工具集 + Chrome + MCP（官方） | 浏览器与桌面操作；官方称可对接数百种工具，含 API（官方） |
| MCP | 已实现，4 server 全 disabled，无加载入口 | 未核验 | 原生 MCP，跨端通用（官方） | 未核验 |
| Skills/插件 | 三级命名空间，Markdown 注入，不可执行 | SDK 为可组合 Python 库（官方） | skills + hooks + plugins（官方） | 集成体系与文档生成；技能模型未明确（官方） |
| 子代理/并行 | MultiModelAgent 未接线 | 一个 Canvas 连接多个 Agent Server（官方） | 子代理 + agent teams（实验）+ background agents + 并行会话（官方） | 一组 Devin 并行（官方） |
| 记忆 | 进程内记忆已用，持久化未接线；DB 记忆有契约缺陷 | conversations 由 Agent Server 持久化（官方） | CLAUDE.md + auto memory（官方） | 学习代码库与隐性知识，读历史会话轨迹（官方） |
| 上下文工程 | ContextEnvelope 已建，memory/mcp 未接入 | 未核验 | `/context`、`/compact`、自动压缩（官方） | 未核验 |
| 可恢复/replay | checkpoint 有，跨进程恢复未接线 | conversations 经 REST/WebSocket 暴露，replay 未明确（官方） | 会话持久，环境回收后恢复对话历史，后台工作不恢复（官方） | 基于历史 session trajectories（官方） |
| 可观测性 | SSE 事件 + 进度事件 | Canvas 控制中心 + 用量报表与预算（官方） | 会话 diff + 行内评论；PR 自动修复订阅 GitHub 事件（官方） | 每步可审计，PR 审阅（官方） |
| 服务端执行隔离 | 语法门禁；工具在服务端进程内执行 | 独立沙箱控制面，承载沙箱环境（官方） | 隔离托管 VM；网络访问受限；凭据留在沙箱外（官方） | 云运行时；隔离机制未明确（官方） |
| 多模型路由 | 动态评分 + 熔断 + fallback（已接线） | 企业级模型控制（官方） | 会话级 `/model` 切换（官方） | 未核验 |
| 远程/IM 触点 | 无 | 未明确 | Slack、移动端、Remote Control、Channels（Telegram/Discord/iMessage/webhook）（官方） | Slack/Teams/Linear/GitHub（官方） |

### 4.2 背景：本地形态

运行时在本地，本地文件、终端与系统沙箱属形态差异。本表仅记录产品原貌，不用于能力打分。

| 维度 | DeepSeek Harness | ZCode | AutoClaw | MiMo Code |
| --- | --- | --- | --- | --- |
| 控制模型 | 可插拔 loop 插件 | Goals 长任务持续规划/执行/验证（官方） | 目标驱动逐步执行（官方） | agentic 模型驱动（官方） |
| 计划与调度 | 调度为插件（官方） | 任务分解 + todo（官方） | 多步任务分解（官方） | 未核验 |
| 工具生态 | 工具即插件（官方） | 内置终端/Git 等（官方） | 浏览器/办公/文件（官方） | 未核验 |
| MCP | 插件体系可承载（官方） | 未明确 | 未明确 | OpenClaw 生态（官方） |
| Skills/插件 | 一切皆插件，可执行可组合（官方） | Skills（官方） | 50+ 预置技能（官方） | 未核验 |
| 子代理 | subagent scheduling 入日志（官方） | 多智能体协作（官方） | 未明确 | 未核验 |
| 记忆与可恢复 | append-only 会话日志，resume/fork/replay（官方） | 会话恢复（官方页面示例） | 未明确 | 未核验 |
| 远程/IM 触点 | 未明确 | 微信/飞书/Telegram（官方） | Slack/Telegram/WhatsApp/Lark（官方） | 未核验 |

## 五、关键差异

### 5.1 相对优势

- 生成正确性门禁强于同类：冻结文件集、跨文件契约索引、`contract_refs` 落盘前校验、四级预算、原子提交与四集合成功门禁，这套组合在市场产品中较少见到同等级别的工程约束。
- 增量修改有真实事务语义：stage/commit/rollback 加未授权变更检测，对「只改受影响的文件」有结构性保障。
- 多语言与框架画像体系完整：语言 Adapter、Framework Profile、Profile bridge、Toolchain 探测覆盖 Python/JS/TS/Java/Go/Rust 与多框架，且命令以参数数组 + `shell=false` 执行。
- 模型路由具备运行时自适应：成功率/延迟/队列三因子评分、探索率、熔断、按模型并发覆盖，比固定角色映射更接近生产级调度。
- 修复闭环有预算与分类：`RepairRouter` 按错误类别路由自动修复，`RepairBudget` 限制单类 3 次、累计 5 次，避免无限重试。

### 5.2 结构性差距

按严重度排序，均为事实性差距，不含主观评分。

1. 能力建成但未接线，形成「纸面能力」。（高）
V0-V6 分层验证 714 行零消费、`MultiModelAgent` 零调用、`ModelGateway` 未挂入 Core、`ContextAssembler` 的记忆与 MCP 入参无人传、`WorkflowIR` 写入后无读取、跨进程恢复工厂无注册方。对比 OpenHands 把 agent 执行、会话、工具、工作区拆成可组合 SDK 与 REST/WebSocket 服务，以及 Claude Code on the web 的子代理、skills、hooks、MCP 都有真实消费入口，本仓库这批模块停在「写好了但没接上」。

2. 对外声明与真实执行不一致。（高）
`incremental=True` 时横幅宣称 core、实际走 legacy，且 `/modify` 的 core 分支不可达、`/generate` 的 core_handler 为透传。这会让上层 UI 与验收结论失真，也给后续排障制造假象。

3. 缺少 append-only 会话日志与 replay/fork。（高）
本仓库有 checkpoint 与 SSE 事件，但没有「模型所见全部输入」的单一事件流。主对标两家都把会话做成持久资产：OpenHands 由 Agent Server 通过 REST/WebSocket 暴露 conversations，Claude Code on the web 在环境回收后仍恢复对话历史。本仓库的 checkpoint 是本地 JSON 文件且跨进程恢复未接线，因此缺少问题复盘、回归取证与「从某一步分叉重跑」的能力。

4. 内核不可插件化。（中高）
本仓库的能力以硬编码注册表与继承 mixin 组织（`SPECIALIST_TOOLS`、六个 generation mixin、固定阶段枚举）。主对标里 OpenHands 用可组合 SDK 与独立 Server 组合能力，Claude Code on the web 用 skills、hooks、plugins 与 `.claude/agents/` 扩展；背景组的 DSh 更进一步，把模型/工具/技能/会话/沙箱/存储/循环/调度/UI 全部外置为 Cordis 插件。扩展新能力在本仓库需要改核心代码。

5. 服务端执行工具缺少隔离边界。（中高）
`execute_code` 与 `run_command` 在服务端进程内执行，依赖正则黑名单与命令前缀白名单。主对标里这一层是硬约束：OpenHands 用独立 Sandbox Server 创建与管理沙箱环境，Claude Code on the web 每个会话跑在隔离托管 VM 中、网络访问默认受限、git 与 API 凭据留在沙箱之外。Web 端 Agent 的等价安全边界应落在服务端 runner 上，当前缺少资源上限与文件系统边界，属本职范围内的真实风险。本地宿主侧的执行与审批策略归 VS Code 负责范围。

6. 本地验证出口链路依赖 VS Code Agent Host。（边界记录，跨范围）
云端下发的本地验证动作缺 `command`/`working_directory`/`timeout_seconds`/`operation`/`validation_scope`/`event_id`，Host 的 `parsePendingAction` 强制要求这些字段，端到端当前无法解析。Web 端出口侧的可控部分是把动作字段补全，实际打通需与 VS Code 插件侧协同，不作为本轮 Web 端改造项。

7. 记忆与会话状态没有统一归属。（中）
进程内记忆按 session 且不持久化，DB 记忆按 user/session 但存在 `tags` 契约缺陷，`persist_agent_state` 又受 `checkpoints`→`tasks` 外键不匹配影响。主对标里 Claude Code on the web 用 `CLAUDE.md` 加 auto memory，OpenHands 由 Agent Server 持久化 conversations，状态都有单源归属；本仓库的状态源分散在 JSON checkpoint、SQL 事件表与进程内对象三处。

8. 观测面偏向开发者日志，缺产品级轨迹。（中）
有 SSE 进度事件与事件表，但缺少按「模型所见来源」组织的轨迹视图。主对标里 Claude Code on the web 有会话 diff 与行内评论，Devin 强调每一步完整可审计；背景组的 DSh 有按来源检视的 Trajectory 视图。本仓库的观测面仍以开发者日志为主。

9. 冗余与双轨仍在累积。（中低）
两份 `CodeValidator`、两套模型静态枚举、`nodes/*` 死包装器、`ir_projection`/`engine_router` 死符号、多份图片/沙箱相关清单并存，都会提高后续接线的误伤概率。

## 六、改进建议

### 6.1 短期：先接线，不新造（P0）

1. 补齐本地验证出口字段（Web 端可控部分）。云端 pending action 需要携带 `command`/`working_directory`/`timeout_seconds`/`operation`/`validation_scope`/`event_id`，或在协议层约定「云端给语义、宿主侧补命令」；实际打通依赖 VS Code 插件侧协同。
2. 消除引擎展示与执行分歧。让 `_pipeline_mode_payload` 与实际 `select_engine` 结果同源，或在 `run_incremental_core` 路径显式写入 `engine`。
3. 给已建能力选定明确归宿：`MultiModelAgent`、`ModelGateway`、V0-V6、`WorkflowIR` 读取、跨进程恢复工厂，各自要么接线，要么标记「实验性、无生产消费」并从默认路径剔除，避免继续被当作已完成能力。
4. 修复记忆契约与状态持久化。修正 `add_knowledge` 的 `tags` 契约；修复 `tasks.task_id` 唯一索引（Alembic 迁移补唯一约束）以恢复 `checkpoints` 外键级联。

### 6.2 中期：补内核抽象（P1）

1. 引入单一 append-only 会话事件日志，作为系统 prompt、上下文注入、工具调用与结果的唯一记录源；resume/replay/fork 都读同一流。现有 SSE 事件与 checkpoint 可作为该日志的投影，不必推倒重来。参照 OpenHands 由 Agent Server 持久化 conversations、Claude Code on the web 在环境回收后恢复对话历史。
2. 把工具、Skills、MCP server、模型 provider 抽象为可注册插件，至少先做到「新增工具/Skill 不需要改核心注册表」。主对标对照面是 OpenHands 的可组合 SDK 与 Claude Code on the web 的 skills/hooks/plugins 加 `.claude/agents/`。
3. 建立产品级轨迹视图，按来源（需求/计划/契约/检索/记忆/工具结果）展示模型所见内容，复用现有 `ContextEnvelope` 的 source/scope/hash 字段。
4. 为服务端执行补最小隔离：把 `execute_code`/`run_command` 收敛到统一 runner，复用 `IsolatedTestRunner` 的 venv 隔离与 Toolchain 的参数数组契约，并按记忆中的运行时差异施加资源上限（Python `RLIMIT_AS`、Node `--max-old-space-size`、Go `GOMEMLIMIT`）。主对标对照面是 OpenHands 的 Sandbox Server 与 Claude Code on the web 的隔离 VM 加凭据外置。本地宿主执行不在本轮范围。

### 6.3 治理：防止继续累积（P1/P2）

1. 增加「声明能力必须有生产消费方」的检查：对新增模块/导出符号，CI 校验存在非测试调用点，或显式登记为实验性。
2. 收敛双轨：两份 `CodeValidator`、静态 `ModelRouter` 与 `DynamicModelRouter`、`nodes/*` 与 `orchestration/*`，每类保留一条主轨。
3. 把本次测绘的三态清单固化为可复跑的脚本（引用计数 + 路由挂载检查），避免人工清单过期。

## 七、验收与后续验证建议

- 本轮为只读测绘，所有结论需在改动后重新验证；「已接线」判定应以生产调用点与路由挂载为准，不以模块是否存在为准。
- 引擎分歧、记忆契约与服务端执行隔离三项建议优先做确定性探针（不依赖 LLM 与 Playwright），先复现再修；本地验证出口字段属跨范围，先在 Web 端固定出口契约。
- 涉及 Agent 主链路改动后，按项目约定跑定向测试加全量 `python3 -m pytest -q -p no:randomly`，并核对失败集合与既有基线一致。
- 市场能力条目中标注「未核验/未明确」的部分，若需作为选型依据，应补充官方文档或实测。

## 附录 A：本地证据索引

| 主题 | 文件 |
| --- | --- |
| 编排阶段机 | `app/agent/orchestration/models.py`、`state_machine.py`、`core.py` |
| 图运行时 | `app/agent/state/graph.py`、`reducer.py`、`checkpoint.py` |
| 计划与契约 | `app/agent/orchestration/plan.py`、`app/agent/contract_index.py` |
| 调度与预算 | `app/agent/orchestration/generation_scheduler.py`、`budget.py` |
| 产物提交与事务 | `app/agent/orchestration/artifact_committer.py`、`file_transaction.py` |
| 适配器 | `app/agent/orchestration/adapters.py` |
| 三管线 | `app/agent/orchestrator_generation/{traditional_generate,spec_first_generate,incremental_modify,incremental_generate}.py` |
| 工作流注册 | `app/agent/workflow_registry.py`、`app/agent/orchestration/routing.py` |
| 工具与 ReAct | `app/agent/tools.py`、`react_engine.py`、`executor.py` |
| MCP | `app/agent/mcp_client.py`、`data/mcp_servers.json`、`app/api/v2/mcp_admin.py` |
| Skills | `app/services/skill_registry.py`、`custom_skill_manager.py` |
| 沙箱与语法门禁 | `app/agent/utils.py`、`app/agent/test_runner.py` |
| Agent Host（跨范围，仅后端出口侧） | `app/api/v1/agent_host.py`、`vscode-extension/src/{protocol,tool-dispatcher,validation-runner,agent-host-runtime}.ts` |
| 验证与修复 | `app/agent/code_validator.py`、`synthesis_validation.py`、`repair_router.py`、`error_recovery.py` |
| 模型路由与调用 | `app/agent/dynamic_model_router.py`、`llm_client.py`、`app/utils/aicloud/llm_caller.py`、`http_client.py` |
| 记忆与上下文 | `app/agent/memory.py`、`context_assembler.py`、`app/services/agent_memory_service.py` |
| 状态持久化 | `app/services/agent_state_adapter.py`、`app/models/task.py`、`app/db/database.py` |
| 评测 | `app/agent/evaluation_matrix.py`、`tests/manual/run_core_evaluation_matrix.py` |
| 整体架构 | `.monkeycode/docs/ARCHITECTURE.md` |

## 附录 B：市场事实来源

| 产品 | 来源 |
| --- | --- |
| OpenHands | `https://www.all-hands.dev/`、`https://docs.openhands.dev/` |
| Claude Code on the web | `https://docs.claude.com/en/docs/claude-code/overview`、`https://docs.claude.com/en/docs/claude-code/claude-code-on-the-web` |
| Devin | `https://devin.ai/` |
| DeepSeek Harness（背景） | `https://www.deepseek.com/harness/en/`、`https://github.com/deepseek-ai/deepseek-harness` |
| ZCode | `https://zcode.z.ai/en` |
| AutoClaw | `https://autoclaw.z.ai/`、`https://autoclaw.zhipuai.cn/` |
| MiMo / MiMo Desktop | `https://mimo.xiaomimimo.com/desktop/invite/apply/`、`https://aistudio.xiaomimimo.com/`、社区教程（搜索摘要） |

> 抓取日期：2026-09-18。市场产品处于快速迭代期，引用前请复核官方页面。
