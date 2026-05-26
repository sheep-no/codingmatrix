# AI 云管理 (Aicloud)

AI 云管理是 CodingMatrix 的 superadmin 功能，提供完整的 AI 会话管理、文件操作、审计和知识库能力。

## 功能概览

| 功能 | 端点 | 权限 |
|------|------|------|
| 聊天 | POST /api/v1/aicloud/chat | admin |
| 流式聊天 | POST /api/v1/aicloud/chat/stream | admin |
| 文件读取 | POST /api/v1/aicloud/read | admin |
| 文件写入 | POST /api/v1/aicloud/write | admin |
| 历史记录 | GET /api/v1/aicloud/history | admin |
| 审计日志 | GET /api/v1/aicloud/audit-logs | admin |
| 审查管理 | GET/POST /api/v1/aicloud/reviews | admin |
| 代码执行 | POST /api/v1/aicloud/execute | admin |
| 知识管理 | /api/v1/aicloud/knowledge/* | admin |
| 模型列表 | GET /api/v1/aicloud/models | admin |

## API 端点详情

### 聊天

**POST /api/v1/aicloud/chat** — 同步聊天请求。

请求体:
```json
{ "message": "string", "model": "string", "session_id": "string" }
```

响应: `{"content": "string", "tokens": number}`

**POST /api/v1/aicloud/chat/stream** — 流式聊天，SSE 推送。

### 文件操作

**POST /api/v1/aicloud/read** — 读取文件内容。

**POST /api/v1/aicloud/write** — 写入文件内容。

### 会话管理

**GET /api/v1/aicloud/history** — 获取会话历史列表。

**GET /api/v1/aicloud/history/search** — 搜索历史会话。

**GET /api/v1/aicloud/history/export/{session_id}** — 导出会话。

**DELETE /api/v1/aicloud/history/{session_id}** — 删除会话。

### 审计与审查

**GET /api/v1/aicloud/audit-logs** — 获取审计日志。

**GET /api/v1/aicloud/reviews** — 获取审查列表。

**POST /api/v1/aicloud/reviews/approve** — 批准审查。

**POST /api/v1/aicloud/reviews/reject** — 拒绝审查。

### 知识管理

**POST /api/v1/aicloud/knowledge/upload** — 上传文档到知识库。

**GET /api/v1/aicloud/knowledge/docs** — 列出知识库文档。

**DELETE /api/v1/aicloud/knowledge/docs/{doc_id}** — 删除文档。

**POST /api/v1/aicloud/knowledge/search** — 搜索知识库。

### 其他

**GET /api/v1/aicloud/models** — 列出可用模型。

**POST /api/v1/aicloud/execute** — 执行代码。

## 工具函数

工具模块位置: `app/utils/aicloud/`

### 核心工具

| 工具 | 文件 | 描述 |
|------|------|------|
| API Client | `api_client.py` | SiliconFlow API 客户端封装 |
| Session Manager | `session_manager.py` | 会话生命周期管理 |
| Code Executor | `code_executor.py` | 沙箱代码执行 |
| File Manager | `file_manager.py` | 文件读写操作 |
| Audit Logger | `audit_logger.py` | 审计日志记录 |
| Review Engine | `review_engine.py` | 内容审查 |

### 使用示例

```python
from app.utils.aicloud.session_manager import SessionManager
from app.utils.aicloud.audit_logger import AuditLogger

manager = SessionManager()
session = manager.create_session(user_id="1", model="qwen2.5-coder")

logger = AuditLogger()
logger.log(session_id=session.id, action="chat", user_id="1")
```

### 生产级能力

| 模块 | 能力 |
|------|------|
| 会话管理 | 创建、恢复、超时清理；上下文窗口管理；多会话并发控制 |
| 审计追踪 | 所有操作审计日志；IP/时间戳/操作类型记录；不可篡改日志存储 |
| 内容审查 | AI 生成内容自动审查；敏感词过滤；人工审查工作流 |
| 代码执行安全 | Docker 容器沙箱隔离；超时控制；CPU/内存资源限制；网络隔离 |
| 知识库管理 | 文档解析 (PDF/Markdown/TXT)；向量化索引；语义搜索；版本管理 |

### 安全注意事项

1. 所有文件操作在沙箱中进行
2. 代码执行有严格的超时和资源限制
3. 审计日志不可删除
4. 敏感操作需要管理员权限

## 需求与设计规格

### 需求 — 用户故事

1. 作为管理员，通过统一的 AI 云界面管理所有 AI 会话
2. 作为管理员，审计所有 AI 操作记录
3. 作为管理员，审查 AI 生成的内容
4. 作为管理员，在沙箱中执行 AI 生成的代码

### 数据模型

**AicloudSession**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 会话 UUID |
| user_id | Integer (FK) | 用户 ID |
| model | String | 使用的模型 |
| created_at | DateTime | 创建时间 |

**AicloudKnowledge**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 文档 UUID |
| filename | String | 文件名 |
| content | Text | 文档内容 |
| user_id | Integer (FK) | 用户 ID |
| created_at | DateTime | 创建时间 |

### 审计日志结构

```json
{
 "timestamp": "2026-05-08T00:00:00Z",
 "user_id": "1",
 "session_id": "uuid",
 "action": "chat",
 "model": "qwen2.5-coder",
 "tokens_used": 1500
}
```

### 实现状态: 完成

最后更新: 2026-05-13