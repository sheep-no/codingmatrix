# CodingMatrix 文档中心

> 最后更新：2026-06-22 | 后端代码：356 文件 / 99,618 行 | 前端代码：~58,000 行 | Agent 模块：76 + 3 子包 | 端点：240+ | E2E 用例：409

## 快速导航

### 入门
- [快速开始](guides/GETTING-STARTED.md) - 环境配置、快速启动
- [多供应商配置](guides/MULTI-PROVIDER-SETUP.md) - 7 个 LLM 供应商配置
- [API Key 指南](guides/API-KEY-GUIDE.md) - API Key 管理和使用

### 架构
- [系统架构](architecture/ARCHITECTURE.md) - 完整架构设计（含 9 大子系统）
- [模块说明](architecture/MODULES.md) - 后端 356 文件 + 前端 58,000 行详细清单
- [模型系统](architecture/MODELS.md) - 多供应商 LLM 适配器
- [API 职责矩阵](architecture/API-RESPONSIBILITY-MATRIX.md) - v1/v2 路由职责

### API
- [API 文档](api/API-DOCUMENTATION.md) - 240+ 个端点完整文档
- [API 版本管理](api/API-VERSIONS.md) - 版本策略和迁移指南

### 核心功能模块
- [Agent 系统](features/AGENT.md) - 多角色协作、项目生成、ReAct 工具调用
- [动态模型路由](features/DYNAMIC-MODEL-ROUTER.md) - 健康感知路由、熔断、模型分配
- [ReAct 工具调用](features/REACT-TOOL-CALLING.md) - 自主循环、阶段化模型、ToolRegistry
- [会话生命周期](features/SESSION-LIFECYCLE.md) - 会话创建/恢复/暂停/取消/清理
- [AI 云管理](features/AICLOUD.md) - 模型切换、故障转移
- [工作流引擎](features/WORKFLOW.md) - DAG 编排、9 种节点类型
- [免费模型管理](features/MODEL-MANAGER.md) - 内置模型查看、切换
- [动态供应商](features/DYNAMIC-PROVIDERS.md) - 自定义 API 接入
- [Web 搜索增强](features/WEB-SEARCH-ENHANCEMENTS.md) - 查询优化、结果去重
- [多语言依赖解析](features/MULTI-LANGUAGE-DEPENDENCY-PARSER.md) - 14 种语言依赖分析
- [SSE 展示优化](features/SSE-DISPLAY-OPTIMIZATION.md) - 流式响应展示
- [PPT Agent](features/PPT-AGENT.md) - PPT 智能生成
- [自定义 Skill](features/CUSTOM-SKILLS.md) - 自定义提示词管理、热重载
- [虚拟姬](features/GIRLAI.md) - AI 情感陪伴角色
- [项目介绍](features/PROJECT-INTRODUCTION.md) - 平台功能总览

### 部署运维
- [生产部署](guides/PRODUCTION.md) - Docker Compose、服务管理
- [服务管理](guides/SERVICES.md) - 服务启停、健康检查

### 安全
- [安全架构](security/SECURITY-OVERVIEW.md) - 安全概览（含 API Key 加密、并发限制）
- [加密登录](security/ENCRYPTED-LOGIN.md) - RSA 加密登录
- [CSRF 防护](security/CSRF-IMPLEMENTATION.md) - CSRF 实现
- [权限规范](security/PERMISSION-SPEC.md) - RBAC 权限模型

### 演化路径
- [演化路径索引](evolution/README.md) - 各核心子系统未来演化规划
- [Agent 引擎演化路径](evolution/AGENT-ENGINE.md) - 编排核心、角色、路由、验证闭环的拆分与演进
- [前端 Agent 界面演化路径](evolution/AGENT-FRONTEND.md) - 布局修正、对话流重构、行级 diff、多文件标签、目录树

### 其他
- [分布式追踪](observability/TRACING.md) - OpenTelemetry 集成
- [AI 提示词](prompts/PROMPTS.md) - 22 个提示词模板
- [Skills](skills/HISTORY.md) - Skills 历史和列表
- [技术债务](TECH-DEBT.md) - 技术债务跟踪

---

## 项目概览

CodingMatrix 是 AI 驱动的全栈代码生成与开发平台，基于 FastAPI (Python 3.11) + Vue 3 + SQLite + Playwright 构建。核心能力是**多角色 AI Agent 系统**：从需求理解、架构设计到代码生成、验证、修复全自动完成。

### 项目规模 (2026-06-09)

| 维度 | 数量 | 说明 |
|------|------|------|
| **Python 文件** | 356 | 后端核心逻辑，99,618 行 |
| **Vue 组件** | 69 | 前端 UI 组件 (+ 13 Agent 子组件) |
| **JS 文件** | ~80 | 前端逻辑和工具 (含 16 API 客户端) |
| **TS 文件** | 1 | 类型定义 |
| **代码文件总计** | ~520 | |
| **Agent 模块** | 76 + 3 子包 | 多角色协作系统 (34,166 行) |
| **Orchestrator Mixins** | 25 | 生成流程协调 |
| **API 路由模块** | 25 | 19 v1 用户 + 8 v2 管理 |
| **API 端点** | 240+ | 前后端接口 |
| **E2E 测试** | 77 spec / 409 用例 | 端到端测试 |
| **单元测试** | 88 文件 / 1376 用例 | 测试覆盖 |
| **集成测试** | 2 文件 | 多数已归档到 archive/ |

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | FastAPI + Python 3.11 | 异步 Web 框架 |
| 数据库 | SQLAlchemy + SQLite + Alembic | 异步 ORM + 11 个迁移版本 |
| 缓存 | Redis | 会话、API Key 存储 (可降级内存) |
| 任务队列 | Celery + APScheduler | 异步任务 + 定时任务 |
| 前端 | Vue 3 + Vite + Pinia | 响应式 SPA (9 stores) |
| 测试 | Playwright + pytest | E2E (77) + 单元 (1376) |
| 部署 | Docker + Nginx | 容器化部署, 3 阶段 Dockerfile |

### 核心子系统 (2026-06-09)

| 子系统 | 模块路径 | 描述 |
|--------|----------|------|
| **AI Agent 引擎** | `app/agent/` | **76 模块 + 3 子包, 34,166 行, 25 mixin, 5 角色专家, ReAct 引擎** |
| **统一 LLM 层** | `app/agent/llm_client.py` (191 行) | 并发信号量 6, 超时保护, 成本追踪, 自动上报 DynamicModelRouter |
| **动态模型路由** | `app/agent/dynamic_model_router.py` (996 行) | 健康度 0-100 评分, 熔断, 角色模型分配, 降级链, epsilon-greedy 学习路由 |
| **ReAct 引擎** | `app/agent/react_engine.py` (684 行) | simple + full 双模式, 滑动窗口历史, 300s 单轮超时 |
| **MCP Client** | `app/agent/mcp_client.py` (513 行) | stdio/HTTP 双传输, JSON-RPC 2.0, 4 集成点 (executor/specialist/agent/orchestrator) |
| **依赖图** | `app/agent/dependency_graph.py` (1,007 行) | 4 模块拆分, 14 语言解析, 拓扑排序 + BFS 影响分析 |
| **会话管理** | `app/agent/session_manager.py` (582 行) | 5 状态机, 30 天 TTL + 500 上限, DB 写透缓存, 429 限流 |
| **错误恢复** | `app/agent/error_recovery.py` (797 行) | 8 种错误分类, 3 次重试, 4 级降级链 + 供应商感知 |
| **统一 JSON 层** | `app/agent/json_parser.py` (345 行) | 5 层解析链, 工具调用 3 种策略 |
| **工具系统** | `app/agent/tools.py` (1,079 行) | 21 个内置工具 (唯一实现源) + MCP 扩展, SPECIALIST_TOOLS 注册表 |
| **多供应商 LLM** | `app/adapter/` | 7 供应商 + 动态供应商 + context_length 4 级 fallback |

### 端点模块 (27 个 include_router, 240+ 端点)

| 模块 | 端点 | 功能 |
|------|------|------|
| Agent 系统 | `/api/v1/agent/*` | 5 子路由聚合 (orchestrate/generate/association/knowledge/performance), 项目生成/代码审查/快照/会话/ReAct |
| AI 代码 | `/api/v1/code`, `/api/v1/AiProjectCode` | 代码生成、流式输出 |
| PPT 生成 | `/api/v1/pptx/*` | 异步任务、多格式输出 |
| 图像生成 | `/api/v1/kolors/*` | 文生图、图生图 |
| AI Cloud | `/api/v1/aicloud/*` + `/aicloud-knowledge` | 沙箱执行、审查队列、知识库 |
| 文件上传 | `/api/v1/files/*` | 单文件/分片上传 (5MB)、断点续传、hash 去重 |
| 工作流 | `/api/v1/workflow/*` | DAG 编排、9 种节点、重试机制 |
| 任务队列 | `/api/v1/tasks` | Celery 驱动, WebSocket 进度推送 |
| 视觉 | `/api/v1/vision` | 图像理解、OCR、代码从图像、安全检查 |
| 免费模型 | `/api/v1/models` | 内置模型查看、切换 |
| 动态供应商 | `/api/v1/providers` | 自定义 API 接入、context_length |
| 用户管理 | `/api/v2/Controller/*` | CRUD、权限管理 |
| API Key | `/api/v1/apikey` | 用户 API Key 管理、RSA-2048 加密、context_length |
| 模型管理 | `/api/v2/models` | 管理员配置 context_length、fallback chain |
| MCP 管理 | `/api/v2/mcp` | MCP Server CRUD + test + toggle |
| 沙箱管理 | `/api/v2/admin/sandbox-config` | 管理员配置代码沙箱 |
| Skills API | `/api/v2/skills/*` | 自定义 Skill CRUD + 热重载 |
| Nginx | `/api/v2/nginx/*` | Nginx 配置检查/生成/部署 |
| 守护路由 | `/api/v2/guardian` | 服务守护 (最大 v2 模块 858 行) |
| 健康检查 | `/api/v1/health` | Prometheus 指标 |

---

## 快速开始

### 启动服务

```bash
# 启动后端 (端口 8000，包含前端 dist)
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 访问前端
open http://localhost:8000
```

### 运行测试

```bash
# E2E 冒烟测试 (推荐，18 秒)
npx playwright test tests/e2e/smoke-test-simple.spec.js

# 所有 E2E 测试
npx playwright test tests/e2e/

# 单元测试
pytest tests/unit/ -v
```

---

## 文档结构

```
docs/
├── README.md                    # 本文件（主入口）
├── TECH-DEBT.md                 # 技术债务跟踪
├── architecture/                # 架构设计
│   ├── ARCHITECTURE.md          # 系统架构（9 大子系统）
│   ├── MODULES.md               # 模块说明（76 Agent 模块）
│   ├── MODELS.md               # 模型系统
│   └── API-RESPONSIBILITY-MATRIX.md
├── api/                         # API 文档
│   ├── API-DOCUMENTATION.md    # API 完整文档
│   └── API-VERSIONS.md         # API 版本管理
├── features/                   # 功能模块
│   ├── AGENT.md                # Agent 系统（1557 行）
│   ├── DYNAMIC-MODEL-ROUTER.md # 动态模型路由
│   ├── REACT-TOOL-CALLING.md  # ReAct 工具调用
│   ├── SESSION-LIFECYCLE.md   # 会话生命周期
│   ├── AICLOUD.md             # AI 云
│   ├── WORKFLOW.md            # 工作流
│   ├── MODEL-MANAGER.md       # 免费模型管理
│   ├── DYNAMIC-PROVIDERS.md   # 动态供应商
│   ├── MULTI-LANGUAGE-DEPENDENCY-PARSER.md
│   ├── SSE-DISPLAY-OPTIMIZATION.md
│   ├── WEB-SEARCH-ENHANCEMENTS.md
│   ├── PPT-AGENT.md           # PPT 智能生成
│   ├── CUSTOM-SKILLS.md       # 自定义 Skill 系统
│   ├── GIRLAI.md              # 虚拟姬
│   └── PROJECT-INTRODUCTION.md # 项目介绍
├── guides/                      # 开发指南
│   ├── GETTING-STARTED.md       # 快速开始
│   ├── MULTI-PROVIDER-SETUP.md  # 多供应商配置
│   ├── PRODUCTION.md            # 生产部署
│   ├── SERVICES.md              # 服务管理
│   └── API-KEY-GUIDE.md         # API Key 指南
├── security/                    # 安全文档
│   ├── SECURITY-OVERVIEW.md     # 安全概览
│   ├── ENCRYPTED-LOGIN.md       # 加密登录
│   ├── CSRF-IMPLEMENTATION.md   # CSRF 防护
│   └── PERMISSION-SPEC.md       # 权限规范
├── observability/               # 可观测性
│   └── TRACING.md               # 分布式追踪
├── prompts/                     # AI 提示词
│   └── PROMPTS.md               # 提示词模板
├── skills/                      # Skills 文档
│   └── HISTORY.md               # Skills 历史
├── testing/                     # 测试
│   ├── README.md
│   ├── TESTING.md
│   └── test_agent_core_selfcheck.py
└── specs/                       # 规格设计
```

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| **v5.15.0** | **2026-06-22** | **模型配置 v4.0 + 自定义 Skill 系统 + 虚拟姬增强 + API Key 降级偏好** |
| **v5.14.0** | **2026-06-06** | **项目规模扩展：76 Agent 模块 + 25 Orchestrator Mixins + 69 Vue 组件 + 26 API 路由** |
| **v5.13.0** | **2026-06-05** | **LLM 调用路径统一 + 多模态兼容 + 供应商感知降级链** |
| v5.12.0+ | 2026-06-02 | ReAct 工具调用深度集成 + 动态批处理规划 + 模型 context_length 多级管理 + API Key 修复 + 前端消息处理完善 + 代码沙箱 admin 配置 |
| v5.12.0 | 2026-06-01 | 模型 context_length 管理（4 级 fallback）+ 用户自定义 context_length + 用户 API Key 模型同步 + API Key 查找修复 + 前端消息处理完善 |
| v5.11.0 | 2026-05-30 | 智能会话恢复系统 + SSE 响应解析修复 + API Key 管理增强 + 检查点恢复优化 |
| v5.10.0 | 2026-05-27 | 工作流节点扩展（9种） + 重试机制 + 条件分支 |
| v5.9.0 | 2026-05-26 | API Key 全局化 + Token 统计 + Orchestrator 端点 |
| v5.8.1 | 2026-05-23 | KV Cache 优化 + 多角度审查系统 |

### v5.15.0 (2026-06-22)

- **模型配置 v4.0**: 新增 nex-n2-pro 模型，角色分配调整
- **FileModelRouter**: 改为从 agent_model_config.json 读取配置
- **自定义 Skill 系统**: 完整的 CRUD API + 热重载 + Agent 提示词覆盖
- **虚拟姬增强**: 自定义角色、用户偏好、历史搜索
- **API Key 降级偏好**: fallback_preference (disabled/custom/admin_default)
- **Bug 修复**: 验证禁用时 validation_report 缺少 runnable 键

### v5.14.0 项目规模扩展

- **Agent 模块扩展**：从 38 个扩展到 76 个模块
- **Orchestrator Mixins**：新增 25 个 Mixin 协调生成流程
- **前端组件**：69 个 Vue 组件，完整功能覆盖
- **API 路由**：26 个路由模块
- **测试覆盖**：76 个 E2E spec + 1622 单元测试

### v5.12.0+ 最新更新要点

- **MCP 协议集成**: MCP Client 支持 stdio/HTTP 双传输，用户可接入任意外部工具（数据库、浏览器、搜索等）
- **工具系统统一**: tools.py 作为唯一实现源 (21 工具)，executor.py 适配后注册
- **ReAct 引擎统一**: react_engine.py 统一 simple + full 双模式，滑动窗口历史管理
- **统一 LLM/JSON 层**: llm_client.py 并发信号量 + 超时保护; json_parser.py 5 层解析链
- **依赖图拆分**: 4 模块 (rules/extractor/scanner/graph) + 外部化规则
- **交叉验证优化**: priority <= 2 且命中关键模式才触发，节省 token
- **26 个 bare except 修复** + **22 个重复 import 清除** + **39 处硬编码模型名统一**

详细版本历史见 [versions/](../versions/) 目录

---

最后更新：2026-06-22
