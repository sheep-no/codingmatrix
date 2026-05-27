# CodingMatrix 文档索引

> 最后更新：2026-05-27 | 版本：v5.10.0（工作流节点扩展 + 重试机制）

## 快速导航

### 入门
- [README.md](README.md) - 项目概述
- [快速开始](guides/GETTING-STARTED.md) - 环境配置、快速启动
- [多供应商配置](guides/MULTI_PROVIDER_SETUP.md) - 7 个 LLM 供应商配置
- [测试文档](testing/TESTING.md) - 111+ 测试文件，850+ 测试用例

### 架构与设计
- [系统架构](architecture/ARCHITECTURE.md) - v5.9.0 完整架构
- [模块说明](architecture/MODULES.md) - 代码结构、职责划分
- [模型系统](architecture/MODELS.md) - 多供应商 LLM 适配器

### API 文档
- [API 文档](api/) - 25+ 个 API 端点完整文档
- [Agent API](api/AGENT-API.md) - Agent 系统 API

### Agent 系统
- [Agent 系统架构](features/agent.md) - 多角色协作、项目生成
- [Agent 工具](features/AGENT-TOOLS.md) - 19 个工具

### 功能模块
- [AI 云管理](features/aicloud.md) - 模型切换、故障转移
- [PPT 生成](features/PPT.md) - 异步任务、多格式输出
- [图像生成](features/IMAGE.md) - 文生图、图生图
- [工作流](features/WORKFLOW.md) - DAG 编排、9 种节点类型、重试机制、条件分支
- [免费模型管理](features/MODEL-MANAGER.md) - 内置模型查看、切换和管理
- [Web 搜索增强](features/WEB-SEARCH-ENHANCEMENTS.md) - 智能查询优化、结果去重、质量评分

### 测试
- [测试文档](testing/TESTING.md) - 完整测试指南
- [E2E 测试](testing/E2E.md) - Playwright 测试

### 部署与运维
- [生产部署](guides/PRODUCTION.md) - Docker Compose、服务管理
- [服务管理](SERVICES.md) - 服务启停、健康检查

### 安全
- [安全架构](security/SECURITY-OVERVIEW.md) - 安全概览
- [加密登录](security/ENCRYPTED_LOGIN.md) - RSA 加密登录
- [CSRF 防护](security/CSRF.md) - CSRF 实现
- [权限规范](PERMISSION-SPEC.md) - 权限系统设计

### 可观测性
- [分布式追踪](observability/TRACING.md) - OpenTelemetry
- [日志系统](observability/LOGGING.md) - 结构化日志

### 提示词
- [AI 提示词](prompts/PROMPTS.md) - 提示词模板

### 代码质量
- [技术债务](TECH-DEBT.md) - 技术债务跟踪

---

## 文档结构

```
docs/
├── INDEX.md                     # 文档索引 (本文件)
├── README.md                    # 项目概述
├── TECH-DEBT.md                 # 技术债务跟踪
├── PERMISSION-SPEC.md           # 权限规范
├── SERVICES.md                  # 服务架构
├── architecture/                # 架构设计
│   ├── ARCHITECTURE.md          # 系统架构
│   ├── MODULES.md               # 模块说明
│   └── MODELS.md                # 模型系统
├── api/                         # API 文档
│   ├── AGENT-API.md             # Agent API
│   └── ...
├── features/                    # 功能模块
│   ├── agent.md                 # Agent 系统
│   ├── aicloud.md               # AI 云
│   ├── PPT.md                   # PPT 生成
│   ├── IMAGE.md                 # 图像生成
│   └── WORKFLOW.md              # 工作流
├── guides/                      # 开发指南
│   ├── GETTING-STARTED.md       # 快速开始
│   ├── MULTI_PROVIDER_SETUP.md  # 多供应商配置
│   └── PRODUCTION.md            # 生产部署
├── security/                    # 安全文档
│   ├── SECURITY-OVERVIEW.md     # 安全概览
│   ├── ENCRYPTED_LOGIN.md       # 加密登录
│   └── CSRF.md                  # CSRF 防护
├── observability/               # 可观测性
│   ├── TRACING.md               # 分布式追踪
│   └── LOGGING.md               # 日志系统
├── testing/                     # 测试文档
│   └── TESTING.md               # 完整测试指南
├── prompts/                     # AI 提示词
├── skills/                      # Skills 文档
├── specs/                       # 规格设计
└── versions/                    # 版本历史
```

---

## 关键指标

| 指标 | 数值 |
|------|------|
| 后端 API | 25+ 端点 |
| Agent 系统 | 58 个文件 |
| 数据库模型 | 24 个表 |
| 前端视图 | 7 个页面 |
| 前端组件 | 44 个组件 |
| Pinia Store | 6 个状态库 |
| 测试文件 | 111+ |
| 测试用例 | 850+ |
| 文档数量 | 50+ |

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

# 集成测试
pytest tests/integration/ -v
```

---

## 版本历史

| 版本 | 日期 | 主要更新 |
|------|------|----------|
| v5.10.0 | 2026-05-27 | 工作流节点扩展（9种） + 重试机制 + 条件分支 |
| v5.9.0 | 2026-05-26 | API Key 全局化 + Token 统计 |
| v5.8.1 | 2026-05-23 | KV Cache 优化 + 多角度审查系统 |
| v5.7.0 | 2026-05-23 | 批量操作 + 审计日志 |
| v5.6.0 | 2026-05-23 | CI/CD集成 |
| v5.5.0 | 2026-05-23 | 多供应商 API Key 管理 |
| v5.4.0 | 2026-05-22 | 多供应商模型 + E2E 测试完成 |

---

## 相关资源

- [完整测试文档](testing/TESTING.md)
- [技术债务跟踪](TECH-DEBT.md)
- [权限规范](PERMISSION-SPEC.md)
- [服务架构](SERVICES.md)

---

最后更新：2026-05-27
