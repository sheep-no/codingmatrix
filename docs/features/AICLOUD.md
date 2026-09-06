# AI Cloud

> 最后更新：2026-09-03

AI Cloud 为具有 admin 或更高权限的用户提供受控的 AI 会话、沙箱文件、审查、审计、代码执行和知识库能力。每个端点先通过 JWT 获取用户 ID，再调用 `check_aicloud_permission()` 校验管理员权限。

## API 总览

主路由前缀为 `/api/v1/aicloud`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/aicloud/chat` | 同步聊天 |
| POST | `/api/v1/aicloud/chat/stream` | SSE 流式聊天 |
| POST | `/api/v1/aicloud/read` | 读取沙箱文件 |
| POST | `/api/v1/aicloud/write` | 写入沙箱文件或进入审查流程 |
| GET | `/api/v1/aicloud/history` | 获取会话历史 |
| GET | `/api/v1/aicloud/history/search` | 搜索历史 |
| GET | `/api/v1/aicloud/history/export/{session_id}` | 导出会话 |
| DELETE | `/api/v1/aicloud/history/{session_id}` | 删除会话 |
| GET | `/api/v1/aicloud/audit-logs` | 查询审计日志 |
| GET | `/api/v1/aicloud/reviews` | 查询审查队列 |
| POST | `/api/v1/aicloud/reviews/approve` | 批准审查项 |
| POST | `/api/v1/aicloud/reviews/reject` | 拒绝审查项 |
| GET | `/api/v1/aicloud/models` | 列出可用模型 |
| POST | `/api/v1/aicloud/execute` | 执行代码任务 |

知识库路由前缀为 `/api/v1/aicloud/knowledge`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/aicloud/knowledge/upload` | 上传并处理文档 |
| GET | `/api/v1/aicloud/knowledge/docs` | 列出当前用户文档 |
| DELETE | `/api/v1/aicloud/knowledge/docs/{doc_id}` | 删除当前用户文档 |
| POST | `/api/v1/aicloud/knowledge/search` | 向量检索 |

## 会话状态

同步和流式聊天均维护两套状态：

- `AicloudSession` 与 `AicloudMessage` 保存 AI Cloud 旧版会话数据。
- `app/services/aicloud_state_adapter.py` 将同一会话和消息写入统一状态模型。
- 会话读取、导出和删除按当前用户过滤；删除接口清理旧版会话及其消息并失效相关缓存。

模型来自 AI Cloud 模型注册表。请求可指定模型 ID，缺省时使用注册表默认模型。

## 沙箱文件与执行

- `ensure_user_sandbox()` 为用户准备隔离工作区。
- `SandboxFileOperator` 处理文件读取和写入。
- `is_protected_path()` 与 `is_protected_file()` 阻止访问受保护目标。
- 写操作会记录审计信息，并可进入人工审查队列。
- `execute_with_llm_loop()` 负责代码执行及模型反馈循环，具体隔离强度取决于当前沙箱执行器和部署环境。

## 审查与审计

- 审查队列支持创建、批准和拒绝。
- 审计日志记录聊天、文件读取、文件写入等操作。
- 列表接口按调用者权限和服务查询条件返回数据。

## 知识库

上传流程依次执行文件保存、内容解析、文本分块、嵌入生成和数据库写入。当前允许的扩展名包括：

`.txt`、`.md`、`.pdf`、`.docx`、`.py`、`.js`、`.ts`、`.json`、`.yaml`、`.yml`、`.csv`、`.log`。

知识库文件存放在 `/workspace/data/knowledge`，元数据和文本块分别使用 `AicloudKnowledgeDoc`、`AicloudKnowledgeChunk` 持久化。列表、删除和搜索均校验当前用户及 collection 范围。

## 权限边界

- `AICLOUD_REQUIRED_PERMISSION` 为 `admin`。
- `is_admin()` 决定 admin 与更高权限级别的访问结果。
- 普通用户收到 HTTP 403。
- AI Cloud 权限独立于 `/api/v2/model-config` 的 superadmin 管理权限。
- 聊天写入会同步统一状态；当前历史删除路由没有调用统一状态删除适配器，因此对应统一 session/message 可能继续保留。

## 相关文件

- `app/api/v1/aicloud.py`
- `app/api/v1/aicloud_knowledge.py`
- `app/utils/aicloud/permission.py`
- `app/utils/aicloud/sandbox.py`
- `app/utils/aicloud/sandbox_operator.py`
- `app/utils/aicloud/review_queue.py`
- `app/utils/aicloud/audit_logger.py`
- `app/services/aicloud_state_adapter.py`
- `app/models/aicloud.py`
- `app/models/aicloud_knowledge.py`
- `src/components/Aicloud.vue`
- `src/utils/api/aicloud.js`
