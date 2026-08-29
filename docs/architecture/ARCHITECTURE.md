# 系统架构

> 最后更新: 2026-06-09 | 路由总数：240+ | 后端：356 文件 / 99,618 行 | 前端：~58,000 行 | Agent 模块：76 + 3 子包 | E2E 用例：409

---

## 架构概览 (v5.15.0)

v5.13.0+ 完成 **LLM 调用路径统一**（`call_siliconflow` → `call_llm`）、**多模态兼容**（`messages` 参数）、**4 个架构级 Bug 修复**、**供应商感知降级链**、**ReActWithFallback 死代码清理**。

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend (Vue 3)                                            │
│ Vite 5 + Element Plus + Pinia + ECharts                      │
│ 69 组件 + 13 Agent 子组件 · 9 个视图 · 9 个 Store · 13 composables │
└──────────────────────────┬──────────────────────────────────┘
                            │ HTTP / SSE / WebSocket
┌──────────────────────────┴──────────────────────────────────┐
│ Backend (FastAPI / Python 3.11)                             │
│ 356 文件 / 99,618 行 / 27 个 include_router / 240+ 端点      │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Agent 引擎 (76 模块 + 3 子包, 34,166 行)             │    │
│ │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │    │
│ │  │ Architect│ │ Frontend │ │ Backend  │ │ Reviewer │ │    │
│ │  │ +ReAct  │ │ +ReAct   │ │ +ReAct   │ │ +ReAct   │ │    │
│ │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ │    │
│ │  ┌──────────────────────────────────────────────┐   │    │
│ │  │ tools.py (1,079 行, 21 工具) + MCP Client 扩展 │   │    │
│ │  │ react_engine.py (684 行, 统一 ReAct 引擎)     │   │    │
│ │  │ llm_client.py (191 行, 并发信号量 6 + 超时)   │   │    │
│ │  │ json_parser.py (345 行, 5 层解析链)           │   │    │
│ │  └──────────────────────────────────────────────┘   │    │
│ │                                                     │    │
│ │ 核心子系统:                                         │    │
│ │ • 动态模型路由 (健康度 0-100 + 熔断 + 学习路由)      │    │
│ │ • ReAct 引擎 (simple/full 双模式, 滑动窗口 3+6000) │    │
│ │ • MCP Client (stdio/HTTP + JSON-RPC 2.0)            │    │
│ │ • 依赖图 (4 模块拆分, 14 语言, 拓扑排序 + BFS)      │    │
│ │ • 会话生命周期 (5 状态机, 30 天 TTL, DB 写透)       │    │
│ │ • 错误恢复 (8 分类 + 3 重试 + 4 级降级链)            │    │
│ │ • 代码沙箱 (Python AST + JS Node.js, 30s 超时)      │    │
│ │ • 迭代修复循环 (RefinementLoop)                      │    │
│ │ • 多角度审查 (性能/安全/可维护性)                    │    │
│ │ • 代码补丁生成器 (CodePatcher)                       │    │
│ │ • 复杂度分析器 (5 级 SIMPLE→ENTERPRISE)             │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Multi-Provider Model Layer (v5.4.0+, 7 供应商)      │    │
│ │ 7 内置供应商 + 动态供应商 + context_length 4 级 fallback │    │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ │    │
│ │ │SiliconFlw│ │ DashScope│ │ Zhipu    │ │DeepSeek  │ │    │
│ │ └──────────┘ └──────────┘ └──────────┘ └──────────┘ │    │
│ │ ┌──────────┐ ┌──────────┐ ┌──────────┐            │    │
│ │ │ OpenAI   │ │Anthropic │ │ Ollama   │            │    │
│ │ └──────────┘ └──────────┘ └──────────┘            │    │
│ │ + DynamicProvider (OpenAI 兼容自定义)               │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ MCP Client Layer (MCP 协议扩展)                       │    │
│ │ • MCPServerConnection: stdio/HTTP 双传输              │    │
│ │ • MCPClientManager: 多 Server 管理 (单例)             │    │
│ │ • 工具前缀 mcp_{server}_{tool}, 对 ReAct 透明        │    │
│ │ • 4 个集成点: executor/specialist/agent/orchestrator  │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ API Key Management (v5.9.0+, v5.12.0 增强)           │    │
│ │ - RSA-2048 加密传输 + context_length 同步            │    │
│ │ - Redis 内存存储 + Lua 原子脚本 + TTL 自动过期       │    │
│ │ - 反向索引 O(1) 查找 + Token 统计                    │    │
│ │ - fallback_preference: use_admin_default / custom / disabled │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Code Sandbox (v5.12.0+, admin 可配)                  │    │
│ │ - Python AST 沙箱 + 30s 超时                        │    │
│ │ - JavaScript Node.js 沙箱 + 30s 超时               │    │
│ │ - admin API 动态启用/禁用                           │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Middleware Layer (7 层)                              │    │
│ │ CORS │ RequestLog │ InputValidator │ RateLimit       │    │
│ │ FeatureSwitch │ SecurityHeaders │ GZip               │    │
│ │ + drain_mode_middleware (优雅关闭)                  │    │
│ └─────────────────────────────────────────────────────┘    │
│                                                             │
│ ┌─────────────────────────────────────────────────────┐    │
│ │ Session Lifecycle (v5.12.0+)                          │    │
│ │ - 5 状态机: running/paused/completed/failed/cancelled │    │
│ │ - 30 天 TTL + 500 上限 + 僵尸检测                     │    │
│ │ - DB 写透缓存 + per-session 锁 + 429 限流            │    │
│ └─────────────────────────────────────────────────────┘    │
└──────────────────────────┬──────────────────────────────────┘
                           │
┌──────────────────────────┴──────────────────────────────────┐
│ Data Layer                                                  │
│                                                             │
│ SQLite (Async SQLAlchemy + Alembic, 11 个迁移版本)         │
│ Redis (Cache/API Key) — 可降级到内存                       │
│ Celery + APScheduler (异步任务 + 定时任务)                   │
│ SQLite 性能追踪 (模型调用统计)                              │
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

## Agent 系统架构 (v5.12.0+, 2026-06-09 校对)

```
┌─────────────────────────────────────────────────────────────┐
│ Agent Orchestrator (6 mixin 协调, 137 行)                    │
│                                                             │
│  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐          │
│  │ Architect   │ │ Frontend    │ │ Backend     │          │
│  │ (568行)     │ │ (107行)     │ │ (119行)     │          │
│  └─────────────┘ └─────────────┘ └─────────────┘          │
│  ┌─────────────┐ ┌─────────────┐                           │
│  │ Reviewer    │ │ Specialist  │                           │
│  │ (158行)     │ │ Base (177行)│                           │
│  └─────────────┘ └─────────────┘                           │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ tools.py (1,079 行, 21 个内置工具)                    │  │
│  │ ┌─────────────────────────────────────────────────┐ │  │
│  │ │ 代码分析 (6): read_file, list_files,            │ │  │
│  │ │   read_symbols, read_imports, summarize_file,   │ │  │
│  │ │   git_status/diff/log                           │ │  │
│  │ │ 写入工具 (4): partial_update, insert_content,   │ │  │
│  │ │   regex_replace, write_file                     │ │  │
│  │ │ 执行工具 (2): execute_code (Python AST+JS沙箱), │ │  │
│  │ │   run_command (黑名单+白名单)                    │ │  │
│  │ │ 网络工具 (2): web_search (DuckDuckGo),          │ │  │
│  │ │   http_request (SSRF防护)                       │ │  │
│  │ │ Git 工具 (3): git_status, git_diff, git_log     │ │  │
│  │ └─────────────────────────────────────────────────┘ │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ react_engine.py (684 行, 统一 ReAct 引擎)             │  │
│  │ • simple 模式: Thought → Tool → Result (Specialist)   │  │
│  │ • full 模式: Thought → Action → Observation →         │  │
│  │   Reflection → Final (ReActAgent)                     │  │
│  │ • 滑动窗口: 最近 3 条完整 + 更早摘要, 6000 字符上限    │  │
│  │ • 单轮 300s 超时                                       │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ llm_client.py (191 行, 统一 LLM 调用层)               │  │
│  │ • 全局并发信号量 MAX_CONCURRENT_LLM_CALLS=6          │  │
│  │ • 超时保护 + 成本追踪 + 自动记录到 DynamicModelRouter  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ json_parser.py (345 行, 5 层 JSON 解析链)             │  │
│  │ • thinking 清理 + 代码块提取                          │  │
│  │ • json.loads → 提取{} + 修复 → 状态机截断修复         │  │
│  │ • json_repair 库兜底 → ValueError                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ MCP Client (mcp_client.py, 513 行)                    │  │
│  │ • MCPServerConnection: stdio/HTTP 双传输              │  │
│  │ • JSON-RPC 2.0 (协议版本 2024-11-05)                 │  │
│  │ • MCPClientManager: 多 Server 管理 (单例)             │  │
│  │ • 工具命名: mcp_{server}_{tool}                       │  │
│  │ • 配置: data/mcp_servers.json                         │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Orchestrator Mixins (orchestrator_generation/        │  │
│  │   orchestrator_requirements/, 3,401 行)             │  │
│  │ • Generation: 5 mixin (spec_first/traditional/      │  │
│  │   incremental/evaluate/error_recovery)               │  │
│  │ • Requirements: 3 层关联 + 双模型对抗 + 魔鬼代言人  │  │
│  │ • Progress/Files/Testing/Utils: 协调与持久化         │  │
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
   ├─ 五角色模型配置
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
| SIMPLE | glm-z1-9b | deepseek-r1 | nex-n2-pro | glm-z1-9b | 关键词匹配 |
| SMALL | glm-z1-9b | deepseek-r1 | nex-n2-pro | glm-z1-9b | 关键词匹配 |
| MEDIUM | glm-z1-9b | deepseek-r1 | nex-n2-pro | glm-z1-9b | LLM 校准 |
| LARGE | glm-z1-9b | deepseek-r1 | nex-n2-pro | glm-z1-9b | LLM 校准 |
| XLARGE | glm-z1-9b | deepseek-r1 | nex-n2-pro | glm-z1-9b | LLM 校准 |

> 复杂度分析模型: qwen3-8b (Qwen/Qwen3-8B)

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
| 模型管理 | /api/v1/models | 免费模型管理 |
| 供应商 | /api/v1/providers | 动态供应商管理 |
| 任务队列 | /api/v1/tasks | 任务管理 |
| skills.py | 自定义 Skill 管理 | /api/v1/skills/* | 241 行 | 8 个端点: upload, list, categories, get, update, delete, upload-file, reload |

### v2 API (管理功能, 8 个模块)

| 模块 | 端点前缀 | 功能 |
|------|----------|------|
| 管理 | /api/v2/Controller/* | 系统监控 |
| 用户 | /api/v2/Controller/users/* | 用户管理 |
| Nginx | /api/v2/nginx/* | Nginx 配置 |
| 配置 | /api/v2/admin/* | 系统配置 + 沙箱 (v5.12.0+) |
| 模型管理 | /api/v2/models | 模型管理 + context_length (v5.12.0+) |
| MCP 管理 | /api/v2/mcp | MCP Server CRUD + 测试连接 |
| 守护路由 | /api/v2/guardian | 安全守护 |

---

## v5.12.0+ 关键子系统

### 1. 动态模型路由 (Dynamic Model Router)

详见 [DYNAMIC-MODEL-ROUTER.md](../features/DYNAMIC-MODEL-ROUTER.md)

- 健康度评分 (0-100)，失败降低分数
- 熔断器：连续失败自动跳过
- 五角色模型配置分配
- LearningRouter: epsilon-greedy 探索 (20%)
- ModelPerformanceTracker: SQLite 持久化统计
- 上下文窗口自适应：32K/64K/128K 分级计算 max_tokens

### 2. ReAct 引擎 (react_engine.py)

详见 [REACT-TOOL-CALLING.md](../features/REACT-TOOL-CALLING.md)

- 统一引擎：simple 模式 (Specialist) + full 模式 (ReActAgent)
- 滑动窗口工具历史管理：最近 3 条完整 + 更早摘要
- 21 个内置工具 (tools.py) + MCP 扩展工具 (动态加载)
- 弱模型自动降级（不调用工具 = 零开销）

### 3. MCP Client (mcp_client.py)

- MCPServerConnection: stdio (子进程 stdin/stdout) + HTTP (POST JSON-RPC)
- MCPClientManager: 多 Server 管理 (单例模式)
- 工具前缀 `mcp_{server}_{tool}` 避免与内置工具冲突
- 4 个集成点：executor / specialist_base / agent_executor / orchestrator
- 配置文件：`data/mcp_servers.json`
- 前端管理：`/api/v2/mcp/servers` CRUD + test + toggle

### 4. 统一 LLM 调用层 (llm_client.py)

- LLMClient: 全局并发信号量 (MAX_CONCURRENT_LLM_CALLS=6)
- 超时保护 + 成本追踪
- 自动记录到 DynamicModelRouter (start_call/record_call)
- 401/403 错误抛出 LLMClientError

### 5. 统一 JSON 解析层 (json_parser.py)

- 5 层解析链：thinking 清理 → json.loads → 提取+修复 → 状态机截断修复 → json_repair 兜底
- parse_tool_call(): 3 种策略（代码块 → 正则 → 状态机匹配嵌套）
- safe_parse_json(): 安全解析，失败抛 ValueError

### 6. 依赖图 (4 模块拆分)

- `dependency_rules.py` (183 行): 外部化规则 (DEPENDENCY_RULES + PATH_TYPE_RULES + EXTENSION_TYPE_MAP)
- `signature_extractor.py` (144 行): 函数签名提取
- `shadow_scanner.py` (83 行): 影子扫描
- `dependency_graph.py` (983 行): 核心图构建 + 拓扑排序 + BFS 影响分析
- 循环打破策略：移除入度最大目标的边

### 7. 会话生命周期 (Session Lifecycle)

详见 [SESSION-LIFECYCLE.md](../features/SESSION-LIFECYCLE.md)

- 30 天 TTL + 500 上限
- 5 状态机：running / completed / failed / cancelled / expired
- 僵尸会话检测（DB 与内存同步）
- 并发限制：2 个项目会话/用户

### 8. 工具系统统一 (tools.py)

- tools.py (996 行): 唯一工具实现源，21 个工具函数
- executor.py (451 行): ToolRegistry 单例 + EnhancedExecutor，适配后注册 18 个工具
- ANALYSIS_TOOLS: 6 个只读工具子集
- SPECIALIST_TOOLS: 18 个工具注册表
- MCP 工具通过 load_mcp_tools() 动态合并

### 9. 代码沙箱 (Code Sandbox, v5.12.0+ 新增)

- Python AST 沙箱 + 限制性 builtins + 30s 超时
- JavaScript Node.js 子进程 + 危险模式拦截 + 30s 超时
- admin API 动态启用/禁用
- 仅 superadmin 可访问

### 10. 错误恢复 (Error Recovery)

- 8 种错误类型分类
- 3 次重试 + 降级链 (默认 Qwen3-8B → DeepSeek-R1 → Qwen3.5-4B)
- ReAct 自动修复失败测试
- FeedbackLearner: 向量匹配修复模式

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

最后更新：2026-06-09
