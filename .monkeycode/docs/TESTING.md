# 测试指南

## 测试分层

| 层级 | 目录或配置 | 工具 | 用途 |
|---|---|---|---|
| 后端单元 | `tests/unit/`、`pyproject.toml` | pytest、pytest-asyncio | 服务、状态、适配器和安全规则 |
| 后端集成 | `tests/integration/` | pytest、Redis、数据库 | 事件重放、checkpoint、任务恢复 |
| 前端单元 | `src/**/*.test.js`、`src/vite.config.js` | Vitest、jsdom | Store、composable、路由和 API 客户端 |
| 前端构建预算 | `src/scripts/check-performance-budget.js` | Vite manifest、Node.js zlib | 首屏 JS/CSS、图片和路由 chunk 体积 |
| 浏览器 E2E | `tests/e2e/`、`playwright.config.js` | Playwright、Chromium | 登录、导航、Agent 和业务流程 |
| VS Code 扩展 | `vscode-extension/test/`、`vscode-extension/e2e/` | Node test、VS Code Test Electron | 协议、Host、工作台和真实扩展激活 |

## 常用命令

```bash
# 后端单元测试
python3 -m pytest tests/unit -q

# 后端集成测试
python3 -m pytest tests/integration/test_state_recovery.py -q

# Python 语法检查
python3 -m compileall -q app/agent app/api

# 前端单元测试
npm --prefix src run test:run

# 前端生产构建与性能预算检查
npm --prefix src run build:budget

# 复查已有 dist 产物的性能预算
npm --prefix src run budget:check

# 根目录 Playwright E2E
npm run test:e2e

# 游戏 AI PPT 真实生成 E2E
cd /workspace
npx --no-install playwright test tests/e2e/test_ppt_game_ai.e2e.spec.js --config=playwright.config.js --project=chromium

# VS Code 扩展测试
npm --prefix vscode-extension test

# VS Code 扩展 E2E
npm --prefix vscode-extension run e2e
```

根目录 `package.json` 是 E2E 工程配置，仅提供 `test:e2e`。前端的 `dev`、`build`、`lint` 和 Vitest 命令均位于 `src/package.json`。

## 测试配置

- Python 测试路径、异步模式和 marker 位于 `pyproject.toml`；`configs/pytest.ini` 是兼容配置。
- 前端 Vitest 使用 `jsdom`、globals 和 v8 coverage。
- 性能预算测试位于 `src/scripts/check-performance-budget.test.js`；构建预算使用 `dist/.vite/manifest.json` 聚合首屏静态依赖，以入口的直接动态导入识别路由 chunk，并检查 manifest 与 `src/public/` 中的图片。
- 性能采集测试位于 `src/utils/performanceMetrics.test.js`，覆盖 CLS session window、INP interaction 聚合、LCP 更新、成功与失败路由导航以及观察器和守卫释放。
- 消息渲染性能测试位于 `src/utils/messageVirtualizer.test.js`、`src/utils/streamUpdateBatcher.test.js`、`src/utils/imageThumbnail.test.js` 和 `src/components/chat/message-parts.test.js`，覆盖可变高度窗口、帧级增量合并、终止冲刷、图片尺寸限制、懒加载与原图入口。
- Playwright 默认使用 `http://127.0.0.1:3000`，浏览器项目为 Chromium。
- CI Playwright 使用单 worker，并在失败时重试 2 次。
- 浏览器测试需要先启动前端，涉及真实 API 的用例还需要后端、Redis、数据库和测试账号。
- `tests/e2e/test_ppt_game_ai.e2e.spec.js` 在浏览器上下文中动态注册一次性用户，调用真实 `/api/v1/pptx/generate`，验证领域化回退内容和 PPTX 下载；该用例使用根目录 `playwright.config.js` 与 Chromium 项目。

浏览器场景 E2E 从仓库根目录运行，统一使用根目录 `playwright.config.js` 与 Chromium 项目：

```bash
npx --no-install playwright test tests/e2e/girlai-companion-scenarios.spec.js --config=playwright.config.js --project=chromium
npx --no-install playwright test tests/e2e/image-generation-scenarios.spec.js --config=playwright.config.js --project=chromium
npx --no-install playwright test tests/e2e/chart-editor-scenarios.spec.js --config=playwright.config.js --project=chromium
npx --no-install playwright test tests/e2e/admin-panel-scenarios.spec.js --config=playwright.config.js --project=chromium
```

`admin-panel-scenarios.spec.js` 使用种子账户 `admin_test@example.com` 打开 `/admin`，覆盖模块搜索、用户管理、取消创建用户、取消退出、刷新后菜单恢复，以及日志页再进入。认证 E2E 默认邮箱见 `DEVELOPER_GUIDE.md`。

## Agent 重点回归

GirlAI 结构化伙伴回合解析和字段完整性测试位于 `tests/unit/test_girlai_companion_service.py`，覆盖默认字段、降级字段、模型上下文和记忆候选组合。当前伙伴回合保持纯对话契约，不包含工具请求、任务记录或提醒字段。

前端伙伴状态、结构化回合和记忆确认测试位于 `src/composables/useGirlAiCompanion.test.js` 与 `src/utils/api/girl.test.js`，覆盖状态合并、候选记忆确认/忽略和 API 错误传播。

```bash
# 运行 GirlAI 结构化回合测试
python3 -m pytest tests/unit/test_girlai_companion_service.py -q
```

跨会话上下文隔离和模型上下文恢复集成测试位于 `tests/integration/test_girlai_companion_context_recovery.py`，覆盖用户消息、授权记忆、伙伴事件归属，以及恢复后的模型配置、fallback 历史和 token 统计。

```bash
# 运行 GirlAI 上下文恢复测试
python3 -m pytest tests/integration/test_girlai_companion_context_recovery.py tests/unit/test_girlai_companion_context.py tests/unit/test_girlai_companion_model.py -q
```

分类模型故障时文字主链路属性测试位于 `tests/unit/test_girlai_companion_classifier.py`，覆盖模型选择失败、主备分类模型失败、纯文本/JSON/code fence 回复和既有降级能力组合；测试确认助手文本保留，情绪与意图安全回落，并返回分类降级标记。

```bash
# 运行 GirlAI 分类降级测试
python3 -m pytest tests/unit/test_girlai_companion_classifier.py tests/unit/test_girlai_companion_api.py -q
```

legacy 历史与统一状态事务一致性集成测试位于 `tests/integration/test_girlai_legacy_unified_consistency.py`，覆盖成功回合的 legacy/unified 双写关联，以及统一写入失败时两套历史同时回滚并保留脱敏失败事件。

```bash
# 运行 GirlAI 双写事务一致性测试
python3 -m pytest tests/integration/test_girlai_legacy_unified_consistency.py -q

# 运行 GirlAI 前端伙伴测试
npm --prefix src run test:run -- utils/api/girl.test.js composables/useGirlAiCompanion.test.js
```

Agent 模型上下文修改后运行：

```bash
# 后端模型上下文和状态持久化回归
python3 -m pytest tests/unit/test_model_context_service.py tests/unit/test_agent_state_persistence.py tests/unit/test_workflow_state_persistence_hook.py -q

# 前端会话和 API 客户端回归
npm --prefix src run test:run -- stores/agentSession.test.js utils/api/project.test.js
```

Agent Host 和本地验证修改后运行 `npm --prefix vscode-extension test`，涉及真实 Extension Host 时再运行 `npm --prefix vscode-extension run e2e`。模型供应商调用和认证 E2E 需要由测试环境提供对应账号与用户项目配置。

## 验证边界

- `/api/v1/health` 检查数据库和 Redis，健康响应不能证明 Celery worker 已在线。
- 进程内 ASGI 测试不能证明真实端口、Nginx、worker 和 broker 链路。
- `verify-integration.sh` 主要提供静态、语法和配置级证据。
- 真实 PPT Celery、VS Code Extension Host、供应商调用和多 worker 行为需要单独验收。
- 游戏 AI PPT 用例验证了 16 页最终文件、15 个内容页、`NPC`/`UGC` 领域语义和 200 下载响应；模型凭据不可用时，日志应显示领域化大纲回退或跳过视觉分析，本地布局继续完成生成。
- 修改后至少执行 `git diff --check`、相关测试和生产构建。

## 最近结果（2026-09-07）

- VS Code 扩展：TypeScript 构建成功，`npm --prefix vscode-extension test` 为 `62 passed`。
- VS Code Extension Development Host：E2E 通过，已验证扩展激活、Agent Workbench 打开、兼容性握手和工作区能力。
- 前端相关回归：`23 passed`，生产构建成功。
- Web 任务反馈专项：`4 files passed, 36 tests passed`，覆盖归一化、增量合并、断线恢复、过期快照、终态保护、游标重置和组件操作派发；前端完整 Vitest 为 `25 files passed, 108 tests passed`。
- Web 性能采集与预算：前端完整 Vitest 为 `27 files passed, 115 tests passed`；首屏 JavaScript `356.1 KiB gzip / 450 KiB`、首屏 CSS `55.0 KiB gzip / 100 KiB`、最大图片 `124.6 KiB / 200 KiB`、最大路由 chunk `46.7 KiB gzip / 150 KiB`，生产构建预算检查通过。
- Web 消息与资源加载优化：前端完整 Vitest 为 `30 files passed, 126 tests passed`；首屏 JavaScript `356.1 KiB gzip / 450 KiB`、首屏 CSS `55.0 KiB gzip / 100 KiB`、最大图片 `124.6 KiB / 200 KiB`、最大路由 chunk `47.4 KiB gzip / 150 KiB`，生产构建预算检查通过。
- Web 工作台浏览器回归：`workbench-responsive.spec.js` 与 `capability-center.spec.js` 共 `3 passed`，覆盖首页、Agent Dashboard、Capability Center 以及 1440px、768px、390px 视口；移动端 Chromium 快照为导航 `412ms`、LCP `4012ms`、CLS `0.05`，INP 因无交互样本为空，Long Task 条目为空。
- Lighthouse：使用生产预览服务器完成优化后移动端和桌面端审计。移动端性能分数 `30`，LCP `8.7s`、FCP `4.5s`、TBT `2,260ms`、CLS `0.062`；桌面端性能分数 `27`，LCP `8.2s`、FCP `4.3s`、TBT `970ms`、CLS `0.047`。两种视口均提示约 `21 KiB` 未使用 JavaScript，INP 因无交互样本为空。移除首屏完整 Element Plus 插件注册后，首屏 JavaScript gzip 从 `356.1 KiB` 降至 `86.5 KiB`，Element Plus vendor gzip 从 `275.75 KiB` 降至 `30.77 KiB`。开发服务器模式曾出现 `NO_FCP`，生产预览模式已完成有效审计。
- PPT 专项回归：`141 passed`；真实 HTTP/WebSocket 验收覆盖 HTML 生成、PPTX 下载、进度事件和格式错误隔离。
- 原始 `npm --prefix vscode-extension run e2e` 在当前无头环境会受到 `xauth` 缺失影响；使用已启动的 `Xvfb` 直接运行 E2E 入口后完成验收。
- 游戏 AI PPT 真实生成 E2E 当前结果为 `1 passed`；运行时曾发现根目录与 `src/node_modules` 的 Playwright 依赖冲突，固定使用根目录 CLI、配置和 Chromium 项目后通过。

## 最近结果（2026-09-12）

- 虚拟姬场景：`tests/e2e/girlai-companion-scenarios.spec.js` 为 `2 passed`。
- 图片生成场景：`tests/e2e/image-generation-scenarios.spec.js` 为 `2 passed`；`src/views/ImageGenerate.test.js` 为 `6 passed`。
- 图表编辑器场景：`tests/e2e/chart-editor-scenarios.spec.js` 为 `2 passed`；`src/views/ChartEditorPage.test.js` 为 `20 passed`。
- 管理员面板场景：`tests/e2e/admin-panel-scenarios.spec.js` 为 `2 passed`；使用 `admin_test@example.com` 打开 `/admin`，覆盖搜索、用户管理、取消对话框、刷新后菜单恢复，以及日志页再进入。
- 能力中心：`src/views/CapabilityCenter.test.js` 为 `5 passed`，覆盖 Tab 延迟加载、错误重试、删除确认和键盘导航。
- 搜索历史：`src/components/leftlist.test.js` 为 `4 passed`，覆盖打开搜索框、`POST /history` 关键词检索、失败重试和清除后拉全量。
