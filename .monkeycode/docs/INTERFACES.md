# Interfaces

## 认证与公共 API

- `POST /api/v1/auth/login`：登录并建立认证会话。
- `POST /api/v1/auth/register`：注册用户。
- `GET /api/v1/health`：检查数据库和 Redis 状态。
- `GET /api/v1/public-key`：读取前端加密所需的公开密钥。

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

- `POST /api/v1/agent/generate`：生成项目。
- `POST /api/v1/agent/modify`：修改项目或执行分析请求。
- `POST /api/v1/agent/orchestrate`：同步编排项目生成。
- `POST /api/v1/agent/orchestrate/stream`：SSE 流式编排。
- `POST /api/v1/agent/stop/{session_id}`：停止 Agent 会话。
- `POST /api/v1/agent/complete/{session_id}`：完成 Agent 会话。
- `POST /api/v1/agent/search_sessions`：查询当前用户会话。
- `GET /api/v1/agent/generate/files`：列出生成项目文件。
- `GET /api/v1/agent/generate/read`：读取生成文件内容。
- `GET /api/v1/agent/generate/download/{project_path}`：下载生成项目。
- `GET /api/v1/agent/token-usage`：读取 token 使用统计。
- `GET /api/v1/agent/sessions/{session_id}/model-context`：读取当前用户 Agent 会话的最新模型上下文；旧会话返回当前运行时默认上下文。
- `PUT /api/v1/agent/sessions/{session_id}/model-context`：合并角色模型、当前模型、调用统计和降级记录，并创建独立模型上下文 Checkpoint。

VS Code 工作台使用 `POST /api/v1/agent/orchestrate/stream` 接收 SSE Agent 事件。Agent Host 使用独立的握手会话完成本地动作协作；工作台界面提供需求输入和会话控制，Web 工作台继续提供完整的会话历史、文件管理和模型配置 UI。

## PPT API

- `POST /api/v1/pptx/generate_task`：创建异步 PPT 任务。文本请求使用 `prompt`、`template`、`slide_count`、`output_format` 和 `options`；`options` 支持 `auto_images` 与 `enable_animation`。
- `GET /api/v1/pptx/history`：返回 `{records, total}`，前端按 `records` 消费历史列表。
- `GET /api/v1/pptx/download/{ppt_id}?format=pptx`：下载生成文件。
- `GET /api/v1/pptx/preview/{ppt_id}`：返回 PPTX 快照预览页面。
- `GET /api/v1/pptx/{ppt_id}/slides`：读取预览所需的幻灯片快照。
- `DELETE /api/v1/pptx/{task_id}/cancel`：取消生成任务。
- `GET /api/v1/ws/ppt/{task_id}`：接收进度、完成和错误事件；事件回放使用 `payload.message` 或 `payload.result` 承载详细数据。

PPT 生成支持 `pptx`、`html` 和 `markdown` 格式的严格产物分流。下载或预览请求的格式必须对应实际产物；API 与 Celery 使用共享 `ppt-artifacts` 产物卷时可以跨容器读取同一文件。HTML 标题和内容经过服务端转义，上传链路采用分块写盘。

模型上下文包含 `schema_version`、`config_version`、`roles`、`current_model`、`current_agent`、`assignments`、`fallback_history` 和 `updated_at`。接口仅接收模型标识和运行统计，不接收供应商凭据。

## State Contracts

`app.agent.state.models` 定义 `State`、`StateDelta` 和 `MessageEnvelope`。State 包含 session/task 标识、revision、status、消息、计划变更、生成文件、验证结果、待执行动作、错误和 metadata。该模型已实现为可序列化契约，完整多阶段生产编排仍在迁移中。

`StateReducer.apply()` 要求 delta 的 `expected_revision` 等于当前 revision。成功合并后 revision 递增；具有相同 `event_id` 的消息和验证结果只应用一次，纯重复验证结果保持 revision 不变。

## Workflow Contracts

`WorkflowDefinition` 包含 workflow 名称、入口节点、StateGraph 和 legacy endpoint。当前定义主要承载单节点 legacy workflow。`build_legacy_workflow()` 将旧 Agent handler 转换为 StateDelta，并在 metadata 中保留原始结果。`run_workflow()` 从可序列化 State 启动图运行。

## Retrieval Contracts

统一检索使用 `RetrievalRequest`、`RetrievalChunk` 和 `RetrievalResult`。chunk 实际携带 `source_type`、`source_id`、`content_hash`、`metadata` 和 `retrieved_at`；项目/会话范围通过请求字段和 metadata 过滤，来源信息由来源字段和 metadata 表达。服务支持排序、去重和降级结果，当前尚未接入生产 Agent 主链路。

## Validation Contracts

云端验证使用 `source=cloud`、`scope=cloud_syntax`，并根据 `State.metadata.required_validation_scopes` 创建本地验证动作。本地结果适配器只接受 `local_runtime` 或 `local_e2e`，校验 task、session、revision、schema version、scope 和 `source=local`，并将协议字段映射到内部 `scope`、`passed`、`source=vscode` 契约。`passed`、`skipped`、`failed`、`timeout`、`rejected` 和 `cancelled` 进入终态推导，其中 `skipped` 视为已完成阶段，`waiting_for_confirmation` 保持未完成；适配器按已完成 scope 更新待执行动作，所有必需 scope 通过或跳过后才产生 `completed` 状态。VS Code 插件本地 E2E、Agent Host 真实 HTTP session 控制闭环和用户模型 Key 流程均已验收，模型驱动的跨工作台续跑仍属于独立场景验收。

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
