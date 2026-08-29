# 项目结构说明

> 最后更新：2026-08-29

本文档描述当前仓库的目录职责、主要入口和配置边界。目录调整遵循“运行代码、测试代码、项目文档、运行数据分区”的原则。

## 顶层结构

```text
workspace/
├── app/                 # FastAPI 后端、Agent 引擎、服务和数据访问
├── src/                 # Vue 3 + Vite 前端
├── tests/               # 自动化测试和手工接口流程测试
│   ├── unit/            # 后端单元测试
│   ├── integration/     # 后端集成测试
│   ├── e2e/             # Playwright 端到端测试
│   ├── performance/     # 性能测试
│   └── manual/          # 需要运行服务的手工流程脚本
├── configs/             # Nginx、测试、依赖和业务配置模板
├── data/                # 模型配置、运行数据、知识库和备份
├── migrations/          # 数据库迁移脚本
├── docs/                # 面向开发者和运维人员的项目文档
│   ├── PROJECT-STRUCTURE.md # 项目结构总览
│   └── ROOT-FILES.md     # 根目录文件分类
├── scripts/             # 启动、停止、迁移、测试和验证脚本
├── examples/            # 示例代码
├── .monkeycode/         # 项目规格、协作记忆和平台元数据
├── .claude/             # Agent skill 与提示词资源
├── Dockerfile           # 镜像构建入口
├── docker-compose.yml   # 本地 Compose 编排
└── docker-compose.prod.yml # 生产 Compose 编排
```

## 代码分层

### 后端 `app/`

- `app/main.py`：FastAPI 应用创建、生命周期和路由挂载入口。
- `app/api/v1/`：用户侧和业务侧 v1 API。
- `app/api/v2/`：管理侧和配置侧 v2 API。
- `app/api/v1/ai_agent/`：Agent 编排相关的聚合路由、端点和请求模型。
- `app/agent/`：Agent 执行器、ReAct 引擎、状态、工具、模型路由和验证模块。
- `app/services/`：配置管理、供应商健康检查、任务和业务服务。
- `app/models/`：SQLAlchemy 数据模型。
- `app/schema/`：API 请求和响应 Schema。
- `app/core/`：应用配置、日志、文件校验和生命周期基础设施。
- `app/utils/`：文件操作、模型适配、缓存、加密和通用工具。

### 前端 `src/`

- `src/main.js`、`src/App.vue`：前端启动与应用外壳。
- `src/router/`：路由和访问控制。
- `src/views/`：页面级组件。
- `src/components/`：可复用组件；领域组件按 `agent/`、`settings/` 分组。
- `src/composables/`：Agent 会话、生成、文件、流式传输和工作区逻辑。
- `src/stores/`：Pinia 全局状态。
- `src/utils/api/`：按业务领域划分的 API 客户端。
- `src/vite.config.js`：Vite 开发服务器、构建和 API 代理配置。

## 测试结构

- `tests/unit/`：后端模块级测试，运行配置位于 `configs/pytest.ini`。
- `tests/integration/`：需要多个应用组件协作的测试。
- `tests/e2e/`：浏览器端到端测试，根目录 `playwright.config.js` 是默认兼容入口。
- `tests/performance/`：性能和资源相关测试。
- `tests/manual/`：手工调用真实服务的流程脚本。脚本通过 `TEST_BASE_URL`、`TEST_ADMIN_EMAIL`、`TEST_ADMIN_PASSWORD` 和 `TEST_API_KEY` 读取运行参数。
- `examples/`：独立示例代码，不参与应用启动和自动化测试。

## 配置与数据边界

### `configs/`

存放可随代码版本控制的基础配置：

- `nginx.conf` 和 `nginx-upstream-*.conf`：反向代理配置。
- `alembic.ini`：数据库迁移配置。
- `pytest.ini`、`requirements*.txt`：测试和 Python 依赖配置。
- `playwright.config.js`：多浏览器测试配置。
- `ppt/`、`domain_templates/`：业务模板。

### `data/`

存放运行时配置和持久化数据：

- `unified_model_config.yaml`：管理面统一模型配置。
- `agent_model_config.yaml`：Agent 运行时模型配置。
- `custom_skills/`：用户自定义 Skill 内容及元数据。
- `knowledge/`：AI Cloud 知识库文件。
- `backups/`、`learning_data/`：备份和学习数据；仓库根目录 `metrics/` 保存指标输出。
- `*.json.legacy`：配置格式迁移时保留的历史副本。

敏感凭据通过环境变量注入，测试脚本和文档使用占位符或环境变量名。

## 运行入口

| 场景 | 入口 | 说明 |
|------|------|------|
| 开发启动 | `scripts/dev.sh` | 启动后端开发服务 |
| 完整启动 | `scripts/start.sh` | 按脚本约定启动前后端及依赖服务 |
| 仅后端 | `scripts/start-backend.sh` | 单独启动后端 |
| 数据库迁移 | `scripts/migrate.sh` | 执行迁移到最新版本 |
| 后端测试 | `scripts/test.sh` | 运行测试套件 |
| 容器启动 | `docker-compose.yml` | 本地容器编排 |
| 生产容器 | `docker-compose.prod.yml` | 生产服务编排 |

## 整理约定

1. 新的后端代码进入 `app/` 对应领域目录。
2. 新的前端页面进入 `src/views/`，可复用 UI 进入 `src/components/`。
3. 新的自动化测试按测试类型进入 `tests/unit/`、`tests/integration/`、`tests/e2e/` 或 `tests/performance/`。
4. 需要真实服务和人工凭据的流程测试进入 `tests/manual/`。
5. 新项目文档进入 `docs/` 下的对应分类；历史记录继续放在 `docs/evolution/` 或 `docs/versions/`。
6. 一次性脚本和已停用脚本保留在 `scripts/_archive/`，避免与活跃入口混淆。
7. 根目录仅保留应用入口、构建编排、环境模板和 Git 项目元文件。
