# AI Cloud API

## 聊天

### POST /api/v1/aicloud/chat
同步聊天请求。

**请求体**:
```json
{ "message": "string", "model": "string", "session_id": "string" }
```

**响应**: `{"content": "string", "tokens": number}`

### POST /api/v1/aicloud/chat/stream
流式聊天，SSE 推送。

## 文件操作

### POST /api/v1/aicloud/read
读取文件内容。

### POST /api/v1/aicloud/write
写入文件内容。

## 会话管理

### GET /api/v1/aicloud/history
获取会话历史列表。

### GET /api/v1/aicloud/history/search
搜索历史会话。

### GET /api/v1/aicloud/history/export/{session_id}
导出会话。

### DELETE /api/v1/aicloud/history/{session_id}
删除会话。

## 审计与审查

### GET /api/v1/aicloud/audit-logs
获取审计日志。

### GET /api/v1/aicloud/reviews
获取审查列表。

### POST /api/v1/aicloud/reviews/approve
批准审查。

### POST /api/v1/aicloud/reviews/reject
拒绝审查。

## 知识管理

### POST /api/v1/aicloud/knowledge/upload
上传文档到知识库。

### GET /api/v1/aicloud/knowledge/docs
列出知识库文档。

### DELETE /api/v1/aicloud/knowledge/docs/{doc_id}
删除文档。

### POST /api/v1/aicloud/knowledge/search
搜索知识库。

## 其他

### GET /api/v1/aicloud/models
列出可用模型。

### POST /api/v1/aicloud/execute
执行代码。
