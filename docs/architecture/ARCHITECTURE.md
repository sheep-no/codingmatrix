# 系统架构

> 最后更新: 2026-05-11 | 路由总数: 170+

## 技术栈

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend (Vue 3)                     │
│  Vite 5 + Element Plus + Tailwind CSS + Pinia + ECharts   │
│  51 个组件 · 7 个视图 · 5 个 Store · 8 个路由             │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP / SSE / WebSocket
┌────────────────────────┴────────────────────────────────┐
│                  Backend (FastAPI / Python 3.11)          │
│                                                          │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Auth    │  │ AI Code  │  │ Kolors   │  │  PPTX    │ │
│  │ Module   │  │  Gen     │  │  Image   │  │  Gen     │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │
│  │  Agent   │  │ Workflow │  │  Vision  │  │ Aicloud  │ │
│  │  Core    │  │  Engine  │  │  Analyze │  │  Cloud   │ │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │
│                                                          │
│  ┌──────────────────────────────────────────────────────┐│
│  │              Middleware Layer (7 层)                   ││
│  │  CORS │ RequestLog │ InputValidator │ RateLimit       ││
│  │  FeatureSwitch │ SecurityHeaders │ GZip │ Drain       ││
│  └──────────────────────────────────────────────────────┘│
└────────────────────────┬────────────────────────────────┘
                         │
┌────────────────────────┴────────────────────────────────┐
│                    Data Layer                             │
│                                                          │
│  SQLite (Async SQLAlchemy + Alembic) │ APScheduler       │
│  Redis (Cache/可选) │ Celery (异步任务)                    │
└─────────────────────────────────────────────────────────┘
```

## 模块架构图

```
app/
├── main.py                     # FastAPI 应用入口 (311 行)
├── celery_app.py               # Celery 异步任务配置
│
├── api/
│   ├── v1/                     # 主要业务 API (16 个模块)
│   │   ├── auth.py             # 认证 (登录/注册/Token/RSA)
│   │   ├── Aicode.py           # AI 代码生成
│   │   ├── AiProjectCode.py    # AI 项目生成
│   │   ├── ai_agent.py         # Agent 核心 (编排/会话/知识/ReAct)
│   │   ├── GirlAi.py           # 虚拟 AI 角色对话
│   │   ├── kolors_api.py       # 图像生成 (文生图/图生图/修复)
│   │   ├── kolors_history.py   # 图像历史 CRUD
│   │   ├── aiGeneratorPptx.py  # PPT 生成 (异步/预览/下载)
│   │   ├── file_upload.py      # 文件上传 (分片/下载)
│   │   ├── task_queue.py       # 任务队列管理
│   │   ├── vision_api.py       # 视觉分析/OCR/代码提取
│   │   ├── workflow.py         # 工作流引擎 (DAG/导入导出)
│   │   ├── aicloud.py          # AI 云服务
│   │   ├── aicloud_knowledge.py # 知识库管理
│   │   ├── health.py           # 健康检查/Prometheus
│   │   └── preview.py          # 文件预览
│   │
│   └── v2/                     # 系统管理 API (6 个模块)
│       ├── Controller.py       # 系统控制器
│       ├── nginx_api.py        # Nginx 配置管理
│       ├── nginx_ai.py         # AI 辅助 Nginx 配置
│       ├── guardian_router.py  # 服务守护/熔断
│       ├── user_manage.py      # 用户 CRUD
│       └── admin_config.py     # 系统配置/并发限制
│
├── agent/                      # AI Agent 引擎 (23 个模块)
│   ├── orchestrator.py         # 总指挥 (复杂度分析/角色协作)
│   ├── multi_model_agent.py    # 多模型协调器
│   ├── react_agent.py          # ReAct 自我反思 Agent
│   ├── executor.py             # 执行器 (工具调用)
│   ├── specialists.py          # 专家角色 (架构师/工程师/审查员)
│   ├── memory.py               # 记忆系统
│   ├── dynamic_model_router.py # 动态模型路由
│   ├── spec_first_generator.py # 规范优先生成
│   ├── refinement_loop.py      # 迭代修复循环
│   ├── cross_validator.py      # 交叉验证器
│   ├── dependency_graph.py     # 文件依赖图
│   ├── code_validator.py       # 代码验证器
│   ├── code_patcher.py         # 代码补丁
│   ├── error_recovery.py       # 错误恢复
│   ├── complexity.py           # 复杂度分析
│   ├── session_manager.py      # 会话管理
│   ├── spec_cache.py           # 规范缓存
│   ├── feedback_learner.py     # 反馈学习
│   ├── test_runner.py          # 测试运行器
│   ├── shared_context.py       # 共享上下文
│   └── api_contract_checker.py # API 契约检查
│
├── core/                       # 核心配置
│   ├── config.py               # 全局配置 (pydantic-settings)
│   ├── logging_config.py       # 日志配置
│   └── graceful_shutdown.py    # 优雅关闭管理
│
├── db/                         # 数据库层
│   ├── base.py                 # SQLAlchemy 基类
│   ├── database.py             # 异步引擎/会话管理
│   └── scheduler.py            # APScheduler 配置
│
├── middleware/                  # 中间件层
│   ├── rate_limiter.py         # 速率限制中间件
│   ├── security_headers.py     # 安全响应头中间件
│   ├── feature_switch.py       # 功能开关中间件
│   └── input_validator.py      # 输入验证中间件
│
├── models/                     # SQLAlchemy 模型 (12 个)
│   ├── user.py                 # 用户信息/权限
│   ├── history.py              # 聊天/代码生成历史
│   ├── file.py                 # 上传文件元数据
│   ├── task.py                 # 异步任务状态
│   ├── saved_project.py        # 已保存项目
│   ├── agent_memory.py         # Agent 会话记忆
│   ├── aicloud.py              # AI 云会话/审核
│   ├── aicloud_knowledge.py    # 知识库文档
│   ├── server_config.py        # 服务器配置
│   ├── chat_history.py         # 对话历史
│   ├── Permission.py           # 权限定义
│   └── base.py                 # 模型基类
│
├── schema/                     # Pydantic Schema
├── scripts/                    # 运维脚本
├── services/                   # 业务服务层
├── tasks/                      # Celery 任务
│
└── utils/                      # 工具层 (45+ 模块)
    ├── security.py             # JWT/密码哈希/权限检查
    ├── encryption.py           # RSA-OAEP + AES-CBC
    ├── csrf.py                 # CSRF Token
    ├── rate_limiter.py         # IP/用户限流
    ├── circuit_breaker.py      # 服务熔断
    ├── cache.py                # Redis/内存缓存
    ├── cache_decorator.py      # 缓存装饰器
    ├── logging.py              # 请求日志
    ├── structured_logging.py   # 结构化日志
    ├── error_handler.py        # 全局异常处理
    ├── error_codes.py          # 错误码定义
    ├── system_config.py        # 系统配置/并发限制
    ├── system_monitor.py       # 系统监控
    ├── performance_monitor.py  # 性能监控
    ├── web_search.py           # Bing/DuckDuckGo 搜索
    ├── vision.py               # 图像分析/OCR
    ├── docker_runner.py        # Docker 容器运行
    ├── file_operator.py        # 安全文件操作
    ├── project_validator.py    # 项目验证
    ├── pptxGenerateUtil.py     # PPT 生成工具
    ├── AiCodeUtil.py           # AI 代码工具
    ├── agent_core.py           # Agent 核心工具
    ├── agent_skills.py         # Agent 技能
    ├── json_parser.py          # JSON 解析
    ├── retry.py                # 重试机制
    ├── hot_reload.py           # 热重载
    ├── sentry.py               # Sentry 集成
    ├── startup_alert.py        # 启动告警
    ├── log_archiver.py         # 日志归档
    └── workflow/               # 工作流引擎
```

## 数据流

### AI 代码生成流

```
用户输入 → CodeGenerator → POST /api/v1/code (SSE)
    → Aicode.py → SiliconFlow API (LLM)
    → SSE 流式返回 → 前端实时渲染 Markdown
    → 代码高亮 + 复制
```

### 项目生成流 (Orchestrator Agent)

```
用户提示词 → ProjectGenerator → POST /api/v1/agent/generate
    → ai_agent.py → OrchestratorAgent
    ├── 复杂度分析 → 模型分配 → 架构设计
    ├── 规范生成 (OpenAPI/类型/DB Schema)
    ├── 依赖图构建 → 分层并发生成
    ├── 交叉验证 (关键文件) → 迭代修复
    └── 最终验证 → SSE 进度推送
    → 前端展示文件树 + 代码预览
    → 保存 → SQLite (saved_projects)
```

### 异步任务流 (PPT/图片)

```
用户请求 → POST /api/v1/pptx/generate_task
    → APScheduler 异步任务
    → LLM 生成内容 → python-pptx 生成文件
    → 状态轮询 → 下载/预览
```

### Agent 处理流 (ReAct 模式)

```
用户请求 → POST /api/v1/agent/process
    → MultiModelAgent
    ├── 内容识别 → TaskType (代码/视觉/推理等)
    ├── 模型路由 → 选择最佳模型
    ├── 任务规划 → 分解为步骤
    ├── 计划审查 → AIReviewer
    ├── 步骤执行 → EnhancedExecutor (工具调用)
    ├── 文件契约 → 路径安全验证
    └── 返回结果
```

## 中间件链

```
请求 → CORS → RequestLog → InputValidator → RateLimit
     → FeatureSwitch → SecurityHeaders → GZip → Drain
     → 路由处理 → 响应
```

## 中间件详情

| 中间件 | 文件 | 功能 |
|--------|------|------|
| CORSMiddleware | FastAPI 内置 | 跨域资源共享 |
| RequestLoggingMiddleware | logging.py | 生成 request_id、记录请求耗时 |
| InputValidatorMiddleware | input_validator.py | SQL 注入/XSS 检测、请求体大小限制 |
| RateLimitMiddleware | rate_limiter.py | IP/用户/端点速率限制 |
| FeatureSwitchMiddleware | feature_switch.py | 功能模块开关 |
| SecurityHeadersMiddleware | security_headers.py | X-Frame-Options、CSP 等安全头 |
| GZipMiddleware | FastAPI 内置 | 响应压缩 (≥500 字节) |
| Drain Mode | main.py | 优雅关闭时拒绝新请求 |

## 生命周期管理

```
启动 (lifespan)
├── 创建用户上传目录
├── 初始化速率限制
├── 初始化缓存 (Redis/内存)
├── 数据库连接池预热
├── 启动 AsyncSmartGuardian (服务监控)
├── 运行 Alembic 数据库迁移
└── 启动 APScheduler 定时任务

关闭
├── 停止 Guardian 监控
├── 优雅关闭 (graceful_shutdown)
├── 清理 HTTP 客户端连接
└── 关闭缓存管理器
```

## 系统配置管理层

```
SystemConfigManager (单例)
├── 加载 configs/system_config.json
├── 用户并发限制管理
│   ├── 默认角色层级 (free/basic/premium/enterprise/superadmin)
│   └── 用户覆盖配置 (user_overrides)
├── 会话管理配置
│   ├── 活跃会话清理
│   └── 自动清理开关
└── PPT 生成配置
    ├── 最大幻灯片数量
    └── 支持模板列表
```

## 部署架构

```
Nginx (反向代理)
├── / → Vue 前端 (dist/ 静态文件)
├── /api/v1/ → FastAPI v1 (业务 API)
├── /api/v2/ → FastAPI v2 (管理 API)
└── /static/ → 静态资源

FastAPI (uvicorn workers)
├── SQLite (持久化 + Alembic 迁移)
├── APScheduler (后台任务调度)
├── Celery (异步任务队列)
├── Redis (缓存，可选)
└── AsyncSmartGuardian (服务健康监控)
```
