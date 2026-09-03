# 项目结构说明

> 最后核对：2026-09-03

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
├── vscode-extension/    # VS Code Agent Host、工作台和本地验证扩展
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
- `app/agent/state/`：可序列化 `State`、`StateDelta`、reducer、checkpoint 和 StateGraph runtime。
- `app/agent/nodes/`：规格、依赖图、拓扑和验证节点。
- `app/agent/adapters/`：legacy Agent、事件、会话、Spec-first 和语言适配器。
- `app/services/`：配置、供应商、统一状态、业务适配、核对、读切换、保留策略、PPT 编排和 worker recovery 服务。
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

### 统一状态与服务层

- `app/models/unified_state.py`：`Session`、`Message`、`TaskEvent`、`Checkpoint`、`Artifact`、兼容映射、保留记录和核对记录。
- `app/services/unified_state_service.py`：统一资源写入基础服务。
- `app/services/{aicloud,girlai,agent,workflow}_state_adapter.py`：四个业务域的 legacy 到统一状态适配。
- `app/services/reconciliation_service.py`、`state_cutover_service.py`：双写差异核对、模块级读切换、灰度和回滚。
- `app/services/state_migration_service.py`：兼容映射与归档、清理、重试生命周期。
- `app/services/task_{state,event,checkpoint}_service.py`、`artifact_service.py`：任务状态、事件、checkpoint 和产物服务。
- `app/services/worker_recovery_service.py`：过期 lease 扫描与重投递。

当前生产入口通过单节点 legacy wrapper 接入 StateGraph。State 契约、checkpoint、本地验证等待与恢复已经实现；完整 Spec-first、RAG、依赖图、拓扑和验证多阶段主链仍在渐进迁移。

### PPT 语义渲染

- `app/schema/ppt_outline.py`：版本化大纲、页面语义和质量请求契约。
- `app/models/ppt_state.py`、`app/services/ppt_state_service.py`：大纲版本、批准快照和质量报告持久化。
- `app/utils/pptx/semantic_planner.py`：页面类型、叙事角色、布局候选和容量预算规划。
- `app/utils/pptx/semantic_renderer.py`：页面类型归一与渲染元数据。
- `app/utils/pptx/design_tokens.py`、`templates/`：任务级设计令牌和模板解析。
- `app/services/ppt_generation_orchestrator.py`、`ppt_quality_orchestrator.py`：`planning -> assets -> rendering -> rule_qa -> reflow -> vision_qa -> completed` 阶段与质量流水线。
- `app/tasks/ppt_tasks.py`：Celery `ppt` 队列任务。

PPTX 渲染优先消费结构化 `content_blocks`，兼容旧 `content` 与 `bullets`。五类叙事角色和九套主题进入独立页面构图，前端 `PPTGenerate.vue` 与 `PPTPreview.vue` 提供大纲审阅、批准、质量报告和单页重生成流程。

### VS Code Agent Host

- `vscode-extension/src/extension.ts`：扩展激活、命令注册和组件组装。
- `agent-host.ts`、`protocol.ts`、`connection.ts`：Host 会话、版本化 Envelope、握手和云端通信。
- `agent-host-runtime.ts`、`tool-dispatcher.ts`、`approval-bridge.ts`：动作运行、能力分发和审批门禁。
- `workspace-authorization.ts`、`validation-runner.ts`：多工作区授权、参数数组命令、`shell=false`、超时和取消。
- `result-sanitizer.ts`、`result-store.ts`：结果脱敏、离线持久化与幂等回传。
- `agent-workbench.ts`、`webview-bridge.ts`、`status-view.ts`：原生工作台、Webview 消息和状态快照。
- `app/api/v1/agent_host.py`：认证握手、动作、事件、策略、Skills 和 session control 后端端点；队列与确认原子保存到 `data/agent_host_sessions/`。

## 测试结构

- `tests/unit/`：后端模块级测试；2026-09-03 静态清点为 144 个 `test_*.py`。
- `tests/integration/`：认证、健康、PPT 大纲和状态恢复共 4 个测试文件。
- `tests/e2e/`：浏览器端到端测试，根目录 `playwright.config.js` 是默认兼容入口。
- `src/**/*.test.js`：Vitest 前端单元测试，共 15 个文件，配置位于 `src/vite.config.js`。
- `vscode-extension/test/`、`vscode-extension/e2e/`：Node 原生测试和真实 Extension Host E2E。
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

### `migrations/`

- `migrations/runner.py`：运行时建表并为既有 `tasks` 表补齐统一状态字段。
- `migrations/versions/20260829_add_state_migration_tables.py`：兼容映射与保留记录。
- `migrations/versions/20260829_add_unified_task_fields.py`：统一任务 revision、stage、lease 和结果字段。
- `migrations/versions/20260829_add_state_reconciliation.py`：双写核对记录。
- `migrations/versions/20260902_add_ppt_quality_state.py`：PPT 大纲、质量报告和任务关联字段；该 revision 汇合此前多个 Alembic head。

既有数据库首次接入当前 Alembic 链时，先执行 `alembic -c configs/alembic.ini stamp 20260902_ppt_quality_state` 登记基线，再执行 `alembic -c configs/alembic.ini upgrade head` 验证；运行时迁移器继续承担本地既有库的补表和字段兼容。

敏感凭据通过环境变量注入，测试脚本和文档使用占位符或环境变量名。

## 运行入口

| 场景 | 入口 | 说明 |
|------|------|------|
| 后端开发启动 | `PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload` | 在仓库根目录执行 |
| 前端开发启动 | `npm --prefix src run dev` | Vite 监听 3000，并代理 API 到后端 8000 |
| 完整启动脚本 | `scripts/start.sh` | **当前不可用入口**：项目根定位到 `scripts/`，无参数时仅显示状态 |
| 仅后端 | `scripts/start-backend.sh` | 单独启动后端 |
| 数据库迁移脚本 | `scripts/migrate.sh` | **当前不可用入口**：未指定 `configs/alembic.ini` |
| 数据库迁移 | `alembic -c configs/alembic.ini upgrade head` | 已核验的 Alembic 入口，在仓库根目录执行 |
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
