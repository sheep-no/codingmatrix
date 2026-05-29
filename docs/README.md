# CodingMatrix 文档中心

> 最后更新：2026-05-29 | 版本：v5.10.0

## 快速导航

### 入门
- [快速开始](guides/GETTING-STARTED.md) - 环境配置、快速启动
- [多供应商配置](guides/MULTI-PROVIDER-SETUP.md) - 7 个 LLM 供应商配置
- [API Key 指南](guides/API-KEY-GUIDE.md) - API Key 管理和使用

### 架构
- [系统架构](architecture/ARCHITECTURE.md) - 完整架构设计
- [模块说明](architecture/MODULES.md) - 代码结构、职责划分
- [模型系统](architecture/MODELS.md) - 多供应商 LLM 适配器
- [API 职责矩阵](architecture/API-RESPONSIBILITY-MATRIX.md) - v1/v2 路由职责

### API
- [API 文档](api/API-DOCUMENTATION.md) - 180+ 个端点完整文档
- [API 版本管理](api/API-VERSIONS.md) - 版本策略和迁移指南

### 功能模块
- [Agent 系统](features/AGENT.md) - 多角色协作、项目生成
- [AI 云管理](features/AICLOUD.md) - 模型切换、故障转移
- [工作流引擎](features/WORKFLOW.md) - DAG 编排、9 种节点类型
- [免费模型管理](features/MODEL-MANAGER.md) - 内置模型查看、切换
- [动态供应商](features/DYNAMIC-PROVIDERS.md) - 自定义 API 接入
- [Web 搜索增强](features/WEB-SEARCH-ENHANCEMENTS.md) - 查询优化、结果去重
- [多语言依赖解析](features/MULTI-LANGUAGE-DEPENDENCY-PARSER.md) - 14 种语言依赖分析
- [SSE 展示优化](features/SSE-DISPLAY-OPTIMIZATION.md) - 流式响应展示
- [项目介绍](features/PROJECT-INTRODUCTION.md) - 平台功能总览

### 部署运维
- [生产部署](guides/PRODUCTION.md) - Docker Compose、服务管理
- [服务管理](guides/SERVICES.md) - 服务启停、健康检查

### 安全
- [安全架构](security/SECURITY-OVERVIEW.md) - 安全概览
- [加密登录](security/ENCRYPTED-LOGIN.md) - RSA 加密登录
- [CSRF 防护](security/CSRF-IMPLEMENTATION.md) - CSRF 实现
- [权限规范](security/PERMISSION-SPEC.md) - RBAC 权限模型

### 其他
- [分布式追踪](observability/TRACING.md) - OpenTelemetry
- [AI 提示词](prompts/PROMPTS.md) - 22 个提示词模板
- [Skills](skills/HISTORY.md) - Skills 历史和列表
- [技术债务](TECH-DEBT.md) - 技术债务跟踪

---

## 项目概览

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | FastAPI + Python 3.11 | 异步 Web 框架 |
| 数据库 | SQLAlchemy + SQLite | 异步 ORM |
| 缓存 | Redis | 会话、API Key 存储 |
| 任务队列 | Celery + APScheduler | 异步任务 + 定时任务 |
| 前端 | Vue 3 + Vite + Pinia | 响应式 SPA |
| 测试 | Playwright + pytest | E2E + 单元测试 |
| 部署 | Docker + Nginx | 容器化部署 |

### 功能模块

| 模块 | 端点 | 功能 |
|------|------|------|
| Agent 系统 | `/api/v1/agent/*` | 项目生成、代码审查、快照管理 |
| AI 代码 | `/api/v1/code` | 代码生成、流式输出 |
| PPT 生成 | `/api/v1/pptx/*` | 异步任务、多格式输出 |
| 图像生成 | `/api/v1/kolors/*` | 文生图、图生图 |
| AI Cloud | `/api/v1/aicloud/*` | 沙箱执行、审查队列 |
| 文件管理 | `/api/v1/files/*` | 分片上传、去重、解析缓存 |
| 工作流 | `/api/v1/workflow/*` | DAG 编排、9 种节点、重试机制 |
| 免费模型 | `/api/v1/models` | 内置模型查看、切换 |
| 用户管理 | `/api/v2/Controller/*` | CRUD、权限管理 |
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
│   ├── ARCHITECTURE.md          # 系统架构
│   ├── MODULES.md               # 模块说明
│   ├── MODELS.md                # 模型系统
│   └── API-RESPONSIBILITY-MATRIX.md
├── api/                         # API 文档
│   ├── API-DOCUMENTATION.md     # API 完整文档
│   └── API-VERSIONS.md          # API 版本管理
├── features/                    # 功能模块
│   ├── AGENT.md                 # Agent 系统
│   ├── AICLOUD.md               # AI 云
│   ├── WORKFLOW.md              # 工作流
│   ├── MODEL-MANAGER.md         # 免费模型管理
│   ├── DYNAMIC-PROVIDERS.md     # 动态供应商
│   └── ...                      # 其他功能文档
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
└── specs/                       # 规格设计
```

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| v5.10.0 | 2026-05-27 | 工作流节点扩展（9种） + 重试机制 + 条件分支 |
| v5.9.0 | 2026-05-26 | API Key 全局化 + Token 统计 |
| v5.8.1 | 2026-05-23 | KV Cache 优化 + 多角度审查系统 |

详细版本历史见 [versions/](../versions/) 目录

---

最后更新：2026-05-29
