# AI Cloud - 技术设计

## 数据模型

### AicloudSession

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 会话 UUID |
| user_id | Integer (FK) | 用户 ID |
| model | String | 使用的模型 |
| created_at | DateTime | 创建时间 |

### AicloudKnowledge

| 字段 | 类型 | 说明 |
|------|------|------|
| id | String (PK) | 文档 UUID |
| filename | String | 文件名 |
| content | Text | 文档内容 |
| user_id | Integer (FK) | 用户 ID |
| created_at | DateTime | 创建时间 |

## 审计日志

所有操作记录到结构化日志:

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

## 代码执行沙箱

- 使用 Docker 容器隔离
- CPU/内存限制
- 超时控制
- 网络隔离
