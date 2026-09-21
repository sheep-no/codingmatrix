# CodingMatrix

**AI 驱动的全栈代码生成与开发平台**

> 版本：见 [CHANGELOG.md](CHANGELOG.md) | 技术栈：FastAPI (Python 3.11) + Vue 3 + SQLite + Flutter (Riverpod) + Playwright

当前项目基线（代码规模、能力状态、API 口径）以 [`docs/README.md`](docs/README.md) 为单一来源。

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
- [项目结构](docs/PROJECT-STRUCTURE.md)
- [根目录文件说明](docs/ROOT-FILES.md)

### API
- [API 文档](docs/api/API-DOCUMENTATION.md)

### 功能
- [Agent 系统](docs/features/AGENT.md)
- [Flutter 客户端](docs/features/FLUTTER-CLIENT.md)
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
| `app/` | 后端 (FastAPI) | 423 个 Python 文件 / ~118K 行 |
| `app/api/v1/` | v1 API 路由 | 20 个挂载 Router / 201 条路由 |
| `app/agent/` | Agent 系统 | ~15K LOC |
| `app/utils/aicloud/` | 多供应商模型 | ~3K LOC |
| `src/` | 前端 (Vue 3) | ~71K 行源码（不含 `src/node_modules`） |
| `src/views/` | 页面组件 | 9 个主视图 |
| `src/components/` | 组件库 | 54 个组件 |
| `flutter_client/` | Flutter Agent 客户端 | 70 个 Dart 文件 / 12,217 行 |
| `vscode-extension/` | VS Code 本地验证扩展 | 协议包 + E2E |
| `tests/` | 测试 | 后端单元 144 文件 + 浏览器 E2E 77 spec |
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
| **Flutter 客户端** | ✅ 完成 | 18 个页面、能力注册表分组导航、生成开关按账号保持 |
| **VS Code 扩展** | ✅ 完成 | 本地验证协议包、动作队列与 Skill 同步 |
| **会话恢复** | ✅ 完成 | SSE 断线续跑、`reconnectable` / `is_resume` 挂回 |

## 🎯 测试规模

| 类型 | 数量 | 位置 |
|------|------|------|
| 后端单元 | 144 文件 / 1,848 用例 | `tests/unit/` |
| 后端集成 | 4 文件 / 31 用例 | `tests/integration/` |
| 前端 Vitest | 15 文件 | `src/**/*.test.js` |
| 浏览器 E2E | 77 spec / 433 用例 | `tests/e2e/` |
| Flutter | 32 文件 | `flutter_client/test/` |

数量为静态定义口径，实际执行受参数化、skip 与运行依赖影响；运行结果以 [测试指南](docs/testing/TESTING.md) 为准。

## 🛠️ 开发指南

### 环境要求
- Python 3.11+
- Node.js 18+
- SQLite 3.35+
- Flutter SDK（构建 Flutter 客户端时需要，Dart SDK ^3.9.2）
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
| 后端代码 | 423 文件 / ~118K 行 |
| 前端源码 | ~71K 行（不含 `src/node_modules`） |
| Flutter 客户端 | 70 文件 / ~12K 行 / 18 个页面 |
| API 业务路由 | 275 条（28 个挂载 Router） |
| ORM 表 | 34 |
| 测试文件 | 后端单元 144 / 浏览器 E2E 77 spec / Flutter 33 |
| 文档数量 | 50+ |

## 🔗 相关资源

- [完整文档索引](docs/README.md)
- [测试报告](tests/e2e/E2E-TEST-REPORT.md)
- [技术债务跟踪](docs/TECH-DEBT.md)
- [版本历史](docs/versions/)

---

**许可证**: MIT | **最后更新**: 2026-09-19
