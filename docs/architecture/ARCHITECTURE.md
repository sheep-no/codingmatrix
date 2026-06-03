# 系统架构

> 最后更新: 2026-06-02 | 路由总数：180+ | 版本:v5.12.0+

---

## 架构概览 (v5.12.0+)

v5.12.0+ 新增 **ReAct 工具调用深度集成**、**动态批处理规划**、**代码沙箱 admin 可配**、**模型 context_length 多级管理**、**工程师主动编辑模式（git stash 原子回滚）**、**会话生命周期完整化**等多项核心能力。

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend (Vue 3)                                            │
│ Vite 5 + Element Plus + Pinia + ECharts                      │
│ 64 个组件 · 8 个视图 · 7 个 Store                              │
└──────────────────────────┬──────────────────────────────────┘
                           │ HTTP / SSE / WebSocket
┌──────────────────────────┴──────────────────────────────────┐
│ Backend (FastAPI / Python 3.11)                             │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Agent 引擎 (v5.12.0+)                                │    │
│ │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │    │
│ │  │ Architect│ │ Frontend │ │ Backend  │ │ Reviewer │ │    │
│ │  │ +ReAct  │ │ +ReAct   │ │ +ReAct   │ │ +ReAct   │ │    │
│ │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │    │
│ │  ┌──────────────────────────────────────────────┐   │    │
│ │  │ Specialist (13 tools, edit tracking, sandbox)│   │    │
│ │  │ + Git Stash 原子回滚                          │   │    │
│ │  └──────────────────────────────────────────────┘   │    │
│ │                                                     │    │
│ │  核心子系统:                                         │    │
│ │  • 动态模型路由 (健康度评分 + 熔断)                    │    │
│ │  • ReAct 工具调用 (阶段化模型 + 自主循环)               │    │
│ │  • 会话生命周期 (TTL + 清理 + 限制)                    │    │
│ │  • 依赖图 (14 语言 + 拓扑分层)                        │    │
│ │  • 错误恢复 (ReAct 自动修复)                          │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Multi-Provider Model Layer (v5.4.0, v5.12.0 增强)    │    │
│ │ 7 供应商 + 动态供应商 + context_length 4级 fallback   │    │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │    │
│ │ │SiliconFlw│ │ DashScope│ │ Zhipu    │ │DeepSeek  │ │    │
│ │ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │    │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│ │ │ OpenAI   │ │Anthropic │ │ Ollama   │            │    │
│ │ └──────────┘ └──────────┘ └──────────┘            │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ API Key Management (v5.9.0, v5.12.0 增强)            │    │
│ │ - RSA-2048 加密传输 + context_length 同步            │    │
│ │ - Redis 内存存储 + TTL 自动过期                       │    │
│ │ - 多级查找 + Token 统计                              │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Code Sandbox (v5.12.0+, admin 可配)                  │    │
│ │ - Python AST 沙箱 + 30s 超时                         │    │
│ │ - JavaScript Node.js 沙箱 + 30s 超时                  │    │
│ │ - admin API 动态启用/禁用                              │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Middleware Layer (9 层)                              │    │
│ │ CORS │ RequestLog │ InputValidator │ RateLimit       │    │
│ │ FeatureSwitch │ SecurityHeaders │ GZip │ Drain       │    │
│ │ SessionCleanup                                       │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Session Lifecycle (v5.12.0+)                          │    │
│ │ - 30 天 TTL + 500 上限 + 僵尸检测                     │    │
│ │ - DB 同步 + 并发限制 (429)                            │    │
│ │ - 状态机: running/completed/failed/cancelled/expired │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Prompt Optimizer (v5.8.1)                            │    │
│ │ - 静态前缀缓存 (KV Cache 命中)                       │    │
│ │ - 动态变量清理 (时间戳/UUID)                         │    │
│ │ - JSON 键顺序固定                                     │    │
│ │ - 动态 max_tokens + 动态 spec/context 注入预算 (v5.12.0+)│    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Multi-Angle Review (v5.8.1)                          │    │
│ │ - 性能师 (并行) │ 安全师 (并行) │ 可维护性师 (并行) │    │
│ │ - 三档严格度：轻量/标准/严格                         │    │
│ └─────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Data Layer                                                  │
│                                                             │
│ SQLite (Async SQLAlchemy + Alembic) │ Celery + APScheduler  │
│ Redis (Cache/API Key)               │ 异步任务 + 定时任务   │
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
| 模型层 | 多供应商适配器 | 7 供应商 + 动态供应商 |
| **API Key** | **RSA-2048 + Redis** | **v5.9.0 新增, v5.12.0 增强 context_length** |
| **Prompt 优化** | **KV Cache 优化** | **v5.8.1 新增, v5.12.0 动态预算** |
| **审查系统** | **多角度并行审查** | **v5.8.1 新增** |
| **工作流引擎** | **9 种节点 + 重试机制** | **v5.10.0 新增** |
| **智能会话恢复** | **LLM 语义匹配** | **v5.11.0 新增** |
| **ReAct 工具调用** | **13 工具 + 阶段化模型** | **v5.12.0+ 新增** |
| **动态模型路由** | **健康度评分 + 熔断** | **v5.12.0+ 增强** |
| **代码沙箱** | **Python + JavaScript** | **v5.12.0+ 新增** |
| **会话生命周期** | **TTL + 限制 + 清理** | **v5.12.0+ 增强** |
| **编辑原子回滚** | **Git stash** | **v5.12.0+ 新增** |
| 监控 | OpenTelemetry + Jaeger | 分布式追踪 |
| 容器 | Docker + Docker Compose | 服务编排 |

---

## 多供应商模型架构 (v5.4.0+ v5.12.0 增强)

```
┌─────────────────────────────────────────────────────────────┐
│ Unified LLM Interface                                       │
│  call_llm(model, prompt, system_prompt, stream, ...)        │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Dynamic Model Router (v5.12.0+)                             │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐       │
│  │ Health Score │ │ Circuit      │ │ Layered      │       │
│  │ (0-100)      │ │ Breaker      │ │ Assignment   │       │
│  └──────────────┘ └──────────────┘ └──────────────┘       │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Provider Adapters (含 context_length 4 级 fallback)         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│  │SiliconFlw│ │DashScope │ │  Zhipu   │ │DeepSeek  │      │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐                   │
│  │  OpenAI  │ │Anthropic │ │  Ollama  │                   │
│  └──────────┘ └──────────┘ └──────────┘                   │
│  ┌──────────────────────────────────────────────────────┐ │
│  │ DynamicProvider (OpenAI-compatible 自定义)            │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 供应商配置

| 供应商 | 环境变量 | 默认模型 | context_length |
|--------|----------|----------|----------------|
| SiliconFlow | `SILICONFLOW_API_KEY` | glm-z1-9b | 模型相关 |
| 阿里百炼 | `DASHSCOPE_API_KEY` | qwen-turbo | 32k |
| 智谱 GLM | `ZHIPU_API_KEY` | glm-4-flash | 32k |
| DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat | 128k |
| OpenAI | `OPENAI_API_KEY` | gpt-3.5-turbo | 16k |
| Anthropic | `ANTHROPIC_API_KEY` | claude-3-haiku | 200k |
| Ollama | `OLLAMA_BASE_URL` | llama2 | 4k |

### context_length 优先级 (v5.12.0+)

```
1. 用户自定义 (管理员设置) - 最高优先级
2. 配置文件 (data/agent_model_config.json)
3. 代码内置映射 (MODEL_CONTEXT_LENGTHS)
4. 动态供应商声明
5. 默认 32k - 兜底
```

---

## Agent 系统架构 (v5.12.0+)

```
┌─────────────────────────────────────────────────────────────┐
│ Agent Orchestrator (6 mixin 协调)                            │
│                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │ Architect   │ │ Frontend    │ │ Backend     │          │
│  │ +ReAct      │ │ +ReAct      │ │ +ReAct      │          │
│  │ +动态批处理  │ │ +edit track │ │ +edit track │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │ Reviewer    │ │ Tester      │ │ Memory      │          │
│  │ +ReAct      │ │ +ReAct      │ │ Manager     │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Specialist 工具 (13 个, v5.12.0+)                     │  │
│  │ ┌─────────────────────────────────────────────────┐ │  │
│  │ │ 只读工具 (9 个)                                  │ │  │
│  │ │ read_file, list_files, search_in_files,         │ │  │
│  │ │ read_symbols, find_definition, read_imports,     │ │  │
│  │ │ find_references, summarize_file, glob_files     │ │  │
│  │ └─────────────────────────────────────────────────┘ │  │
│  │ ┌─────────────────────────────────────────────────┐ │  │
│  │ │ 写入/验证工具 (4 个)                             │ │  │
│  │ │ partial_update, insert_content,                 │ │  │
│  │ │ regex_replace, execute_code (沙箱)               │ │  │
│  │ └─────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ReAct 循环 (call_llm_with_tools)                      │  │
│  │  Thought → Action → Observe, max 2 工具轮 + 1 最终   │  │
│  │  阶段化模型 (think/action/final 不同模型)            │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ 编辑原子回滚 (v5.12.0+)                              │  │
│  │  Git stash push (修改前) → 写入 → 成功 drop / 失败 pop│  │
│  │  新文件: unlink() 兜底                                │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ ToolRegistry (12 个, ReActAgent 用)                   │  │
│  │  delete_files_by_pattern, cross_file_patch_auto,     │  │
│  │  web_search, http_request, screenshot_diagnose, ...  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### 5 阶段生成流程 (v5.12.0+)

```
需求输入
   ↓
[1] 复杂度分析 (complexity.py)
   ├─ SIMPLE/SMALL: 关键词匹配
   └─ MEDIUM+: LLM 校准
   ↓
[2] 模型分配 (dynamic_model_router)
   ├─ 5 复杂度档 × 5 角色模型
   └─ 健康度评分
   ↓
[3] 架构师设计 (architect.py)
   ├─ 动态批处理 (while True 循环)
   ├─ 文件清单 + 依赖图
   └─ 优先级排序
   ↓
[4] 工程师生成 (backend/frontend engineer)
   ├─ ReAct 工具调用 (按需读取)
   ├─ 写入/编辑/验证
   ├─ 编辑追踪 (_edited_files)
   └─ Git stash 原子回滚
   ↓
[5] 审查 + 验证 (reviewer + tester)
   ├─ 多角度并行审查
   ├─ 沙箱执行 (Python/JavaScript)
   └─ 错误自动恢复 (ReAct)
```

### Agent 功能 (v5.12.0+)

| 功能 | API 端点 | 说明 |
|------|----------|------|
| 项目生成 | POST /agent/orchestrate/stream | 流式生成完整项目 (5 阶段) |
| 项目修改 | POST /agent/modify | 增量修改已有项目 |
| 需求评价 | POST /agent/evaluate | 评价需求质量 |
| 复杂度分析 | POST /agent/analyze_complexity | 分析需求复杂度 |
| 快照管理 | GET /agent/snapshots/{id} | 项目快照列表 |
| 快照回滚 | POST /agent/rollback/{id} | 回滚到指定快照 |
| 快照对比 | GET /agent/snapshot/diff | 对比两个快照差异 |
| 会话管理 | POST /agent/session/{id}/action | 暂停/恢复/取消/expired |
| 决策提交 | POST /agent/session/{id}/decision | 提交人工决策 |
| 知识库 | POST/GET /agent/knowledge | 知识库管理 |
| 需求联想 | POST /agent/requirement-association | 需求关联分析 |
| 性能监控 | GET /agent/performance | 性能指标统计 |
| Token 统计 | GET /agent/token-usage | Token 使用统计 |
| 智能恢复 | POST /agent/search_sessions | 语义搜索历史 session |
| **API Key** | **POST /agent/apikey/{token}/context-lengths** | **v5.12.0+ 新增** |
| **模型健康** | **GET /agent/model-health** | **v5.12.0+ 新增** |
| **ReAct 调用** | **POST /agent/react** | **v5.12.0+ 新增** |

### 模型分配策略 (v5.12.0+)

| 复杂度 | 架构师 | 前端 | 后端 | 审查员 | 复杂度分析 |
|--------|--------|------|------|--------|------------|
| SIMPLE | qwen3.5-4b | qwen3-8b | qwen3-8b | qwen3-8b | 关键词匹配 |
| SMALL | glm-z1-9b | qwen3-8b | deepseek-r1 | deepseek-r1 | 关键词匹配 |
| MEDIUM | glm-z1-9b | qwen3-8b | deepseek-r1 | deepseek-r1 | LLM 校准 |
| LARGE | glm-z1-9b | qwen3-8b | deepseek-r1 | deepseek-r1 | LLM 校准 |
| XLARGE | glm-z1-9b | qwen3-8b | deepseek-r1 | deepseek-r1 | LLM 校准 |

> 临时配置：因 SiliconFlow Qwen3.5-4B 暂不可用，SIMPLE 架构师临时改为 qwen3-8b。

---

## 数据库模型

共 22 个表，分布在 13 个模型文件中。

### 核心表

| 表名 | 说明 | 主要字段 |
|------|------|----------|
| user | 用户表 | id, username, email, password_hash, permission_level |
| permission | 权限表 | id, user_id, level, granted_at |
| history | 对话历史 | id, user_id, prompt, response, created_at |
| chat_histories | 新版对话 | id, user_id, session_id, message, token_usage |
| chat_summaries | 对话摘要 | id, user_id, session_id, summary |
| files | 文件管理 | id, user_id, filename, path, size |
| tasks | 任务队列 | id, user_id, status, result |
| saved_projects | 保存项目 | id, user_id, name, project_data |
| server_config | 服务配置 | id, key, value |
| server_stats | 服务统计 | id, metric, value, recorded_at |

### Agent 表

| 表名 | 说明 |
|------|------|
| agent_sessions | Agent 会话 (含 status 状态机) |
| memory_entries | Agent 记忆 |
| agent_reflections | Agent 反思 |
| knowledge_entries | 知识库 |
| tool_execution_logs | 工具执行日志 |
| model_usage_stats | 模型使用统计 |
| project_sessions | **项目会话 (v5.12.0+ 新增)** |

### AI Cloud 表

| 表名 | 说明 |
|------|------|
| aicloud_sessions | AI Cloud 会话 |
| aicloud_messages | AI Cloud 消息 |
| aicloud_reviews | AI Cloud 审查 |
| aicloud_audit_logs | AI Cloud 审计 |
| aicloud_knowledge_docs | 知识库文档 |
| aicloud_knowledge_chunks | 知识库分片 |

---

## API 端点分类

### v1 API (用户功能, 19 个模块)

| 模块 | 端点前缀 | 功能 |
|------|----------|------|
| 认证 | /api/v1/login, /register | 用户认证 |
| Agent | /api/v1/agent/* | 项目生成、代码审查、ReAct |
| AI 代码 | /api/v1/code | 代码生成 |
| AI 项目代码 | /api/v1/AiProjectCode | 项目代码生成 |
| PPT | /api/v1/pptx/* | PPT 生成 |
| 图像 | /api/v1/kolors/* | 图像生成 |
| 图像历史 | /api/v1/kolors-history | 图像生成历史 |
| AI Cloud | /api/v1/aicloud/* | AI 云管理 |
| AI Cloud 知识 | /api/v1/aicloud-knowledge | 知识库管理 |
| 文件 | /api/v1/files/* | 文件管理 |
| 工作流 | /api/v1/workflow/* | DAG 编排、9 种节点、重试、条件分支 |
| 视觉分析 | /api/v1/vision | 图像理解 |
| 健康 | /api/v1/health | 健康检查 |
| API Key | /api/v1/apikey | API Key 管理 + context_length (v5.12.0+) |
| GitHub | /api/v1/github | GitHub 集成 |
| 预览 | /api/v1/preview | 项目预览 |
| 模型管理 | /api/v1/models | 免费模型管理 |
| 供应商 | /api/v1/providers | 动态供应商管理 |
| 任务队列 | /api/v1/tasks | 任务管理 |

### v2 API (管理功能, 7 个模块)

| 模块 | 端点前缀 | 功能 |
|------|----------|------|
| 管理 | /api/v2/Controller/* | 系统监控 |
| 用户 | /api/v2/Controller/users/* | 用户管理 |
| Nginx | /api/v2/nginx/* | Nginx 配置 |
| 配置 | /api/v2/admin/* | 系统配置 + 沙箱 (v5.12.0+) |
| 模型管理 | /api/v2/models | 模型管理 + context_length (v5.12.0+) |
| 守护路由 | /api/v2/guardian | 安全守护 |

---

## v5.12.0+ 关键子系统

### 1. 动态模型路由 (Dynamic Model Router)

详见 [DYNAMIC-MODEL-ROUTER.md](../features/DYNAMIC-MODEL-ROUTER.md)

- 健康度评分 (0-100)，失败降低分数
- 熔断器：连续失败自动跳过
- 5 复杂度档 × 5 角色模型分配
- 多模型交叉验证
- 跨模型 `MODEL_ID_TO_KEY` 映射

### 2. ReAct 工具调用 (ReAct Tool Calling)

详见 [REACT-TOOL-CALLING.md](../features/REACT-TOOL-CALLING.md)

- 5 阶段循环：思考 / 行动 / 观察 / 反思 / 最终
- 阶段化模型路由（不同阶段可用不同模型）
- 13 个 Specialist 工具 + 12 个 ToolRegistry 工具
- 编辑追踪（`_edited_files`）
- 弱模型自动降级（不调用工具 → 零开销）

### 3. 会话生命周期 (Session Lifecycle)

详见 [SESSION-LIFECYCLE.md](../features/SESSION-LIFECYCLE.md)

- 30 天 TTL + 500 上限
- 5 状态机：running / completed / failed / cancelled / expired
- 僵尸会话检测（DB 与内存同步）
- 并发限制：2 个项目会话/用户
- 409 响应返回活跃会话列表

### 4. 代码沙箱 (Code Sandbox, v5.12.0+ 新增)

- Python AST 沙箱 + 限制性 builtins + 30s 超时
- JavaScript Node.js 子进程 + 危险模式拦截 + 30s 超时
- admin API 动态启用/禁用
- 仅 superadmin 可访问

### 5. 错误恢复 (Error Recovery)

- 8 种错误类型分类
- 3 次重试 + 降级链
- ReAct 自动修复失败测试

### 6. 依赖图 (Dependency Graph)

- 14 种语言解析
- 拓扑分层 + BFS 跨文件影响分析
- `__init__.py` 最后生成（priority=5）

### 7. 工程师主动编辑 (Engineer Active Editing, v5.12.0+)

- 工程师从"被动接收"转为"主动 Agent"
- 编辑追踪（`_edited_files`）
- Edit marker 协议：返回 JSON `{"action": "edited", "files": [...]}`
- Orchestrator 检测 marker → 从磁盘读取已修改文件
- Git stash 原子回滚

### 8. 动态批处理规划 (Dynamic Batch Planning, v5.12.0+)

- 架构师 `expand_file_plan()` 改为 `while True` 循环
- 3 个自然终止条件（不再有新增、模型拒绝补充、达到总容量）
- 无 `max_batches` 硬限制

---

## 相关文档

- [模块说明](MODULES.md)
- [模型系统](MODELS.md)
- [API 职责矩阵](API-RESPONSIBILITY-MATRIX.md)
- [Agent 详细文档](../features/AGENT.md)
- [动态模型路由](../features/DYNAMIC-MODEL-ROUTER.md)
- [ReAct 工具调用](../features/REACT-TOOL-CALLING.md)
- [会话生命周期](../features/SESSION-LIFECYCLE.md)
- [权限规范](../security/PERMISSION-SPEC.md)
- [技术债务](../TECH-DEBT.md)

---

最后更新：2026-06-02
