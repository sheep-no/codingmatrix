# API 文档

> 最后更新: 2026-05-27 | 路由总数：180+ | 版本：v1 (17 模块) + v2 (6 模块) | 项目版本：v5.10.0

## 认证

### POST /api/v1/login
登录获取 JWT Token。密码使用 RSA-OAEP 加密。

**请求体**:
```json
{ "username": "string", "password": "encrypted_string" }
```

**响应**: `{"access_token": "...", "refresh_token": "..."}`

### POST /api/v1/register
注册新用户。

**请求体**:
```json
{ "username": "string", "password": "string", "email": "string" }
```

### POST /api/v1/refresh
刷新 Access Token。

### GET /api/v1/public-key
获取 RSA 公钥 (PEM 格式)。

### GET /api/v1/csrf-token
获取 CSRF Token (用于 Double-submit Cookie 模式)。

### GET /api/v1/user/profile
获取当前用户资料。需要 JWT 认证。

## AI 代码生成 (`/api/v1/code`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/code` | 生成代码 (SSE 流式) | normal |
| POST | `/api/v1/code/resume` | 断点续传 | normal |
| GET | `/api/v1/code/resume/{resume_id}` | 获取部分响应 | normal |
| DELETE | `/api/v1/code/history` | 删除代码历史 | normal |

## AI 项目生成 (`/api/v1/agent`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/agent/generate` | 生成项目 | normal |
| POST | `/api/v1/agent/generate_stream` | 流式生成 (SSE) | normal |
| POST | `/api/v1/agent/generate_task` | 异步任务 | normal |
| GET | `/api/v1/agent/generate/status/{task_id}` | 任务状态 | normal |
| GET | `/api/v1/agent/generate/files` | 文件列表 | normal |
| GET | `/api/v1/agent/generate/read` | 读取文件 | normal |
| DELETE | `/api/v1/agent/generate/file` | 删除文件 | normal |
| GET | `/api/v1/agent/generate/download/{project_path}` | 下载项目 | normal |
| POST | `/api/v1/agent/save` | 保存项目 | normal |
| GET | `/api/v1/agent/saved` | 已保存列表 | normal |
| GET | `/api/v1/agent/saved/{project_id}` | 加载项目 | normal |
| DELETE | `/api/v1/agent/saved/{project_id}` | 删除项目 | normal |

## GitHub 集成 (`/api/v1/github`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/github/config` | 保存 GitHub 配置 | normal |
| GET | `/api/v1/github/config` | 获取 GitHub 配置 | normal |
| POST | `/api/v1/github/save-project` | 保存项目至 GitHub | normal |
| GET | `/api/v1/github/verify-token` | 验证 Token 有效性 | normal |

## AI Agent (`/api/v1/agent`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/agent/process` | 处理任务 | normal |
| POST | `/api/v1/agent/chat` | Agent 对话 | normal |
| POST | `/api/v1/agent/chat/stream` | 流式对话 (SSE) | normal |
| GET | `/api/v1/agent/sessions` | 会话列表 | normal |
| GET | `/api/v1/agent/sessions/{session_id}` | 会话详情 | normal |
| DELETE | `/api/v1/agent/sessions/{session_id}` | 删除会话 | normal |
| GET | `/api/v1/agent/knowledge` | 知识列表 | normal |
| POST | `/api/v1/agent/knowledge` | 添加知识 | normal |
| DELETE | `/api/v1/agent/knowledge/{id}` | 删除知识 | normal |
| GET | `/api/v1/agent/stats` | 统计信息 | normal |

## 虚拟 AI (`/api/v1/GirlAi`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v1/GirlAi/characters` | 角色列表 | normal |
| POST | `/api/v1/GirlAi` | 发送消息 | normal |
| GET | `/api/v1/GirlAi/history` | 历史记录 | normal |
| DELETE | `/api/v1/GirlAi/history` | 清空历史 | normal |

## 图像生成 (`/api/v1/kolors`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/kolors/text-to-image` | 文生图 | normal |
| POST | `/api/v1/kolors/image-to-image` | 图生图 | normal |
| POST | `/api/v1/kolors/inpaint` | 图像修复 | normal |
| POST | `/api/v1/kolors/avatar` | 头像生成 | normal |
| POST | `/api/v1/kolors/landscape` | 风景生成 | normal |
| POST | `/api/v1/kolors/icon` | 图标生成 | normal |
| GET | `/api/v1/kolors/config` | 配置信息 | normal |
| GET | `/api/v1/kolors/history` | 历史列表 | normal |
| GET | `/api/v1/kolors/history/{image_id}` | 历史详情 | normal |
| DELETE | `/api/v1/kolors/history/{image_id}` | 删除历史 | normal |
| DELETE | `/api/v1/kolors/history` | 删除全部 | normal |

## PPT 生成 (`/api/v1/pptx`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/pptx/generate_task` | 异步任务 | normal |
| POST | `/api/v1/pptx/generate` | 同步生成 | normal |
| GET | `/api/v1/pptx/download/{ppt_id}` | 下载 | normal |
| GET | `/api/v1/pptx/preview/{ppt_id}` | 预览 | normal |
| GET | `/api/v1/pptx/{ppt_id}/slides` | 幻灯片列表 | normal |
| DELETE | `/api/v1/pptx/{task_id}/cancel` | 取消任务 | normal |
| POST | `/api/v1/pptx/{task_id}/update` | 更新任务 | normal |

## 文件上传 (`/api/v1/files`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/files/upload` | 单文件上传 | normal |
| GET | `/api/v1/files/{file_id}/download` | 下载文件 | normal |
| POST | `/api/v1/files/upload/init` | 初始化分片 | normal |
| POST | `/api/v1/files/upload/chunk/{file_id}/{chunk_index}` | 上传分片 | normal |
| POST | `/api/v1/files/upload/merge/{file_id}` | 合并分片 | normal |

## 任务队列 (`/api/v1/tasks`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/tasks` | 创建任务 | normal |
| GET | `/api/v1/tasks/{task_id}` | 任务状态 | normal |
| GET | `/api/v1/tasks` | 任务列表 | normal |
| DELETE | `/api/v1/tasks/{task_id}` | 取消任务 | normal |
| POST | `/api/v1/tasks/{task_id}/retry` | 重试任务 | normal |

## 视觉分析 (`/api/v1/vision`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/vision/analyze` | 图像分析 | normal |
| POST | `/api/v1/vision/ocr` | OCR 识别 | normal |
| POST | `/api/v1/vision/code-from-image` | 代码提取 | normal |
| POST | `/api/v1/vision/check-safety` | 安全检查 | normal |

## 工作流 (`/api/v1/workflow`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/workflow/execute` | 自然语言执行工作流（流式 NDJSON） | normal |
| POST | `/api/v1/workflow/{workflow_id}/execute` | 执行已导入的工作流 | normal |
| GET | `/api/v1/workflow/status/{workflow_id}` | 状态查询 | normal |
| POST | `/api/v1/workflow/import` | 导入工作流 JSON | normal |
| GET | `/api/v1/workflow/export/{workflow_id}` | 导出工作流 JSON | normal |
| DELETE | `/api/v1/workflow/{workflow_id}` | 删除工作流 | normal |
| GET | `/api/v1/workflow/history` | 历史记录 | normal |

**支持的节点类型**: web_search, code_execution, chart_generation, file_processing, llm_call, conditional, human_approval, http_request, data_transform

**节点状态**: pending, running, completed, failed, waiting_approval, skipped

**资源限制**: 最大并发 4 节点, 单节点超时 300s, 工作流超时 1800s, 内存 512MB

## AI 云管理 (`/api/v1/aicloud`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v1/aicloud/chat` | 聊天 | admin |
| POST | `/api/v1/aicloud/chat/stream` | 流式聊天 | admin |
| POST | `/api/v1/aicloud/read` | 读取文件 | admin |
| POST | `/api/v1/aicloud/write` | 写入文件 | admin |
| GET | `/api/v1/aicloud/history` | 历史记录 | admin |
| GET | `/api/v1/aicloud/audit-logs` | 审计日志 | admin |
| GET | `/api/v1/aicloud/reviews` | 审查列表 | admin |
| POST | `/api/v1/aicloud/reviews/approve` | 批准审查 | admin |
| POST | `/api/v1/aicloud/reviews/reject` | 拒绝审查 | admin |
| GET | `/api/v1/aicloud/history/search` | 搜索历史 | admin |
| GET | `/api/v1/aicloud/history/export/{session_id}` | 导出会话 | admin |
| DELETE | `/api/v1/aicloud/history/{session_id}` | 删除会话 | admin |
| GET | `/api/v1/aicloud/models` | 模型列表 | admin |
| POST | `/api/v1/aicloud/execute` | 执行代码 | admin |
| POST | `/api/v1/aicloud/knowledge/upload` | 上传文档 | admin |
| GET | `/api/v1/aicloud/knowledge/docs` | 文档列表 | admin |
| DELETE | `/api/v1/aicloud/knowledge/docs/{doc_id}` | 删除文档 | admin |
| POST | `/api/v1/aicloud/knowledge/search` | 搜索知识 | admin |

## 文件预览 (`/api/v1/preview`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v1/preview/{file_id}` | 文件预览 | normal |
| GET | `/api/v1/preview/{file_id}/raw` | 原始文件 | normal |
| GET | `/api/v1/preview/{file_id}/thumbnail` | 缩略图 | normal |
| POST | `/api/v1/preview/batch` | 批量预览 | normal |

## 系统管理 v2 (`/api/v2`)

### 用户管理

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v2/Controller/users` | 用户列表 | admin |
| POST | `/api/v2/Controller/create_user` | 创建用户 | admin |
| PATCH | `/api/v2/Controller/update_user/{user_id}` | 更新用户 | admin |
| DELETE | `/api/v2/Controller/delete_user/{user_id}` | 删除用户 | admin |
| POST | `/api/v2/Controller/{user_id}/reset-password` | 重置密码 | admin |

### 服务管理

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v2/Controller/services` | 服务列表 | admin |
| GET | `/api/v2/Controller/health/{port}` | 健康检查 | admin |
| POST | `/api/v2/Controller/guard/start` | 启动守护 | admin |
| PUT | `/api/v2/Controller/service/{port}/rename` | 重命名服务 | admin |
| PUT | `/api/v2/Controller/service/{port}/fuse-config` | 熔断配置 | admin |
| GET | `/api/v2/Controller/service/{service_name}/fuse-status` | 熔断状态 | admin |

### Nginx 管理

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| POST | `/api/v2/nginx/generate` | 生成配置 | super |
| POST | `/api/v2/nginx/check` | 检查配置 | admin |
| POST | `/api/v2/nginx/deploy` | 部署配置 | super |
| GET | `/api/v2/nginx/config` | 获取配置 | super |
| GET | `/api/v2/nginx/backups` | 备份列表 | super |
| DELETE | `/api/v2/nginx/backup/{backup_name}` | 删除备份 | super |

### 系统配置 (super)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v2/Controller/admin/config` | 配置列表 | super |
| GET | `/api/v2/Controller/admin/config/{key}` | 获取配置 | super |
| PUT | `/api/v2/Controller/admin/config/{key}` | 更新配置 | super |
| PUT | `/api/v2/Controller/admin/config/batch` | 批量更新 | super |
| GET | `/api/v2/Controller/admin/stats` | 系统统计 | super |
| GET | `/api/v2/Controller/admin/docker/containers` | Docker 容器 | super |
| GET | `/api/v2/Controller/admin/ws-stats` | WS 统计 | super |
| GET | `/api/v2/Controller/admin/log-config` | 日志配置 | super |
| PUT | `/api/v2/Controller/admin/log-config/level` | 更新日志级别 | super |
| PUT | `/api/v2/Controller/admin/log-config/global-level` | 全局日志级别 | super |
| GET | `/api/v2/Controller/admin/memory` | 内存统计 | super |
| GET | `/api/v2/Controller/admin/backup` | 创建备份 | super |
| GET | `/api/v2/Controller/admin/backup/list` | 备份列表 | super |
| GET | `/api/v2/Controller/admin/backup/{timestamp}` | 下载备份 | super |
| POST | `/api/v2/Controller/admin/backup/restore` | 恢复备份 | super |
| DELETE | `/api/v2/Controller/admin/backup/{filename}` | 删除备份 | super |
| GET | `/api/v2/Controller/admin/rate-limit` | 限流配置 | super |
| PUT | `/api/v2/Controller/admin/rate-limit/global` | 全局限流 | super |
| PUT | `/api/v2/Controller/admin/rate-limit/ip` | IP 限流 | super |
| PUT | `/api/v2/Controller/admin/rate-limit/user` | 用户限流 | super |
| PUT | `/api/v2/Controller/admin/rate-limit/endpoint` | 端点限流 | super |
| DELETE | `/api/v2/Controller/admin/rate-limit/endpoint/{endpoint}` | 删除限流 | super |
| PUT | `/api/v2/Controller/admin/rate-limit/enabled` | 开关限流 | super |

### 并发限制管理 (super)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v2/admin/config` | 获取系统配置 | super |
| POST | `/api/v2/admin/config` | 更新系统配置 | super |
| POST | `/api/v2/admin/user-limit` | 更新用户并发限制 | super |
| DELETE | `/api/v2/admin/user-limit/{user_id}` | 移除用户并发限制 | super |

## 健康检查 (`/api/v1/health`)

| 方法 | 路径 | 描述 | 权限 |
|------|------|------|------|
| GET | `/api/v1/health` | 基础健康检查 | public |
| GET | `/api/v1/health/ready` | 就绪检查 | public |
| GET | `/api/v1/health/live` | 存活检查 | public |
| GET | `/api/v1/health/detailed` | 详细健康信息 | public |
| GET | `/api/v1/health/metrics` | Prometheus 指标 | public |
| GET | `/api/v1/health/models` | 模型健康状态 | public |

## API 集成状态

> 端点总数: 180+ | 状态: 全部集成完成

### 认证相关 (6/6)
- [x] POST /api/v1/login - 用户登录 (RSA 加密密码)
- [x] POST /api/v1/register - 用户注册
- [x] POST /api/v1/refresh - Token 刷新
- [x] GET /api/v1/public-key - 获取 RSA 公钥
- [x] GET /api/v1/csrf-token - 获取 CSRF Token
- [x] GET /api/v1/user/profile - 用户资料

### AI 代码生成 (4/4)
- [x] POST /api/v1/code - 生成代码 (SSE 流式)
- [x] POST /api/v1/code/resume - 断点续传
- [x] GET /api/v1/code/resume/{resume_id} - 获取部分响应
- [x] DELETE /api/v1/code/history - 删除历史

### AI 项目生成 (13/13)
- [x] POST /api/v1/agent/generate - 生成项目
- [x] POST /api/v1/agent/generate_stream - 流式生成
- [x] POST /api/v1/agent/generate_task - 异步任务生成
- [x] GET /api/v1/agent/generate/status/{task_id} - 任务状态
- [x] GET /api/v1/agent/generate/files - 文件列表
- [x] GET /api/v1/agent/generate/read - 读取文件
- [x] DELETE /api/v1/agent/generate/file - 删除文件
- [x] GET /api/v1/agent/generate/download/{project_path} - 下载项目
- [x] POST /api/v1/agent/save - 保存项目
- [x] GET /api/v1/agent/saved - 已保存列表
- [x] GET /api/v1/agent/saved/{project_id} - 加载项目
- [x] DELETE /api/v1/agent/saved/{project_id} - 删除项目

### AI Agent (22/22)
- [x] POST /api/v1/agent/process - 处理任务
- [x] POST /api/v1/agent/process/stream - 流式处理
- [x] POST /api/v1/agent/react/process - ReAct 处理
- [x] POST /api/v1/agent/react/stream - ReAct 流式
- [x] GET /api/v1/agent/models - 可用模型列表
- [x] POST /api/v1/agent/review - 内容审查
- [x] POST /api/v1/agent/sessions - 创建会话
- [x] GET /api/v1/agent/sessions - 会话列表
- [x] GET /api/v1/agent/sessions/{session_id} - 会话详情
- [x] DELETE /api/v1/agent/sessions/{session_id} - 删除会话
- [x] POST /api/v1/agent/knowledge - 添加知识
- [x] GET /api/v1/agent/knowledge - 知识列表
- [x] GET /api/v1/agent/knowledge/search - 知识搜索
- [x] GET /api/v1/agent/stats/models - 模型统计
- [x] POST /api/v1/agent/orchestrate - 项目编排
- [x] POST /api/v1/agent/orchestrate/stream - 编排流式
- [x] POST /api/v1/agent/analyze_complexity - 复杂度分析
- [x] GET /api/v1/agent/cache/stats - 缓存统计
- [x] POST /api/v1/agent/cache/clear - 清空缓存
- [x] GET /api/v1/agent/learning/stats - 学习统计
- [x] GET /api/v1/agent/learning/common-errors/{file_type} - 常见错误

### 虚拟 AI (GirlAi) (4/4)
- [x] GET /api/v1/GirlAi/characters - 角色列表
- [x] POST /api/v1/GirlAi - 发送消息
- [x] GET /api/v1/GirlAi/history - 历史记录
- [x] DELETE /api/v1/GirlAi/history - 清空历史

### 图像生成 (Kolors) (11/11)
- [x] POST /api/v1/kolors/text-to-image - 文生图
- [x] POST /api/v1/kolors/image-to-image - 图生图
- [x] POST /api/v1/kolors/inpaint - 图像修复
- [x] POST /api/v1/kolors/avatar - 头像生成
- [x] POST /api/v1/kolors/landscape - 风景生成
- [x] POST /api/v1/kolors/icon - 图标生成
- [x] GET /api/v1/kolors/config - 配置信息
- [x] GET /api/v1/kolors/history - 历史列表
- [x] GET /api/v1/kolors/history/{image_id} - 历史详情
- [x] DELETE /api/v1/kolors/history/{image_id} - 删除历史
- [x] DELETE /api/v1/kolors/history - 删除全部历史

### PPT 生成 (7/7)
- [x] POST /api/v1/pptx/generate_task - 异步生成任务
- [x] POST /api/v1/pptx/generate - 同步生成
- [x] GET /api/v1/pptx/download/{ppt_id} - 下载
- [x] GET /api/v1/pptx/preview/{ppt_id} - 预览
- [x] GET /api/v1/pptx/{ppt_id}/slides - 幻灯片列表
- [x] DELETE /api/v1/pptx/{task_id}/cancel - 取消任务
- [x] POST /api/v1/pptx/{task_id}/update - 更新任务

### 文件管理 (5/5)
- [x] POST /api/v1/files/upload - 单文件上传
- [x] GET /api/v1/files/{file_id}/download - 下载文件
- [x] POST /api/v1/files/upload/init - 初始化分片上传
- [x] POST /api/v1/files/upload/chunk/{file_id}/{chunk_index} - 上传分片
- [x] POST /api/v1/files/upload/merge/{file_id} - 合并分片

### 任务队列 (5/5)
- [x] POST /api/v1/tasks - 创建任务
- [x] GET /api/v1/tasks/{task_id} - 任务状态
- [x] GET /api/v1/tasks - 任务列表
- [x] DELETE /api/v1/tasks/{task_id} - 取消任务
- [x] POST /api/v1/tasks/{task_id}/retry - 重试任务

### 视觉分析 (4/4)
- [x] POST /api/v1/vision/analyze - 图像分析
- [x] POST /api/v1/vision/ocr - OCR 识别
- [x] POST /api/v1/vision/code-from-image - 代码提取
- [x] POST /api/v1/vision/check-safety - 安全检查

### 工作流 (9/9)
- [x] POST /api/v1/workflow/execute - 执行工作流
- [x] GET /api/v1/workflow/status/{workflow_id} - 状态查询
- [x] POST /api/v1/workflow/import - 导入工作流
- [x] POST /api/v1/workflow/{workflow_id}/execute - 执行导入
- [x] GET /api/v1/workflow/export/{workflow_id} - 导出工作流
- [x] DELETE /api/v1/workflow/{workflow_id} - 删除工作流
- [x] GET /api/v1/workflow/history - 历史记录
- [x] GET /api/v1/workflow/history/{workflow_id} - 历史详情
- [x] DELETE /api/v1/workflow/history/{workflow_id} - 删除历史

### AI 云管理 (18/18)
- [x] POST /api/v1/aicloud/chat - 聊天
- [x] POST /api/v1/aicloud/chat/stream - 流式聊天
- [x] POST /api/v1/aicloud/read - 读取文件
- [x] POST /api/v1/aicloud/write - 写入文件
- [x] GET /api/v1/aicloud/history - 历史记录
- [x] GET /api/v1/aicloud/audit-logs - 审计日志
- [x] GET /api/v1/aicloud/reviews - 审查列表
- [x] POST /api/v1/aicloud/reviews/approve - 批准审查
- [x] POST /api/v1/aicloud/reviews/reject - 拒绝审查
- [x] GET /api/v1/aicloud/history/search - 搜索历史
- [x] GET /api/v1/aicloud/history/export/{session_id} - 导出会话
- [x] DELETE /api/v1/aicloud/history/{session_id} - 删除会话
- [x] GET /api/v1/aicloud/models - 模型列表
- [x] POST /api/v1/aicloud/execute - 执行代码
- [x] POST /api/v1/aicloud/knowledge/upload - 上传文档
- [x] GET /api/v1/aicloud/knowledge/docs - 文档列表
- [x] DELETE /api/v1/aicloud/knowledge/docs/{doc_id} - 删除文档
- [x] POST /api/v1/aicloud/knowledge/search - 搜索知识

### 系统管理 (v2)

#### 用户管理 (5/5)
- [x] GET /api/v2/Controller/users - 用户列表
- [x] POST /api/v2/Controller/create_user - 创建用户
- [x] PATCH /api/v2/Controller/update_user/{user_id} - 更新用户
- [x] DELETE /api/v2/Controller/delete_user/{user_id} - 删除用户
- [x] POST /api/v2/Controller/{user_id}/reset-password - 重置密码

#### 服务管理 (6/6)
- [x] GET /api/v2/Controller/services - 服务列表
- [x] GET /api/v2/Controller/health/{port} - 健康检查
- [x] POST /api/v2/Controller/guard/start - 启动守护
- [x] PUT /api/v2/Controller/service/{port}/rename - 重命名服务
- [x] PUT /api/v2/Controller/service/{port}/fuse-config - 熔断配置
- [x] GET /api/v2/Controller/service/{service_name}/fuse-status - 熔断状态

#### Nginx 管理 (6/6)
- [x] POST /api/v2/nginx/generate - 生成配置
- [x] POST /api/v2/nginx/check - 检查配置
- [x] POST /api/v2/nginx/deploy - 部署配置
- [x] GET /api/v2/nginx/config - 获取配置
- [x] GET /api/v2/nginx/backups - 备份列表
- [x] DELETE /api/v2/nginx/backup/{backup_name} - 删除备份

#### 系统管理 (super) (23/23)
- [x] GET /api/v2/Controller/admin/config - 配置列表
- [x] GET /api/v2/Controller/admin/config/{key} - 获取配置
- [x] PUT /api/v2/Controller/admin/config/{key} - 更新配置
- [x] PUT /api/v2/Controller/admin/config/batch - 批量更新
- [x] GET /api/v2/Controller/admin/stats - 系统统计
- [x] GET /api/v2/Controller/admin/docker/containers - Docker 容器
- [x] GET /api/v2/Controller/admin/ws-stats - WebSocket 统计
- [x] GET /api/v2/Controller/admin/log-config - 日志配置
- [x] PUT /api/v2/Controller/admin/log-config/level - 更新日志级别
- [x] PUT /api/v2/Controller/admin/log-config/global-level - 全局日志级别
- [x] GET /api/v2/Controller/admin/memory - 内存统计
- [x] GET /api/v2/Controller/admin/backup - 创建备份
- [x] GET /api/v2/Controller/admin/backup/list - 备份列表
- [x] GET /api/v2/Controller/admin/backup/{timestamp} - 下载备份
- [x] POST /api/v2/Controller/admin/backup/restore - 恢复备份
- [x] DELETE /api/v2/Controller/admin/backup/{filename} - 删除备份
- [x] GET /api/v2/Controller/admin/rate-limit - 限流配置
- [x] PUT /api/v2/Controller/admin/rate-limit/global - 全局限流
- [x] PUT /api/v2/Controller/admin/rate-limit/ip - IP 限流
- [x] PUT /api/v2/Controller/admin/rate-limit/user - 用户限流
- [x] PUT /api/v2/Controller/admin/rate-limit/endpoint - 端点限流
- [x] DELETE /api/v2/Controller/admin/rate-limit/endpoint/{endpoint} - 删除限流
- [x] PUT /api/v2/Controller/admin/rate-limit/enabled - 开关限流

#### 并发限制管理 (super) (4/4)
- [x] GET /api/v2/admin/config - 获取系统配置
- [x] POST /api/v2/admin/config - 更新系统配置
- [x] POST /api/v2/admin/user-limit - 更新用户并发限制
- [x] DELETE /api/v2/admin/user-limit/{user_id} - 移除用户并发限制
