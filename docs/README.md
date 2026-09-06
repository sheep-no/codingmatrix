# CodingMatrix 文档中心

> 最后更新：2026-09-03 | 后端：423 个 Python 文件 / 117,655 行 | API：28 个挂载 Router / 275 条业务路由 | ORM：34 张表 | Alembic：15 个有效迁移文件

CodingMatrix 是基于 FastAPI、Vue 3 和 SQLite 构建的 AI 开发平台，覆盖智能对话、项目生成、多 Agent 协作、模型与供应商配置、PPT 生成、AI Cloud、GirlAI，以及 Web、Mobile 和 VS Code 多端 Agent 工作流。

## 文档时效范围

- 本首页及 `architecture/`、`api/`、`features/`、`guides/`、`security/`、`testing/`、`observability/`、`prompts/`、`skills/` 和顶层结构文档描述 2026-09-03 当前项目状态。
- `evolution/`、`.monkeycode/specs/` 和 `versions/` 保存历史规划、功能规格与版本快照，按形成时的历史语义保留；其中的规模、接口和验收数字不代表当前基线。
- 当前 API 数量采用实际挂载后的路由记录口径；测试数量采用静态测试定义口径。运行结果、依赖条件和验收日期以对应测试文档为准。

## 快速导航

### 项目结构

- [项目结构](PROJECT-STRUCTURE.md) - 目录职责、代码分层、统一状态、PPT 与 VS Code Host 结构
- [根目录文件说明](ROOT-FILES.md) - 根目录文件、运行数据和脚本分类
- [技术债务](TECH-DEBT.md) - 当前技术债务跟踪

### 入门与运维

- [快速开始](guides/GETTING-STARTED.md) - 环境配置、数据库初始化、开发启动和验证
- [多供应商配置](guides/MULTI-PROVIDER-SETUP.md) - 内置与动态 LLM 供应商配置
- [API Key 指南](guides/API-KEY-GUIDE.md) - 用户 Key 加密、存储和使用
- [服务与端口](guides/SERVICES.md) - 服务启停、端口、代理和健康检查
- [生产部署](guides/PRODUCTION.md) - Docker Compose、Nginx 和生产运行

### 架构

- [系统架构](architecture/ARCHITECTURE.md) - 系统分层、统一状态、PPT 编排和多端 Agent
- [模块说明](architecture/MODULES.md) - 后端、前端、测试和关键模块清单
- [数据模型与 LLM](architecture/MODELS.md) - 34 张 ORM 表、模型配置和供应商适配器
- [API 职责矩阵](architecture/API-RESPONSIBILITY-MATRIX.md) - v1/v2 Router 职责和关键执行链

### API

- [API 文档](api/API-DOCUMENTATION.md) - 275 条可达业务路由的口径、重点端点和能力索引
- [API 版本管理](api/API-VERSIONS.md) - URL 版本策略、当前挂载基线和迁移约定

### Agent 与模型

- [Agent 系统](features/AGENT.md) - Web/Mobile Agent、StateGraph 迁移层、模型上下文和 VS Code Host
- [动态模型路由](features/DYNAMIC-MODEL-ROUTER.md) - 健康感知、熔断、角色分配和学习路由
- [ReAct 工具调用](features/REACT-TOOL-CALLING.md) - 编排内自主循环、工具注册和事件输出
- [会话生命周期](features/SESSION-LIFECYCLE.md) - 会话、任务、事件、checkpoint 和恢复
- [模型管理](features/MODEL-MANAGER.md) - 用户模型浏览与管理面配置边界
- [动态供应商](features/DYNAMIC-PROVIDERS.md) - OpenAI 兼容与 Anthropic 协议供应商
- [自定义 Skill](features/CUSTOM-SKILLS.md) - 用户 Skill 管理、热重载和 Host 同步
- [SSE 展示](features/SSE-DISPLAY-OPTIMIZATION.md) - Agent 流式事件与前端展示

### 业务能力

- [项目功能介绍](features/PROJECT-INTRODUCTION.md) - 平台当前能力总览
- [PPT Agent](features/PPT-AGENT.md) - 版本化大纲、审批、质量检查和单页重生成
- [GirlAI](features/GIRLAI.md) - 角色对话、自定义角色、偏好和统一状态
- [AI Cloud](features/AICLOUD.md) - 沙箱、审查、知识库和统一会话状态
- [工作流引擎](features/WORKFLOW.md) - DAG 执行、节点类型和状态接入边界
- [Web 搜索增强](features/WEB-SEARCH-ENHANCEMENTS.md) - 查询优化模块及当前接入状态
- [多语言依赖解析](features/MULTI-LANGUAGE-DEPENDENCY-PARSER.md) - 独立解析器能力及生产接入边界

### 安全与测试

- [安全概览](security/SECURITY-OVERVIEW.md) - 认证、密钥、RBAC、中间件和工作区边界
- [加密登录](security/ENCRYPTED-LOGIN.md) - AES/RSA 登录载荷流程
- [CSRF 防护](security/CSRF-IMPLEMENTATION.md) - Double-submit Cookie 实现与边界
- [权限规范](security/PERMISSION-SPEC.md) - normal、admin、superadmin 权限模型
- [测试索引](testing/README.md) - 测试文档入口和运行条件
- [测试指南](testing/TESTING.md) - pytest、Vitest、Playwright 与 VS Code Extension Host 测试

### 可观测性与提示资源

- [分布式追踪](observability/TRACING.md) - OpenTelemetry 集成
- [AI 提示词](prompts/PROMPTS.md) - 提示词模板与索引
- [Skills](skills/HISTORY.md) - Skills 历史和清单

### 历史资料

- [演化路径](evolution/README.md) - 子系统规划与演进记录
- [版本快照](versions/README.md) - 历史版本说明和迁移记录

## 当前项目基线

### 代码与数据规模

| 维度 | 当前数量 | 口径 |
|------|---------:|------|
| 后端 Python | 423 个文件 / 117,655 行 | `app/**/*.py` |
| FastAPI Router | 28 个挂载 | `app/main.py` 中 20 个 v1 + 8 个 v2 Router |
| 业务路由 | 275 条 | 271 条 HTTP + 4 条 WebSocket，排除框架文档、静态资源和前端 catch-all |
| ORM | 34 张表 | `app/models/` 中的有效 `__tablename__` 声明 |
| Alembic | 15 个有效迁移文件 | `migrations/versions/` |
| 前端 Vue | 71 个文件 | `src/**/*.vue` |
| 前端视图 | 9 个 | `src/views/` |
| Pinia Stores | 10 个 | `src/stores/` |
| Composables | 14 个 | `src/composables/` |
| API Client JS | 19 个 | 前端 API client JavaScript 文件 |
| 前端源码 | 约 62,953 行 | `src/` 源码静态清点 |

### 测试规模

| 层级 | 当前数量 | 说明 |
|------|---------:|------|
| 后端单元测试 | 144 个文件 / 1,848 个定义 | `tests/unit/test_*.py` 中的 `test_*` 定义 |
| 后端集成测试 | 4 个文件 / 31 个定义 | 认证、健康、PPT 大纲和统一状态恢复 |
| 前端 Vitest | 15 个文件 | `src/**/*.test.js` |
| 浏览器 E2E | 77 个 spec / 433 个直接定义 | `tests/e2e/*.spec.js` 中的直接 `test(...)` 定义 |

参数化、动态生成、skip、收集失败和运行依赖会影响实际执行数量。已记录的测试结果及适用范围见[测试指南](testing/TESTING.md)。

### 技术栈

| 层级 | 技术 | 当前用途 |
|------|------|----------|
| 后端 | FastAPI + Python 3.11 | 异步 API、Agent 与业务服务 |
| 前端 | Vue 3 + Vite 5 + Pinia + Element Plus | 单页应用与响应式 Agent 工作台 |
| 数据 | SQLAlchemy 2.0 + SQLite + Alembic | 业务、统一状态与迁移 |
| 缓存与任务 | Redis + Celery + APScheduler | Key、缓存、任务队列和定时任务 |
| 流式通信 | SSE + WebSocket | Agent 事件、任务进度和系统状态 |
| 测试 | pytest + Vitest + Playwright + VS Code Extension Host | 后端、前端、浏览器和扩展验证 |
| 部署 | Docker Compose + Nginx | API、Worker、Redis 和前端入口 |

## 最新能力状态

| 能力 | 当前状态 |
|------|----------|
| 统一状态 | `sessions`、`messages`、`tasks`、`task_events`、`checkpoints` 和 `artifacts` 形成统一持久化层；legacy 业务通过适配器、双写核对和模块级切换渐进迁移 |
| Agent 编排 | Web 主入口继续运行成熟的 legacy Orchestrator，并通过单节点 StateGraph wrapper 保存 checkpoint、事件和产物；细粒度多节点图处于渐进接入阶段 |
| 模型上下文 | 按 Agent 会话持久化 schema version 1 的角色分配、调用统计和最多 50 条 fallback history；独立 revision 支持乐观并发与恢复，凭据不进入上下文 |
| GirlAI | 5 个预设角色与用户自定义角色支持对话、历史、搜索、导出和偏好；legacy 历史与统一 session/message 同事务维护，归档摘要进入 checkpoint |
| PPT 大纲与质量 | 大纲支持版本化编辑和批准门禁；生成按 `planning -> assets -> rendering -> rule_qa -> reflow -> vision_qa -> completed` 编排，提供质量报告、最多 2 次自动重排和单页重生成 |
| Mobile Agent | 与 Web Agent 共用 `/agent`、API 和 Store；768px 以下提供单列布局、会话/文件抽屉、遮罩、焦点管理和移动工具栏 |
| VS Code Agent Host | 协议版本 1 支持 workspace、file、terminal、diagnostics、validation 和 skill runtime，包含握手、动作队列、审批策略、Skill 同步及 pause/resume/cancel |
| 任务恢复 | SQL Task/Event 为持久化事实源，支持事件重放、worker lease 心跳、retry、recover、取消检查和 checkpoint 恢复 |

## API 基线

| 版本 | 挂载 Router | HTTP | WebSocket | 合计 | 主要职责 |
|------|------------:|-----:|----------:|-----:|----------|
| v1 | 20 | 199 | 2 | 201 | 认证、聊天、Agent、PPT、任务、GirlAI、AI Cloud 和模型浏览 |
| v2 | 8 | 72 | 2 | 74 | 用户与系统管理、Nginx、模型配置、MCP 和守护能力 |
| 总计 | 28 | 271 | 4 | 275 | 当前实际可达业务路由 |

HTTP schema 以运行时 `/api/openapi.json` 为准；兼容隐藏端点和 WebSocket 路径需结合 [API 文档](api/API-DOCUMENTATION.md) 与源码核对。

## 快速开始

```bash
# 启动后端
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 启动前端
cd /workspace/src
npm run dev
```

开发环境访问前端 `http://localhost:3000`，后端健康检查位于 `http://localhost:8000/api/v1/health`，Swagger UI 位于 `http://localhost:8000/api/docs`。数据库初始化、迁移和完整验证命令见[快速开始](guides/GETTING-STARTED.md)。

---

最后更新：2026-09-03
