# 会话生命周期

> 最后核对：2026-09-03
> 状态：多层会话模型并存，Agent StateGraph 已接入统一状态落库

## 会话层次

当前 Agent 运行包含四类相关状态。每一层承担不同职责：

| 层次 | 存储 | 职责 | 恢复能力 |
| --- | --- | --- | --- |
| Legacy `SessionManager` | 内存与 `./sessions/{session_id}.json` | 文件进度、增量检测、审批暂停和运行状态 | 30 天内可从 JSON 恢复 |
| `ProjectSession` | 数据库 `project_sessions` | 用户所有权、输出目录、总体状态和进度 | API 查询与兼容映射依据 |
| 统一状态 | Session、Task、Checkpoint、Event、Artifact 表 | StateGraph 快照、事件、产物和跨模块一致状态 | 按 Task/Checkpoint 恢复 |
| Agent Host | 内存与 `data/agent_host_sessions` | VS Code Host 握手、策略、待执行动作、事件 ACK、Skill 和控制状态 | JSON 原子持久化后重新加载 |

这些层次目前共同服务生产链路。`SessionManager` 的 JSON 状态仍然活跃，统一状态承担 StateGraph 和模型上下文的持久化。

## Legacy SessionManager

### 状态机

`SessionStatus` 定义五种状态：

- `running`
- `paused`
- `completed`
- `failed`
- `cancelled`

TTL 清理还会把运行中的数据库 `ProjectSession` 标记为 `expired`。

### 会话内容

`SessionState` 保存需求、输出目录、架构、文件计划、逐文件状态、当前步骤、错误、警告、增量文件集合、审批信息和历史 Git 快照字段。审批队列属于进程内对象，不写入 JSON。

### 恢复与清理

- 默认目录：`./sessions`
- TTL：30 天
- 内存活跃上限：500
- 加载顺序：内存优先，随后读取 JSON
- 并发恢复：按 session 使用锁和双重检查，避免创建重复实例
- 超限处理：先清理过期会话，再驱逐最旧的非 `running` 会话
- 过期处理：移除内存状态和 JSON，并尝试将运行中的 `ProjectSession` 更新为 `expired`

## 主流式入口并发与重连契约

`POST /api/v1/agent/orchestrate/stream` 按用户串行化创建检查。入口先清理该用户 `running` 状态且最后活动超过 7 天，或内存中缺少 `SessionState` 的僵尸会话，并将其标记为 `failed`。随后每个用户只允许一个 `running` 会话：同一 Token 对同一 `session_id`/task 且原生成任务仍活跃时，复用原任务队列并继续 SSE 重连；已有其他运行任务时返回 HTTP 429。`MAX_PROJECT_SESSIONS_PER_USER=2` 控制历史会话及其文件资源的保留数量，属于历史资源清理阈值。

`complete_session` 和 `cancel_session` 会写 JSON，并通过数据库会话工厂同步 `ProjectSession`。普通文件状态更新主要写入 JSON。

## ProjectSession

Agent 编排端点使用 `ProjectSession` 进行身份校验、状态查询、输出目录定位和运行结果记录。会话 action 执行前会校验当前用户所有权。

取消操作会触发运行取消事件、清理活跃任务、尝试清理输出目录、更新 JSON/DB 状态并释放并发计数。该操作具有文件清理副作用，客户端应在用户确认后调用。

## 统一状态落库

`app/agent/workflow_registry.py` 使用 `StateGraph` 运行工作流。每次完成运行后：

1. 保存本地 CheckpointStore 快照到 `data/agent_state_checkpoints`。
2. 在获得数据库上下文和用户 ID 时调用 `persist_agent_state`。
3. 将 legacy session ID 映射为统一 Session。
4. 创建或获取 `agent_graph` Task。
5. 保存完整 State Checkpoint。
6. 将 State 消息写为 Event。
7. 将生成文件写为 Artifact。
8. 持久化模型配置上下文。

`CompatibilityMapping` 连接 legacy `project_session` 标识与统一 Session ID。该映射支持渐进迁移期间的所有权查询和上下文读取。

当前生产 Agent 图由 `build_legacy_workflow` 包装 legacy handler，图内是单个 legacy 节点。统一状态链路已经生效，细粒度 Spec、依赖分析、生成和验证节点仍处于后续图迁移范围。

## 模型上下文持久化

模型上下文使用独立的 `agent_model_context` Task 和独立 revision 流。保存内容包括：

- schema 与配置版本
- 角色到模型的映射
- 当前模型和当前 Agent
- 各角色分配统计
- 最近 50 条 fallback 历史

读取与更新接口：

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| `GET` | `/api/v1/agent/sessions/{session_id}/model-context` | 读取最新快照；缺省时返回运行时默认上下文 |
| `PUT` | `/api/v1/agent/sessions/{session_id}/model-context` | 合并部分更新并写入新 revision |

PUT 支持 `expected_revision` 乐观并发控制，版本冲突返回 409。上下文只保存模型标识与运行统计，不保存凭据。

## Web Agent 控制

`POST /api/v1/agent/session/{session_id}/action?action=...` 支持：

| action | 行为 |
| --- | --- |
| `cancel` | 停止生成、清理状态与项目文件、标记取消 |
| `resume` | 从暂停状态恢复并按批准继续 |
| `approve` | 向审批队列提交批准并恢复 |
| `reject` | 向审批队列提交拒绝、跳过暂停文件并恢复 |

架构问题答案使用 `POST /api/v1/agent/session/{session_id}/decision` 提交。

## VS Code Agent Host 生命周期

握手端点 `POST /api/v1/agent/host/handshake` 创建 30 分钟 Host 会话。会话保存 workspace、能力、策略版本、待执行动作、已接收事件、Skill 和 `control_status`。

Host 控制端点 `POST /api/v1/agent/host/sessions/{session_id}/control` 接受 `pause`、`resume`、`cancel`。服务器更新状态并排队 `session_control` envelope，扩展轮询 actions 后在本地 runtime 应用控制。

Host 事件以 `message_id` 去重并返回 ACK。`tool_result` 会合并回 StateGraph，并在存在后续节点时继续执行。重启恢复依赖 `data/agent_host_sessions` 和 Agent 图的本地 checkpoint。

Host 能力集合：`workspace`、`file`、`terminal`、`diagnostics`、`validation`、`skill_runtime`。

本地验证 operation：`syntax_check`、`dependency_install`、`dependency_check`、`build`、`unit_test`、`e2e_test`、`service_check`。具体 operation 还受会话 policy 的布尔白名单控制。

## 恢复边界

- Legacy JSON 恢复文件生成上下文和逐文件状态。
- 统一 Checkpoint 恢复 StateGraph 状态与 revision。
- 模型上下文通过独立 Task 恢复，避免与图 revision 相互覆盖。
- Host JSON 恢复动作队列、事件和本地控制状态。
- Workflow API 使用另一套进程内注册表，其恢复边界见 `docs/features/WORKFLOW.md`。

## 代码索引

- `app/agent/session_manager.py`
- `app/db/models.py` 中的 `ProjectSession`
- `app/agent/state/`
- `app/agent/workflow_registry.py`
- `app/services/agent_state_adapter.py`
- `app/services/model_context_service.py`
- `app/api/v1/ai_agent/model_context_endpoints.py`
- `app/api/v1/agent_host.py`
- `vscode-extension/src/agent-host-runtime.ts`
