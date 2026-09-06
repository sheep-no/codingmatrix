# 测试文档

> 最后核对：2026-09-03

本文档以 `.monkeycode/docs/TESTING.md`、`.monkeycode/docs/DEVELOPER_GUIDE.md`、当前测试目录和实际配置为准。文件数与测试定义数是 2026-09-03 的静态清点，验收数字保留原始记录的范围和日期。

## 当前测试版图

| 层级 | 当前位置 | 配置或工具 | 静态清点 |
|---|---|---|---:|
| 后端单元 | `tests/unit/test_*.py` | pytest、pytest-asyncio | 144 个文件，1848 个 `test_*` 定义 |
| 后端集成 | `tests/integration/test_*.py` | pytest、数据库、Redis | 4 个文件，31 个 `test_*` 定义 |
| Web 单元 | `src/**/*.test.js` | Vitest、jsdom、Vue Test Utils | 15 个文件，31 个直接 `test/it` 定义 |
| 浏览器 E2E | `tests/e2e/*.spec.js` | Playwright | 77 个 spec，433 个直接 `test(...)` 定义 |
| VS Code 单元 | `vscode-extension/test/*.test.mjs` | Node test、TypeScript | `npm --prefix vscode-extension test` |
| VS Code Host E2E | `vscode-extension/e2e/` | `@vscode/test-electron`、Xvfb | `npm --prefix vscode-extension run e2e` |

静态定义数用于描述代码规模，参数化、动态生成、skip 和收集失败会使实际 pytest/Vitest/Playwright 收集结果产生差异。

当前集成测试文件为：

- `tests/integration/test_auth_api.py`
- `tests/integration/test_health_api.py`
- `tests/integration/test_ppt_outline_api.py`
- `tests/integration/test_state_recovery.py`

## 当前命令

```bash
# 后端单元测试
python3 -m pytest tests/unit -q

# 后端集成测试
python3 -m pytest tests/integration -q

# 统一状态恢复专项
python3 -m pytest tests/integration/test_state_recovery.py -q

# 前端 Vitest
npm --prefix src run test:run

# 前端 Vitest coverage
npm --prefix src run test:coverage

# 前端生产构建
npm --prefix src run build

# 根目录 Playwright
npm run test:e2e

# 指定 Playwright 文件
npx playwright test tests/e2e/09-ppt-generator.spec.js

# VS Code 扩展构建与 Node 测试
npm --prefix vscode-extension test

# VS Code Extension Host E2E
npm --prefix vscode-extension run e2e
```

根目录 `package.json` 只定义 `test:e2e`。Vite、Vitest、lint 和前端构建脚本位于 `src/package.json`。`Makefile` 的 `make test` 等价于执行项目 pytest 默认收集，`scripts/test.sh` 会执行 `pytest tests/ -v --tb=short`，范围还包含 `tests/` 根部测试文件。

## 配置事实

- pytest 主配置位于 `pyproject.toml`，默认收集 `tests/unit` 与 `tests/integration`，启用 `asyncio_mode=auto` 和 strict markers；`configs/pytest.ini` 是兼容配置并额外声明 `slow`、`selenium` 与 300 秒 timeout。
- Vitest 配置位于 `src/vite.config.js`，使用 `jsdom`、globals 和 v8 coverage。
- 根目录 `playwright.config.js` 和 `src/playwright.config.js` 都指向 `tests/e2e`，默认 base URL 为 `http://127.0.0.1:3000`，默认 Chromium；CI 重试 2 次并使用单 worker。
- `configs/playwright.config.js` 是多浏览器配置，包含 Chromium、Firefox 和 WebKit，执行时需要显式指定该配置。
- 浏览器流程通常需要 Vite；涉及真实 API 的用例还需要 FastAPI、Redis、数据库和测试账号。
- 根目录与 `src/node_modules` 各有 Playwright 依赖。执行 `tests/e2e` 时应让 CLI 和测试文件解析到同一份 `@playwright/test`，避免重复加载冲突。

## 已记录验收结果

### 2026-09-02 至 2026-09-03 当前记录

- 后端 unit/integration 完整回归：`1784 passed, 2 skipped`。该记录覆盖本地基础依赖，不代表生产端口、Nginx、Celery 或多 worker 链路。
- 前端全量 Vitest：`36 passed`；Vite 生产构建成功。
- PPT 专项单元回归：`141 passed`。
- `elegant` 主题统一生成：`24 passed`；6 页 PPTX、PDF 和 PNG 样稿生成成功，证据页与路线页二轮视觉评分分别为 `9.0/10` 和 `8.5/10`。
- VS Code 扩展 TypeScript 构建成功，Node 原生测试：`62 passed`。
- VS Code Extension Development Host E2E 已验证扩展发现、激活、兼容性握手、Agent Workbench 打开和工作区加载。原始 npm E2E 在当时无头环境受 `xauth` 影响，复用已启动 Xvfb 后完成验收。
- 真实 Agent/PPT HTTP 与 WebSocket 验收覆盖 HTML 生成、PPTX 下载、进度事件和错误格式请求 404 隔离。

### 保留的历史记录

- 历史云端单元记录：`1605 passed, 2 skipped`，当时排除了 Redis、数据库和 FAISS 外部条件。
- P4.4 历史专项：状态迁移、核对、切换、worker recovery、SQL replay、快照恢复和跨用户所有权 `16 passed`；认证、核心导航、Workflow、PPT 浏览器验收 `34 passed`；API 路由契约 `3 passed, 2 skipped`。
- Agent 能力 Playwright 历史记录为 `23 passed`，无认证综合诊断为 `6 passed`，历史会话整组为 `5 passed`。真实模型 Agent 曾有 `2 skipped`，原因是测试环境缺少 `TEST_API_KEY`。
- 2026-06-09 的目录快照为 88 个单元文件、2 个集成文件和 77 个 E2E spec；该快照已被当前目录规模替代，仅作为演进记录保留。

## 验证边界

- `/api/v1/health` 覆盖数据库和 Redis，未覆盖 Celery worker 在线状态。
- 进程内 ASGI 测试无法证明真实端口、Nginx、broker、共享产物卷和多 worker 行为。
- `scripts/verify-integration.sh` 主要提供静态、语法和配置级证据。
- 模型供应商调用、认证 E2E、PPT Celery、VS Code Extension Host 和跨进程 StateGraph 恢复需要对应环境单独验收。
- 验收数字必须连同命令、范围、依赖条件和日期引用。
