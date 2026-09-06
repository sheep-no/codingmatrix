# 测试指南

## 测试分层

| 层级 | 目录或配置 | 工具 | 用途 |
|---|---|---|---|
| 后端单元 | `tests/unit/`、`pyproject.toml` | pytest、pytest-asyncio | 服务、状态、适配器和安全规则 |
| 后端集成 | `tests/integration/` | pytest、Redis、数据库 | 事件重放、checkpoint、任务恢复 |
| 前端单元 | `src/**/*.test.js`、`src/vite.config.js` | Vitest、jsdom | Store、composable、路由和 API 客户端 |
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

# 前端生产构建
npm --prefix src run build

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
- Playwright 默认使用 `http://127.0.0.1:3000`，浏览器项目为 Chromium。
- CI Playwright 使用单 worker，并在失败时重试 2 次。
- 浏览器测试需要先启动前端，涉及真实 API 的用例还需要后端、Redis、数据库和测试账号。
- `tests/e2e/test_ppt_game_ai.e2e.spec.js` 在浏览器上下文中动态注册一次性用户，调用真实 `/api/v1/pptx/generate`，验证领域化回退内容和 PPTX 下载；该用例使用根目录 `playwright.config.js` 与 Chromium 项目。

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

## 最近结果（2026-09-05）

- VS Code 扩展：TypeScript 构建成功，`npm --prefix vscode-extension test` 为 `62 passed`。
- VS Code Extension Development Host：E2E 通过，已验证扩展激活、Agent Workbench 打开、兼容性握手和工作区能力。
- 前端相关回归：`23 passed`，生产构建成功。
- PPT 专项回归：`141 passed`；真实 HTTP/WebSocket 验收覆盖 HTML 生成、PPTX 下载、进度事件和格式错误隔离。
- 原始 `npm --prefix vscode-extension run e2e` 在当前无头环境会受到 `xauth` 缺失影响；使用已启动的 `Xvfb` 直接运行 E2E 入口后完成验收。
- 游戏 AI PPT 真实生成 E2E 当前结果为 `1 passed`；运行时曾发现根目录与 `src/node_modules` 的 Playwright 依赖冲突，固定使用根目录 CLI、配置和 Chromium 项目后通过。
