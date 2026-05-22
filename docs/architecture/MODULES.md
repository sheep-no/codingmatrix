# CodingMatrix 模块说明

> 最后更新: 2026-05-22 | 版本: v5.4.0

## 项目结构概览

```
codingmatrix/
├── app/ # 后端 (FastAPI, Python 3.11)
├── src/ # 前端 (Vue 3, Vite 5)
├── tests/ # 测试 (Pytest + Playwright)
├── docs/ # 文档 (全部 Markdown)
├── configs/ # 配置文件 (.coveragerc, playwright, prometheus 等)
├── scripts/ # 运维脚本 (logs, status 等)
├── cache/ # 缓存目录 (embedding_cache, spec_cache)
├── data/ # 数据目录 (SQLite, dependency_graph, learning_data)
├── keys/ # 密钥目录 (RSA 密钥对, cookies)
├── logs/ # 日志目录
├── migrations/ # Alembic 数据库迁移
├── projects/ # 用户项目上传目录
├── sessions/ # Agent 会话数据
│
├── .claude/ # AI Agent 配置 (Skills/Rules)
├── .monkeycode/ # MonkeyCode 项目文档
├── .github/ # GitHub CI/CD 配置
│
├── main.py # 项目启动入口
├── Makefile # Make 命令集
├── pyproject.toml # Python 项目配置
│
├── configs/ # 配置文件
│ ├── alembic.ini
│ ├── requirements.txt
│ ├── requirements-test.txt
│ ├── pytest.ini
│ ├── .coveragerc
│ ├── nginx.conf
│ ├── prometheus.yml
│ └── playwright.config.js
│
├── scripts/ # 运维脚本
│ ├── start.sh / start.bat
│ ├── stop.sh / stop.bat
│ ├── logs.sh / logs.bat
│ └── status.sh / status.bat
│
├── package.json # Node.js 依赖 (前端)
├── package-lock.json
│
├── docker-compose.yml # Docker Compose (开发)
├── docker-compose.prod.yml # Docker Compose (生产)
├── Dockerfile # Docker 镜像
│
├── .env.example # 环境变量模板
├── .env.production.example # 生产环境变量模板
├── .gitignore # Git 忽略规则
│
├── start.sh / start.bat # 启动脚本
├── stop.sh / stop.bat # 停止脚本
│
├── test_output/ # 测试输出 (git ignored)
├── playwright-report/ # Playwright 报告 (git ignored)
└── test-results/ # Playwright 结果 (git ignored)
```

```
app/
├── main.py # FastAPI 应用入口 (311 行)
├── celery_app.py # Celery 异步任务配置
│
├── api/ # API 层 (22 个模块)
│ ├── v1/ # 业务 API (16 模块)
│ └── v2/ # 管理 API (6 模块)
│
├── agent/ # AI Agent 引擎
│ ├── orchestrator.py # 总指挥 (含 OpenTelemetry 追踪装饰器)
│ ├── tracing.py # OpenTelemetry 分布式追踪 (Jaeger/OTLP)
│ ├── multi_model_agent.py # 多模型协调器
│ ├── multi_model_agent.py # 多模型协调器
│ ├── react_agent.py # ReAct Agent
│ ├── executor.py # 执行器
│ ├── specialists.py # 专家角色 (含追踪装饰器)
│ ├── memory.py # 记忆系统
│ ├── dynamic_model_router.py # 动态路由
│ ├── spec_first_generator.py # 规范优先生成
│ ├── refinement_loop.py # 迭代修复
│ ├── cross_validator.py # 交叉验证
│ ├── dependency_graph.py # 依赖图
│ ├── code_validator.py # 代码验证
│ ├── code_patcher.py # 代码补丁
│ ├── error_recovery.py # 错误恢复
│ ├── error_classifier.py # 错误分类器
│ ├── fix_pattern_cache.py # 修复模式缓存
│ ├── complexity.py # 复杂度分析
│ ├── session_manager.py # 会话管理 (含追踪装饰器)
│ ├── spec_cache.py # 规范缓存
│ ├── feedback_learner.py # 反馈学习
│ ├── test_runner.py # 测试运行器 (含追踪装饰器)
│ ├── shared_context.py # 共享上下文
│ └── api_contract_checker.py # API 契约检查
│
├── core/ # 核心配置
│ ├── config.py # 全局配置
│ ├── logging_config.py # 日志配置
│ └── graceful_shutdown.py # 优雅关闭
│
├── db/ # 数据库层
│ ├── base.py # SQLAlchemy 基类
│ ├── database.py # 异步引擎/会话
│ └── scheduler.py # APScheduler
│
├── middleware/ # 中间件 (4 个)
│ ├── rate_limiter.py # 速率限制
│ ├── security_headers.py # 安全响应头
│ ├── feature_switch.py # 功能开关
│ └── input_validator.py # 输入验证
│
├── models/ # SQLAlchemy 模型 (12 个)
├── schema/ # Pydantic Schema
├── services/ # 业务服务层
├── tasks/ # Celery 任务
└── utils/ # 工具层 (45+ 模块)
```

```
src/
├── App.vue # 根组件
├── main.js # 入口文件
├── router/index.js # 路由配置 (8 路由)
├── stores/ # Pinia 状态管理 (5 Store)
├── views/ # 视图页面 (5 个)
├── components/ # Vue 组件 (51 个)
├── utils/ # 前端工具
│ ├── api/ # API 客户端
│ ├── chatDatabase.js # IndexedDB 聊天存储
│ ├── csrf.js # CSRF Token
│ ├── encryption.js # RSA 加密
│ ├── streamManager.js # SSE 流管理
│ ├── taskNotification.js # 浏览器通知
│ ├── theme.js # 主题管理
│ ├── tokenManager.js # Token 管理
│ ├── websocketManager.js # WebSocket
│ └── websocketPool.js # WebSocket 池
├── composables/ # 组合式函数
├── styles/ # 样式文件
├── assets/ # 静态资源
└── public/ # 公共资源
```

## 后端模块 (app/)

### 核心框架

| 模块 | 路径 | 行数 | 描述 |
|------|------|------|------|
| 主应用 | `app/main.py` | 311 | FastAPI 应用入口，8 层中间件，22 个路由注册 |
| Celery 配置 | `app/celery_app.py` | - | Celery 异步任务配置 |
| 配置 | `app/core/config.py` | - | 全局配置，pydantic-settings 环境变量加载 |
| 日志配置 | `app/core/logging_config.py` | - | 日志系统配置 |
| 优雅关闭 | `app/core/graceful_shutdown.py` | - | GracefulShutdownManager，Drain 模式 |
| 数据库 | `app/db/database.py` | - | SQLAlchemy 异步引擎，会话管理 |
| 调度器 | `app/db/scheduler.py` | - | APScheduler 定时任务配置 |

### API 层 (v1 - 业务 API)

| 模块 | 路径 | 行数 | 端点前缀 | 描述 |
|------|------|------|----------|------|
| Auth | `app/api/v1/auth.py` | ~400 | `/api/v1` | 登录、注册、Token 刷新、RSA 公钥、权限 |
| AI Code | `app/api/v1/Aicode.py` | ~800 | `/api/v1/code` | 代码生成、历史管理、断点续传 (SSE) |
| AI Project | `app/api/v1/AiProjectCode.py` | ~550 | `/api/v1/agent` | 项目生成、文件管理、保存/加载、GitHub 推送 |
| AI Agent | `app/api/v1/ai_agent.py` | ~2000 | `/api/v1/agent` | Agent 处理、会话、知识、编排、ReAct、Git 操作 |
| GitHub | `app/api/v1/github.py` | ~150 | `/api/v1/github` | GitHub 配置、项目保存、Token 验证 |
| GirlAi | `app/api/v1/GirlAi.py` | ~400 | `/api/v1/GirlAi` | 虚拟 AI 角色对话 (5 种角色)、历史管理 |
| Kolors | `app/api/v1/kolors_api.py` | ~550 | `/api/v1/kolors` | 文生图、图生图、修复、头像生成 |
| Kolors History | `app/api/v1/kolors_history.py` | ~120 | `/api/v1/kolors/history` | 图像历史 CRUD |
| PPTX | `app/api/v1/aiGeneratorPptx.py` | ~1200 | `/api/v1/pptx` | PPT 异步生成、预览、下载 |
| File Upload | `app/api/v1/file_upload.py` | ~400 | `/api/v1/files` | 文件上传、分片上传、下载 |
| Task Queue | `app/api/v1/task_queue.py` | ~300 | `/api/v1/tasks` | 任务管理、状态查询、重试 |
| Vision | `app/api/v1/vision_api.py` | ~250 | `/api/v1/vision` | 图像分析、OCR、代码提取、安全检查 |
| Workflow | `app/api/v1/workflow.py` | ~600 | `/api/v1/workflow` | 工作流执行、DAG、导入导出、历史 |
| Aicloud | `app/api/v1/aicloud.py` | ~750 | `/api/v1/aicloud` | AI 云聊天、文件读写、审计 |
| Aicloud Knowledge | `app/api/v1/aicloud_knowledge.py` | ~280 | `/api/v1/aicloud/knowledge` | 知识库上传、搜索 |
| Health | `app/api/v1/health.py` | ~150 | `/api/v1/health` | 健康检查、就绪/存活、Prometheus |
| Preview | `app/api/v1/preview.py` | ~400 | `/api/v1/preview` | 文件预览中心 |

### API 层 (v2 - 管理 API)

| 模块 | 路径 | 行数 | 端点前缀 | 描述 |
|------|------|------|----------|------|
| Controller | `app/api/v2/Controller.py` | ~350 | `/api/v2/Controller` | 系统控制器 |
| Nginx API | `app/api/v2/nginx_api.py` | ~450 | `/api/v2/nginx` | Nginx 配置生成、检查、部署 |
| Nginx AI | `app/api/v2/nginx_ai.py` | ~100 | `/api/v2/nginx` | AI 辅助 Nginx 配置分析 |
| Guardian | `app/api/v2/guardian_router.py` | ~700 | `/api/v2/Controller` | 服务熔断、守护进程、健康监控 |
| User Manage | `app/api/v2/user_manage.py` | ~300 | `/api/v2/Controller` | 用户 CRUD、密码重置 |
| Admin Config | `app/api/v2/admin_config.py` | ~70 | `/api/v2/admin` | 系统配置管理、用户并发限制 |

### AI Agent 引擎 (app/agent/)

| 模块 | 路径 | 行数 | 描述 |
|------|------|------|------|
| Orchestrator | `orchestrator.py` | ~1900 | 总指挥：复杂度分析、模型分配、角色协作、验证审查 |
| MultiModelAgent | `multi_model_agent.py` | ~850 | 多模型协调：任务路由、规划、执行、审查 |
| ReActAgent | `react_agent.py` | ~500 | ReAct 自我反思：Thought→Action→Observation→Reflection |
| Executor | `executor.py` | ~750 | 执行器：6 种工具类型 (文件/代码/搜索/HTTP/Git)、SSE 状态推送、智能修复集成 |
| Specialists | `specialists.py` | ~800 | 专家角色：架构师、前端/后端工程师、代码审查员 |
| Memory | `memory.py` | - | 记忆系统：对话/知识/反思三种记忆 |
| DynamicRouter | `dynamic_model_router.py` | - | 动态模型路由：健康监控、熔断、重试 |
| SpecFirstGen | `spec_first_generator.py` | - | 规范优先生成：OpenAPI/类型/DB/配置 |
| RefinementLoop | `refinement_loop.py` | - | 迭代修复循环：验证→修复 (最多 3 次) |
| CrossValidator | `cross_validator.py` | - | 交叉验证器：关键文件双模型生成+裁决 |
| DependencyGraph | `dependency_graph.py` | - | 文件依赖图：分层并发生成 |
| CodeValidator | `code_validator.py` | - | 代码验证器：语法/导入检查 |
| ErrorClassifier | `error_classifier.py` | ~200 | 错误分类器：8 种错误类型识别与策略推荐 |
| FixPatternCache | `fix_pattern_cache.py` | ~150 | 修复模式缓存：成功修复知识沉淀与复用 |
| CodePatcher | `code_patcher.py` | - | 代码补丁：增量变更应用 |
| ErrorRecovery | `error_recovery.py` | - | 错误恢复：自动修复循环 |
| Complexity | `complexity.py` | - | 复杂度分析：Simple/Small/Medium/Large/Enterprise |
| SessionManager | `session_manager.py` | - | 会话管理：增量生成支持 |
| SpecCache | `spec_cache.py` | - | 规范缓存：相似需求缓存 |
| FeedbackLearner | `feedback_learner.py` | - | 反馈学习：预防性提示生成 |
| TestRunner | `test_runner.py` | - | 测试运行器：自动化测试执行 |
| SharedContext | `shared_context.py` | - | 共享上下文：跨组件状态 |
| APIContract | `api_contract_checker.py` | - | API 契约检查：前后端一致性 |

### 中间件层 (app/middleware/)

| 中间件 | 路径 | 描述 |
|--------|------|------|
| RateLimit | `rate_limiter.py` | IP/用户/端点速率限制 |
| SecurityHeaders | `security_headers.py` | X-Frame-Options、CSP、HSTS 等安全头 |
| FeatureSwitch | `feature_switch.py` | 功能模块开关控制 |
| InputValidator | `input_validator.py` | SQL 注入/XSS 检测、请求体大小限制 |

### 工具层 (app/utils/)

| 工具 | 文件 | 行数 | 描述 |
|------|------|------|------|
| 安全 | `security.py` | ~180 | JWT 创建/验证、密码哈希、权限检查、superadmin 装饰器 |
| 加密 | `encryption.py` | ~220 | RSA-OAEP + AES-CBC 加密解密 |
| CSRF | `csrf.py` | ~120 | CSRF Token 生成验证、Double-submit Cookie |
| 限流 | `rate_limiter.py` | ~60 | IP/用户/端点限流 |
| 熔断器 | `circuit_breaker.py` | ~200 | 服务熔断保护 |
| 缓存 | `cache.py` | ~300 | Redis/内存缓存管理 |
| 缓存装饰器 | `cache_decorator.py` | ~170 | 方法级缓存装饰器 |
| 日志 | `logging.py` | ~160 | 请求日志中间件 (request_id/耗时) |
| 结构化日志 | `structured_logging.py` | ~120 | JSON 格式结构化日志 |
| 错误处理 | `error_handler.py` | ~160 | 全局异常处理 |
| 错误码 | `error_codes.py` | ~120 | 错误码定义 (AUTH/VAL/RES/BIZ/SYS) |
| 系统配置 | `system_config.py` | ~180 | 用户并发限制、系统配置管理 |
| 系统监控 | `system_monitor.py` | ~40 | 系统资源监控 |
| 性能监控 | `performance_monitor.py` | ~150 | 请求性能监控中间件 |
| 搜索 | `web_search.py` | ~500 | Bing/DuckDuckGo 搜索 |
| 视觉 | `vision.py` | ~220 | 图像分析、OCR |
| Docker | `docker_runner.py` | ~700 | Docker 容器运行管理 |
| 文件操作 | `file_operator.py` | ~550 | 安全文件读写 (路径验证) |
| 项目验证 | `project_validator.py` | ~400 | 项目生成验证 |
| PPT 工具 | `pptxGenerateUtil.py` | ~1400 | PPT 生成工具 (python-pptx) |
| AI 代码工具 | `AiCodeUtil.py` | ~200 | SiliconFlow API 调用 (兼容层) |
| **LLM 调用器** | **`llm_caller.py`** | **~80** | **统一模型调用入口 (v5.4.0)** |
| **多供应商** | **`aicloud/`** | **~2000** | **多供应商模型系统 (v5.4.0)** |
| Agent 核心 | `agent/` | ~2800 | Agent 核心工具函数 |
| Agent 技能 | `agent_skills.py` | ~500 | Agent 技能定义、Git 操作技能 |
| Git 工具 | `git_tools.py` | ~200 | Git 命令封装、路径安全检查 |
| JSON 解析 | `json_parser.py` | ~160 | 健壮 JSON 解析 |
| 重试 | `retry.py` | ~120 | 异步重试机制 |
| 热重载 | `hot_reload.py` | ~160 | 开发时热重载 |
| Sentry | `sentry.py` | ~180 | Sentry 错误追踪集成 |
| 启动告警 | `startup_alert.py` | ~180 | 服务启动告警通知 |
| 日志归档 | `log_archiver.py` | ~250 | 日志归档清理 |
| 分页 | `pagination.py` | ~120 | 标准分页/游标分页 |
| HTTP 客户端 | `http_client.py` | ~70 | 异步 HTTP 客户端 |
| 提示词加载 | `prompt_loader.py` | ~120 | 提示词模板加载 |
| 安全审计 | `security_audit.py` | ~80 | 安全审计日志 |
| 服务配置 | `service_config_manager.py` | ~180 | 服务配置管理 |
| 异步守卫 | `async_enhanced_guard.py` | ~140 | AsyncSmartGuardian |
| 守卫合约 | `guard_contracts.py` | ~280 | 守卫合约定义 |
| 进程守卫 | `process_guard.py` | ~350 | 进程级守卫 |
| 图像生成 | `image_generation.py` | ~320 | Kolors 图像生成工具 |
| 任务分发 | `task_dispatcher.py` | ~50 | 任务分发器 |
| 任务管理 | `task_manager.py` | ~300 | 任务生命周期管理 |
| API 响应 | `api_response.py` | ~120 | 统一 API 响应格式 |
| 数学工具 | `math_utils.py` | ~20 | 数学计算工具 |
| 审查 | `review/` | - | 代码审查工具 |
| 验证器 | `validators/` | - | 数据验证器 |
| 工作流 | `workflow/` | - | 工作流引擎 |
| Aicloud | `aicloud/` | - | AI 云工具 |
| 视觉 | `visual/` | - | 视觉处理工具 |

### 多供应商模型系统 (app/utils/aicloud/) v5.4.0

| 模块 | 文件 | 行数 | 描述 |
|------|------|------|------|
| **入口** | `__init__.py` | ~15 | 全局导出 `call_llm` |
| 统一调用 | `llm_caller.py` | ~80 | `call_llm()` 统一接口，自动路由 |
| 枚举定义 | `providers.py` | ~80 | `ModelProvider` 枚举、配置类 |
| 路由器 | `provider_router.py` | ~120 | 模型路由、故障转移策略 |
| 调用层 | `llm_caller.py` | ~150 | 统一调用入口、故障转移 |

#### 供应商适配器 (app/utils/aicloud/adapters/)

| 适配器 | 文件 | 行数 | 供应商 | 说明 |
|--------|------|------|--------|------|
| Base | `base.py` | ~120 | - | 抽象基类，统一接口 |
| SiliconFlow | `siliconflow.py` | ~180 | SiliconFlow | 默认供应商，10个内置模型 |
| DashScope | `dashscope.py` | ~150 | 阿里百炼 | qwen-plus 等 Qwen 系列 |
| Zhipu | `zhipu.py` | ~150 | 智谱 GLM | glm-4 等 GLM 系列 |
| DeepSeek | `deepseek.py` | ~150 | DeepSeek | deepseek-chat 官方 |
| OpenAI | `openai.py` | ~150 | OpenAI | gpt-4o 等 |
| Anthropic | `anthropic.py` | ~160 | Anthropic | Claude 系列 |

#### 单元测试 (app/utils/aicloud/)

| 测试文件 | 描述 | 数量 |
|----------|------|------|
| `test_providers.py` | 配置和路由测试 | 16 个 |
| `test_adapters.py` | 适配器测试 | 13 个 |
| **合计** | | **29 个** |

### 数据模型 (app/models/)

| 模型 | 文件 | 行数 | 描述 |
|------|------|------|------|
| User | `user.py` | ~50 | 用户信息、权限级别、密码 (RSA-OAEP) |
| History | `history.py` | ~30 | 聊天/代码生成历史 |
| File | `file.py` | ~90 | 上传文件元数据、分片信息 |
| Task | `task.py` | ~100 | 异步任务状态、重试信息 |
| SavedProject | `saved_project.py` | ~25 | 已保存的 AI 项目 |
| AgentMemory | `agent_memory.py` | ~150 | Agent 会话记忆、向量嵌入 |
| Aicloud | `aicloud.py` | ~80 | AI 云会话、审核状态 |
| AicloudKnowledge | `aicloud_knowledge.py` | ~80 | 知识库文档、向量索引 |
| ServerConfig | `server_config.py` | ~80 | 服务器配置、健康状态 |
| ChatHistory | `chat_history.py` | ~40 | 对话历史、GirlAi 聊天记录 |
| Permission | `Permission.py` | ~25 | 权限定义 (free/basic/premium/enterprise/superadmin) |
| Base | `base.py` | ~5 | SQLAlchemy 模型基类 |

## 前端模块 (src/)

### Vue 组件 (51 个)

| 组件 | 路径 | 描述 |
|------|------|------|
| 主页 | `src/components/index.vue` | 首页入口 |
| App 根组件 | `src/App.vue` | 路由容器 |
| MainLayout | `src/components/centerContent.vue` | 主内容区 |
| 侧边栏 | `src/components/leftlist.vue` | 导航侧边栏 |
| 底部输入 | `src/components/bottominput.vue` | 底部输入区 |
| LoginDialog | `src/components/LoginDialog.vue` | RSA 加密登录弹窗 |
| AdminPanel | `src/components/AdminPanel.vue` | 管理面板 (系统监控/用户管理) |
| AiAgent | `src/components/AiAgent.vue` | Agent 核心交互界面 |
| Aicloud | `src/components/Aicloud.vue` | AI 云服务界面 |
| ImageGenerator | `src/components/ImageGenerator.vue` | Kolors 图像生成 |
| PPTGenerator | `src/components/PPTGenerator.vue` | PPT 生成 |
| ProjectGenerator | `src/components/ProjectGenerator.vue` | AI 项目生成 |
| TaskQueue | `src/components/TaskQueue.vue` | 任务队列管理 |
| WorkflowDAG | `src/components/WorkflowDAG.vue` | 工作流 DAG 可视化 |
| WorkflowEditor | `src/components/WorkflowDAG.vue` | 工作流编辑器 |
| EphemeralWorkflow | `src/components/EphemeralWorkflow.vue` | 临时工作流 |
| WorkflowLogViewer | `src/components/WorkflowLogViewer.vue` | 工作流日志查看 |
| WorkflowDiffViewer | `src/components/WorkflowDiffViewer.vue` | 工作流差异对比 |
| WorkflowFilePreview | `src/components/WorkflowFilePreview.vue` | 工作流文件预览 |
| AgentCodeViewer | `src/components/AgentCodeViewer.vue` | Agent 代码查看器 |
| AgentFileTree | `src/components/AgentFileTree.vue` | Agent 文件树 |
| AgentKnowledgePanel | `src/components/AgentKnowledgePanel.vue` | Agent 知识面板 |
| GithubConfigPanel | `src/components/GithubConfigPanel.vue` | GitHub 配置面板 |
| AgentProjectActions | `src/components/AgentProjectActions.vue` | Agent 项目操作 (含 GitHub 保存) |
| AgentProjectPreview | `src/components/AgentProjectPreview.vue` | Agent 项目预览 |
| AgentReActSteps | `src/components/AgentReActSteps.vue` | Agent ReAct 步骤展示 |
| AgentSessionSidebar | `src/components/AgentSessionSidebar.vue` | Agent 会话侧边栏 |
| AgentStatsPanel | `src/components/AgentStatsPanel.vue` | Agent 统计面板 |
| AgentWorkflowPanel | `src/components/AgentWorkflowPanel.vue` | Agent 工作流面板 |
| ChartEditor | `src/components/ChartEditor.vue` | 图表编辑器 |
| DiffViewer | `src/components/DiffViewer.vue` | 代码差异查看器 |
| Dockerfile | `src/components/Dockerfile.vue` | Dockerfile 生成 |
| EmptyState | `src/components/EmptyState.vue` | 空状态组件 |
| ErrorBoundary | `src/components/ErrorBoundary.vue` | 错误边界 |
| FileDropZone | `src/components/FileDropZone.vue` | 文件拖放区 |
| FileManager | `src/components/FileManager.vue` | 文件管理器 |
| FilePreview | `src/components/FilePreview.vue` | 文件预览 |
| FilePreviewCenter | `src/components/FilePreviewCenter.vue` | 文件预览中心 |
| HistoryItem | `src/components/HistoryItem.vue` | 历史条目 |
| KeyboardShortcutsHelp | `src/components/KeyboardShortcutsHelp.vue` | 快捷键帮助 |
| MessageEditor | `src/components/MessageEditor.vue` | 消息编辑器 |
| NginxConfig | `src/components/NginxConfig.vue` | Nginx 配置界面 |
| ResourceControl | `src/components/ResourceControl.vue` | 资源控制面板 |
| ServiceManager | `src/components/ServiceManager.vue` | 服务管理器 |
| ShareDialog | `src/components/ShareDialog.vue` | 分享弹窗 |
| SkeletonLoader | `src/components/SkeletonLoader.vue` | 骨架屏加载 |
| SystemInfo | `src/components/SystemInfo.vue` | 系统信息 |
| SystemLogs | `src/components/SystemLogs.vue` | 系统日志 |
| SystemMonitor | `src/components/SystemMonitor.vue` | 系统监控面板 |
| ToastContainer | `src/components/ToastContainer.vue` | Toast 通知容器 |
| UserManagement | `src/components/UserManagement.vue` | 用户管理 |
| VirtualGirl | `src/components/VirtualGirl.vue` | 虚拟 AI 角色 |
| VirtualHistoryList | `src/components/VirtualHistoryList.vue` | 虚拟 AI 历史 |
| AppLoading | `src/components/AppLoading.vue` | 应用加载动画 |

### 视图页面 (5 个)

| 视图 | 路径 | 描述 |
|------|------|------|
| 项目生成 | `src/views/ProjectGenerate.vue` | AI 项目生成页面 |
| 工作流 | `src/views/Workflow.vue` | 工作流管理页面 |
| PPT 生成 | `src/views/PPTGenerate.vue` | PPT 生成页面 |
| PPT 预览 | `src/views/PPTPreview.vue` | PPT 预览页面 (URL 参数传 slides) |
| 图像生成 | `src/views/ImageGenerate.vue` | 图像生成页面 |

### 状态管理 (Pinia - 6 个 Store)

| Store | 文件 | 描述 |
|-------|------|------|
| User | `src/stores/user.js` | 用户状态、权限、Token |
| Task | `src/stores/task.js` | 任务状态管理 |
| Logs | `src/stores/logs.js` | 日志状态管理 |
| Navigation | `src/stores/navigation.js` | 导航状态管理 |
| Counter | `src/stores/counter.js` | 计数器 (示例 Store) |
| Github | `src/stores/github.js` | GitHub 配置、Token 管理、保存状态 |

### 路由配置 (8 个路由)

| 路径 | 组件 | 描述 | 权限 |
|------|------|------|------|
| `/` | `index.vue` | 首页 | 公开 |
| `/project-generate` | `ProjectGenerate.vue` | 项目生成 | 登录 |
| `/workflow` | `Workflow.vue` | 工作流管理 | 登录 |
| `/ppt-generate` | `PPTGenerate.vue` | PPT 生成 | 登录 |
| `/ppt-preview/:id` | `PPTPreview.vue` | PPT 预览 | 登录 |
| `/image-generate` | `ImageGenerate.vue` | 图像生成 | 登录 |
| `/admin` | `AdminPanel.vue` | 管理面板 | superadmin |
| `/:pathMatch(.*)*` | 重定向 `/` | 404 兜底 | 公开 |

### 前端工具

| 工具 | 文件 | 描述 |
|------|------|------|
| API 客户端 | `src/utils/api/` | HTTP API 封装 (ppt.js 等) |
| GitHub API | `src/utils/api/github.js` | GitHub API 客户端 |
| 聊天数据库 | `chatDatabase.js` | IndexedDB 聊天存储 |
| CSRF | `csrf.js` | CSRF Token 管理 |
| 加密 | `encryption.js` | 前端 RSA 加密 |
| 流管理器 | `streamManager.js` | SSE 流管理 |
| 任务通知 | `taskNotification.js` | 浏览器通知 |
| 主题 | `theme.js` | 主题管理 |
| Token 管理 | `tokenManager.js` | JWT Token 管理 |
| WebSocket | `websocketManager.js` | WebSocket 连接管理 |
| WebSocket Pool | `websocketPool.js` | WebSocket 连接池 |

## 关键统计

| 类别 | 数量 | 说明 |
|------|------|------|
| 后端 API 模块 | 22 | v1 (16) + v2 (6) |
| Agent 模块 | 56 | AI 引擎核心 (v5.4.0) |
| 工具模块 | 50+ | utils/ 目录 |
| **多供应商适配器** | **7** | **v5.4.0 新增** |
| 数据模型 | 12 | SQLAlchemy models |
| 中间件 | 8 | 请求处理链 |
| 前端组件 | 51 | Vue SFC 组件 |
| 前端视图 | 5 | 页面级组件 |
| Pinia Store | 5 | 状态管理 |
| 路由 | 8 | Vue Router |
| 测试文件 | 35+ | 单元 + 集成 + E2E |
| 文档文件 | 50+ | Markdown 文档 |