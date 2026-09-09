# 工作流引擎

> 最后核对：2026-09-03
> 状态：API 与执行器活跃；统一状态适配器已实现、生产 API 尚未接入

## 当前架构

Workflow 接收自然语言请求，通过 `TaskDecomposer` 生成 `TaskGraph`，经 `GraphValidator` 校验后交给 `WorkflowExecutor` 执行。节点开始和结束回调进入异步队列，再以流式 JSON 行返回前端。

主要组件：

- `app/api/v1/workflow.py`：接口、运行时注册表、SSE 和历史记录
- `app/utils/workflow/task_decomposer.py`：自然语言任务分解
- `app/utils/workflow/graph_validator.py`：任务图验证
- `app/utils/workflow/executor.py`：依赖调度、并发执行和结果聚合
- `app/utils/workflow/node_types/`：节点实现
- `app/schema/workflow.py`：请求、任务图和事件契约

## 执行流程

1. `POST /api/v1/workflow/execute` 接收自然语言、超时、会话 ID 和导出选项。
2. 同一 `session_id` 的后续请求读取 `_session_workflows` 中的前序请求，构造继续执行上下文。
3. `TaskDecomposer` 生成任务图，`GraphValidator` 校验节点和依赖。
4. 任务图写入进程内 `_workflows`。
5. `WorkflowExecutor` 以 `max_concurrent=3` 执行节点，单节点超时取 300 秒与总超时一半中的较小值。
6. 完成结果写入 `WorkflowHistory`，会话续接信息写入 `_session_workflows`。

## 状态与恢复

当前生产 API 存在两类状态：

- 运行态：`_workflows` 和 `_session_workflows`，位于 API 进程内存中。进程重启后该状态消失，`status`、`export`、直接执行导入图和会话续接均依赖该状态。
- 历史态：`WorkflowHistory` 数据库记录，用于列表和详情查询。

`app/services/workflow_state_adapter.py` 已实现将 Workflow 阶段写入统一 Task/Event 状态模型的适配能力，并有单元测试覆盖。截至 2026-09-03，`app/api/v1/workflow.py` 未调用该适配器，因此统一状态恢复尚未成为 Workflow API 的生产恢复路径。

## 流式事件

`/execute` 和 `/{workflow_id}/execute` 返回 `application/x-ndjson`，每行是一个 JSON 对象。当前事件包括：

- `workflow_started`
- `continuation_context`
- `task_graph_generated`
- `workflow_exported`
- `node_started`
- `node_completed`
- `workflow_completed`
- `workflow_error`

事件字段随类型变化，常用字段包括 `workflow_id`、`session_id`、`node_id`、`data`、`error`、`message` 和 `timestamp`。

## API

所有业务端点使用 Token 认证：

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/api/v1/workflow/execute` | 分解并执行自然语言工作流 |
| `GET` | `/api/v1/workflow/status/{workflow_id}` | 查询进程内工作流状态 |
| `POST` | `/api/v1/workflow/import` | 校验并导入任务图到进程内存 |
| `POST` | `/api/v1/workflow/{workflow_id}/execute` | 执行已导入任务图 |
| `GET` | `/api/v1/workflow/export/{workflow_id}` | 导出进程内任务图 |
| `DELETE` | `/api/v1/workflow/{workflow_id}` | 移除进程内任务图 |
| `GET` | `/api/v1/workflow/history` | 分页查询当前用户历史 |
| `GET` | `/api/v1/workflow/history/{workflow_id}` | 查询当前用户历史详情 |
| `DELETE` | `/api/v1/workflow/history/{workflow_id}` | 删除当前用户历史记录 |

## 运行限制

- 状态查询和导入图执行要求请求命中保存该工作流的同一进程。
- 会话续接保存的是前序请求和工作流标识，数据库历史不会自动重建 `_session_workflows`。
- `WorkflowHistory` 提供审计和历史展示，当前不承担断点恢复。
- 统一状态适配器接入生产 API 后，才可将 Task、Event 与 Checkpoint 用作统一恢复依据。

## 前端

Workflow 页面相关代码位于 `src/views/Workflow.vue` 及其调用链。消费者应按 NDJSON 行解析，不应套用 Agent 的 `data: ...` SSE 帧协议。

## 代码索引

- `app/api/v1/workflow.py`
- `app/schema/workflow.py`
- `app/utils/workflow/`
- `app/services/workflow_state_adapter.py`
- `app/db/models.py` 中的 `WorkflowHistory`
