# 系统架构

> 最后更新: 2026-05-27 | 路由总数：180+ | 版本:v5.10.0

---

## 架构概览 (v5.10.0)

v5.10.0 新增 **工作流节点扩展**（9种节点类型）和 **重试机制**，支持更复杂的业务编排。

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend (Vue 3)                                            │
│ Vite 5 + Element Plus + Tailwind CSS + Pinia + ECharts     │
│ 44 个组件 · 7 个视图 · 6 个 Store · 12 个路由                │
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
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Multi-Provider Model Layer (v5.4.0)                 │    │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐    │    │
│ │ │SiliconFlw│ │ DashScope│ │ Zhipu    │ │DeepSeek  │    │    │
│ │ └──────────┘ └──────────┘ └──────────┘ └──────────┘    │    │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐               │    │
│ │ │ OpenAI   │ │Anthropic │ │ Ollama   │               │    │
│ │ └──────────┘ └──────────┘ └──────────┘               │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ API Key Management (v5.9.0)                          │   │
│ │ - RSA-2048 加密传输                                   │   │
│ │ - Redis 内存存储 + TTL 自动过期                       │   │
│ │ - 所有功能统一使用用户 API Key                        │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                             │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Middleware Layer (8 层)                              │   │
│ │ CORS │ RequestLog │ InputValidator │ RateLimit       │   │
│ │ FeatureSwitch │ SecurityHeaders │ GZip │ Drain      │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                             │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Prompt Optimizer (v5.8.1)                            │   │
│ │ - 静态前缀缓存 (KV Cache 命中)                       │   │
│ │ - 动态变量清理 (时间戳/UUID)                         │   │
│ │ - JSON 键顺序固定                                     │   │
│ └──────────────────────────────────────────────────────┘   │
│                                                             │
│ ┌──────────────────────────────────────────────────────┐   │
│ │ Multi-Angle Review (v5.8.1)                          │   │
│ │ - 性能师 (并行) │ 安全师 (并行) │ 可维护性师 (并行) │   │
│ │ - 三档严格度：轻量/标准/严格                         │   │
│ └──────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Data Layer                                                  │
│                                                             │
│ SQLite (Async SQLAlchemy + Alembic) │ APScheduler          │
│ Redis (Cache/API Key)               │ 定时任务调度          │
└─────────────────────────────────────────────────────────────┘
```

---

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Vue 3 + Vite 5 + Element Plus | 响应式 UI |
| 后端 | FastAPI + Python 3.11 | 异步 API |
| 数据库 | SQLite + SQLAlchemy 2.0 | 异步 ORM |
| 缓存 | Redis | 会话、API Key 存储 |
| 任务队列 | Celery + APScheduler | 异步任务 |
| 模型层 | 多供应商适配器 | 7 供应商支持 |
| **API Key** | **RSA-2048 + Redis** | **v5.9.0 新增** |
| **Prompt 优化** | **KV Cache 优化** | **v5.8.1 新增** |
| **审查系统** | **多角度并行审查** | **v5.8.1 新增** |
| **工作流引擎** | **9 种节点 + 重试机制** | **v5.10.0 新增** |
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
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Provider Adapters                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │SiliconFlw│ │DashScope │ │  Zhipu   │ │DeepSeek  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                   │
│  │  OpenAI  │ │Anthropic │ │  Ollama  │                   │
│  └──────────┘ └──────────┘ └──────────┘                   │
└─────────────────────────────────────────────────────────────┘
```

### 供应商配置

| 供应商 | 环境变量 | 默认模型 |
|--------|----------|----------|
| SiliconFlow | `SILICONFLOW_API_KEY` | THUDM/GLM-Z1-9B-0414 |
| 阿里百炼 | `DASHSCOPE_API_KEY` | qwen-turbo |
| 智谱 GLM | `ZHIPU_API_KEY` | glm-4-flash |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat |
| OpenAI | `OPENAI_API_KEY` | gpt-3.5-turbo |
| Anthropic | `ANTHROPIC_API_KEY` | claude-3-haiku |
| Ollama | `OLLAMA_BASE_URL` | llama2 |

---

## Agent 系统架构 (v5.9.0)

```
┌─────────────────────────────────────────────────────────────┐
│ Agent Orchestrator                                          │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ Architect    │ │ Frontend     │ │ Backend      │      │
│  │ Specialist   │ │ Specialist   │ │ Specialist   │      │
│  └──────────────┘ └──────────────┘ └──────────────┘      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐      │
│  │ Reviewer     │ │ Tester       │ │ Memory       │      │
│  │ Specialist   │ │ Specialist   │ │ Manager      │      │
│  └──────────────┘ └──────────────┘ └──────────────┘      │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Tool System (19 Tools)                                      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │read_file │ │write_file│ │edit_file │ │list_files│      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │run_cmd   │ │search    │ │insert    │ │partial   │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │regex     │ │delete    │ │cross_file│ │generate  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└─────────────────────────────────────────────────────────────┘
```

### Agent 功能

| 功能 | API 端点 | 说明 |
|------|----------|------|
| 项目生成 | POST /agent/orchestrate/stream | 流式生成完整项目 |
| 项目修改 | POST /agent/modify | 增量修改已有项目 |
| 需求评价 | POST /agent/evaluate | 评价需求质量 |
| 复杂度分析 | POST /agent/analyze_complexity | 分析需求复杂度 |
| 快照管理 | GET /agent/snapshots/{id} | 项目快照列表 |
| 快照回滚 | POST /agent/rollback/{id} | 回滚到指定快照 |
| 快照对比 | GET /agent/snapshot/diff | 对比两个快照差异 |
| 会话管理 | POST /agent/session/{id}/action | 暂停/恢复/取消会话 |
| 决策提交 | POST /agent/session/{id}/decision | 提交人工决策 |
| 知识库 | POST/GET /agent/knowledge | 知识库管理 |
| 需求联想 | POST /agent/requirement-association | 需求关联分析 |
| 性能监控 | GET /agent/performance | 性能指标统计 |
| Token 统计 | GET /agent/token-usage | Token 使用统计 |

---

## 数据库模型

### 核心表

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| user | 用户表 | id, username, email, password_hash, permission_level |
| permission | 权限表 | id, user_id, level, granted_at |
| history | 对话历史 | id, user_id, prompt, response, created_at |
| chat_histories | 新版对话 | id, user_id, session_id, message, token_usage |
| files | 文件管理 | id, user_id, filename, path, size |
| tasks | 任务队列 | id, user_id, status, result |
| saved_projects | 保存项目 | id, user_id, name, project_data |
| agent_sessions | Agent 会话 | id, user_id, status, session_data |
| memory_entries | Agent 记忆 | id, session_id, content, category |
| knowledge_entries | 知识库 | id, content, category, tags |
| image_generation_history | 图像生成 | id, user_id, prompt, image_url |
| workflow_history | 工作流 | id, user_id, workflow_data, status (pending/running/completed/failed/waiting_approval/skipped) |

---

## API 端点分类

### v1 API (用户功能)

| 模块 | 端点前缀 | 功能 |
|------|----------|------|
| 认证 | /api/v1/login, /register | 用户认证 |
| Agent | /api/v1/agent/* | 项目生成、代码审查 |
| AI 代码 | /api/v1/code | 代码生成 |
| PPT | /api/v1/pptx/* | PPT 生成 |
| 图像 | /api/v1/kolors/* | 图像生成 |
| AI Cloud | /api/v1/aicloud/* | AI 云管理 |
| 文件 | /api/v1/files/* | 文件管理 |
| 工作流 | /api/v1/workflow/* | DAG 编排、9 种节点、重试、条件分支 |
| 健康 | /api/v1/health | 健康检查 |

### v2 API (管理功能)

| 模块 | 端点前缀 | 功能 |
|------|----------|------|
| 管理 | /api/v2/Controller/* | 系统监控 |
| 用户 | /api/v2/Controller/users/* | 用户管理 |
| Nginx | /api/v2/nginx/* | Nginx 配置 |
| 配置 | /api/v2/admin/* | 系统配置 |

---

## 相关文档

- [模块说明](MODULES.md)
- [模型系统](MODELS.md)
- [API 责任矩阵](api-responsibility-matrix.md)
- [权限规范](../PERMISSION-SPEC.md)
- [技术债务](../TECH-DEBT.md)

---

最后更新：2026-05-26
