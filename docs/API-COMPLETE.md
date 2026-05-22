# CodingMatrix API 完整文档（v5.4.0）

> 最后更新：2026-05-22 | 版本：v5.4.0

## 概述

本文档包含 CodingMatrix 项目所有 API 端点的完整说明，包括 Agent 系统、AI 云管理、用户认证、**多供应商模型系统**等。

**新增 v5.4.0**: 多供应商模型支持（SiliconFlow、阿里百炼、智谱 GLM、DeepSeek、OpenAI、Anthropic、Ollama）

---

## Agent 系统 API

### 基础信息

**基础路径**: `/api/v1/agent`

**认证**: 所有端点需要 JWT Token（通过 `Authorization: Bearer <token>` 头传递）

### 项目生成

#### 1. 流式生成项目（主要入口）

**端点**: `POST /orchestrate/stream`

**请求体**:
```json
{
  "requirement": "创建 Vue3 待办事项应用",
  "output_dir": "./projects/my_app",
  "enable_review": true,
  "enable_validation": true,
  "enable_error_recovery": true,
  "enable_memory": true,
  "spec_first": false,
  "dependency_graph": true,
  "session_id": "optional_custom_id",
  "incremental": false,
  "require_approval": false,
  "evaluation_only": false
}
```

**响应**: SSE (Server-Sent Events)

**事件类型**:
```
data: {"type": "progress", "data": {"message": "分析需求...", "phase": "analyzing"}}
data: {"type": "critical_decisions", "data": {"decisions": [...]}}
data: {"type": "done", "data": {"success": true, "total_files_created": 15}}
data: {"type": "error", "data": {"error": "生成失败"}}
```

**使用场景**: 新项目生成

---

#### 2. 增量修改项目

**端点**: `POST /modify`

**请求体**:
```json
{
  "project_path": "orchestrator/project_20260522_123456",
  "requirement": "添加删除待办事项功能",
  "session_id": "reuse_existing_id",
  "enable_review": false,
  "enable_validation": true,
  "enable_error_recovery": true,
  "enable_memory": true,
  "dependency_graph": true
}
```

**响应**: `OrchestratorResponse`
```json
{
  "success": true,
  "output_dir": "orchestrator/project_20260522_123456",
  "total_files_created": 3,
  "total_files": 15,
  "generated_files": [...],
  "models_used": {"architect": "...", "frontend": "..."}
}
```

**使用场景**: 已有项目增量修改

---

#### 3. 需求评估

**端点**: `POST /evaluate`

**请求体**:
```json
{
  "requirement": "创建一个电商网站",
  "output_dir": "./projects/evaluation_xxx"
}
```

**响应**: `EvaluateResponse`
```json
{
  "success": true,
  "evaluation_report": "需求分析报告...",
  "improvement_suggestions": ["建议 1", "建议 2"]
}
```

**特点**: 只分析不修改

---

### 复杂度分析

#### 4. 分析需求复杂度

**端点**: `POST /analyze_complexity`

**请求体**:
```json
{
  "requirement": "创建 Vue3 待办事项应用"
}
```

**响应**: `ComplexityAnalysisResponse`
```json
{
  "level": "small",
  "estimated_files": 12,
  "has_frontend": true,
  "has_backend": false,
  "has_database": false,
  "key_technologies": ["Vue 3", "Vite", "Pinia"],
  "risk_factors": [],
  "model_assignment": {
    "architect": "THUDM/GLM-Z1-9B-0414",
    "frontend": "Qwen/Qwen2.5-7B-Instruct",
    "backend": "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B"
  }
}
```

---

### 项目管理

#### 5. 保存项目

**端点**: `POST /save`

**请求体**:
```json
{
  "name": "我的待办事项应用",
  "description": "Vue3 实现的待办事项管理",
  "project_path": "orchestrator/project_20260522_123456",
  "project_data": "{\"files\": [...]}"  // JSON 字符串
}
```

**响应**: `SaveProjectResponse`
```json
{
  "id": 123,
  "name": "我的待办事项应用",
  "description": "...",
  "project_path": "orchestrator/project_20260522_123456",
  "created_at": "2026-05-22T10:00:00Z",
  "message": "项目保存成功"
}
```

**限制**: 每用户最多保存 `MAX_SAVED_PROJECTS_PER_USER` 个项目

---

#### 6. 获取已保存项目列表（分页）

**端点**: `GET /saved`

**查询参数**:
- `offset` (int, optional): 偏移量，默认 0
- `limit` (int, optional): 每页数量，默认 50

**响应**: `ProjectListResponse`
```json
{
  "projects": [
    {
      "id": 123,
      "name": "...",
      "description": "...",
      "project_path": "...",
      "created_at": "2026-05-22T10:00:00Z",
      "updated_at": "2026-05-22T11:00:00Z"
    }
  ],
  "total": 50,
  "max_allowed": 100
}
```

---

#### 7. 加载已保存项目

**端点**: `GET /saved/{project_id}`

**响应**: `LoadProjectResponse`
```json
{
  "id": 123,
  "name": "...",
  "description": "...",
  "project_path": "...",
  "project_data": "{\"files\": [...]}",
  "created_at": "...",
  "updated_at": "..."
}
```

---

#### 8. 删除已保存项目

**端点**: `DELETE /saved/{project_id}`

**响应**:
```json
{
  "status": "deleted",
  "project_id": 123
}
```

---

### 文件操作

#### 9. 获取项目文件列表

**端点**: `GET /generate/files`

**查询参数**:
- `project_path` (string, required): 项目路径

**响应**:
```json
{
  "project": "orchestrator/project_xxx",
  "total": 25,
  "skipped_dirs": 2,
  "skipped_files": 5,
  "files": [
    {
      "path": "src/App.vue",
      "name": "App.vue",
      "type": "file",
      "size": 1234,
      "modified": "2026-05-22T10:00:00Z"
    }
  ]
}
```

**排序**: 优先显示 `README.md`, `index.html`, `main.py`, `package.json`, `requirements.txt`

---

#### 10. 读取文件内容

**端点**: `GET /generate/read`

**查询参数**:
- `project_path` (string, required): 项目路径
- `file_path` (string, required): 文件相对路径

**响应**:
```json
{
  "project": "...",
  "file_path": "src/App.vue",
  "name": "App.vue",
  "mime_type": "text/vue",
  "size": 1234,
  "modified": "...",
  "content": "<template>...</template>"
}
```

---

#### 11. 删除文件

**端点**: `DELETE /generate/file`

**查询参数**:
- `project_path` (string, required)
- `file_path` (string, required)

**响应**:
```json
{
  "status": "deleted",
  "file_path": "src/App.vue"
}
```

---

#### 12. 下载项目 ZIP

**端点**: `GET /generate/download/{project_path:path}`

**路径参数**: `project_path` (string): 项目路径（URL encoded）

**响应**: File response (application/zip)

**Content-Disposition**: `attachment; filename="project_name.zip"`

---

### 会话管理

#### 13. 会话操作（取消/恢复/审批）

**端点**: `POST /session/{session_id}/action?action=<action>`

**路径参数**: `session_id` (string)

**查询参数**: `action` (enum): `"cancel"`, `"resume"`, `"approve"`, `"reject"`

**响应**:
```json
{
  "status": "cancelled",
  "session_id": "project_xxx"
}
```

---

#### 14. 提交用户决策

**端点**: `POST /session/{session_id}/decision`

**请求体**: `Dict[str, str]` - 用户选择的决策

**响应**:
```json
{
  "status": "submitted",
  "session_id": "...",
  "decisions": {...}
}
```

---

#### 15. 删除会话

**端点**: `DELETE /sessions/{session_id}`

**响应**:
```json
{
  "success": true,
  "message": "会话已删除"
}
```

---

### 快照管理

#### 16. 列出快照

**端点**: `GET /snapshots/{session_id}`

**响应**:
```json
{
  "session_id": "...",
  "snapshots": [
    {
      "tag": "v1.0.0",
      "commit": "abc123",
      "message": "Initial commit",
      "timestamp": "2026-05-22T10:00:00Z"
    }
  ]
}
```

---

#### 17. 回滚到快照

**端点**: `POST /rollback/{session_id}?target_tag=<tag>&delete_branch=true`

**响应**:
```json
{
  "success": true,
  "previous_tag": "v1.0.1",
  "current_tag": "v1.0.0",
  "files_restored": 5
}
```

---

#### 18. 快照差异对比

**端点**: `GET /snapshot/diff?session_id=&from_tag=&to_tag=`

**响应**:
```json
{
  "session_id": "...",
  "from": "v1.0.0",
  "to": "v1.0.1",
  "diff": "diff --git a/file.py b/file.py\n..."
}
```

---

### 需求联想

#### 19. 创建需求联想

**端点**: `POST /requirement-association`

**请求体**:
```json
{
  "requirement": "创建电商网站"
}
```

**响应**:
```json
{
  "association_id": 123,
  "associated_items": [
    {
      "id": 1,
      "type": "domain_template",
      "content": "电商领域模板...",
      "confidence": 0.95
    }
  ]
}
```

---

#### 20. 确认联想项

**端点**: `POST /requirement-association/confirm?association_id=<id>`

**响应**:
```json
{
  "success": true,
  "message": "联想项已确认"
}
```

---

#### 21. 反馈帮助性

**端点**: `POST /requirement-association/helpfulness`

**请求体**:
```json
{
  "association_id": 123,
  "helpful": true,
  "feedback": "很有帮助"
}
```

---

#### 22. 获取统计信息

**端点**: `GET /requirement-association/stats`

**响应**:
```json
{
  "total_associations": 1000,
  "helpful_count": 850,
  "helpful_rate": 0.85
}
```

---

### 知识库

#### 23. 添加知识

**端点**: `POST /knowledge`

**请求体**:
```json
{
  "content": "Vue 3 最佳实践...",
  "tags": ["vue", "frontend"],
  "file_type": "vue"
}
```

---

#### 24. 获取知识列表

**端点**: `GET /knowledge`

**查询参数**:
- `limit` (int, optional): 默认 50，最大 200
- `offset` (int, optional)

**响应**:
```json
{
  "total": 500,
  "items": [...]
}
```

---

#### 25. 搜索知识

**端点**: `GET /knowledge/search?query=<query>&limit=10`

**响应**: 语义搜索结果

---

### 性能监控

#### 26. 获取性能指标

**端点**: `GET /performance`

**响应**:
```json
{
  "avg_generation_time": 45.2,
  "total_projects": 150,
  "success_rate": 0.92
}
```

---

#### 27. 获取性能趋势

**端点**: `GET /performance/trends`

**响应**: 时间序列数据

---

#### 28. 导出性能数据

**端点**: `POST /performance/export`

**响应**: CSV/Excel 文件

---

### 并发限制管理

#### 29. 更新并发限制

**端点**: `PUT /concurrent-limits?role=<role>&new_limit=<limit>`

**权限**: Superadmin only

**响应**:
```json
{
  "role": "free",
  "old_limit": 1,
  "new_limit": 2,
  "changed_by": "admin",
  "timestamp": "2026-05-22T10:00:00Z"
}
```

---

#### 30. 获取推荐限制

**端点**: `GET /concurrent-limits/recommended`

**响应**:
```json
{
  "recommendations": {
    "free": 1,
    "basic": 2,
    "premium": 5
  }
}
```

---

#### 31. 获取限制变更历史

**端点**: `GET /concurrent-limits/history?limit=50`

**响应**:
```json
{
  "history": [
    {
      "role": "free",
      "old_limit": 1,
      "new_limit": 2,
      "changed_by": "admin",
      "timestamp": "..."
    }
  ]
}
```

---

### 缓存管理

#### 32. 获取缓存统计

**端点**: `GET /cache/stats`

**响应**:
```json
{
  "total_entries": 1500,
  "hit_rate": 0.75,
  "memory_usage_mb": 256
}
```

---

#### 33. 清除缓存

**端点**: `POST /cache/clear?mode=<mode>`

**参数**: `mode` (enum): `"expired"` (default), `"all"`

**响应**:
```json
{
  "cleared_count": 120,
  "mode": "expired"
}
```

---

### 学习系统

#### 34. 获取学习统计

**端点**: `GET /learning/stats`

**响应**:
```json
{
  "total_feedback": 500,
  "common_errors": {...}
}
```

---

#### 35. 获取常见错误

**端点**: `GET /learning/common-errors/{file_type}`

**响应**:
```json
{
  "errors": [
    {
      "error": "SyntaxError",
      "count": 50,
      "fix": "..."
    }
  ]
}
```

---

## AI 云管理 API

（待补充完整）

---

## 用户认证 API

（待补充完整）

---

## 管理员仪表板 API

### 系统配置

#### 36. 更新系统配置

**端点**: `PUT /admin/system-config`

**权限**: Superadmin only

**请求体**:
```json
{
  "session_management": {
    "enable_health_aware_routing": true,
    "max_concurrent_sessions": 100
  },
  "ppt_generation": {
    "enabled": true
  }
}
```

---

#### 37. 保存角色限制配置

**端点**: `POST /admin/role-limits`

**请求体**:
```json
{
  "free": 1,
  "basic": 2,
  "premium": 5,
  "enterprise": 10,
  "superadmin": 50
}
```

---

## 错误响应格式

所有 API 错误统一格式：

```json
{
  "detail": "错误描述信息",
  "status_code": 400
}
```

**常见状态码**:
- `200`: 成功
- `400`: 请求参数错误
- `401`: 未授权
- `403`: 禁止访问
- `404`: 资源不存在
- `429`: 请求过多（并发限制）
- `500`: 服务器内部错误

---

## 速率限制

| 用户角色 | 并发会话限制 |
|---------|-------------|
| free | 1 |
| basic | 2 |
| premium | 5 |
| enterprise | 10 |
| superadmin | 50 |

---

## 认证方式

1. 登录获取 JWT Token
2. 在所有请求头中添加: `Authorization: Bearer <token>`

---

## SDK 使用示例

### Frontend (JavaScript)

```javascript
import { api } from '@/utils/api'

// 流式生成项目
const response = await api.project.generateProjectStream({
  requirement: "创建 Vue3 应用",
  enable_review: true
})

// 增量修改
await api.project.modifyProjectStream({
  sessionId: "xxx",
  requirement: "添加删除功能",
  enable_review: false
})

// 保存项目
await api.project.saveProject(
  "我的项目",
  "项目描述",
  JSON.stringify(projectData)
)
```

---

**状态**: ✅ v5.2.2 完整
**维护**: API 变更时自动更新此文档
