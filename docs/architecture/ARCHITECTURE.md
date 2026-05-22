# 系统架构

> 最后更新: 2026-05-22 | 路由总数：180+ | 版本：v5.4.0

---

## 架构概览 (v5.4.0)

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend (Vue 3)                                            │
│ Vite 5 + Element Plus + Tailwind CSS + Pinia + ECharts     │
│ 52 个组件 · 7 个视图 · 6 个 Store · 8 个路由                  │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE / WebSocket
┌──────────────────────────┴──────────────────────────────────┐
│ Backend (FastAPI / Python 3.11)                             │
│                                                             │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│ │ Auth     │ │ AI Code  │ │ Kolors   │ │ PPTX     │        │
│ │ Module   │ │ Gen      │ │ Image    │ │ Gen      │        │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐        │
│ │ Agent    │ │ Workflow │ │ Vision   │ │ Aicloud  │        │
│ │ Core     │ │ Engine   │ │ Analyze  │ │ Cloud    │        │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘        │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐  │
│ │ Multi-Provider Model Layer (v5.4.0)                 │  │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│ │ │SiliconFlw│ │ DashScope│ │ Zhipu    │ │DeepSeek  │  │  │
│ │ └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐               │  │
│ │ │ OpenAI   │ │Anthropic │ │ Ollama   │               │  │
│ │ └──────────┘ └──────────┘ └──────────┘               │  │
│ └─────────────────────────────────────────────────────┘  │
│                                                             │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ Middleware Layer (7 层)                              │ │
│ │ CORS │ RequestLog │ InputValidator │ RateLimit       │ │
│ │ FeatureSwitch │ SecurityHeaders │ GZip │ Drain      │ │
│ └──────────────────────────────────────────────────────┘ │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Data Layer                                                  │
│                                                             │
│ SQLite (Async SQLAlchemy + Alembic) │ APScheduler          │
│ Redis (Cache/可选)                  │ Celery (异步任务)     │
└─────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Vite 5 + Element Plus | 响应式 UI |
| 后端 | FastAPI + Python 3.11 | 异步 API |
| 数据库 | SQLite + SQLAlchemy 2.0 | 异步 ORM |
| 缓存 | Redis (可选) / 内存 | 分布式缓存 |
| 任务队列 | Celery + APScheduler | 异步任务 |
| 模型层 | 多供应商适配器 | 7 供应商支持 |
| 监控 | OpenTelemetry + Jaeger | 分布式追踪 |
| 容器 | Docker + Docker Compose | 服务编排 |

---

## 多供应商模型架构 (v5.4.0)

```
┌─────────────────────────────────────────────────────────────┐
│ Unified LLM Interface                                       │
│  call_llm(model, prompt, system_prompt, stream, ...)        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Provider Router                                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ Model Name   │ │ Fallback     │ │ Health Check │      │
│  │ Mapping      │ │ Strategy     │ │              │      │
│  └──────────────┘ └──────────────┘ └──────────────┘      │
└──────────────────────────┬──────────────────────────────────┘
           │               │               │
    ┌──────┴──────┐ ┌──────┴──────┐ ┌──────┴──────┐
    │ SiliconFlow │ │ DashScope   │ │ Zhipu       │
    │ (Default)   │ │ (Aliyun)    │ │ (GLM)       │
    └─────────────┘ └─────────────┘ └─────────────┘
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │ DeepSeek    │ │ OpenAI      │ │ Anthropic   │
    │ (Official)  │ │ (GPT)       │ │ (Claude)    │
    └─────────────┘ └─────────────┘ └─────────────┘
    ┌─────────────┐
    │ Ollama      │
    │ (Local)     │
    └─────────────┘
```

### 供应商支持

| 供应商 | 枚举值 | Base URL | 需要 API Key |
|--------|--------|----------|--------------|
| SiliconFlow | siliconflow | https://api.siliconflow.cn/v1 | ✅ |
| 阿里百炼 | dashscope | https://dashscope.aliyuncs.com/v1 | ✅ |
| 智谱 GLM | zhipu | https://open.bigmodel.cn/api/paas/v4 | ✅ |
| DeepSeek | deepseek | https://api.deepseek.com/v1 | ✅ |
| OpenAI | openai | https://api.openai.com/v1 | ✅ |
| Anthropic | anthropic | https://api.anthropic.com/v1 | ✅ |
| Ollama | ollama | http://localhost:11434 | ❌ |

---

## Agent 架构

```
┌─────────────────────────────────────────────────────────────┐
│ Orchestrator                                                │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│ │ 复杂度分析   │ │ 模型分配     │ │ 依赖图构建   │         │
│ └──────────────┘ └──────────────┘ └──────────────┘         │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Multi-Provider LLM Layer (v5.4.0)                           │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│ │ Provider     │ │ Auto Route   │ │ Fallback     │         │
│ │ Registry     │ │              │ │ Strategy     │         │
│ └──────────────┘ └──────────────┘ └──────────────┘         │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Specialist Agents                                           │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│ │ 架构师       │ │ 前端工程师   │ │ 后端工程师   │         │
│ └──────────────┘ └──────────────┘ └──────────────┘         │
│ ┌──────────────┐ ┌──────────────┐                            │
│ │ 代码审查员   │ │ 代码修复器   │                            │
│ └──────────────┘ └──────────────┘                            │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Quality Assurance                                             │
│ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│ │ 错误分类器   │ │ 契约检查器   │ │ 修复模式缓存 │         │
│ └──────────────┘ └──────────────┘ └──────────────┘         │
└─────────────────────────────────────────────────────────────┘
```

---

## 模块结构

```
app/
├── main.py                 # FastAPI 应用入口
├── celery_app.py          # Celery 异步任务配置
│
├── api/                   # API 路由层
│ ├── v1/                  # 业务 API (17 个模块)
│ │ ├── auth.py            # 认证 (RSA 加密登录)
│ │ ├── Aicode.py          # AI 代码生成
│ │ ├── AiProjectCode.py   # AI 项目生成
│ │ ├── ai_agent/          # Agent 核心 (v5.2 重构)
│ │ ├── github.py          # GitHub 集成
│ │ ├── GirlAi.py          # 虚拟 AI 角色对话
│ │ ├── kolors_api.py      # 图像生成
│ │ ├── aiGeneratorPptx.py # PPT 生成
│ │ ├── file_upload.py     # 文件上传
│ │ ├── task_queue.py      # 任务队列
│ │ ├── vision_api.py      # 视觉分析
│ │ ├── workflow.py        # 工作流引擎
│ │ ├── aicloud.py         # AI 云服务
│ │ ├── aicloud_knowledge.py # 知识库
│ │ ├── health.py          # 健康检查
│ │ └── preview.py         # 文件预览
│ │
│ └── v2/                  # 系统管理 API (6 个模块)
│     ├── Controller.py    # 系统控制器
│     ├── nginx_api.py     # Nginx 配置
│     ├── guardian_router.py # 服务守护
│     ├── user_manage.py   # 用户管理
│     └── admin_config.py  # 系统配置
│
├── agent/                 # AI Agent 引擎 (56 个模块)
│ ├── orchestrator.py      # 总指挥
│ ├── multi_model_agent.py # 多模型协调器
│ ├── react_agent.py       # ReAct 自我反思
│ ├── executor.py          # 执行器
│ ├── specialists.py       # 专家角色
│ ├── dynamic_model_router.py # 动态模型路由
│ ├── git_operations.py    # Git 操作
│ └── ... (其他 49 个模块)
│
├── core/                  # 核心配置
│ ├── config.py           # 全局配置 (含多供应商 API Keys)
│ ├── logging_config.py   # 日志配置
│ └── graceful_shutdown.py # 优雅关闭
│
├── db/                    # 数据库层
│ ├── base.py             # SQLAlchemy 基类
│ ├── database.py         # 异步引擎
│ └── models/             # 数据模型 (12 个)
│
├── middleware/            # 中间件层
│ ├── rate_limiter.py     # 速率限制
│ ├── security_headers.py # 安全头
│ └── ...
│
└── utils/                 # 工具层 (50+ 模块)
    ├── __init__.py        # 全局入口 (call_llm)
    ├── aicloud/           # 多供应商模型系统 (v5.4.0)
    │   ├── providers.py
    │   ├── provider_router.py
    │   ├── llm_caller.py
    │   └── adapters/
    ├── AiCodeUtil.py      # AI 代码工具 (兼容层)
    ├── agent_core.py      # Agent 核心工具
    └── ... (其他工具)
```

---

## 数据流

### 多供应商模型调用流

```
用户请求 → Agent/API → call_llm(model, prompt)
    ↓
ProviderRouter.route(model)
    ↓
    ┌──────────────────────────────────────────┐
    │ 模型名称匹配 → 选择供应商                │
    │                                          │
    │ Qwen/Qwen3.5-4B → SiliconFlow          │
    │ qwen-plus → DashScope                   │
    │ glm-4 → Zhipu                          │
    │ deepseek-chat → DeepSeek               │
    │ 未知模型 → SiliconFlow (默认)          │
    └──────────────────────────────────────────┘
    ↓
ProviderAdapter.call_llm()
    ↓
HTTP Request → 供应商 API
    ↓
Response → 统一格式返回
```

### 项目生成流 (Orchestrator Agent)

```
用户提示词 → POST /api/v1/orchestrate/generate
    ↓
OrchestratorAgent
    ├── 复杂度分析 → ProviderRouter 路由 → LLM
    ├── 规范生成 (OpenAPI/类型/DB Schema)
    ├── 依赖图构建 → 分层并发生成
    ├── 交叉验证 → call_llm 多次验证
    ├── Git 操作 (可选)
    └── SSE 进度推送
    ↓
前端展示文件树 → 保存到 SQLite/GitHub
```

---

## 中间件链

```
请求 → CORS → RequestLog → InputValidator → RateLimit
     → FeatureSwitch → SecurityHeaders → GZip → Drain
     → 路由处理 → 响应
```

| 中间件 | 功能 |
|--------|------|
| CORS | 跨域资源共享 |
| RequestLog | 生成 request_id、记录请求耗时 |
| InputValidator | SQL 注入/XSS 检测、请求体限制 |
| RateLimit | IP/用户/端点速率限制 |
| FeatureSwitch | 功能模块开关 |
| SecurityHeaders | X-Frame-Options、CSP 等 |
| GZip | 响应压缩 (≥500 字节) |
| Drain | 优雅关闭时拒绝新请求 |

---

## 生命周期管理

```
启动 (lifespan)
├── 创建用户上传目录
├── 初始化速率限制
├── 初始化缓存 (Redis/内存)
├── 数据库连接池预热
├── 初始化 ProviderRegistry (v5.4.0)
├── 启动 AsyncSmartGuardian (服务监控)
├── 运行 Alembic 数据库迁移
└── 启动 APScheduler 定时任务

关闭
├── 停止 Guardian 监控
├── 优雅关闭 (graceful_shutdown)
├── 清理 HTTP 客户端连接
└── 关闭缓存管理器
```

---

## 部署架构

```
Nginx (反向代理)
├── / → Vue 前端 (dist/ 静态文件)
├── /api/v1/ → FastAPI v1 (业务 API)
├── /api/v2/ → FastAPI v2 (管理 API)
└── /static/ → 静态资源

FastAPI (uvicorn workers)
├── SQLite (持久化 + Alembic)
├── APScheduler (后台任务)
├── Celery (异步任务队列)
├── Redis (缓存，可选)
├── Multi-Provider Model Layer (v5.4.0)
└── AsyncSmartGuardian (服务健康监控)
```

---

## 版本演进

| 版本 | 主要更新 |
|------|----------|
| v5.4.0 | 多供应商模型支持 (7 供应商) |
| v5.3.x | 文档整合、模型名称修复 |
| v5.2.x | 后端并发管理、Admin 仪表板 |
| v5.1.x | 需求理解增强、前端优化 |
| v5.0.0 | 需求联想增强 |
| v4.9.0 | Agent 架构重构、性能优化 |
| v4.8.x | SSE 展示优化、Agent 增量修改 |
| v4.7.0 | OpenTelemetry 追踪、安全审计 |

---

*本架构文档最后更新：2026-05-22*
