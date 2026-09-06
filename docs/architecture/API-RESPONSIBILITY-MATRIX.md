# API 职责矩阵

> 最后更新：2026-09-03 | `app/main.py` 挂载 28 个 router，其中 v1 20 个、v2 8 个 | `app/api` 约 279 个 HTTP/WebSocket 路由装饰器

## v1 API 职责

| 挂载模块 | 最终前缀或代表端点 | 核心职责 | 主要状态/服务依赖 |
|----------|--------------------|----------|-------------------|
| `auth` | `/api/v1/login`、`/register`、`/refresh` | 用户认证、Token、资料和会话历史 | JWT、RSA、User、History |
| `Aicode` | `/api/v1/code`、`/code/resume` | 通用问答、代码生成及中断恢复 | `call_llm()`、文件与多模态输入 |
| `GirlAi` | `/api/v1/GirlAi/*` | 角色对话、历史、头像、自定义角色和偏好 | GirlAI 状态适配、统一状态、ChatHistory |
| `aiGeneratorPptx` | `/api/v1/pptx/*`、`/api/v1/generate-text` | 大纲生成/审批、PPT 生成、单页重生成、质量报告、预览和下载 | PPT 编排器、Task、Artifact、PPTOutline、PPTQualityReport |
| `file_upload` | `/api/v1/files/*` | 上传、分片、断点续传和下载 | File、文件存储 |
| `task_queue` | `/api/v1/tasks/*` | 创建、查询、取消、retry、recover、heartbeat、事件重放和 WebSocket 进度 | Celery、Task、TaskEvent、Checkpoint、worker lease |
| `kolors_api` | `/api/v1/kolors/*` | 文生图与图生图 | 图像模型供应商 |
| `kolors_history` | `/api/v1/kolors/*` | 图像生成历史 | ImageGenerationHistory |
| `aicloud` | `/api/v1/aicloud/*` | 聊天、文件读写、审查、审计和执行 | AI Cloud 状态适配、统一状态、LLM |
| `aicloud_knowledge` | `/api/v1/aicloud/knowledge/*` | 文档上传、索引、删除和检索 | KnowledgeDoc、KnowledgeChunk |
| `workflow` | `/api/v1/workflow/*` | 工作流执行、状态、导入导出和历史 | workflow 状态适配、StateGraph |
| `ai_agent` | `/api/v1/agent/*` | 项目编排、生成、修改、会话、快照、知识、性能及模型上下文 | Agent、StateGraph、ModelContextService |
| `vision_api` | `/api/v1/vision/*` | 图像分析、OCR、图生代码和安全检查 | `call_llm(messages=...)` |
| `github` | `/api/v1/github/*` | GitHub 配置和仓库集成 | GitHub API |
| `apikey` | `/api/v1/agent/apikey/*` | 用户 API Key、测试、启停、上下文长度和 fallback 偏好 | RSA、Redis、ProviderRouter |
| `providers` | `/api/v1/providers/*` | 动态供应商 CRUD、模型同步和连通测试 | DynamicProviderManager |
| `agent_host` | `/api/v1/agent/host/*` | VS Code Host 握手、动作、事件、策略、Skill 同步和 pause/resume/cancel | 内存会话、`data/agent_host_sessions/*.json` |
| `model_manager` | `/api/v1/models/*` | 用户可见模型和 Agent 配置浏览 | v5.0 模型配置 |
| `skills` | `/api/v1/skills/*` | 自定义 Skill 上传、查询、更新和重载 | SkillRegistry、CustomSkillManager |
| `health` | `/api/v1/health/*` | API、数据库、Redis、Celery、WebSocket、系统资源和模型健康 | HealthChecker、ProviderHealth |

## v2 API 职责

| 挂载模块 | 最终前缀或代表端点 | 核心职责 | 主要权限 |
|----------|--------------------|----------|----------|
| `nginx_api` | `/api/v2/nginx/*` | Nginx 配置检查、生成、部署、备份和读取 | 管理权限 |
| `Controller` | `/api/v2/Controller/sys-status`、`/logs` | 系统状态和日志 WebSocket | 管理权限 |
| `user_manage` | `/api/v2/Controller/users` 等 | 用户 CRUD 和密码重置 | 管理权限 |
| `admin_config` | `/api/v2/admin/*` | 用户并发限制、系统配置和沙箱配置 | superadmin |
| `guardian_router` | `/api/v2/Controller/*` | 服务守护、熔断、资源、备份、日志与限流配置 | 管理权限 |
| `model_admin` | `/api/v2/models/*` | 默认模型、角色分配、降级链、错误类型和上下文长度 | 管理权限 |
| `model_config_api` | `/api/v2/model-config/*` | v5.0 模型、供应商和 Agent 配置管理及重载 | 管理权限 |
| `mcp_admin` | `/api/v2/mcp/*` | MCP Server CRUD、启停和连接测试 | 管理权限 |

## 源码与挂载边界

`app/api/v1/AiProjectCode.py` 和 `app/api/v2/nginx_ai.py` 仍存在路由源码，但 `app/main.py` 当前没有挂载它们，因此不计入公开 API 职责矩阵。公开能力以 `include_router` 的实际挂载结果为准。

## 关键执行链

| 场景 | 入口 | 编排与状态链 |
|------|------|--------------|
| Agent 生成 | `/api/v1/agent/orchestrate/stream` | ai_agent → workflow registry → legacy wrapper / StateGraph → checkpoint / event |
| GirlAI 对话 | `/api/v1/GirlAi/*` | GirlAi → GirlAIStateAdapter → legacy + unified transaction → reconciliation |
| PPT 生成 | `/api/v1/pptx/outlines/{id}/generate` | outline approval → PPTGenerationOrchestrator → rule QA → reflow → optional vision QA → artifact |
| 任务恢复 | `/api/v1/tasks/{id}/recover` | Task revision / checkpoint → TaskStateService → Celery 重排 → event replay |
| VS Code 操作 | `/api/v1/agent/host/*` | handshake → action queue → host event → approval/policy → control |

## 横切关注点

| 关注点 | 实现位置 | 说明 |
|--------|----------|------|
| 生命周期 | `app/main.py` | 启动恢复、Guardian、调度器和优雅关闭 |
| JWT 认证 | `app/utils/security.py` | Token 创建、验证和角色信息 |
| CSRF 防护 | `app/utils/csrf.py` | Double-submit Cookie |
| 输入校验 | `app/middleware/input_validator.py` | 请求体限制与恶意输入模式检测 |
| 限流 | `app/middleware/rate_limiter.py` | 全局、IP、用户和端点维度 |
| 日志 | `app/middleware/request_logging.py`、`app/core/logging_config.py` | 请求日志和敏感信息脱敏 |
| 错误处理 | `app/utils/error_handler.py` | 全局异常处理注册 |
| 权限 | `app/utils/permissions.py` | RBAC 三级权限检查 |
| 缓存 | `app/utils/cache.py` | Redis 与内存实现 |
| 模型熔断 | `app/agent/dynamic_model_router.py` | 健康度、熔断、降级链和学习路由 |
| 状态一致性 | `app/services/reconciliation_service.py` | legacy 双写差异检测和切换门槛 |
| 任务韧性 | `app/services/worker_recovery_service.py` | lease 过期检测、重排和失败收敛 |
