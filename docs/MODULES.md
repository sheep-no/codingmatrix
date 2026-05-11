# CodingMatrix 模块说明

## 后端模块 (app/)

### 核心框架

| 模块 | 路径 | 描述 |
|------|------|------|
| 主应用 | `app/main.py` | FastAPI 应用入口，中间件挂载，路由注册 |
| 配置 | `app/core/config.py` | 全局配置，环境变量加载 |
| 数据库 | `app/db/base.py` | SQLAlchemy 异步引擎，会话管理 |

### API 层

| 模块 | 路径 | 端点前缀 | 描述 |
|------|------|----------|------|
| Auth | `app/api/v1/auth.py` | `/api/v1` | 登录、注册、Token 刷新、RSA 公钥 |
| AI Code | `app/api/v1/Aicode.py` | `/api/v1/code` | 代码生成、历史管理、断点续传 |
| AI Project | `app/api/v1/AiProjectCode.py` | `/api/v1/agent` | 项目生成、文件管理、保存/加载 |
| AI Agent | `app/api/v1/ai_agent.py` | `/api/v1/agent` | Agent 处理、会话、知识、编排 |
| GirlAi | `app/api/v1/GirlAi.py` | `/api/v1/GirlAi` | 虚拟 AI 角色对话、历史管理 |
| Kolors | `app/api/v1/kolors_api.py` | `/api/v1/kolors` | 文生图、图生图、修复、头像等 |
| Kolors History | `app/api/v1/kolors_history.py` | `/api/v1/kolors/history` | 图像历史 CRUD |
| PPTX | `app/api/v1/aiGeneratorPptx.py` | `/api/v1/pptx` | PPT 异步生成、预览、下载 |
| File Upload | `app/api/v1/file_upload.py` | `/api/v1/files` | 文件上传、分片上传、下载 |
| Task Queue | `app/api/v1/task_queue.py` | `/api/v1/tasks` | 任务管理、状态查询、重试 |
| Vision | `app/api/v1/vision_api.py` | `/api/v1/vision` | 图像分析、OCR、代码提取、安全检查 |
| Workflow | `app/api/v1/workflow.py` | `/api/v1/workflow` | 工作流执行、导入导出、历史 |
| Aicloud | `app/api/v1/aicloud.py` | `/api/v1/aicloud` | AI 云聊天、文件读写、审计 |
| Aicloud Knowledge | `app/api/v1/aicloud_knowledge.py` | `/api/v1/aicloud/knowledge` | 知识库上传、搜索 |
| Health | `app/api/v1/health.py` | `/api/v1/health` | 健康检查、就绪/存活、Prometheus |

### v2 API

| 模块 | 路径 | 端点前缀 | 描述 |
|------|------|----------|------|
| Controller | `app/api/v2/Controller.py` | `/api/v2/Controller` | 用户管理、服务管理、系统管理 |
| Nginx API | `app/api/v2/nginx_api.py` | `/api/v2/nginx` | Nginx 配置生成、检查、部署 |
| Nginx AI | `app/api/v2/nginx_ai.py` | `/api/v2/nginx` | AI 辅助 Nginx 配置分析 |
| Guardian | `app/api/v2/guardian_router.py` | `/api/v2/Controller` | 服务熔断、守护进程 |
| User Manage | `app/api/v2/user_manage.py` | `/api/v2/Controller` | 用户 CRUD、密码重置 |

### 工具层 (app/utils/)

| 工具 | 文件 | 描述 |
|------|------|------|
| 安全 | `security.py` | JWT 创建/验证、密码哈希、权限检查 |
| 加密 | `encryption.py` | RSA-OAEP + AES-CBC 加密解密 |
| CSRF | `csrf.py` | CSRF Token 生成验证、Double-submit Cookie |
| 限流 | `rate_limiter.py` | IP/用户/端点限流 |
| 熔断器 | `circuit_breaker.py` | 服务熔断保护 |
| 缓存 | `cache.py`, `cache_decorator.py` | Redis/内存缓存 |
| 日志 | `logging.py`, `structured_logging.py` | 结构化 JSON 日志 |
| 监控 | `system_monitor.py` | 系统资源监控 |
| 搜索 | `web_search.py` | Bing/DuckDuckGo 搜索 |
| 视觉 | `vision.py` | 图像分析、OCR |
| 工作流 | `workflow/` | 工作流引擎 |
| Docker | `docker_runner.py` | Docker 容器运行 |
| 错误处理 | `error_handler.py` | 全局异常处理 |

### 数据模型 (app/models/)

| 模型 | 文件 | 描述 |
|------|------|------|
| User | `user.py` | 用户信息、权限级别、密码 |
| History | `history.py` | 聊天/代码生成历史 |
| File | `file.py` | 上传文件元数据 |
| Task | `task.py` | 异步任务状态 |
| SavedProject | `saved_project.py` | 已保存的 AI 项目 |
| AgentMemory | `agent_memory.py` | Agent 会话记忆 |
| Aicloud | `aicloud.py` | AI 云会话、审核 |
| AicloudKnowledge | `aicloud_knowledge.py` | 知识库文档 |
| ServerConfig | `server_config.py` | 服务器配置 |
| ChatHistory | `chat_history.py` | 对话历史 |
| Permission | `Permission.py` | 权限定义 |

## 前端模块 (src/)

### Vue 组件

| 组件 | 路径 | 描述 |
|------|------|------|
| App | `src/App.vue` | 根组件，路由容器 |
| Login | `src/components/Login.vue` | RSA 加密登录页 |
| MainLayout | `src/components/MainLayout.vue` | 主布局，侧边栏导航 |
| CodeGenerator | `src/components/CodeGenerator.vue` | AI 代码生成 |
| ProjectGenerator | `src/components/ProjectGenerator.vue` | AI 项目生成 |
| GirlAiChat | `src/components/GirlAiChat.vue` | 虚拟 AI 对话 |
| PptGenerator | `src/components/PptGenerator.vue` | PPT 生成 |
| ImageGenerator | `src/components/ImageGenerator.vue` | Kolors 图像生成 |
| WorkflowEditor | `src/components/WorkflowEditor.vue` | 工作流编辑器 |
| FileUpload | `src/components/FileUpload.vue` | 文件上传 |
| SystemMonitor | `src/components/SystemMonitor.vue` | 系统监控面板 |
| PreviewPanel | `src/components/PreviewPanel.vue` | 多模态文件预览 |
| ToolsPanel | `src/components/ToolsPanel.vue` | 工具面板 |

### 状态管理

| 模块 | 文件 | 描述 |
|------|------|------|
| User Store | `src/stores/user.js` | 用户状态、权限、Token |
| Chat Store | `src/stores/chat.js` | 聊天消息、会话 |
| Task Store | `src/stores/task.js` | 任务状态管理 |
