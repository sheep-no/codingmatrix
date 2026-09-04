# Developer Guide

## 环境

开发与测试约定使用 Python 3.11。当前 Dockerfile 使用 Python 3.10，部署前需要统一版本或明确兼容矩阵。测试依赖至少包含 `pytest`、`pytest-asyncio`、`aiofiles`、`PyJWT` 和 `apscheduler`。Redis、数据库和 FAISS 相关测试还需要对应本地服务或可选组件。

本地默认环境使用 SQLite `app.db` 和 Redis `redis://127.0.0.1:6379/0`。硅基流动配置使用 `SILICONFLOW_API_KEY` 和 `SILICONFLOW_BASE_URL`，默认地址为 `https://api.siliconflow.cn/v1`；真实 API Key 只放在本地 `.env`，使用占位符维护示例。启动时 `.env` 采用 `override=False`，已有进程环境变量优先。

前端 Vite 默认监听 3000 端口，并将 `/api/v1`、`/api/v2` 和 WebSocket 请求代理到后端 8000 端口。后端 Docker 运行时使用 8080，Nginx 对外提供 80 端口。前端构建产物输出到仓库根目录 `dist/`。

## 初始化数据库

```bash
# 补齐现有数据库表和统一状态字段
PYTHONPATH=/workspace python3 -c 'import asyncio; from migrations.runner import run_async_migrations; asyncio.run(run_async_migrations())'

# 使用 Alembic 配置检查版本
alembic -c configs/alembic.ini current
```

项目运行时迁移器适用于已有 SQLite 数据库，会创建缺失表并补齐 `tasks` 字段。历史 Alembic 目录存在多个 head，迁移链整理完成前以运行时迁移器作为本地初始化入口。

## 启动服务

```bash
# 启动后端
PYTHONPATH=/workspace python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 启动前端
cd src
npm run dev

# 启动 PPT worker
cd /workspace
PYTHONPATH=/workspace REDIS_URL=redis://127.0.0.1:6379/0 celery -A app.celery_app worker --loglevel=info --concurrency=1 --pool=solo --queues=ppt
```

配置 `PPT_USE_CELERY=true` 后，PPT 异步生成入口提交到 `ppt` 队列。

统一状态保留任务每天执行一次：默认资源在 7 天后进入归档窗口，归档后 30 天进入外部 artifact 清理窗口。活动任务、有效会话和恢复中的任务会阻止处理；外部存储清理失败会保留 `retryable` 记录并等待下次调度重试。

读切换前调用 `build_reconciliation_report` 检查六类统一资源覆盖和开放差异，再使用 `ReadCutoverController.enable` 按模块顺序推进；发现一致性或权限异常时调用 `rollback` 恢复该模块的 legacy 读源。

四模块批量切换使用 `activate_modules_in_order`，通过 `rollout_percentage` 控制用户 cohort 比例。灰度验证应按 AICloud、GirlAI、Agent、Workflow 顺序执行，每个模块完成核对后再进入下一个模块。

历史 P4.4 验收记录：状态迁移、核对、切换、worker recovery、SQL replay、快照恢复和跨用户所有权测试为 `16 passed`；认证、核心导航、Workflow、PPT 浏览器验收为 `34 passed`；API 路由契约测试为 `3 passed`、`2 skipped`。该批次记录用于追溯，实时结果以当前命令执行输出为准。浏览器测试使用系统 Chromium；供应商 401 响应类型错误和过时系统信息端点引用已修复。

API 路由契约 E2E 已完成静态路径校准，当前结果为 `3 passed`、`2 skipped`。认证 E2E 使用 `TEST_ADMIN_EMAIL` 和 `TEST_ADMIN_PASSWORD`，默认测试邮箱为 `admin_test@example.com`；固定账号未设置密码时认证用例会明确跳过。完整浏览器验收已通过一次性本地测试账号完成。

GirlAI 情绪与意图增强专项回归覆盖结构化回合、分类阈值、关怀策略、记忆、上下文、幂等预留、过期租约接管、owner fencing、首次会话唯一性、失败事件、统一状态和数据库服务，当前结果为 `81 passed`。Alembic head 为 `20260904_girlai_turn_fencing`。真实 HTTP 已验证主模型调用、分类 fallback、状态恢复和同一 `turn_id` 幂等回放成功；分类 reasoning 参数兼容、内部推理文本过滤和降级标记修复已通过定向单元测试，更新后真实供应商复验需要重新向服务进程注入临时凭据。

## 验证命令

```bash
# 运行完整单元测试
python3 -m pytest tests/unit -q

# 运行 StateGraph 和入口迁移相关测试
python3 -m pytest tests/unit/test_workflow_registry.py tests/unit/test_agent_state.py tests/unit/test_state_checkpoint.py tests/unit/test_retrieval_service.py tests/unit/test_agent_adapters.py tests/unit/test_state_graph_runtime.py tests/unit/test_state_graph_nodes.py tests/unit/test_validation_nodes.py tests/unit/test_local_validation_adapter.py -q

# 运行 AICloud 和 GirlAI 历史迁移回归测试
python3 -m pytest tests/unit/test_aicloud_state_adapter.py tests/unit/test_girlai_state_adapter.py -q

# 运行 Agent 模型上下文持久化回归测试
python3 -m pytest tests/unit/test_model_context_service.py tests/unit/test_agent_state_persistence.py tests/unit/test_workflow_state_persistence_hook.py -q

# 运行统一状态 Redis、SQL replay 和快照恢复集成测试
python3 -m pytest tests/integration/test_state_recovery.py -q

# 执行语法编译检查
python3 -m compileall -q app/agent app/api

# 构建并测试 VS Code 插件协议包
npm --prefix vscode-extension test

# 在真实 VS Code Extension Host 中运行插件 E2E
npm --prefix vscode-extension run e2e
```

## 最近验收结果（2026-09-02）

- PPT 专项单元测试：`141 passed`。
- `elegant` 董事会备忘录主题统一生成测试：`24 passed`；6 页 PPTX、PDF 和 PNG 样稿生成成功，证据页与路线页二轮视觉评分为 `9.0/10` 和 `8.5/10`。
- 前端全量测试：`36 passed`；PPT 工作流测试覆盖大纲修改、新增、重排、删除、批准禁用，以及逐页质量分、问题、修复动作和人工复核标记展示；前端生产构建成功。
- VS Code 扩展构建成功，Node 原生测试：`62 passed`。
- VS Code Extension Development Host E2E 成功，覆盖扩展发现、激活、兼容性校验、Agent Workbench 命令和工作区加载。
- 已生成 VSIX：`vscode-extension/codingmatrix-local-validation-0.1.0.vsix`。
- 真实 Agent/PPT 验收已覆盖 HTML 产物生成、PPTX HTTP 下载、WebSocket 进度事件和错误格式请求返回 404。

VS Code 扩展打包仍会提示缺少 `repository`、`LICENSE` 和 `.vscodeignore` 元数据。这些提示不影响当前构建与测试，正式发布前应补齐。

## 前端开发

```bash
# 进入前端目录
cd /workspace/src

# 启动开发服务
npm run dev

# 单次运行测试
npm run test:run

# 执行 lint
npm run lint

# 构建生产资源
NODE_OPTIONS=--max-old-space-size=1800 npm run build
```

根目录的 `npm run test:e2e` 用于 Playwright；前端 `dev`、`build`、`lint` 和 Vitest 命令均位于 `src/package.json`。

历史云端验证记录为：排除 Redis、数据库和 FAISS 外部条件的单元测试 1605 passed、2 skipped。当前本地环境已安装 FAISS 并启动 Redis，后端 unit/integration 完整回归结果为 `1784 passed, 2 skipped`；该结果覆盖单元测试与本地基础依赖，生产入口和本地插件验证闭环仍需独立验收。

## StateGraph 开发约定

- 节点只读取快照并返回 StateDelta。
- 文件状态使用路径、hash、摘要和诊断字段。
- 云端状态不能把本地构建、依赖安装或 E2E 标记为完成。
- legacy endpoint 迁移保留原响应和事件结构，便于渐进式回归。
- 修改后执行 `git diff --check` 和相关测试。
- GirlAI 相关修改后执行 `python3 -m pytest tests/unit/test_girlai_refactor.py tests/unit/test_girlai_state_adapter.py tests/unit/test_database_services.py -q`，并在 `/workspace/src` 执行 `npm run test:run -- utils/api/girl.test.js`。
- GirlAI 结构化伙伴契约修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_refactor.py tests/unit/test_girlai_state_adapter.py -q`。
- GirlAI 伙伴上下文和模型选择修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_companion_model.py -q`。
- GirlAI 伙伴 API 修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_api.py tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_companion_model.py tests/unit/test_girlai_refactor.py tests/unit/test_girlai_state_adapter.py -q`。
- GirlAI 伙伴记忆修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_memory.py tests/unit/test_girlai_companion_api.py tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_companion_model.py tests/unit/test_girlai_refactor.py tests/unit/test_girlai_state_adapter.py -q`。
- GirlAI 情绪、意图和统一回合事件修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_api.py tests/unit/test_girlai_state_adapter.py tests/unit/test_girlai_companion_classifier.py tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_companion_memory.py tests/unit/test_girlai_companion_model.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_refactor.py tests/unit/test_unified_state_models.py tests/unit/test_unified_state_service.py tests/unit/test_database_services.py -q`。
- Agent 模型上下文只保存模型 ID、配置版本、调用统计和降级记录；模型 Key 对应的供应商凭据继续由现有 Key Store 管理。修改模型上下文契约后同时运行后端 `test_model_context_service.py` 与前端 `agentSession.test.js`、`project.test.js`。
- 验证节点通过 `State.metadata.required_validation_scopes` 声明 `local_runtime` 或 `local_e2e`；云端验证保持 `cloud_syntax`，本地结果按 scope 回传。
- 本地结果协议使用 `validation_scope`、`status` 和 `source=local`；`local_result_to_delta()` 负责映射为内部字段并执行 task/session/revision/schema 校验。StateReducer 按验证结果 `event_id` 去重，重复回传保持状态和 revision 不变。
- 会话回放使用 `replay_session()`；发现 sequence 缺口时，调用方应执行返回的 `snapshot_recovery` action。
- VS Code 插件包位于 `vscode-extension/`；修改 `src/protocol.ts` 或 `src/connection.ts` 后执行 `npm --prefix vscode-extension test`，该命令会先进行严格 TypeScript 构建，再运行 Node 原生测试。
- 工作区授权策略位于 `src/workspace-authorization.ts`；测试通过注入 `realpath` 适配器覆盖符号链接越界和多工作区隔离场景。
- 验证执行器位于 `src/validation-runner.ts`；真实 VS Code 适配层应注入 `child_process` 的参数数组 spawn 实现，保持 `shell=false` 并复用现有超时、取消和输出限制测试。
- 结果脱敏和缓存分别位于 `src/result-sanitizer.ts` 与 `src/result-store.ts`；持久化适配层实现 `ResultStorage` 的 `get` 和 `update`，云端确认后调用 `acknowledge(event_id)`。
- `CloudConnection` 可注入 `ResultStore`，网络中断时持久化结果，恢复连接后调用 `flushPendingResults()`；新连接实例可继续刷新同一存储中的待回传队列。
- `ValidationStatusView` 位于 `src/status-view.ts`，当前以纯 TypeScript 快照承载状态、通知和诊断数据；修改后通过 `npm --prefix vscode-extension test` 验证，真实 VS Code StatusBar、通知和 DiagnosticCollection 适配层在发布验收阶段接入。
- `compatibility.ts` 负责 schema 和插件版本握手校验；插件 manifest 位于 `vscode-extension/package.json`，构建后入口是 `dist/extension.js`。本地安装 `vsce` 后可运行 `npm --prefix vscode-extension run package` 生成 VSIX。
- `agent-host.ts` 负责版本化 Agent Host Envelope、Host Hello、能力声明、会话握手和策略版本门禁；该模块保持纯 TypeScript，可在接入 VS Code Webview 和原生 API 前独立测试。
- 后端 Agent Host 使用 `POST /api/v1/agent/host/handshake` 初始化会话，使用 session actions、events 和 policy 端点完成动作拉取、事件回传和策略同步；所有端点需要 access token，并校验用户与 session 绑定。当前会话状态为进程内存，StateGraph 动作入队时需替换为持久化或任务存储。
- `run_workflow()` 在工作流产生新 State 后自动调用 `enqueue_state_actions()`，把 `pending_actions` 适配为带 session/task/revision/workspace 上下文的 Host `tool_action`，并依赖 `action_id` 去重。`AgentHostSessionStore` 将队列和事件确认原子保存到 `data/agent_host_sessions/`，该目录属于运行时数据并已加入忽略规则。
- `tool-dispatcher.ts` 负责将 Agent Host 动作路由到工作区文件、诊断和验证适配器；文件动作必须通过 `WorkspaceAuthorization`，验证动作必须通过 `ValidationRunner`，策略关闭时拒绝新的本地动作。
- 终端 Agent Host 动作沿用 `PendingAction` 的操作白名单和工作区目录约束，并通过 `ValidationRunner` 执行；新增终端能力时保持参数数组和 `shell=false`。
- `webview-bridge.ts` 和 `agent-host-runtime.ts` 组成 Webview 消息层与 Agent Host 动作运行层；两者保持 VS Code API 解耦，使用 `npm --prefix vscode-extension test` 验证请求关联、超时、会话门禁和结果事件。
- `agent-workbench.ts` 和 `extension.ts` 提供原生 Webview 面板及 `codingmatrix.openAgentWorkbench` activation 命令；真实 Extension Host E2E 通过 `npm --prefix vscode-extension run e2e` 验证命令注册和面板打开。
- `CloudConnection.streamAgentPrompt()` 调用 `/api/v1/agent/orchestrate/stream`；修改连接路径或流式协议时必须同步更新 `vscode-extension/test/connection.test.mjs`。
- `approval-bridge.ts` 管理 Host 动作的审批请求和决定；`AgentHostRuntime` 通过会话策略的 `auto_approve` 开关控制动作暂停、批准继续和拒绝结果。
- `AgentWorkbenchController` 通过 `onMessage` 回调接收已验证的 Webview 控制消息；审批请求在工作台中展示批准和拒绝操作，并按原 Envelope 回传决定。
- `extension.ts` activation 会为当前工作区创建本地 Agent Host；真实进程执行使用 `node:child_process.spawn`，工作区授权和审批桥接由 Host 组件统一管理。
- 真实插件 E2E 位于 `vscode-extension/e2e/`，由 `@vscode/test-electron` 启动 VS Code `1.135.0` 和 `fixtures` 临时工作区；无头 Linux 环境需要 `xvfb`，脚本已通过 `xvfb-run` 提供 DISPLAY。测试覆盖工作区打开、manifest 发现、扩展激活和兼容性握手。

## 运行时验证边界

- `/api/v1/health` 是 API 健康路由，`/health` 只可作为部署配置中的显式别名核对。
- 健康检查覆盖数据库和 Redis，当前不能代表 Celery worker 已在线。
- `verify-integration.sh` 主要执行静态文件、源码文本和语法检查；ASGI 健康测试使用进程内传输，Celery 测试主要验证配置和任务注册。
- 真实端口、worker、broker、数据库迁移、Nginx upstream、Nginx 权限和多 worker scheduler 行为需要本地运行环境验证；RC1-RC2 已完成代码配置修复。
- StateGraph 当前通过单节点 legacy wrapper 接入生产入口；RAG、checkpoint 自动恢复、统一事件出口和 VS Code 本地验证回传仍属于迁移中的能力。验证节点和会话 replay 已完成云端契约层实现，真实插件 E2E 已在 VS Code `1.135.0` Extension Host 中通过。
- 当前本地验证已确认 Redis 返回 `PONG`，PPT worker 在线、监听 `ppt` 队列并注册 `app.tasks.ppt_tasks.generate_ppt`；真实 HTTP Markdown 任务已完成 `success` 并生成产物；后端健康接口返回 `healthy`，Redis 缓存往返成功。
- 使用 `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` 重跑 PPT 真实调用时，SiliconFlow 返回 HTTP 402 余额不足；任务沿用默认大纲回退并完成 `success`，该结果表明余额问题属于当前供应商账户状态。
- 重启 PPT worker 后再次调用 DeepSeek R1，SiliconFlow 返回 HTTP `200 OK`；响应 JSON 不完整触发大纲解析回退，任务完成 `success`。当前验证重点转为模型响应解析的容错处理。
- Agent 能力 Playwright E2E 已通过 `23 passed`；无认证综合诊断 E2E 已通过 `6 passed`。相关测试使用 `API_BASE`，页面检查使用 `domcontentloaded`，未认证端点按 5xx 服务错误判定。
- 认证 Agent API、会话生命周期和历史会话 E2E 初次执行结果为 `10 failed`，失败集中在测试账号登录，后端返回“邮箱或密码错误”，连续重试后出现登录端点限流。更新被 Git 忽略的 `.env.test` 后，种子账号认证成功，Agent API 验收为 `2 passed`。
- 会话 UI 使用当前 `AgentSidebar` 的 `.session-item` 和 `button[title="新建会话"]` 选择器；历史会话整组 E2E 曾为 `5 passed`，生命周期创建、切换、删除主流程、并发限制 API 和取消状态均已通过。真实模型 Agent E2E 曾有 `2 skipped`，原因是测试环境缺少 `TEST_API_KEY`。本轮手机端改动的前端单元测试为 `23 passed`，生产构建返回 `0`。
- StateGraph 当前通过单节点 legacy wrapper 接入生产入口；RAG、checkpoint 自动恢复、统一事件出口和 VS Code 本地验证回传仍属于迁移中的能力。验证节点和会话 replay 已完成云端契约层实现，真实插件 E2E 已在 VS Code `1.135.0` Extension Host 中通过。
