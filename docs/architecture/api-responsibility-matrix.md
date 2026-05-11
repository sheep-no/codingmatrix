# API 职责矩阵

## v1 API 职责

| 模块 | 职责 | 主要端点 | 依赖 |
|------|------|----------|------|
| Auth | 用户认证、Token 管理 | login, register, refresh | JWT, RSA |
| Aicode | AI 代码生成 | /code, /code/resume | SiliconFlow LLM |
| AiProjectCode | AI 项目生成 | /agent/generate, /agent/save | LLM, SQLite |
| ai_agent | Agent 核心处理 | /agent/process, /agent/sessions | LLM, 知识库 |
| GirlAi | 虚拟 AI 对话 | /GirlAi, /GirlAi/history | LLM |
| kolors_api | 图像生成 | /kolors/text-to-image | SiliconFlow Image API |
| aiGeneratorPptx | PPT 生成 | /pptx/generate | LLM, python-pptx |
| file_upload | 文件管理 | /files/upload, /files/download | 文件系统 |
| task_queue | 异步任务 | /tasks | APScheduler |
| vision_api | 视觉分析 | /vision/analyze | LLM Vision |
| workflow | 工作流引擎 | /workflow/execute | 图执行引擎 |
| aicloud | AI 云管理 | /aicloud/chat | LLM |
| health | 健康检查 | /health | - |

## v2 API 职责

| 模块 | 职责 | 主要端点 | 权限 |
|------|------|----------|------|
| Controller | 用户/服务/系统管理 | /users, /admin/* | admin/super |
| nginx_api | Nginx 配置管理 | /nginx/generate, /nginx/deploy | super |
| nginx_ai | AI 辅助 Nginx 分析 | /nginx/check | admin |
| guardian_router | 服务守护/熔断 | /guard/start, /service/fuse | admin |
| user_manage | 用户 CRUD | /users, /reset-password | admin |

## 横切关注点

| 关注点 | 实现位置 | 说明 |
|--------|----------|------|
| JWT 认证 | `app/utils/security.py` | Token 创建、验证、解析 |
| CSRF 防护 | `app/utils/csrf.py` | Double-submit Cookie |
| 限流 | `app/utils/rate_limiter.py` | IP/用户/端点维度 |
| 日志 | `app/utils/logging.py` | 结构化 JSON 日志 |
| 错误处理 | `app/utils/error_handler.py` | 全局异常处理 |
| 权限 | `app/utils/permissions.py` | RBAC 三级权限检查 |
| 缓存 | `app/utils/cache.py` | Redis/内存缓存 |
| 熔断 | `app/utils/circuit_breaker.py` | 服务熔断保护 |
