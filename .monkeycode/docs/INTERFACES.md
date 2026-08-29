# Interfaces

## Agent API

- `POST /api/v1/ai-agent/generate`：生成项目。
- `POST /api/v1/ai-agent/modify`：修改项目或执行分析请求。
- `POST /api/v1/ai-agent/orchestrate`：同步编排项目生成。
- `POST /api/v1/ai-agent/orchestrate/stream`：SSE 流式编排。

## State Contracts

`app.agent.state.models` 定义 `State`、`StateDelta` 和 `MessageEnvelope`。State 包含 session/task 标识、revision、status、消息、计划变更、生成文件、验证结果、待执行动作、错误和 metadata。该模型已实现为可序列化契约，完整多阶段生产编排仍在迁移中。

`StateReducer.apply()` 要求 delta 的 `expected_revision` 等于当前 revision。成功合并后 revision 递增；具有相同 `event_id` 的消息和验证结果只应用一次，纯重复验证结果保持 revision 不变。

## Workflow Contracts

`WorkflowDefinition` 包含 workflow 名称、入口节点、StateGraph 和 legacy endpoint。当前定义主要承载单节点 legacy workflow。`build_legacy_workflow()` 将旧 Agent handler 转换为 StateDelta，并在 metadata 中保留原始结果。`run_workflow()` 从可序列化 State 启动图运行。

## Retrieval Contracts

统一检索使用 `RetrievalRequest`、`RetrievalChunk` 和 `RetrievalResult`。chunk 实际携带 `source_type`、`source_id`、`content_hash`、`metadata` 和 `retrieved_at`；项目/会话范围通过请求字段和 metadata 过滤，来源信息由来源字段和 metadata 表达。服务支持排序、去重和降级结果，当前尚未接入生产 Agent 主链路。

## Validation Contracts

云端验证使用 `source=cloud`、`scope=cloud_syntax`，并根据 `State.metadata.required_validation_scopes` 创建本地验证动作。本地结果适配器只接受 `local_runtime` 或 `local_e2e`，校验 task、session、revision、schema version、scope 和 `source=local`，并将协议字段映射到内部 `scope`、`passed`、`source=vscode` 契约。`passed`、`failed`、`timeout`、`rejected` 和 `cancelled` 进入终态推导，`waiting_for_confirmation` 保持未完成；适配器按已完成 scope 更新待执行动作，所有必需 scope 通过后才产生 `completed` 状态。VS Code 插件的真实消费与结果回传仍需本地 E2E 环境验收。

`vscode-extension/src/protocol.ts` 提供 VS Code 端的 `PendingAction` 和 `LocalValidationResult` 类型及运行时解析器。插件端使用 `validation_scope`、`source=local` 和参数数组命令；连接层接入云端时需将 Envelope 字段映射到现有本地结果适配器的 `scope` 和 `source` 契约。

`vscode-extension/src/agent-host.ts` 提供通用 `AgentHostEnvelope`、Host Hello、能力声明、策略快照和 `AgentHostSession`。会话握手校验协议版本、工作区、扩展版本、能力清单和待执行动作；策略更新要求 `policy_version` 严格递增，支持的能力包括 `workspace`、`file`、`terminal`、`diagnostics`、`validation` 和 `skill_runtime`。

`vscode-extension/src/tool-dispatcher.ts` 提供本地工具分发。文件读取和修改使用工作区授权路径、UTF-8 内容 hash、读取大小上限和 expected hash 冲突保护；诊断通过注入适配器获取；验证和终端动作复用 `ValidationRunner`，并遵守参数数组、`shell=false`、本地执行总开关和验证操作开关。

`vscode-extension/src/webview-bridge.ts` 提供 Webview 与扩展 Host 的消息、请求响应关联、超时和释放处理。`vscode-extension/src/agent-host-runtime.ts` 校验会话与策略版本，将工具动作交给 `ToolDispatcher`，并把非验证结果包装为 `tool_result` 事件或将本地验证结果提交到云端连接层。

`vscode-extension/src/agent-workbench.ts` 提供原生 Webview 工作台控制器和安全 HTML。`codingmatrix.openAgentWorkbench` 命令由 `src/extension.ts` 注册，打开单例 Agent 面板并通过 `WebviewBridge` 连接 Host 消息。

`vscode-extension/src/approval-bridge.ts` 管理本地审批请求和决定。`AgentHostRuntime` 在会话策略关闭自动批准时暂停工具动作，发布 `approval_request`，并在批准后继续执行；拒绝决定返回 `rejected` 状态。

`vscode-extension/src/connection.ts` 提供 Bearer 认证的动作拉取和结果提交客户端，默认路径为 `/api/v1/agent/local-validation/actions` 与 `/api/v1/agent/local-validation/results`。客户端对 401/403 返回认证错误，对 408/429/5xx 执行有限重试，网络中断时将结果写入可注入的 `ResultStore`，新连接实例可刷新持久化队列并在云端确认后删除记录。

`vscode-extension/src/workspace-authorization.ts` 提供工作区授权、撤销、多工作区隔离和路径解析。路径必须相对授权根目录，解析后的符号链接目标也必须位于对应工作区内。

`vscode-extension/src/validation-runner.ts` 通过注入的进程适配器执行验证动作，固定使用参数数组和 `shell=false`，并提供操作白名单、超时、取消、退出码和输出上限控制。执行结果统一映射为 `LocalValidationResult`。

`vscode-extension/src/result-sanitizer.ts` 在结果回传前处理密钥、Bearer token、密码、Cookie、私钥和连接串，并对处理后的结果执行安全复检。`vscode-extension/src/result-store.ts` 通过可注入存储保存待回传结果，按 `event_id` 去重，并在云端确认后移除记录。

`vscode-extension/src/status-view.ts` 提供与 VS Code API 解耦的验证状态视图模型。`ValidationStatusView` 将授权等待、运行、通过、失败、超时、拒绝和取消映射为可展示快照，提供耗时、取消能力、通知文本和带文件位置的诊断摘要；结果兜底匹配同时校验 `session_id`、`task_id`、`revision` 和 `validation_scope`，避免多 scope 动作串写。

`vscode-extension/src/compatibility.ts` 提供启动阶段兼容性校验。云端握手必须声明支持插件当前的 `schema_version`，可选的 `plugin_version.min` 和 `plugin_version.max` 使用严格 `x.y.z` 版本格式；不兼容时返回结构化 `CompatibilityError`，调用方应阻止创建新的本地验证动作并展示升级指引。`package.json` 的 manifest 入口为 `dist/extension.js`，打包脚本为 `vsce package --no-dependencies`。

## 持久化与事件

`CheckpointStore` 提供版本化 JSON checkpoint 的保存和加载能力，`progress_event_to_message()` 提供进度事件到 `MessageEnvelope` 的转换，`replay_session()` 提供带序列缺口恢复动作的回放结果。插件连接层使用 `ResultStore` 支持跨实例断线结果恢复。当前 API、SessionManager 和任务队列尚未自动调用 checkpoint 持久化，现有 SSE 仍保留原始事件出口。
