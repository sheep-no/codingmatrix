# Interfaces

## Chat API

- `POST /api/v1/chat`：主聊天接口，支持流式输出、会话历史、文件理解和联网搜索。
- `POST /api/v1/code`：主聊天兼容别名，客户端迁移到 `/api/v1/chat`。

## GirlAI API

- `GET /api/v1/GirlAi/characters`：返回内置角色列表。
- `GET /api/v1/GirlAi/characters/custom/list`：返回当前认证用户拥有的自定义角色。
- `POST /api/v1/GirlAi/characters/custom`：创建用户自定义角色；角色通过 `custom_<id>` 作为对话请求的 `character_id`。
- `POST /api/v1/GirlAi`：生成一轮虚拟姬对话。自定义角色按角色 ID 和用户 ID 校验归属；模型调用成功后，legacy `chat_histories` 与 unified `sessions/messages` 在同一事务中写入。
- `GET /api/v1/GirlAi/history`：按 `limit` 和 `offset` 查询当前用户历史，结果按最新记录优先返回。
- `GET /api/v1/GirlAi/history/search`：搜索当前用户历史记录。
- `DELETE /api/v1/GirlAi/history?all=true`：清空当前用户 legacy 和 unified GirlAI 消息。
- `DELETE /api/v1/GirlAi/history?all=false&record_ids=<id>`：删除指定 legacy 记录，并按 `legacy_message_id` 同步清理 unified 消息。

模型供应商异常由 GirlAI 路由转换为通用 `502`，请求事务回滚，供应商原始错误细节不会返回给客户端。

## Agent API

- `POST /api/v1/ai-agent/generate`：生成项目。
- `POST /api/v1/ai-agent/modify`：修改项目或执行分析请求。
- `POST /api/v1/ai-agent/orchestrate`：同步编排项目生成。
- `POST /api/v1/ai-agent/orchestrate/stream`：SSE 流式编排。

## State Contracts

`app.agent.state.models` 定义 `State`、`StateDelta` 和 `MessageEnvelope`。State 包含 session/task 标识、revision、status、消息、计划变更、生成文件、验证结果、待执行动作、错误和 metadata。该模型已实现为可序列化契约，完整多阶段生产编排仍在迁移中。

云端生成编排使用 `app.agent.shared_context.SharedContext` 保存单文件 `FileArtifact`。产物清单通过 `get_artifact_manifest()` 输出路径、内容 hash、导入、导出、语言、依赖、状态和诊断，`is_file_ready()` 与 `are_dependencies_ready()` 用于阻止无效上游释放下游生成。

修复编排使用 `app.agent.repair_router.RepairRouter` 和 `RepairBudget`。基础语法、导入、名称和类型错误进入自动修复；业务逻辑、测试断言和未知错误进入用户确认；默认单类错误最多 3 次、任务累计最多 5 次。

`StateReducer.apply()` 要求 delta 的 `expected_revision` 等于当前 revision。成功合并后 revision 递增；具有相同 `event_id` 的消息和验证结果只应用一次，纯重复验证结果保持 revision 不变。

### Orchestrator Core Contracts

`app.agent.orchestration` 定义下一代生成编排的独立内部契约。`OrchestrationCommand` 保存 task、session、生成模式、请求和 `engine_version`；`OrchestrationState` 保存 stage、status、revision、恢复游标、已应用事件、唯一终态事件和结构化诊断；`StageResult` 与 `OrchestrationResult` 用于阶段和任务返回。所有模型使用 Pydantic 严格字段校验，checkpoint 通过 JSON round-trip 恢复。

`advance_state()` 只接受 `created -> planning -> scheduling -> generating -> persisting -> validating -> finalizing` 的相邻转换。`terminate_state()` 允许活动阶段进入 `failed`、`timed_out` 或 `cancelled`，`completed` 仅从 `finalizing` 进入。转换要求 `expected_revision`，首次应用的 `event_id` 递增 revision，已持久化的重复 `event_id` 返回原状态。

`OrchestrationStore` 是异步 checkpoint 协议，`OrchestrationCheckpointStore` 提供原子 JSON 文件实现。`OrchestratorCore` 当前提供 `run()`、`advance()`、`finish()`、`cancel()` 和 `resume()`；生产 Agent API 尚未路由到该 Core。

`build_file_plan()` 将现有文件字典列表转换为不可变 `GenerationPlan`。传入 `requested_paths` 时产生 `strict` 策略，计划文件集合必须与规范化请求集合一致；省略该参数时产生 `extensible` 策略，`origin=extension` 的新增文件必须携带 `source` 和 `reason`。`normalize_plan_path()` 统一 POSIX 相对路径表示并拒绝绝对路径、父目录遍历、受保护项目文件和不受支持的分隔符。

`GenerationPlan` 保存 `version`、策略、请求路径、不可变 `PlannedFile` 元组、SHA-256 digest 和冻结时间。构建过程以结构化 `PlanIssue` 返回重复文件、缺失请求文件、范围外文件、缺失依赖、自依赖和扩展来源错误；计划模型在 JSON 恢复时重新验证文件集合、依赖集合和 digest。

`ExecutionBudget` 定义 `task_seconds`、`stage_seconds`、`file_seconds` 和 `model_call_seconds`，要求模型预算不超过文件预算、文件预算不超过阶段预算、阶段预算不超过任务预算。`OrchestrationCommand.budgets` 在任务创建时复制到 `OrchestrationState.budgets`，checkpoint 恢复保持原任务预算。

`ModelCallContext` 保存 `task_id`、`stage_id`、`file_path`、`call_id`、`react_round`、`started_at` 和绝对 `deadline_at`。`ModelGateway.call()` 约束非流式调用，`ModelGateway.stream()` 将流创建和完整迭代纳入同一墙钟 deadline；保活数据只更新 `last_keepalive_at`，业务 token 更新 `last_model_data_at`，两者均不会延长 deadline。预算到期抛出带 `model_timeout` 诊断的 `ModelCallTimeout`，取消事件抛出带 `model_cancelled` 诊断的 `ModelCallCancelled`，外部 asyncio 任务取消保持 `CancelledError` 传播并关闭底层流。
`ModelCallContext` 可选携带 `context_hash`，模型错误诊断在该字段存在时回传同一 hash，用于关联生成上下文与验证证据。

`ArtifactCommitter.commit()` 接收计划内相对路径、生成内容和模型名称，执行非空、UTF-8 大小、原子写入、磁盘回读和 SHA-256 校验。首次成功返回带稳定 `event_id` 的 `ArtifactCompletionEvent` 并登记 `SharedContext` 产物清单；相同路径和内容的重复提交返回 `idempotent=true` 且不产生第二个完成事件。写入、路径、大小或回读失败返回 `artifact_commit_failed`，磁盘与内存或清单 hash 不一致返回 `artifact_consistency_failed`。

`check_artifact_success_gate()` 比较 `GenerationPlan`、ArtifactManifest、`ArtifactCompletionEvent` 和输出目录中的业务文件集合，并校验事件、清单与磁盘 hash 以及清单验证终态。隐藏路径作为编排元数据豁免。`OrchestratorCore.finish(..., status=completed)` 要求传入成功的 `ArtifactConsistencyResult`；失败的门禁结果将任务收敛到 `failed` 并保存一致性诊断。

`ValidationReport` 位于 `app.agent.validation_report`，由 `ValidationFinding` 和 `RepairEvidence` 组成。每条 finding 包含 `category`、`message`、`file_path`、`scope`、可选错误码和 `context_hash`；报告包含稳定 `report_hash`，`passed` 表示 finding 集合为空。`authorize_repair()` 根据 finding 类别调用 `RepairRouter`，仅自动路由允许的代码/依赖修复，并通过 `RepairBudget` 记录 attempt、candidate hash 和是否应用；业务、测试与未知错误保留人工确认路径。

框架能力模型位于 `app.agent.capabilities`，内置 `http_api`、`orm`、`database`、`authentication`、`websocket`、`dependency_injection`、`test_client` 和 `migrations` 能力。`app.agent.framework_profiles` 提供 FastAPI、Flask、Express 和 NestJS 的版本化 Profile；JavaScript 与 JS 别名统一解析到 TypeScript Profile，未知框架通过 `LookupError` 暴露待配置状态。

`GenerationScheduler.run()` 接收冻结的 `GenerationPlan`、`GeneratedContent` 异步生成器和 `ExecutionBudget`。`FileGenerationContext` 为生成器提供计划文件、已完成上游内容、尝试次数和取消事件；文件提交统一经过 `ArtifactCommitter`。`GenerationNodeStatus` 支持 `pending`、`ready`、`running`、`completed`、`failed`、`timed_out`、`cancelled` 和 `blocked`，`GenerationScheduleResult` 返回每个节点状态、完成事件、调度终态和并发统计。无效上游阻断所有后代；无就绪节点且仍存在未完成节点时记录死锁并将其收敛为 `blocked`。

`TraditionalAdapter` 实现 `GenerationModeAdapter`，将现有 `OrchestratorAgent` 的架构规划和单文件生成转换为 `GenerationPlan` 与 `GeneratedContent`。`route_generation()` 按 `AGENT_ORCHESTRATION_ENGINE` 或显式请求选择 `legacy`/`core`，默认选择 `legacy`；可选 shadow 执行只比较成功状态和文件路径集合，不保存源码内容。legacy workflow checkpoint 会记录 `engine`、`engine_version` 和 `engine_route`，恢复时可识别创建任务时的引擎版本。

`app.agent.context_assembler` 提供 `ContextItem`、`ContextEnvelope`、`SkillPolicy` 和 `MCPToolDescriptor`。`ContextAssembler.assemble()` 按优先级排序并去重需求、计划、Retrieval、Memory 和 MCP/Skill 输入，输出稳定 `context_hash`；MCP 描述通过读写 scope、项目 scope、依赖、超时和审计字段表达权限边界。`app.agent.languages` 的 `get_language_adapter()` 和 `get_language_capabilities()` 为生成与验证提供统一语言入口。

语言适配器还提供 `extract_signatures(content, file_path)` 接口。依赖图优先通过目标语言适配器提取接口，适配器可以接入语言专用解析器或受控工具链，失败时回退到内置解析器。

`app.agent.toolchain.ToolchainRunner` 只执行 `CommandSpec` 参数数组，固定使用 `shell=false`，并施加工作目录、超时和输出大小限制。接口探针可以使用 `ToolchainAction.INSPECT`，Shell 解释器和 Shell 操作符会在 `CommandSpec` 校验阶段被拒绝。

`app.agent.evaluation_matrix` 提供六种技术栈的固定 CRUD 评测样例，以及 `EvaluationRecord`、`summarize()` 和 `build_report()`。评测记录覆盖计划、接口、依赖闭包、文件、编译、测试、启动和持久化门禁，并聚合最终成功率、Token 数、P95 耗时、缺失样例、非法指标和失败分类。

`app.agent.profile_discovery` 提供 `discover_profile()` 和 `probe_profile()`。发现结果包含语言、框架、应用域、证据、能力和能力缺口；探针结果包含检查项、失败原因和是否通过，允许 Pygame、Scrapy、Electron、React Native 及 Android Gradle 等候选栈进入统一生命周期。
`ProfileCache.record_probe()` 持久化探针状态，`promote_supported()` 要求画像处于 `experimental` 且完整 conformance checks 通过后才升级为 `supported`。
`profile_context()` 输出适合嵌入项目上下文的 JSON 结构，生成入口可据此读取应用域、能力集合和待处理能力缺口。
`app.agent.capability_resolver.resolve_capabilities()` 返回 `ResolvedCapabilities`，包含 required、available、missing、generation_constraints、validation_steps 和 ready 字段。
`ResolvedCapabilities.required_components` 为领域生成计划提供组件角色提示，例如游戏的 rules/renderer/input_loop、爬虫的 fetcher/parser/pipeline 和桌面应用的 window/event_handler。
`ResolvedCapabilities.component_file_plan()` 将组件角色映射为相对文件路径和组件类型，供 GenerationPlan 生成文件节点。
`add_profile_components()` 接收 Profile 上下文和现有文件计划，在 `extensible` 策略下追加领域组件及依赖，在 `strict` 策略下保持请求文件集合不变。
`ValidationCoordinator` 将 Profile 的 `validation_steps` 转换为安全 Toolchain 命令；`execute()` 返回命令结果，`to_report()` 生成统一 `ValidationReport`。

传统单文件生成创建 `HeartbeatTracker` 并传递给 Specialist 与 `ReActEngine`。simple ReAct 和 full ReAct 均监控模型活动；流式 content/reasoning chunk 更新活动时间，超过无活动阈值会取消当前调用并返回空结果，由现有内容恢复链路执行有限重试。API SSE 的 5 秒 heartbeat 仅承担客户端连接保活，不参与模型活动判断。

## Workflow Contracts

`WorkflowDefinition` 包含 workflow 名称、入口节点、StateGraph 和 legacy endpoint。当前定义主要承载单节点 legacy workflow。`build_legacy_workflow()` 将旧 Agent handler 转换为 StateDelta，并在 metadata 中保留原始结果。`run_workflow()` 从可序列化 State 启动图运行。

## Retrieval Contracts

统一检索使用 `RetrievalRequest`、`RetrievalChunk` 和 `RetrievalResult`。chunk 实际携带 `source_type`、`source_id`、`content_hash`、`metadata` 和 `retrieved_at`；项目/会话范围通过请求字段和 metadata 过滤，来源信息由来源字段和 metadata 表达。服务支持排序、去重和降级结果，当前尚未接入生产 Agent 主链路。

## Validation Contracts

云端验证使用 `source=cloud`、`scope=cloud_syntax`，并根据 `State.metadata.required_validation_scopes` 创建本地验证动作。本地结果适配器只接受 `local_runtime` 或 `local_e2e`，校验 task、session、revision、schema version、scope 和 `source=local`，并将协议字段映射到内部 `scope`、`passed`、`source=vscode` 契约。`passed`、`skipped`、`failed`、`timeout`、`rejected`、`cancelled` 和 `unsupported` 进入状态推导，其中 `skipped` 视为已完成阶段，`waiting_for_confirmation` 保持未完成；当语言能力、验证命令或契约版本不可用时使用 `unsupported`，保留 `reason` 等诊断并停止创建后续本地验证动作。适配器按已完成 scope 更新待执行动作，所有必需 scope 通过或跳过后才产生 `completed` 状态。VS Code 插件本地 E2E、Agent Host 真实 HTTP session 控制闭环和用户模型 Key 流程均已验收，模型驱动的跨工作台续跑仍属于独立场景验收。

`vscode-extension/src/protocol.ts` 提供 VS Code 端的 `PendingAction` 和 `LocalValidationResult` 类型及运行时解析器。插件端使用 `validation_scope`、`source=local` 和参数数组命令；连接层接入云端时需将 Envelope 字段映射到现有本地结果适配器的 `scope` 和 `source` 契约。

`vscode-extension/src/agent-host.ts` 提供通用 `AgentHostEnvelope`、Host Hello、能力声明、策略快照和 `AgentHostSession`。会话握手校验协议版本、工作区、扩展版本、能力清单和待执行动作；策略更新要求 `policy_version` 严格递增，支持的能力包括 `workspace`、`file`、`terminal`、`diagnostics`、`validation` 和 `skill_runtime`。

后端 `POST /api/v1/agent/host/handshake` 使用 access token 认证，接收 `workspace_id`、`extension_version`、`protocol_versions` 和 `capabilities`，返回用户绑定的 `session_id`、协议版本、初始 `policy`、`policy_version`、会话过期时间和待执行动作。`GET /api/v1/agent/host/sessions/{session_id}/actions` 拉取 session 动作，`POST /api/v1/agent/host/sessions/{session_id}/events` 接收 Host 事件并按 `message_id` 幂等，`PUT /api/v1/agent/host/sessions/{session_id}/policy` 以期望版本更新策略。当前握手会话保存于进程内存，StateGraph 动作入队仍需接入持久化任务存储。

`app.api.v1.agent_host.enqueue_state_actions()` 将 StateGraph 的 `pending_actions` 转换为版本化 `tool_action` Envelope，补齐 `session_id`、`task_id`、`revision`、`workspace_id` 和当前 `policy_version`，并按 `action_id` 去重。`run_workflow()` 在图执行完成后自动调用该适配器；已连接 Host 可通过 session actions 队列消费本地动作。session 队列、策略版本和事件确认使用 `AgentHostSessionStore` 原子写入 `data/agent_host_sessions/`，支持进程重启后的读取恢复。

`vscode-extension/src/tool-dispatcher.ts` 提供本地工具分发。文件读取和修改使用工作区授权路径、UTF-8 内容 hash、读取大小上限和 expected hash 冲突保护；诊断通过注入适配器获取；验证和终端动作复用 `ValidationRunner`，并遵守参数数组、`shell=false`、本地执行总开关和验证操作开关。

`vscode-extension/src/webview-bridge.ts` 提供 Webview 与扩展 Host 的消息、请求响应关联、超时和释放处理。`vscode-extension/src/agent-host-runtime.ts` 校验会话与策略版本，将工具动作交给 `ToolDispatcher`，并把非验证结果包装为 `tool_result` 事件或将本地验证结果提交到云端连接层；控制消息可应用单调递增的策略更新并处理审批决定。

`vscode-extension/src/agent-workbench.ts` 提供原生 Webview 工作台控制器和安全 HTML。`codingmatrix.openAgentWorkbench` 命令由 `src/extension.ts` 注册，打开单例 Agent 面板并通过 `WebviewBridge` 连接 Host 消息。

工作台控制器订阅并转发已通过协议解析的 Webview Agent Host 消息；内置审批控件可生成 `approval_decision`，供运行时处理挂起的本地动作。

`src/extension.ts` 在存在工作区时创建本地 `AgentHostSession`、`WorkspaceAuthorization`、`ValidationRunner`、`ToolDispatcher` 和 `ApprovalBridge`，并通过 `AgentWorkbenchController` 完成事件回传。

`vscode-extension/src/approval-bridge.ts` 管理本地审批请求和决定。`AgentHostRuntime` 在会话策略关闭自动批准时暂停工具动作，发布 `approval_request`，并在批准后继续执行；拒绝决定返回 `rejected` 状态。

`vscode-extension/src/connection.ts` 提供 Bearer 认证的动作拉取和结果提交客户端，默认路径为 `/api/v1/agent/local-validation/actions` 与 `/api/v1/agent/local-validation/results`。客户端对 401/403 返回认证错误，对 408/429/5xx 执行有限重试，网络中断时将结果写入可注入的 `ResultStore`，新连接实例可刷新持久化队列并在云端确认后删除记录。

`vscode-extension/src/workspace-authorization.ts` 提供工作区授权、撤销、多工作区隔离和路径解析。路径必须相对授权根目录，解析后的符号链接目标也必须位于对应工作区内。

`vscode-extension/src/validation-runner.ts` 通过注入的进程适配器执行验证动作，固定使用参数数组和 `shell=false`，并提供 `dependency_install` 等操作白名单、超时、取消、退出码和输出上限控制。执行结果统一映射为 `LocalValidationResult`；执行计划使用 `plan_schema_version=1`、`run_id`、`step_id` 和串行依赖关系描述文件传输、hash 校验、依赖安装与验证阶段。

`vscode-extension/src/result-sanitizer.ts` 在结果回传前处理密钥、Bearer token、密码、Cookie、私钥和连接串，并对处理后的结果执行安全复检。`vscode-extension/src/result-store.ts` 通过可注入存储保存待回传结果，按 `event_id` 去重，并在云端确认后移除记录。

`vscode-extension/src/status-view.ts` 提供与 VS Code API 解耦的验证状态视图模型。`ValidationStatusView` 将授权等待、运行、通过、失败、超时、拒绝和取消映射为可展示快照，提供耗时、取消能力、通知文本和带文件位置的诊断摘要；结果兜底匹配同时校验 `session_id`、`task_id`、`revision` 和 `validation_scope`，避免多 scope 动作串写。

`vscode-extension/src/compatibility.ts` 提供启动阶段兼容性校验。云端握手必须声明支持插件当前的 `schema_version`，可选的 `plugin_version.min` 和 `plugin_version.max` 使用严格 `x.y.z` 版本格式；不兼容时返回结构化 `CompatibilityError`，调用方应阻止创建新的本地验证动作并展示升级指引。`package.json` 的 manifest 入口为 `dist/extension.js`，打包脚本为 `vsce package --no-dependencies`。

## 持久化与事件

`CheckpointStore` 提供版本化 JSON checkpoint 的保存和加载能力，`progress_event_to_message()` 提供进度事件到 `MessageEnvelope` 的转换，`replay_session()` 提供带序列缺口恢复动作的回放结果。插件连接层使用 `ResultStore` 支持跨实例断线结果恢复。当前 API、SessionManager 和任务队列尚未自动调用 checkpoint 持久化，现有 SSE 仍保留原始事件出口。
Agent、Workflow 和 PPT 入口已逐步接入统一 checkpoint、Task Event 和 Artifact 持久化，现有 SSE 仍保留原始事件出口。

## Unified Task State

- `GET /api/v1/tasks/{task_id}`：按用户归属查询任务快照。
- `GET /api/v1/tasks/{task_id}/events?after_sequence=0`：从 SQL 事件日志重放任务事件。
- `DELETE /api/v1/tasks/{task_id}`：撤销 Celery 任务并写入取消事件。
- `POST /api/v1/tasks/{task_id}/recover`：恢复失败或取消任务，并为已支持的 Celery 任务重新投递。

任务状态同时写入既有 Redis/进程内任务状态和 SQL `tasks` 表。状态变化发布到 Redis `task_events:{task_id}`，SQL `task_events` 保存断线重放记录。统一实体模型位于 `app.models.unified_state`，服务入口位于 `app.services.unified_state_service`。

后续模块使用 `state_compatibility_mappings` 解析旧模块标识，使用 `state_retention_records` 管理资源归档和清理生命周期。两类记录均以统一资源类型和资源标识建立可追溯关联。

服务入口为 `upsert_compatibility_mapping`、`resolve_compatibility_mapping`、`create_retention_record` 和 `advance_retention_record`。

统一保留服务入口为 `process_retention_records`。`RetentionPolicy` 定义归档和清理时间窗口；处理器会检查活动任务、有效会话和恢复状态，归档时保留统一资源记录，清理外部 artifact 前记录固定幂等键、资源版本、删除意图和执行结果。外部存储通过 `ExternalStorageAdapter` 注入，默认 `LocalFileStorageAdapter` 支持 `file://` URI；失败记录进入 `retryable` 状态。scheduler 每天执行 `unified_state_retention`。

核对服务入口为 `record_difference`、`schedule_difference_retry` 和 `list_open_differences`，记录模型为 `state_reconciliation_records`。

模块级切换服务入口为 `build_reconciliation_report` 和 `ReadCutoverController`。报告要求 session、message、task、event、checkpoint、artifact 六类资源均有记录，并且不存在 `open` 或 `retryable` 差异；控制器按 AICloud、GirlAI、Agent、Workflow 顺序启用 unified read source，任一模块可回滚到 legacy source。

`activate_modules_in_order` 执行四模块灰度切换。`ReadCutoverController.enable(..., rollout_percentage=N)` 使用稳定用户 cohort 将模块按 0 到 100 的比例分批切换；`source_for_user` 返回当前用户的 legacy 或 unified 读源，回滚会将模块灰度比例恢复为 0。

AICloud 适配器入口为 `ensure_session`、`append_legacy_message` 和 `list_session_messages`，旧会话和消息通过 `state_compatibility_mappings` 保留可追溯关系。

GirlAI 适配器入口为 `ensure_session`、`append_conversation_turn`、`delete_messages_for_legacy_ids`、`clear_messages_for_user`、`list_messages_for_user` 和 `save_summary_checkpoint`，角色标识、legacy 消息关联和摘要来源保存在统一状态 metadata 或 checkpoint state 中。

AICloud 与 GirlAI 的旧历史读取回归测试覆盖兼容映射复用、缺失映射创建、用户归属隔离、消息顺序和读取数量限制。

Agent 适配器入口为 `ensure_project_session`、`save_graph_checkpoint` 和 `persist_agent_state`。`generate`、同步 `orchestrate`、增量修改 SSE 和 `orchestrate/stream` 已通过 `run_workflow(..., db=db, user_id=user_id)` 触发统一持久化。Workflow 适配器入口为 `ensure_workflow_task`、`record_workflow_stage` 和 `register_workflow_artifacts`。

PPT WebSocket `GET /ws/ppt/{task_id}?after_sequence=N` 建立连接后按 SQL `task_events.sequence` 重放事件，再发送当前任务状态变化；没有后续事件时返回 `{type: "snapshot_recovery", revision, step, state}`。Celery 任务入口为 `app.tasks.ppt_tasks.generate_ppt(task_id, user_id, request_data)`，其中 `request_data` 必须是 JSON 对象。

PPT Celery worker 使用统一 `heartbeat_task` 写入 90 秒 lease，进度更新会触发续租；过期 lease 的扫描和恢复由后续调度器负责。

`app.services.worker_recovery_service.recover_expired_tasks(db, now=None, limit=100)` 执行一次过期 lease 扫描，支持 `project_generate`、`code_generate`、`ppt_generate` 和 `ppt_generation`，成功重投递后记录 `task.recovered` 事件。`app.db.scheduler` 的 `worker_lease_recovery` job 每分钟调用一次。

设置 `PPT_USE_CELERY=true` 后，`POST /pptx/generate_task` 通过 `app.services.ppt_dispatch_service.dispatch_ppt_to_celery` 创建统一任务并提交 JSON 参数；默认值保持旧任务执行路径。

Celery PPT worker 的进度写入统一 `tasks` 和 `task_events`，WebSocket 优先重放事件并在缓存缺失时读取 SQL Task 状态。

本地 Celery 运行时使用 Redis 作为 broker/backend。PPT worker 需要监听 `ppt` 队列，并注册 `app.tasks.ppt_tasks.generate_ppt`；worker lease 过期后由 `worker_lease_recovery` scheduler job 触发恢复。

P3 集成测试位于 `tests/integration/test_state_recovery.py`，覆盖 Redis Pub/Sub 消息接收、SQL 事件按序重放、最新 checkpoint 快照恢复、序列缺口的 `snapshot_recovery` 动作和任务归属校验。
