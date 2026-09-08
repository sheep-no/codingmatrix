# 测试指南

## Flutter GitHub 配置适配（2026-09-08）

`GithubClient` 和 `GithubSettingsPage` 已接入 `/api/v1/github/config` GET/POST。定向测试 5/5 通过，包含配置字段映射、原始 Token 不保留在返回模型、窄屏工作台入口和提交状态。当前页面将服务端占位成功显示为“配置已提交，尚未验证绑定”。真实 GitHub 授权、仓库/分支选择、持久化绑定和连接验证等待 D2 契约。

## 候选模块契约盘点（2026-09-08）

已完成聊天、PPT、绘图、工作流和文件上传的路由盘点，结果见 `INTERFACES.md`。聊天存在双轨接口，绘图输入输出尚未确认，工作流使用 NDJSON，上传同时支持完整和分片流程；在 D4 明确前不进行 Flutter 业务页面实现。

聊天第一阶段已完成同步页面和入口接入。Flutter analyze 通过，全量测试 53/53 通过；未进行真实后端联调、流式聊天、历史会话和附件上传验收。

## Android APK 构建验证（2026-09-08）

当前代码已完成 `flutter build apk --release --no-pub`，执行时显式设置 `ANDROID_HOME=/tmp/opencode/android-sdk`。构建耗时 410.7 秒，退出码 0，峰值内存约 2.04 GiB；日志 `/tmp/terminal_term_1788869844986_116.log`。Gradle 的重复目录监听提示未阻断本次构建。

产物：`flutter_client/build/app/outputs/flutter-apk/app-release.apk`，约 51.2 MB，版本 1.0.0 (1)，包名 `com.example.codingmatrix_desktop`。最低 API 24、目标 API 36，包含 arm64-v8a、armeabi-v7a、x86_64。APK v2 签名和 ZIP 完整性校验通过，证书为 Android Debug；校验日志 `/tmp/terminal_term_1788870305414_117.log`。

SHA-256：`9f353f73d9e472d484433132b7638ed08f8fc11168c5325bda881f37d14db276`。

本次未连接 Android 真机或模拟器，安装启动、设备安全存储、真实 API 和下载闭环仍待验收。此包用于测试，正式发布签名待配置。

## Flutter Agent 交付验证（2026-09-08）

`agent_delivery_test.dart` 覆盖决策字典提交、超时 ignored 响应、迟到决策隔离、终态保护、文件查询参数、ZIP 流式保存、中断失败和文件树预览；Widget 测试覆盖停止清理确认。全量 48 项测试通过，静态分析无问题，日志 `/tmp/terminal_term_1788867475340_109.log`。后端定向文件交付测试 4 项通过；当前真实服务到设备链路及新版 APK 待验证。

工作台出现关键决策后点击“处理架构决策”；生成成功返回 project_path 后点击“查看项目文件”。ZIP 保存到应用文档目录（Android 为私有目录），失败文件不作为下载成功产物展示。会话历史与存活任务重连见下节；增量修改和系统分享入口继续未接入。

## Flutter 会话历史与重连（2026-09-08）

Flutter 静态分析无问题，全量 52/52 测试通过；日志 `/tmp/terminal_term_1788869482324_114.log`。新增测试覆盖历史与详情请求、账号/服务切换后的迟到历史响应隔离、显式恢复 409 时仅发送一次请求，以及已完成详情的文件入口和禁用恢复按钮。`git diff --check` 通过。

工作台工具栏“会话历史”入口提供最近 50 条会话、详情刷新、错误信息及项目文件入口。详情仅在后端返回 `reconnectable: true` 时启用恢复，确认后重新查询状态，并携带原 `session_id` 和 `is_resume: true` 连接 SSE。当前进程无存活任务或已有订阅时返回 409，客户端不会自动创建新任务。

后端 `tests/unit/test_flutter_session_history.py` 与 `tests/unit/test_flutter_project_delivery.py` 共 9 项通过，覆盖列表数量限制、详情订阅状态、现有队列重连、结束任务冲突及文件交付。恢复仅接收未消费及后续事件；已消费事件、决策重放和进程重启续跑尚未支持。APK 构建结果见上节；真实 API 联调和设备下载待验证。

## Flutter Provider 接入验证（2026-09-08）

`flutter_client/test/provider_key_test.dart` 覆盖本地生成 RSA 密钥的 OAEP SHA-256 往返、随机密文、管理接口契约、无效测试响应和窄屏删除确认。Agent 流测试断言 `api_key_token` 与 `provider_id`。当前全量 38 项通过，静态分析无问题，日志 `/tmp/terminal_term_1788866099828_107.log`。

操作入口为工作台的 Provider 设置：添加 Key 后选择“用于生成”。Key 默认为 24 小时有效期；原始值仅用于加密提交，授权引用和选择仅存于当前账号内存，可重新拉取服务端列表。真实 Provider、设备操作与本轮 APK 尚待验证。

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

- VS Code 扩展：TypeScript 构建成功，`npm --prefix vscode-extension test` 为 `75 passed`。
- VS Code Extension Development Host：VS Code `1.136.1` E2E 通过，已验证扩展激活、Agent Workbench 打开、兼容性握手和工作区能力。
- 前端相关回归：`23 passed`，生产构建成功。
- PPT 专项回归：`141 passed`；真实 HTTP/WebSocket 验收覆盖 HTML 生成、PPTX 下载、进度事件和格式错误隔离。
- 无头 Linux 环境安装 `xvfb`、`xauth`、`libgtk-3-0`、`libgbm1` 和 `libxkbcommon0` 后，可直接运行 `npm --prefix vscode-extension run e2e` 完成验收。
- 游戏 AI PPT 真实生成 E2E 当前结果为 `1 passed`；运行时曾发现根目录与 `src/node_modules` 的 Playwright 依赖冲突，固定使用根目录 CLI、配置和 Chromium 项目后通过。

## Flutter 认证验证（2026-09-08）

在 `flutter_client/` 使用 SDK `/tmp/opencode/flutter` 执行 `flutter analyze --no-pub`，结果为 `No issues found`；执行 `flutter test --no-pub --concurrency=1 --reporter expanded`，结果为 `34 passed`。验证通过受管后台终端执行，退出码 0，CPU 上限 150%、内存上限 30%、超时 240 秒；最终峰值内存约 748 MiB。日志位于 `/tmp/terminal_term_1788863400873_103.log`。

新增测试覆盖安全存储适配器、重启恢复、访问令牌过期、并发及迟到 401、Cookie 合并和作用域、账号/服务隔离、刷新跨账号拒绝、退出期间在途响应与持久化、清理失败重试、HTTP/网络/JSON 脱敏、写请求禁止自动重发、Riverpod 工作台缓存隔离和退出不调用 stop。设备存储使用插件 mock；真实 KeyStore/Credential Manager/Secret Service、真实后端联调与平台构建仍待单独验收。
