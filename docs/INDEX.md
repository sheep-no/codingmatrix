# CodingMatrix 文档索引

> 最后更新：2026-05-22 | 版本：v5.4.0（多供应商模型支持）

## 快速导航

### 入门
- [README.md](../README.md) - 项目概述
- [guides/GETTING-STARTED.md](guides/GETTING-STARTED.md) - 开发者指南（含 Windows 快速启动）
- [PROJECT_STATUS.md](PROJECT_STATUS.md) - 项目状态
- [guides/MULTI_PROVIDER_SETUP.md](guides/MULTI_PROVIDER_SETUP.md) - **多供应商模型配置指南** ⭐
- [versions/MULTI_PROVIDER_MIGRATION_v5.4.md](versions/MULTI_PROVIDER_MIGRATION_v5.4.md) - v5.4.0 迁移报告
- [versions/CHANGELOG-v5.1.2.md](versions/CHANGELOG-v5.1.2.md) - 版本历史

### 架构与设计
- [architecture/ARCHITECTURE.md](architecture/ARCHITECTURE.md) - 系统架构（v5.4.0）
- [architecture/MODULES.md](architecture/MODULES.md) - 模块说明 + 项目结构
- [architecture/MODELS.md](architecture/MODELS.md) - 数据模型 + **多供应商 LLM 适配器**
- [BUILTIN_MODELS.md](BUILTIN_MODELS.md) - **内置模型清单**（10个模型 + 多供应商支持）

### API 文档
- [API-COMPLETE.md](API-COMPLETE.md) - **完整 API 文档**（v5.2.2）
- [api/API-VERSIONS.md](api/API-VERSIONS.md) - API 版本管理

### Agent 系统
- [AGENT-COMPLETE-REPORT.md](AGENT-COMPLETE-REPORT.md) - **Agent 系统综合报告**（重设计 + 工具 + 修复）
- [features/agent.md](features/agent.md) - Agent 系统架构

### 功能模块
- [features/aicloud.md](features/aicloud.md) - AI 云管理
- [features/SSE-DISPLAY-OPTIMIZATION.md](features/SSE-DISPLAY-OPTIMIZATION.md) - v4.8.1 SSE 展示优化

### 部署与运维
- [guides/PRODUCTION.md](guides/PRODUCTION.md) - 生产部署指南（含 Docker Compose）
- [SERVICES.md](SERVICES.md) - 服务管理文档

### 安全
- [security/SECURITY-OVERVIEW.md](security/SECURITY-OVERVIEW.md) - 安全架构概览
- [security/ENCRYPTED_LOGIN.md](security/ENCRYPTED_LOGIN.md) - RSA 加密登录

### 可观测性
- [observability/TRACING.md](observability/TRACING.md) - OpenTelemetry 分布式追踪

### 测试
- [testing/TESTING.md](testing/TESTING.md) - 测试文档

### 提示词
- [prompts/PROMPTS.md](prompts/PROMPTS.md) - AI 提示词 (22 个)

### Skills
- [skills/HISTORY.md](skills/HISTORY.md) - Skills 迁移与更新记录

### 规格设计
- [specs/admin-resource-control/](specs/admin-resource-control/) - 管理员资源控制
- [specs/agent-git-operations/](specs/agent-git-operations/) - Agent Git 操作
- [specs/aicloud/](specs/aicloud/) - AI 云规格
- [specs/ephemeral-workflow/](specs/ephemeral-workflow/) - 临时工作流规格
- [specs/production-ready/](specs/production-ready/) - 生产就绪规格

---

## 文档结构

```
docs/
├── INDEX.md                     # 文档索引（本文件）
├── README.md                    # 项目概述
├── PROJECT_STATUS.md            # 项目状态
├── COMPREHENSIVE_FIXES_v5.2.md # v5.2.x 综合修复报告
├── API-COMPLETE.md              # 完整 API 文档
├── AGENT-COMPLETE-REPORT.md     # Agent 系统综合报告
├── versions/                    # 版本记录
│   ├── CHANGELOG-v5.1.2.md      # v5.1.2 前端修复
│   ├── CHANGELOG-v5.1.0.md      # v5.1.0 需求理解增强
│   ├── CHANGELOG-v5.0.0.md      # v5.0.0 需求联想增强
│   └── ...
├── architecture/                # 架构设计
├── api/                         # API 文档
├── features/                    # 功能模块
├── guides/                      # 开发指南
├── security/                    # 安全文档
├── observability/               # 可观测性
├── testing/                     # 测试文档
├── prompts/                     # AI 提示词
└── specs/                       # 规格设计
```
