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

## 相关文档

- [API.md](API.md) - 详细 API 文档
- [MODELS.md](MODELS.md) - 模型配置
- [UTILS.md](UTILS.md) - 工具函数
- [PRODUCTION-UTILS.md](PRODUCTION-UTILS.md) - 生产工具
