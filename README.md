# CodingMatrix

**AI 驱动的全栈代码生成与开发平台**

> 版本：v5.10.0 | 技术栈：FastAPI (Python 3.11) + Vue 3 + SQLite + Playwright

## 🚀 快速开始

```bash
# 启动后端 (端口 8000，包含前端 dist)
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 访问前端
open http://localhost:8000
```

## 📋 运行测试

```bash
# E2E 冒烟测试 (推荐，18 秒快速验证)
npx playwright test tests/e2e/smoke-test-simple.spec.js --reporter=list

# 所有 E2E 测试
npx playwright test tests/e2e/

# 单元测试
pytest tests/unit/ -v

# 集成测试
pytest tests/integration/ -v
```

**当前测试状态**: ✅ E2E 冒烟测试 5/5 通过 (100%)

## 📚 文档导航

### 入门
- [快速开始](docs/guides/GETTING-STARTED.md)
- [多供应商配置](docs/guides/MULTI-PROVIDER-SETUP.md)

### 架构
- [系统架构](docs/architecture/ARCHITECTURE.md)
- [模块说明](docs/architecture/MODULES.md)
- [模型系统](docs/architecture/MODELS.md)

### API
- [API 文档](docs/api/API-DOCUMENTATION.md)

### 功能
- [Agent 系统](docs/features/AGENT.md)
- [AI 云管理](docs/features/AICLOUD.md)
- [SSE 优化](docs/features/SSE-DISPLAY-OPTIMIZATION.md)

### 测试
- [测试文档](docs/testing/TESTING.md)
- [E2E 测试报告](tests/e2e/E2E-TEST-REPORT.md)

### 部署
- [生产部署](docs/guides/PRODUCTION.md)
- [服务管理](docs/guides/SERVICES.md)

## 🏗️ 项目结构

| 目录 | 说明 | 代码量 |
|------|------|--------|
| `app/` | 后端 (FastAPI) | ~50K LOC |
| `app/api/v1/` | API 路由 (19 个端点) | ~8.6K LOC |
| `app/agent/` | Agent 系统 | ~15K LOC |
| `app/utils/aicloud/` | 多供应商模型 | ~3K LOC |
| `src/` | 前端 (Vue 3) | ~162K LOC |
| `src/views/` | 页面组件 (8 个主视图) | ~120K LOC |
| `src/components/` | 组件库 (62 个) | ~42K LOC |
| `tests/` | 测试 (136 文件) | ~1100+ 测试 |
| `docs/` | 项目文档 | 50+ 文档 |

完整的目录职责、入口关系和配置边界见 [`docs/PROJECT-STRUCTURE.md`](docs/PROJECT-STRUCTURE.md)。

手工接口流程测试位于 `tests/manual/`，通过 `TEST_ADMIN_PASSWORD` 等环境变量提供测试凭据。

## ✨ 核心特性

| 特性 | 状态 | 说明 |
|------|------|------|
| **多供应商模型** | ✅ 完成 | 7 个供应商、故障转移 |
| **AI 代码生成** | ✅ 完成 | 流式输出、断点续传 |
| **AI 项目生成** | ✅ 完成 | 脚手架、增量修改 |
| **图像生成** | ✅ 完成 | Kolors 模型、多模式 |
| **PPT 生成** | ✅ 完成 | 异步任务、预览下载 |
| **虚拟 AI 对话** | ✅ 完成 | GirlAi 多角色 |
| **工作流编排** | ✅ 完成 | 可视化、历史记录 |
| **视觉分析** | ✅ 完成 | OCR、图像理解 |
| **用户管理** | ✅ 完成 | 三级权限、RSA 加密 |
| **系统监控** | ✅ 完成 | 健康检查、熔断限流 |

## 🎯 测试覆盖率

| 类型 | 文件数 | 测试用例 | 通过率 |
|------|--------|----------|--------|
| 单元测试 | 50+ | 600+ | ~95% |
| 集成测试 | 30+ | 250+ | ~90% |
| **E2E 测试** | **56** | **250+** | **100% (冒烟)** |
| **总计** | **136** | **1100+** | **~94%** |

## 🛠️ 开发指南

### 环境要求
- Python 3.11+
- Node.js 18+
- SQLite 3.35+
- Docker (可选)

### 配置环境变量

```bash
# .env 最小配置
SILICONFLOW_API_KEY=your-key
SECRET_KEY=your-secret
```

### 后端端口

✅ **重要**: 后端的 `dist/` 目录包含前端构建产物，统一在 **8000 端口** 提供服务

```bash
# 正确启动
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 访问前端
http://localhost:8000

# API 端点
http://localhost:8000/api/v1/health
```

## 📊 关键指标

| 指标 | 数值 |
|------|------|
| 后端代码 | ~50,000 LOC |
| 前端代码 | ~162,000 LOC |
| API 端点 | 26 (v1=19, v2=7) |
| Agent 工具 | 21 |
| 测试文件 | 136 |
| 测试用例 | 1100+ |
| 文档数量 | 50+ |

## 🔗 相关资源

- [完整文档索引](docs/README.md)
- [测试报告](tests/e2e/E2E-TEST-REPORT.md)
- [技术债务跟踪](docs/TECH-DEBT.md)
- [版本历史](docs/versions/)

---

**许可证**: MIT | **最后更新**: 2026-05-29
