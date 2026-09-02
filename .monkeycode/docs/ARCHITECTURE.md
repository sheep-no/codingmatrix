# AI Backend Architecture

## 概述

本项目是基于 FastAPI 的 AI 编程后端，提供项目生成、项目修改、编排执行、模型路由、会话管理和代码验证能力。Agent 能力由传统 Agent、Spec-first、依赖图、拓扑调度和 ReAct 工具链组成。StateGraph 迁移层以统一 State、StateDelta、checkpoint 和事件适配器连接现有能力。

## 技术栈

- Python 3.11（开发与测试约定）；当前 Dockerfile 使用 Python 3.10，部署环境存在版本分裂
- FastAPI、Pydantic、SQLAlchemy、Celery
- SQLite/PostgreSQL 数据访问与 Redis 会话缓存
- pytest、pytest-asyncio
- FAISS/VectorIndex 与外部模型、知识检索服务

## 项目结构

```text
app/
├── api/                 # HTTP 路由和请求模型
├── agent/               # Agent、编排、工具、验证和状态图
│   ├── state/            # State、reducer、checkpoint、graph runtime
│   ├── nodes/            # Spec-first、依赖、拓扑、验证节点
│   ├── adapters/         # legacy、事件、session 和 Spec-first 适配器
│   └── retrieval/        # 统一检索契约和服务
├── db/                  # 数据库模型与服务
├── services/             # 业务服务
└── utils/                # 公共工具与模型路由
tests/unit/               # 单元测试
```

## 请求执行

```mermaid
flowchart LR
    Client["客户端"] --> API["FastAPI Agent API"]
    API --> Wrapper["Legacy workflow wrapper"]
    Wrapper --> Graph["StateGraph runtime"]
    Graph --> Agent["现有 Agent 能力"]
    Graph --> State["State reducer"]
    State --> Event["事件适配器与现有 SSE/WS 出口"]
    State --> Checkpoint["Checkpoint 基础能力"]
```

`generate`、`modify`、同步 `orchestrate` 和流式 `orchestrate/stream` 已通过 `build_legacy_workflow` 运行。当前每个入口使用一个 `legacy_agent` 节点包装既有 Agent 结果，并保留原有响应与事件结构。Spec-first、RAG、依赖图、拓扑、验证和恢复能力仍处于渐进迁移阶段，生产入口尚未组成完整多阶段 StateGraph。

## Orchestrator Core 目标架构

多语言代码生成主规格规划使用 `OrchestratorCore` 收敛传统生成、Spec-First 和增量修改的任务生命周期。现有 `OrchestratorAgent` 将保留入口兼容职责，三类生成模式通过适配器提供计划和单文件生成能力。目标生命周期为 `planning`、`scheduling`、`generating`、`persisting`、`validating`、`finalizing`，并统一收敛到完成、失败、超时或取消终态。

```mermaid
flowchart LR
    API["现有 Agent API 和 SSE"] --> Compatibility["OrchestratorAgent 兼容层"]
    Compatibility --> Core["OrchestratorCore 目标状态机"]
    Adapter["生成模式适配器"] --> Core
    Core --> Scheduler["统一拓扑调度器"]
    Scheduler --> Model["模型网关与墙钟预算"]
    Scheduler --> Committer["产物提交器"]
    Committer --> Manifest["磁盘产物清单"]
    Core --> Validation["云端语法与本地验证协调"]
    Core --> Store["Checkpoint 和事件存储"]
```

目标设计采用四级执行预算：单次模型调用、单文件、阶段和任务。流式保活数据不改变墙钟 deadline；超时和用户取消需要传播到活动模型调用及文件任务，并在终态前完成子任务回收。

文件计划分为 `strict` 和 `extensible`。需求明确指定文件集合时使用 `strict`，冻结计划外的业务文件形成结构化计划错误；允许架构补全时使用 `extensible`，新增文件需要记录来源和理由。文件生成成功由原子写入、磁盘回读、非空、大小和 hash 校验共同决定，文件完成事件只能引用已登记产物。

迁移顺序为传统生成、Spec-First、增量修改。每个入口保留 legacy/core 路由和原有 HTTP、SSE、会话契约，checkpoint 记录引擎版本，恢复任务继续使用创建时的引擎版本。

`app.agent.orchestration` 已实现第一阶段内核原语：严格 Pydantic 契约、单向阶段转换、revision 校验、持久化事件幂等、唯一终态、原子 JSON checkpoint，以及任务创建、推进、终止、取消和恢复协调。文件计划层已实现统一安全路径规范化、`strict/extensible` 自动策略、结构化计划错误、依赖集合校验、扩展来源记录，以及带稳定 digest 的不可变计划版本。执行层已实现不可变的任务、阶段、文件和模型调用四级预算，预算随 command 写入 checkpoint；`ModelGateway` 使用绝对墙钟 deadline 包住模型调用和完整流消费，区分保活、普通流数据与业务模型数据，并在超时、用户取消或外部任务取消后关闭活动流。`ArtifactCommitter` 统一执行安全路径校验、大小限制、原子写入、磁盘回读和 SHA-256 一致性验证，验证成功后才登记 `SharedContext` 清单并返回幂等的 `file_completed` 事件。成功门禁比较冻结计划、完成事件、清单和磁盘业务文件集合，忽略隐藏元数据，并要求每个计划文件 hash 一致且验证状态有效；Core 进入 `completed` 前必须携带通过的门禁结果，失败结果收敛为带 `artifact_consistency_failed` 诊断的失败终态。`GenerationScheduler` 以冻结计划为输入，按依赖就绪队列调度独立文件，使用 `TaskGroup` 管理子任务，执行并发上限、重试预算、文件/阶段超时、取消传播、上游失败阻断和循环依赖死锁收敛，并保证活动任务最终归零。传统入口已具备 `TraditionalAdapter`、legacy/core 引擎选择、无源码影子状态对比和 checkpoint 引擎版本元数据；传统单文件生成还将 120 秒活动 tracker 传递到 Specialist 和 simple ReAct，模型流 chunk 更新活动时间，无活动调用取消后进入内容恢复重试。Core 生产生成入口等待任务 11.1 的契约与真实生成验收后切换。实施进度和验收门禁记录在 `../specs/2026-08-31-multilanguage-generation-orchestration/`。

云端文件校验通过 `app.agent.validation_report.ValidationReport` 统一表达。报告为不可变、可序列化结构，记录 `cloud_syntax` scope、错误类别、文件路径、诊断上下文 hash、修复候选 hash 和修复证据；`RepairRouter` 对 syntax、dependency、export、signature、async、fixture、schema 和 type 类错误使用受控自动修复，对 business、test 和 unknown 类错误进入用户确认流程。`RepairBudget` 限制单类错误最多 3 次、任务累计最多 5 次，预算耗尽后保留可定位诊断并停止自动修复。

## StateGraph 边界

节点读取 State 快照并返回 StateDelta，reducer 负责 revision、消息幂等和增量合并。`CheckpointStore`、事件 Envelope 和本地验证适配器已经提供基础契约。会话适配器支持按 sequence replay，并在检测到缺口时返回 snapshot recovery action。云端验证结果限定为 `cloud_syntax`；当 State 声明必需本地 scope 时，验证节点创建 `waiting_local_validation` 动作，`run_workflow()` 将动作适配并发布到已连接的 Agent Host session，同时按 `session_id/task_id` 保存 checkpoint 和下一节点游标；插件 `tool_result` 经过任务版本和本地结果适配器校验后恢复活动 StateGraph，并从游标继续执行后续节点，所有必需 scope 通过后进入 `completed`。活动注册表缺失时可以从 checkpoint 加载状态并合并结果；跨进程续跑需要启动时注册可恢复的 workflow definition。Agent Host session 使用原子 JSON 队列保存动作、策略版本和事件确认，支持进程重启后的恢复；真实 HTTP 已验证 handshake、事件、策略、Skills 和 session control 闭环，用户模型供应商 Key 流程已通过 `13/13` 验收。API 入口仍保留原始 SSE 事件出口，多 worker 和模型驱动的跨工作台续跑仍需独立验收。

## 检索与运行时边界

`RetrievalService` 已实现请求范围过滤、内容 hash 去重、排序和降级结果，但当前未接入生产 Agent 主链路。检索 chunk 的实际字段为 `source_type`、`source_id`、`content_hash`、`metadata` 和 `retrieved_at`；`project_scope` 与 `session_scope` 通过请求和 metadata 参与过滤。

`ContextAssembler` 将需求、计划、检索结果、Memory 和 MCP/Skill 描述转换为带来源、优先级、作用域和内容 hash 的 `ContextEnvelope`，执行字符预算和敏感字段脱敏。`app.agent.languages` 复用已注册的 Python 与 JavaScript Adapter，统一提供解析、符号和编译/测试能力元数据。Toolchain 命令使用参数数组，并通过 Profile 的命令与依赖白名单约束工作区扩展。

`app.agent.profile_discovery` 根据工作区 manifest 和依赖线索创建 `DiscoveredProfile`，应用域覆盖 Web、Windows、Android、爬虫、游戏和 CLI。未知技术栈进入 `custom_pending` 并输出 `CapabilityGap`，通过 Toolchain 探针结果后再升级为实验或正式 Profile。
已验证的工作区画像由 `ProfileCache` 保存到 `.monkeycode/profiles.json`，后续任务可复用画像并通过 schema version 触发安全失效。探针结果将画像从 `custom_pending` 推进到 `experimental`；完整 conformance checks 通过后才升级到 `supported`。
传统、Spec-First 和增量修改入口在规划阶段读取 `profile_context()`，将画像状态和能力缺口传递给生成与验证流程。
`CapabilityResolver` 将应用域映射为必需能力、生成约束和验证步骤；Pygame、Scrapy、Android 和 Windows 等应用类型可以复用同一生成生命周期。
解析结果还包含 `required_components`，为生成计划提供领域级组件提示，保持领域策略与具体框架 Profile 解耦。
`add_profile_components()` 将组件提示投影为 `GenerationPlan` 节点和顺序依赖；`strict` 计划保持用户冻结集合，`extensible` 计划记录受控领域扩展。

Skills 使用 `system:`, `user:` 和 `workspace:<folder-name>:` 命名空间。User Skills 通过认证用户 ID 隔离；Workspace Skills 由 VS Code 的所有 workspace folders 递归发现，并在 Agent Host session 内保存和同步。Web 端读取当前用户 Skills 与用户拥有的 Agent Host sessions，用于展示当前会话上下文。VS Code activation 会为所有 workspace folders 建立独立授权，`workspace` capability 的 `inspect` 和 `list_roots` 操作返回当前已授权根目录。

运行时补扫记录了以下部署约束：

- 应用同时存在 lifespan 与 startup hook，迁移、scheduler 和供应商恢复位于 startup hook。
- ready 检查数据库和 Redis，当前未纳入 Celery worker 状态。
- API 多 worker 与进程内 scheduler 存在重复执行定时任务的风险。
- API 健康路由为 `/api/v1/health`，容器和部分脚本使用 `/health`，健康契约需要统一。
- 独立 Nginx 容器 upstream 已切换为 Compose 服务名 `api:8080`；Dockerfile 的 root master、`nginx` worker 和 `appuser` API 权限模型已调整，Compose 挂载路径和生产 Celery 服务仍需部署前核对。
- `verify-integration.sh` 与现有集成测试主要提供静态、ASGI 或配置级证据，不能单独证明真实端口、worker、broker 和代理链路可用。
- 本地开发时 Vite 监听 3000 端口，并将 `/api/v1`、`/api/v2` 转发到后端 8000 端口；Vite allowed hosts 包含本地地址和 `.monkeycode-ai.online`。

## 统一状态迁移

统一状态层复用既有 `tasks` 表，并新增 `sessions`、`messages`、`task_events`、`checkpoints` 和 `artifacts`。`TaskManager` 在 Redis/内存状态变更时双写 SQL 任务快照和事件，Redis Pub/Sub 仅负责低延迟通知，SQL 事件表负责恢复和重放。启动迁移运行器会为旧 `tasks` 表补齐 session、revision、幂等键、stage、lease、结构化错误/结果和时间字段。

后续模块迁移新增 `state_compatibility_mappings` 和 `state_retention_records`。前者关联旧模块标识与统一资源，后者记录归档、清理、重试和外部文件保留状态。对应模型位于 `app.models.unified_state`，数据库迁移位于 `migrations/versions/20260829_add_state_migration_tables.py`。

兼容映射和保留生命周期服务位于 `app.services.state_migration_service`，通过作用域唯一键保证旧标识幂等绑定，通过受控状态流转记录归档、清理和失败重试。

双写核对服务位于 `app.services.reconciliation_service`，按模块、资源类型和资源标识保存 expected/actual 快照差异，支持差异合并、retryable 状态、延迟重试和 resolved 结果。

模块级核对报告和读切换控制器位于 `app.services.state_cutover_service`。报告覆盖 session、message、task、event、checkpoint、artifact 六类资源，并将开放差异作为切换门禁；`ReadCutoverController` 按 AICloud、GirlAI、Agent、Workflow 顺序切换统一读源，保留模块级 legacy 回滚能力。

四模块灰度执行由 `activate_modules_in_order` 驱动。控制器基于模块和用户 ID 的稳定 hash 选择 cohort，支持阶段比例和逐模块回滚，确保同一用户在灰度期间持续命中同一读源。

AICloud 通过 `app.services.aicloud_state_adapter` 将旧 `aicloud_sessions/aicloud_messages` 标识幂等映射到统一 `sessions/messages`，聊天和流式聊天入口均在旧记录提交后写入统一状态。

GirlAI 通过 `app.services.girlai_state_adapter` 将用户维度的 `chat_histories` 映射为稳定的 `user:{user_id}` 统一会话，每轮历史写入统一 user/assistant 消息；`ChatSummary` 可通过统一 `girlai_summary` 任务保存为 checkpoint。

Agent 通过 `app.services.agent_state_adapter` 映射 `ProjectSession`/JSON session，并将可序列化 State 保存到统一任务 checkpoint；`persist_agent_state` 同时写入消息事件和生成文件 Artifact。`run_workflow` 接收可选数据库上下文后自动调用该持久化入口，`generate`、同步 `orchestrate`、增量修改 SSE 和 `orchestrate/stream` 均已传入数据库上下文。Workflow 通过 `app.services.workflow_state_adapter` 将 `WorkflowHistory` 映射为统一 task，节点阶段写入 Task Event，生成文件登记到 Artifact。

PPT WebSocket 在轮询进程内任务状态前读取 SQL `task_events`，按 sequence 向客户端发送增量事件，支持客户端重连后的事件补发；进程内任务缓存缺失时回退读取 SQL Task。客户端提供 `after_sequence` 且没有后续事件时，服务返回最新 checkpoint 的 `snapshot_recovery` 消息。`app.tasks.ppt_tasks.generate_ppt` 已成为 JSON 参数可序列化的 Celery 任务并路由到 `ppt` 队列，任务在启动、进度更新和完成前续租 90 秒，并双写统一 Task/Event。`PPT_USE_CELERY=true` 时，`app.services.ppt_dispatch_service` 创建 SQL 任务并提交 Celery 任务，支持接口级灰度切换。`app.services.worker_recovery_service.recover_expired_tasks` 提供过期 lease 单次扫描、重投递和 retry 上限处理，`app.db.scheduler` 已按 1 分钟间隔注册恢复任务。

统一状态保留由 `app.services.state_migration_service.process_retention_records` 执行。`RetentionPolicy` 提供归档和清理窗口，资源仍被活动任务、有效会话或恢复流程引用时进入 `blocked`，引用解除后可继续处理。外部产物清理由 `ExternalStorageAdapter` 执行，默认本地 adapter 支持 `file://` URI；每条记录保存稳定 cleanup idempotency key、资源版本、删除意图和执行结果，失败进入 `retryable`。scheduler 每天执行 `unified_state_retention`。
