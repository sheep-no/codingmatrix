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

PPT 同步真实生成 E2E 需要前端监听 `3000`、后端监听 `8000`，并准备 Redis、数据库和可用的临时注册接口。测试会在浏览器上下文中获取 CSRF token、注册一次性用户，调用 `/api/v1/pptx/generate` 并下载返回的 PPTX；测试使用内置占位密码，不读取项目密钥。

统一状态保留任务每天执行一次：默认资源在 7 天后进入归档窗口，归档后 30 天进入外部 artifact 清理窗口。活动任务、有效会话和恢复中的任务会阻止处理；外部存储清理失败会保留 `retryable` 记录并等待下次调度重试。

读切换前调用 `build_reconciliation_report` 检查六类统一资源覆盖和开放差异，再使用 `ReadCutoverController.enable` 按模块顺序推进；发现一致性或权限异常时调用 `rollback` 恢复该模块的 legacy 读源。

四模块批量切换使用 `activate_modules_in_order`，通过 `rollout_percentage` 控制用户 cohort 比例。灰度验证应按 AICloud、GirlAI、Agent、Workflow 顺序执行，每个模块完成核对后再进入下一个模块。

历史 P4.4 验收记录：状态迁移、核对、切换、worker recovery、SQL replay、快照恢复和跨用户所有权测试为 `16 passed`；认证、核心导航、Workflow、PPT 浏览器验收为 `34 passed`；API 路由契约测试为 `3 passed`、`2 skipped`。该批次记录用于追溯，实时结果以当前命令执行输出为准。浏览器测试使用系统 Chromium；供应商 401 响应类型错误和过时系统信息端点引用已修复。

API 路由契约 E2E 已完成静态路径校准，当前结果为 `3 passed`、`2 skipped`。认证 E2E 使用 `TEST_ADMIN_EMAIL` 和 `TEST_ADMIN_PASSWORD`，默认测试邮箱为 `admin_test@example.com`；固定账号未设置密码时认证用例会明确跳过。完整浏览器验收已通过一次性本地测试账号完成。

GirlAI 情绪与意图增强专项回归覆盖结构化回合、分类阈值、关怀策略、记忆、上下文、幂等预留、过期租约接管、owner fencing、首次会话唯一性、失败事件、统一状态和数据库服务，当前结果为 `82 passed`。Alembic head 为 `20260904_girlai_turn_fencing`。真实 HTTP 已验证主模型与分类模型调用、状态恢复和同一 `turn_id` 幂等回放成功；分类模型使用正数 `thinking_budget` 直接完成识别，推理文本过滤生效。嵌入 JSON 提取、512 token 最低结构化输出预算、温度限制和 60 秒伙伴请求超时已通过真实供应商复验：主回合、状态读取和幂等回放均返回 `200`，`structured_output` 降级标记消失，回放响应与原响应一致，状态版本保持一致。

## 验证命令

```bash
# 运行完整单元测试
python3 -m pytest tests/unit -q

# 运行 StateGraph 和入口迁移相关测试
python3 -m pytest tests/unit/test_workflow_registry.py tests/unit/test_agent_state.py tests/unit/test_state_checkpoint.py tests/unit/test_retrieval_service.py tests/unit/test_agent_adapters.py tests/unit/test_state_graph_runtime.py tests/unit/test_state_graph_nodes.py tests/unit/test_validation_nodes.py tests/unit/test_local_validation_adapter.py -q

# 运行 Orchestrator Core 计划、状态机、checkpoint、模型网关和产物提交测试
python3 -m pytest tests/unit/test_orchestration_plan.py tests/unit/test_orchestration_state_machine.py tests/unit/test_orchestration_core.py tests/unit/test_orchestration_model_gateway.py tests/unit/test_orchestration_artifact_committer.py -q

# 运行 GenerationScheduler 调度、超时、取消和终态收敛测试
python3 -m pytest tests/unit/test_orchestration_generation_scheduler.py -q

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

# 检查 Flutter 桌面客户端
cd /workspace/flutter_client
FLUTTER_ALLOW_ROOT=1 flutter analyze
FLUTTER_ALLOW_ROOT=1 flutter test
```

### Flutter 桌面客户端

Flutter SDK 使用 3.35.7 stable。当前环境从 `/tmp/opencode/flutter` 执行 Flutter 命令，并在 `/workspace/flutter_client` 内运行客户端检查：

```bash
# 安装 Flutter 依赖
FLUTTER_ALLOW_ROOT=1 PATH=/tmp/opencode/flutter/bin:$PATH flutter pub get

# 检查 Dart 静态分析
FLUTTER_ALLOW_ROOT=1 PATH=/tmp/opencode/flutter/bin:$PATH flutter analyze

# 运行 Flutter 单元和 Widget 测试
FLUTTER_ALLOW_ROOT=1 PATH=/tmp/opencode/flutter/bin:$PATH flutter test

# 构建 Linux 桌面调试包
# 需要系统已安装 CMake 和 Linux desktop toolchain
FLUTTER_ALLOW_ROOT=1 PATH=/tmp/opencode/flutter/bin:$PATH flutter build linux --debug

# 在无图形显示环境中检查应用启动
xvfb-run -a -s '-screen 0 1440x900x24 -nolisten tcp' timeout 15s ./build/linux/x64/debug/bundle/flutter_client

# 构建 Android 调试 APK
# 需要 Android SDK、Platform Tools 和可用的 Android SDK license
FLUTTER_ALLOW_ROOT=1 PATH=/tmp/opencode/flutter/bin:$PATH flutter build apk --debug

# 当前会话环境构建 release 测试包
# 在受控 background terminal 中执行，显式指定已安装的 SDK
ANDROID_HOME=/tmp/opencode/android-sdk /tmp/opencode/flutter/bin/flutter build apk --release --no-pub
```

Android release 当前使用 debug 签名，产物路径为 `flutter_client/build/app/outputs/flutter-apk/app-release.apk`。当前环境 Gradle 采用单 worker；构建前检查磁盘余量，避免并行运行多个打包任务。真机使用可访问的 HTTPS 服务地址，默认 `127.0.0.1` 指向设备自身。

设备验收步骤：

1. 安装测试 APK，填写 HTTPS 服务地址并登录，关闭应用后重新启动，验证会话恢复。
2. 退出并切换账号或服务地址，确认工作台、Provider 和历史数据随认证上下文更新。
3. 使用自行配置的 Provider 授权完成任务，验证关键决策、文件预览与 ZIP 保存。
4. 对运行任务断开本地连接，从历史详情恢复订阅；任务结束后确认恢复按钮禁用。
5. 仅在明确接受项目文件清理时确认停止，检查服务端任务状态与设备提示。

认证层使用 `CloudAuthClient` 调用 `/api/v1/csrf-token`、`/api/v1/login` 和 `/api/v1/refresh`，路径由 `app/main.py` 的 `/api/v1` 挂载决定。访问令牌和 Cookie 写入 `CredentialStore` 注入的设备安全存储，领域层使用 `AuthSession.accessTokenRef`。`AuthenticatedClient` 负责后续业务请求；生成等副作用请求遇到失败后需要用户核对状态，自动重发被禁用。单一活动会话记录包含服务 origin 和账号，切换登录会清除旧凭据；服务地址只接受不含路径、用户信息、查询或片段的 HTTP(S) origin。生产环境 Cookie 带 Secure，客户端应使用 HTTPS。

测试通过 `SessionStorage` 注入隔离内存实现，并单独验证设备存储适配器的插件 mock。真实 Android KeyStore、Windows Credential Manager 和 Linux Secret Service 尚未验收；Linux 构建需要 `libsecret-1-dev`、`libjsoncpp-dev` 及运行时 Secret Service。应用启动恢复需要网络验证 refresh，失败会清理本地会话并提示重新登录。存储清除失败时，登录页提供“清除本地会话”重试入口。当前静态分析、52 项 Flutter 测试及 Android release APK 构建已通过；APK 签名和 ZIP 校验通过，设备运行与桌面平台验收仍待完成，详见 `TESTING.md`。

### 图表编辑器验证

```bash
# 运行图表编辑器单元测试
npm --prefix src run test:run -- views/ChartEditorPage.test.js

# 运行图表编辑器桌面和移动端 E2E
./node_modules/.bin/playwright test tests/e2e/chart-editor.spec.js --reporter=line --timeout=60000

# 构建前端生产资源
npm --prefix src run build
```

图表编辑器的单元测试覆盖数据导入、字段识别、聚合、图表编辑、撤销重做、草稿两天过期、项目 JSON 导入导出和文件重新关联。E2E 覆盖桌面端导入与恢复流程、PNG 导出、移动端操作和横向溢出检查。项目配置草稿使用 `localStorage` 保存元数据，浏览器清理站点数据后应通过项目 JSON 或原始数据文件恢复。

### 管理员面板验证

```bash
# 运行管理员面板浏览器场景
npx --no-install playwright test tests/e2e/admin-panel-scenarios.spec.js --config=playwright.config.js --project=chromium
```

认证使用 `TEST_ADMIN_EMAIL` 和 `TEST_ADMIN_PASSWORD`，默认邮箱为 `admin_test@example.com`。该账户权限为 `admin`，从 `/admin` 进入；工具集「管理员面板」仅超级用户可见。场景覆盖模块搜索、用户管理、取消创建用户、取消退出、刷新后菜单恢复，以及系统日志再进入。

## 最近验收结果（2026-09-05）

- PPT 专项回归：`225 passed`；共享持久化新增测试覆盖 Artifact 父子关联、内容 hash、质量诊断、Checkpoint、归属隔离和重试幂等，Celery Markdown 生产链路通过隔离数据库验收。
- PPT 最终页数与模板令牌回归：后端单元测试 `1947 passed, 2 skipped`，其中 PPT 相关测试 `236 passed`；大纲 API 集成测试 `5 passed`，前端全量 `51 passed`，Vite 生产构建通过；实际 PPTX 断言覆盖 5 页最终总数、重复封面归一化和模板主色写入。
- PPT 任务 3/4 场景、模板、设计令牌和语义规划专项回归：完整 PPT 测试 `231 passed`；规划器覆盖页面类型兼容映射、容量预算、布局评分、令牌/布局版本和连续布局惩罚。
- PPT 任务 5 编排回归：完整 PPT 测试 `233 passed`；标准模式跳过视觉复审，精修模式保留完整阶段，取消与指定阶段恢复契约通过。
- PPT 任务 6 渲染与素材回归：完整 PPT 测试 `235 passed`；11 类页面视觉骨架、图片等比适配/回退、图表选择和来源占位规则通过。
- `elegant` 董事会备忘录主题统一生成测试：`24 passed`；6 页 PPTX、PDF 和 PNG 样稿生成成功，证据页与路线页二轮视觉评分为 `9.0/10` 和 `8.5/10`。
- 前端全量测试：`36 passed`；PPT 工作流测试覆盖大纲修改、新增、重排、删除、批准禁用，以及逐页质量分、问题、修复动作和人工复核标记展示；前端生产构建成功。
- VS Code 扩展构建成功，Node 原生测试：`75 passed`。
- VS Code Extension Development Host E2E 成功，使用 VS Code `1.136.1` 覆盖扩展发现、激活、兼容性校验、Agent Workbench 命令和工作区加载。
- 已生成 VSIX：`vscode-extension/codingmatrix-local-validation-0.1.0.vsix`。
- 真实 Agent/PPT 验收已覆盖 HTML 产物生成、PPTX HTTP 下载、WebSocket 进度事件和错误格式请求返回 404。
- 游戏 AI PPT 真实生成 E2E：`1 passed`；请求 `slide_count=16` 返回 15 个内容页并下载生成的 16 页 PPTX，内容断言覆盖 `NPC`、`UGC` 和 AI 游戏领域语义。
- PPT 三步 mock E2E 当前为 `1 passed`；前端 Vitest 当前为 `15 files passed, 48 tests passed`。
- 种子账户认证版 PPT 页面 E2E 当前为 `6 passed`；认证 fixture 在已完成登录后允许 CSRF 辅助初始化遇到 `429`，避免重复测试触发限流影响只读页面验收。
- 图表编辑器专项验收：前端单元测试 `19 passed`；桌面和移动端 Playwright `2 passed`；元数据草稿、两天过期、项目 JSON 导入导出和同名文件重新关联通过；Vite 生产构建通过。

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

# 构建生产资源并验证性能预算
NODE_OPTIONS=--max-old-space-size=1800 npm run build:budget

# 复查已有 dist 产物的性能预算
npm run budget:check

# 验证首页与 Agent Dashboard 三档响应式布局
cd /workspace
npx --no-install playwright test tests/e2e/workbench-responsive.spec.js --config=playwright.config.js --project=chromium --reporter=line --timeout=60000

# 验证任务反馈归一化、操作反馈、增量合并和断线恢复
cd /workspace/src
npm run test:run -- utils/taskFeedback.test.js composables/useTaskFeedback.test.js components/shared-state.test.js views/AgentDashboard.test.js views/PPTGenerate.test.js

# 验证消息窗口、流式批处理和图片缩略图
npm run test:run -- utils/messageVirtualizer.test.js utils/streamUpdateBatcher.test.js utils/imageThumbnail.test.js components/chat/message-parts.test.js
```

根目录的 `npm run test:e2e` 用于 Playwright；前端 `dev`、`build`、`lint` 和 Vitest 命令均位于 `src/package.json`。

Web 工作台响应式专项使用 1440px、768px 和 390px 视口，覆盖首页与 Agent Dashboard 的桌面栏位、移动抽屉、焦点恢复、16px 移动输入字号和横向溢出。任务反馈专项覆盖四类领域归一化、操作事件派发、增量合并、计时、重复事件过滤、序列缺口、恢复快照、过期快照拒绝、终态断线保护和游标重置。消息性能专项覆盖实测高度窗口化、帧级 token 合并、尾部强制冲刷、320px 图片缩略图和低频覆盖层动态 chunk。当前前端完整 Vitest 为 `30 files passed, 126 tests passed`；生产构建转换 `2482` 个模块，性能预算基线为首屏 JavaScript `356.1 KiB gzip`、首屏 CSS `55.0 KiB gzip`、最大图片 `124.6 KiB`、最大路由 chunk `47.4 KiB gzip`，四项检查均通过。浏览器性能快照通过 `window.__performanceSnapshot` 或 `codingmatrix:performance-snapshot` 事件读取。专项 ESLint 为 `0 errors`，仓库既有未使用变量与 `console` 规则产生 warning。
Lighthouse 使用生产预览服务器完成优化后复测：移动模拟性能分数 `30`，LCP `8.7s`、FCP `4.5s`、TBT `2,260ms`、CLS `0.062`；桌面模拟性能分数 `27`，LCP `8.2s`、FCP `4.3s`、TBT `970ms`、CLS `0.047`。两种视口均提示约 `21 KiB` 未使用 JavaScript，结果作为后续首屏初始化优化基线。移除首屏完整 Element Plus 插件注册后，首屏 JavaScript gzip 从 `356.1 KiB` 降至 `86.5 KiB`。

PPT 三步流程的供应商无关 E2E 位于 `tests/e2e/ppt-generation-mock.spec.js`，使用 mock HTTP/WebSocket 覆盖大纲草稿、批准、生成进度、质量报告和 PPTX 下载；认证版 PPT E2E 需要设置 `TEST_ADMIN_PASSWORD`。

游戏 AI 真实生成 E2E 位于 `tests/e2e/test_ppt_game_ai.e2e.spec.js`。根目录 Playwright 配置必须与根目录依赖一起使用，避免根目录和 `src/node_modules` 的 Playwright 重复加载：

```bash
# 运行游戏 AI PPT 真实生成 E2E
cd /workspace
npx --no-install playwright test tests/e2e/test_ppt_game_ai.e2e.spec.js --config=playwright.config.js --project=chromium
```

该用例可能因供应商模型不可用进入领域化大纲回退，但 PPTX 内容和下载链路仍应完成；视觉分析在请求没有用户 `api_key_token` 时会被跳过并使用本地布局。

历史云端验证记录为：排除 Redis、数据库和 FAISS 外部条件的单元测试 1605 passed、2 skipped。当前本地环境已安装 FAISS 并启动 Redis，后端 unit/integration 完整回归结果为 `1784 passed, 2 skipped`；该结果覆盖单元测试与本地基础依赖，生产入口和本地插件验证闭环仍需独立验收。

## StateGraph 开发约定

- 增量计划使用 `ProjectSnapshot` 和 `ChangePlan` 管理动态文件集合。`planned_files` 表示本次处理范围，未受影响文件通过 SHA-256 门禁保护；add/modify/delete/rename 在调度前统一进入 `IncrementalFileTransaction`，Core 只在 `completed` 终态提交，失败、取消和异常均回滚，删除-only 计划使用空生成计划。

- 节点只读取快照并返回 StateDelta。
- 文件状态使用路径、hash、摘要和诊断字段。
- 云端状态不能把本地构建、依赖安装或 E2E 标记为完成。
- legacy endpoint 迁移保留原响应和事件结构，便于渐进式回归。
- 修改后执行 `git diff --check` 和相关测试。
- `app.agent.orchestration` 的生命周期变化统一通过 `advance_state()` 或 `terminate_state()`；每个变化携带唯一 `event_id` 和当前 `expected_revision`，恢复游标随 checkpoint 持久化。
- 任务 11.1 真实传统生成验收使用 `PYTHONPATH=/workspace SECRET_KEY=<test-value> python3 tests/manual/test_traditional_generation_acceptance.py`；脚本验证严格 6 文件集合、SHA-256、Python 语法和生成项目 `pytest` CRUD 测试。执行前需要后端进程与验收进程使用相同的测试 `SECRET_KEY`，并配置项目供应商 provider。
- 文件计划通过 `build_file_plan()` 进入内核边界；显式文件范围使用 `requested_paths`，自动补充文件使用 `origin=extension`、`source` 和 `reason`，下游只消费已冻结的 `GenerationPlan`。
- 创建编排命令时通过 `ExecutionBudget` 固定任务、阶段、文件和模型调用预算；恢复任务读取 checkpoint 中的原预算。所有新内核模型调用通过 `ModelGateway`，流式调用的 deadline 覆盖流创建和完整消费，保活数据只用于活动观测。
- 模型取消路径必须关闭底层异步流并归还信号量；现有 `LLMClient` 在成功、失败、超时和取消后均调用动态路由结果记录，使 `active_requests` 收敛为零。
- 新内核生成内容统一通过 `ArtifactCommitter.commit()` 落盘；调用方只发布返回结果中的首次 `completion_event`。任务进入成功终态前调用 `check_artifact_success_gate()`，并将成功结果传给 `OrchestratorCore.finish()`；`artifact_commit_failed` 和 `artifact_consistency_failed` 保持为稳定错误码。
- 新内核文件调度使用 `GenerationScheduler`；生成器只接收 `FileGenerationContext`，完成内容交给 `ArtifactCommitter`，下游只在所有上游节点完成后释放。阶段或用户取消后等待 `TaskGroup` 子任务回收，并将所有未完成节点收敛到对应终态。
- 跨文件生成需要从 `GenerationPlan` 构建一次 `ContractIndex`，并让所有 `FileGenerationContext` 复用该不可变快照。新增生成器通过 `GeneratedContent.contract_refs` 声明接口、文件或 HTTP 契约引用；写盘前的契约校验失败时保留结构化诊断并阻止文件事件。
- 云端校验结果使用 `ValidationReport`；新增修复类别先通过 `RepairRouter` 分类，再由 `RepairBudget` 控制单类 3 次、任务累计 5 次的自动修复额度。错误诊断应携带文件路径、scope、上下文 hash 和候选版本 hash，业务逻辑、测试断言及未知错误进入用户确认。
- 生成前上下文通过 `ContextAssembler` 装配；输入条目必须声明 `source`、`source_id`、`content`、优先级和作用域，Memory、Retrieval 与 MCP/Skill 内容由装配器统一脱敏、去重并生成 `context_hash`。
- 新增语言能力时通过 `app.agent.languages` 暴露 Adapter 和能力元数据，并为导入、模块解析、符号与签名边界增加测试；当前专用 Adapter 覆盖 Python、JavaScript/TypeScript、Java、Go 和 Rust。
- 框架 Profile 通过 `ValidationStage` 声明 install、lint、typecheck、build、test 和 smoke 阶段，每个声明阶段必须存在对应命令。命令使用参数数组与 `shell=false`；工作区 Profile 同时维护命令白名单、依赖白名单和 owner scope。
- 官方脚手架通过 `official_scaffold_request()` 获取固定版本 CLI，通过 `execute_official_scaffold()` 执行并导入计划。目标目录必须是规范化工作区相对路径；导入文件受数量、大小、UTF-8 和符号链接边界约束，产物通过 `import_scaffold_plan()` 冻结为 strict `GenerationPlan`。
- 工作区 Profile 使用 `WorkspaceProfileDocument.build()` 生成带 digest 的 schema v1 文档，通过 `load_workspace_profile()` 校验 owner/workspace 隔离。自定义命令避免解释器内联代码与路径越界参数，并同时出现在 `command_allowlist`；依赖同时出现在 `dependency_allowlist`。
- 自定义 Profile 先运行 `probe_workspace_profile()` 的 syntax、install、startup、crud 和 persistence 有限探针，再调用 `promote_workspace_profile()` 从 `custom_pending` 晋级到 `experimental`；形成第二轮完整 conformance 证据后晋级到 `supported`。
- 数据库能力通过 `app.agent.database_profiles.DEFAULT_DATABASE_PROFILES` 解析；生成前应读取 driver、ORM、迁移工具和测试数据库策略，未知数据库必须保留 `unsupported` 状态与诊断。
- 生成上下文通过 `profile_context(workspace)["database"]` 获取数据库契约；项目 manifest 的 PostgreSQL/MySQL 线索会覆盖 Web 默认 SQLite，未知技术栈继续返回 `unsupported`。
- 语言接口提取优先调用 `LanguageAdapter.extract_signatures()`；需要外部语言工具时使用 `ToolchainRunner` 和 `CommandSpec(action=ToolchainAction.INSPECT, command=(...))`，保持 `shell=false`、超时和输出上限，工具失败后回退内置解析器。
- 技术栈通过 `app.agent.profile_discovery.discover_profile()` 从标准 manifest 生成画像，再用 `build_probe_plan()` 产生参数数组探针；内置 Profile 直接映射注册状态，自定义画像按探针结果执行 `custom_pending`、`experimental` 和 `supported` 状态流转。
- Profile 与 Core 门禁相关修改执行 `python3 -m pytest tests/unit/test_profile_discovery.py tests/unit/test_framework_profiles.py tests/unit/test_languages.py tests/unit/test_java_language_adapter.py tests/unit/test_toolchain.py tests/unit/test_generation_contracts.py -q`，并运行相关 Core 编排回归。
- 脚手架、Toolchain 和工作区 Profile 修改还需加入 `tests/unit/test_scaffolding.py`，验证真实文件导入、manifest 依赖、脚本探测、输出上限、owner/workspace 隔离、恶意命令拒绝和逐级晋级。
- 受约束代码合成的策略选择通过 `SynthesisCapabilityRegistry` 查询现有语言 Adapter 和固定版本脚手架能力。新增语言或脚手架后，运行 `python3 -m pytest tests/unit/test_code_synthesis_contracts.py tests/unit/test_scaffolding.py tests/unit/test_languages.py tests/unit/test_generation_contracts.py tests/unit/test_framework_profiles.py -q`，并执行 Core Adapter、计划和调度回归。
- 新增技术栈通过 `app.agent.stack_adapters.StackAdapterRegistry` 注册语言/框架别名，并实现工作区探测、能力声明、动态 `ChangePlanIR`、符号提取、脚手架结果和验证画像。Artifact 集合由 `StackChangeRequest` 提供；验证 Stack Adapter 时运行 `python3 -m pytest tests/unit/test_stack_adapters.py tests/unit/test_code_synthesis_contracts.py tests/unit/test_profile_discovery.py tests/unit/test_framework_profiles.py tests/unit/test_languages.py tests/unit/test_java_language_adapter.py tests/unit/test_scaffolding.py tests/unit/test_generation_contracts.py tests/unit/test_orchestration_adapters.py tests/unit/test_orchestration_generation_scheduler.py -q`。
- 新增候选契约时，在 `GenerationPlan.files[].contract` 中提供版本化声明，并由语言 Adapter 的 `extract_contract_facts()` 输出对应命名事实集。通用门禁只扩展声明类型或比较算子；技术栈、路径、文件名、符号、签名、路由、字段和内容要求均作为声明数据或解析事实传入。语言修复通过 `repair_source()` 产生最小候选，并重新执行同一个 `validate_candidate()`。Python 外部导出检查仅覆盖可读取且可静态确定导出集合的模块；动态导出、星号导入和多提供者歧义保持保守诊断或跳过修复。本地类构造诊断仅覆盖无基类、无装饰器且未声明 `__init__` 或 `__new__` 的普通类。相关修改运行 `python3 -m pytest tests/unit/test_declarative_contracts.py tests/unit/test_orchestration_adapters.py -q`。
- 分层候选验证通过 `CandidateValidationRouter` 形成 V0-V6 连续前缀，层处理器必须返回其注册层级并在首个非通过结果短路。V2、V3 和 V5 的 Toolchain 命令必须先经 `validation_plan_for_level()` 隔离；V4 契约差异由独立处理器提供，领域语义保留在 Stack Adapter 或契约实现中。候选修复使用 `build_repair_feedback()` 保留原生成策略并限制诊断及上下文预算。相关修改运行 `python3 -m pytest tests/unit/test_synthesis_validation.py tests/unit/test_validation_report.py tests/unit/test_generation_contracts.py tests/unit/test_stack_adapters.py tests/unit/test_code_synthesis_contracts.py tests/unit/test_orchestration_artifact_committer.py -q`。
- `ChangePlanIR` 投影只接受 Core 已具备内容生成语义的 create/modify Artifact。Core 增量生命周期已为 delete/rename 提供文件事务；扩展 `project_change_plan()` 时仍需显式投影相应操作并保留 `degraded` 和能力证据字段。
- 任务 18 的真实脚手架基线使用固定版本 `express-generator@4.16.1` 验证：导入结果包含 7 个运行所需文本文件和 4 个运行时依赖，Toolchain 从 `package.json` 识别安装与启动命令，3 个 JavaScript 源文件通过受控 `node --check`。固定依赖加载后，`GET /` 与 `GET /users` 均返回 HTTP 200，受控停止后端口释放；超时探针返回 124 和稳定诊断，并回收派生子进程组。工作区 Profile 的五阶段探针连续通过两轮并晋级到 `supported`。
- 工作区 Profile 通过 `ProfileCache` 读写 `.monkeycode/profiles.json`；画像缓存属于运行时元数据，读取时必须校验 schema version，写入时使用原子替换。
- 生成模式适配器包括 `TraditionalAdapter`、`SpecFirstAdapter` 和 `IncrementalAdapter`；设置 `AGENT_ORCHESTRATION_ENGINE=core` 后，Spec-First 编排与增量修改通过 `execute_core_generation()` 进入 `OrchestratorCore.execute()`，默认保持 legacy。影子对比只记录成功状态与文件路径集合，checkpoint metadata 保存 `engine_version`。
- 单次编排可显式传 `engine="core"`；省略时沿用服务端配置。使用独立 `contracts`、`framework`、`runtime` 字段传入契约和技术栈事实，端点通过 `_core_request_metadata()` 送入 Core。固定样例源码 fallback 和默认策略注册已从 Core adapter 移除；扩展候选检查继续使用通用声明门禁，语言最小修复后执行同一门禁。
- Core adapter 只生成内容，正常文件落盘统一交给 `ArtifactCommitter`。增量 adapter 以受影响文件冻结 strict 计划，将外部依赖作为只读上下文，并通过 `preserved_paths` 声明未改动业务文件；`IncrementalFileTransaction` 包围文件调度、持久化、验证和最终成功门禁。
- Core 恢复当前支持 `planning` checkpoint 重新执行；其他活动阶段以 `orchestration.resume_stage_unsupported` 收敛。规划异常统一使用 `orchestration.planning_failed`，规划前取消统一进入 `cancelled`。

### 本轮单元验证（2026-09-07）

最终后台回归为 `608 passed, 3 warnings`（12.41 秒）：前次 575 项同范围在最新代码下为 579 项（新增 4 项 repair 目录映射测试），另加 Toolchain 18 项和脚手架 11 项。后台 `compileall` 退出码为 0，`git diff --check` 通过。该结果覆盖单元测试和语法编译；下文单独记录真实 Core 验收失败证据。

```bash
python3 -m pytest tests/unit/test_orchestration_*.py tests/unit/test_evaluation_*.py tests/unit/test_declarative_contracts.py tests/unit/test_code_synthesis_contracts.py tests/unit/test_synthesis_validation.py tests/unit/test_generation_contracts.py tests/unit/test_stack_adapters.py tests/unit/test_languages.py tests/unit/test_java_language_adapter.py tests/unit/test_framework_profiles.py tests/unit/test_orchestrator_files.py tests/unit/test_orchestrator_validation_scopes.py tests/unit/test_orchestrator_request_project_path.py tests/unit/test_input_validator.py tests/unit/test_output_dir_resolution.py tests/unit/test_spec_first_generator.py tests/unit/test_validation_report.py tests/unit/test_toolchain.py tests/unit/test_scaffolding.py -q
python3 -m compileall -q app tests/unit tests/manual
git diff --check
```

评测文件一致性使用 runner 遍历得到的完整业务文件集合与 fixture 严格比较；遍历排除依赖、缓存、构建目录及数据库等运行产物。repair 使用响应实际目录，并将其映射为 `PROJECTS_BASE_DIR` 下的相对路径传入 HTTP `project_path/output_dir`；回归覆盖绝对/相对响应目录经请求 Schema、端点解析和 Orchestrator 构造后仍落到原实际目录，以及基目录本身和越界目录在 HTTP 前被拒绝。

`ToolchainRunner` 使用项目绝对路径作为 `cwd`，并在复制的宿主环境中覆盖 `PYTHONPATH` 为同一路径。隔离回归通过 `ValidationCoordinator` 启动真实 pytest 子进程，分别覆盖普通包和 namespace package，并核对父进程 `PYTHONPATH` 保持原值。

真实 Core 首次候选验收记录：`python-small-spec_first`，`MAX_REPAIR_ATTEMPTS=0`，耗时 `92.272s`，HTTP 200、8 次模型调用，四个必需文件齐全且 `compileall` 通过，最终 `success=false`。产物目录为 `projects/1/evaluation_python-small-spec_first__1788796860`；宿主导入污染已修复，生成测试仍因 `client=None` 导致 `9 failed`，runtime 仍报数据库无表，CRUD 与 SQLite 持久化未通过。完整磁盘集合包含额外文件，记录为 `plan_consistent=false`，必需文件齐全与严格集合一致性分别判定。此次验收没有执行 repair，目录映射单元通过和导入隔离修复均不能推进端到端成功门禁。

### 其他开发约定

本次增量 repair 专项修复和真实重测记录见 [Core 增量修复实测](CORE_REPAIR_EVALUATION_2026-09-07.md)。新增依赖边界回归覆盖授权保留快照、真实导出、缺失文件和快照后新增文件；元数据回归覆盖根 `.dep_graph.json` 与额外隐藏/嵌套文件，字节码回归覆盖缓存刷新及缓存目录中的非法源码。缓存修复后的扩大回归为 `300 passed, 3 warnings`（4.56 秒）。真实验收结果在独立报告中逐轮记录，历史模型矩阵门禁继续按真实证据判定。

2026-09-08 起，runner 的 `repair_attempts` 同时记录每轮 `input_failure`、HTTP repair 响应、模型指标、`result_verification` 和 `result_failure`。`latest_failure` 保留最新失败候选证据，`verification` 保留实际磁盘复验，两者在 rollback 后可以不同。`repair_stop_reason` 区分 `passed`、`http_error`、`budget_exhausted`、`no_progress_repeated_candidate` 和 `no_progress_repeated_diagnostic`；诊断指纹归一化耗时、内存地址与 attempts 计数，候选指纹独立去重，历史循环也会停止。最多三次 repair，单次 HTTP 超时沿用 900 秒，Core 内部预算保持原值。最终相关回归 351 项通过；两次真实运行分别以重复历史诊断和预算耗尽停止，完整交付仍未通过。详细实测见 [运行诊断与有界重试实测](CORE_REPAIR_EVALUATION_2026-09-08.md)。

- 传统生成的模型活动超时由传入 Specialist/ReAct 的 `HeartbeatTracker` 判断，默认 120 秒；流式 chunk 必须调用 `touch()`。SSE heartbeat 只用于 HTTP 连接保活，排查生成停滞时应查看最近模型数据时间和 `react_timeout` 事件。
- Core 模型调用通过 `ModelGateway.telemetry_for(call_id)` 查询单次遥测；重点检查 `finish_reason`、prompt/completion/total tokens、输入字符数、`max_tokens` 和 `elapsed_seconds`，结合 `model_timeout` 判断输出受限与墙钟预算耗尽。
- GirlAI 相关修改后执行 `python3 -m pytest tests/unit/test_girlai_refactor.py tests/unit/test_girlai_state_adapter.py tests/unit/test_database_services.py -q`，并在 `/workspace/src` 执行 `npm run test:run -- utils/api/girl.test.js`。
- GirlAI 结构化伙伴契约修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_refactor.py tests/unit/test_girlai_state_adapter.py -q`。
- GirlAI 伙伴上下文和模型选择修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_companion_model.py -q`。
- GirlAI 伙伴 API 修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_api.py tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_companion_model.py tests/unit/test_girlai_refactor.py tests/unit/test_girlai_state_adapter.py -q`。
- GirlAI 伙伴记忆修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_memory.py tests/unit/test_girlai_companion_api.py tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_companion_model.py tests/unit/test_girlai_refactor.py tests/unit/test_girlai_state_adapter.py -q`。
 - GirlAI 情绪、意图和统一回合事件修改后执行 `python3 -m pytest tests/unit/test_girlai_companion_api.py tests/unit/test_girlai_state_adapter.py tests/unit/test_girlai_companion_classifier.py tests/unit/test_girlai_companion_service.py tests/unit/test_girlai_companion_memory.py tests/unit/test_girlai_companion_model.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_refactor.py tests/unit/test_unified_state_models.py tests/unit/test_unified_state_service.py tests/unit/test_database_services.py -q`。
 - GirlAI 语音适配修改后执行 `python3 -m pytest tests/unit/test_girlai_voice.py tests/unit/test_girlai_companion_api.py -q`，并在 `/workspace/src` 执行 `npm run test:run -- utils/api/girl.test.js composables/useGirlAiCompanion.test.js`。
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
- 真实插件 E2E 位于 `vscode-extension/e2e/`，由直接开发依赖 `@vscode/test-electron` 启动 VS Code 和 `fixtures` 临时工作区；无头 Linux 环境需要 `xvfb`、`xauth` 与 Electron GTK 运行库，脚本通过 `xvfb-run` 提供 DISPLAY。测试覆盖工作区打开、manifest 发现、扩展激活和兼容性握手；最近验收版本为 VS Code `1.136.1`。

## 运行时验证边界

- `/api/v1/health` 是 API 健康路由，`/health` 只可作为部署配置中的显式别名核对。
- 健康检查覆盖数据库和 Redis，当前不能代表 Celery worker 已在线。
- `verify-integration.sh` 主要执行静态文件、源码文本和语法检查；ASGI 健康测试使用进程内传输，Celery 测试主要验证配置和任务注册。
- 真实端口、worker、broker、数据库迁移、Nginx upstream、Nginx 权限和多 worker scheduler 行为需要本地运行环境验证；RC1-RC2 已完成代码配置修复。
- 生产入口默认通过单节点 legacy wrapper 运行；Core 开关已覆盖 Spec-First 同步与流式编排以及增量修改。RAG、Core 跨活动阶段自动恢复和统一事件出口仍属于迁移中的能力；VS Code 本地验证回传、验证节点和会话 replay 已完成契约与真实插件 E2E 验证。
- 当前本地验证已确认 Redis 返回 `PONG`，PPT worker 在线、监听 `ppt` 队列并注册 `app.tasks.ppt_tasks.generate_ppt`；真实 HTTP Markdown 任务已完成 `success` 并生成产物；后端健康接口返回 `healthy`，Redis 缓存往返成功。
- 使用 `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B` 重跑 PPT 真实调用时，SiliconFlow 返回 HTTP 402 余额不足；任务沿用默认大纲回退并完成 `success`，该结果表明余额问题属于当前供应商账户状态。
- 重启 PPT worker 后再次调用 DeepSeek R1，SiliconFlow 返回 HTTP `200 OK`；响应 JSON 不完整触发大纲解析回退，任务完成 `success`。当前验证重点转为模型响应解析的容错处理。
- Agent 能力 Playwright E2E 已通过 `23 passed`；无认证综合诊断 E2E 已通过 `6 passed`。相关测试使用 `API_BASE`，页面检查使用 `domcontentloaded`，未认证端点按 5xx 服务错误判定。
- 认证 Agent API、会话生命周期和历史会话 E2E 初次执行结果为 `10 failed`，失败集中在测试账号登录，后端返回“邮箱或密码错误”，连续重试后出现登录端点限流。更新被 Git 忽略的 `.env.test` 后，种子账号认证成功，Agent API 验收为 `2 passed`。
- 会话 UI 使用当前 `AgentSidebar` 的 `.session-item` 和 `button[title="新建会话"]` 选择器；历史会话整组 E2E 曾为 `5 passed`，生命周期创建、切换、删除主流程、并发限制 API 和取消状态均已通过。真实模型 Agent E2E 曾有 `2 skipped`，原因是测试环境缺少 `TEST_API_KEY`。本轮手机端改动的前端单元测试为 `23 passed`，生产构建返回 `0`。
- StateGraph 当前通过单节点 legacy wrapper 接入生产入口；RAG、checkpoint 自动恢复、统一事件出口和 VS Code 本地验证回传仍属于迁移中的能力。验证节点和会话 replay 已完成云端契约层实现，真实插件 E2E 已在 VS Code `1.135.0` Extension Host 中通过。
- Core 固定评测入口为 `python3 -m app.agent.evaluation_runner records.json`；该报告聚合 24 个固定 case 的最终成功率、首次/候选/修复后三阶段成功率、`model_call_count` 平均值、P95 耗时、缺失样例、非法指标和失败分类，并按 deterministic/llm 策略拆分结果。90% 端到端门槛以真实评测记录为准。固定评测记录可附带 `database_status` 和 `database_diagnostics`；未知数据库记录为 `unsupported` 并归入 `database` 失败分类。
