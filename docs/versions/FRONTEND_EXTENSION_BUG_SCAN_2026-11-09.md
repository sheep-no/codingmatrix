# Flutter 客户端与 VS Code 插件 Bug 扫描报告

**扫描时间**: 2026-11-09
**扫描范围**: `flutter_client/`（71 个 `lib/**/*.dart`）、`vscode-extension/src/`（17 个 `.ts` 模块 + 2 个 `.d.ts`）
**参照基线**: `flutter test` → 497 passed；`flutter analyze lib test` → No issues found；插件 `npm run build` + `node --test test/*.test.mjs` → 109 passed / 0 fail
**修复后基线（2026-11-10）**: `flutter test` → 501 passed；`flutter analyze lib test` → No issues found；插件 124 passed / 0 fail；后端相关单测 86 passed / 0 fail（另 1 skipped）
**判定口径**: 仅把已用脚本或真实调用复现的行为列为「已验证」；仅靠代码阅读得出的列为「静态判定」

---

## 执行摘要

| 编号 | 等级 | 端 | 问题 | 复核结论 | 修复状态 |
|------|------|----|------|----------|----------|
| P0-1 | 严重 | 插件 + 后端 | 本地验证动作无法送达插件，验证结果提交到不存在的接口 | 已验证 | 已修（含后端三项） |
| P0-2 | 严重 | 插件 | HTTP 请求无超时，半开连接使轮询永久挂起 | 已验证 | 已修 |
| P1-1 | 高 | 插件 | 变更型 POST 在 408/429/5xx 自动重放，可能重复执行 | 已验证 | 已修 |
| P1-2 | 高 | 插件 | 编排流 POST 在 5xx 被重放，缺少幂等保护 | 已验证 | 已修 |
| P1-3 | 高 | 插件 | 畸形 SSE 帧直接中断整条事件流 | 已验证 | 已修 |
| P1-4 | 高 | 插件 | 无令牌刷新、无重新握手，30 分钟后永久离线 | 静态判定 + 契约核对 | 部分修复（410 重握手已加，令牌刷新待后端） |
| P1-5 | 高 | Flutter | 退出登录不调用服务端 `/logout`，令牌在 30 分钟内仍有效 | 已验证 | 已修 |
| P2-1 | 中 | 插件 | 真实网络错误（ECONNREFUSED）不触发重试 | 已验证 | 已修 |
| P2-2 | 中 | 插件 | webview 请求 pending 表无超时，条目泄漏且 Promise 永不结算 | 静态判定 | 已修 |
| P2-3 | 中 | 插件 | 动作 ack 接口从未调用，重启后 in-flight 动作被重放 | 静态判定 | 已修（拒绝动作不 ack，保留待重放） |
| P2-4 | 中 | Flutter | `AuthState.copyWith` 不透传 `isRestoring` | 静态判定 | 已修 |
| P2-5 | 中 | Flutter | `apiBaseUrlProvider` 从不更新，偏好作用域键使用默认地址 | 静态判定 | 已修 |
| P2-6 | 低 | 插件 | 无配置变更监听，修改设置需手动重连 | 静态判定 | 已修 |

---

## P0 级

### P0-1 本地验证链路四处断裂，功能端到端不可用

**影响**: 云端把 `local_runtime` / `local_e2e` 验证交给插件执行的设计完全没有落地。用户看到的「等待本地验证」无法推进。

**证据 1：结果提交地址在后端不存在**

`vscode-extension/src/connection.ts:154-155` 定义默认路径，`submitParsedResult`（`connection.ts:577-585`）使用 `resultsPath`：

```ts
const DEFAULT_RESULTS_PATH = "/api/v1/agent/local-validation/results";
```

后端全部路由中不存在该路径。`app/api/v1/agent_host.py` 只提供 `/agent/host/sessions/{id}/events`，全仓 `rg "local-validation" app` 无命中。

复现脚本 `/tmp/opencode/verify_result_path.mjs`（用握手成功 + 该路径 404 模拟真实后端）：

```
REJECTED request_failed 404 cloud request failed with status 404: Not Found
PENDING_QUEUE 0
CALLS ["POST .../agent/host/handshake", "POST .../api/v1/agent/local-validation/results"]
```

404 被归类为 `request_failed`，`submitResult` 只对网络错误落队（`connection.ts:526-537`），因此结果既不送达也不进重试队列，直接丢弃。

**证据 2：后端下发的动作载荷缺少插件必需字段**

后端在 `app/agent/workflow_registry.py:173-184` 生成的 pending action 只有 `type/scopes/status/source_revision`，经 `app/api/v1/agent_host.py:96-113` 补充 `action_id/session_id/task_id/revision/workspace_id`。插件 `parsePendingAction`（`protocol.ts:197-233`）强制要求 `command`、`requested_by`、`timeout_seconds`、`working_directory`、`validation_scope`、`operation`。

复现脚本 `/tmp/opencode/verify_local_validation_chain.mjs` 用后端真实载荷形状驱动插件运行时：

```
POLL_REJECTED ProtocolError invalid_payload command must be a non-empty string array
```

插件在解析阶段即抛错，`pollOnce`（`agent-host-runtime.ts:255-264`）不捕获，整轮轮询失败。

**证据 3：会话 ID 不一致，动作根本不会入队**

插件编排流用客户端生成的会话号（`extension.ts:26`、`:57`、`:162`，形如 `vscode-agent-<workspace>-<ts>`），Agent Host 用的是握手返回的 uuid（`app/api/v1/agent_host.py:257`）。`dispatch_state_actions(session_id)` 按编排会话号查 `_sessions`，而 `_sessions` 以握手 uuid 为键；`app/agent/host_action_dispatch.py:25-36` 把 `KeyError` 静默吞掉，因此动作从未投递。

**证据 4：插件从不请求本地验证**

`required_validation_scopes` 默认空列表（`app/api/v1/ai_agent/schemas.py:157-161`），插件与 Flutter 都未发送该字段（全仓 `rg required_validation_scopes` 仅命中后端与测试）。默认请求下 `state.pending_actions` 为空，链路连起点都不会触发。

**修复建议**

1. 统一结果提交走 `/api/v1/agent/host/sessions/{session_id}/events`，把 `LocalValidationResult` 包装成 `kind:"tool_result"` 的 envelope，复用已有的 `message_id` 去重（`agent_host.py:383`）。
2. 后端在 `enqueue_state_actions` 里完成 `{type, scopes}` 到插件 `PendingAction` 的翻译：补齐 `command`、`operation`、`working_directory`、`timeout_seconds`、`requested_by`。
3. 让编排会话号与 Host 会话号一致，或者让 `dispatch_state_actions` 支持从编排会话映射到已握手的 Host 会话。
4. 插件在请求里显式传递 `required_validation_scopes`，或者后端按策略自动填充。
5. 为上述四条各补一条端到端用例，先红后绿。

**修复进展（2026-11-10）**

- 已完成（插件侧）：`submitResult` 在存在 Host 会话时改为提交 `POST /api/v1/agent/host/sessions/{session_id}/events`，包装成 `kind:"tool_result"`、`message_id` 为 `<action>:result`、`payload` 为原始结果；无 Host 会话时才回退旧 `resultsPath`。执行结果被云端接受后调用 `actions/ack` 清理 in-flight；结果仅入队（`status:"queued"`）时保留动作以便重放。
- 已完成（插件侧）：排队结果会连同提交上下文（`messageId`/`capability`/`policyVersion`）一起持久化，重新握手后按当时的 action 重新封装 `:result` envelope 并发送到新的 Host 会话，避免上下文丢失导致 ack 与去重失配。
- 已完成（插件侧）：`request` 的超时同时覆盖响应体读取，头部到达但响应体停住时也会以 `network_unavailable` 失败，轮询不会再次永久挂起。
- 已完成（后端侧）：`enqueue_state_actions` 由 `detect_toolchain` 按 scope 选择命令，补齐 `event_id`/`schema_version`/`validation_scope`/`operation`/`command`/`working_directory`/`timeout_seconds`/`requested_by`；无可用命令时不下发会导致插件解析失败的动作。
- 已完成（后端侧）：新增 `bind_workflow_session` 建立「稳定会话号 → Host 会话」映射并校验 owner，重握手会解除旧 Host 会话的绑定；`enqueue_state_actions` 与 events `tool_result` 均按该映射路由，workflow checkpoint 仍以稳定会话号为键，断点续传不受影响。
- 已完成（后端侧 + 插件侧）：`OrchestratorRequest`/`ModifyRequest` 新增 `host_session_id` 与 `required_validation_scopes`，modify/orchestrate/stream 在调用 `run_workflow` 前完成绑定，scopes 经 schema 校验去重后写入 workflow metadata；插件在 `enable_validation` 时注入这两个字段。
- 回归结果：`test_agent_host_api.py` 26 passed、`test_orchestrator_validation_scopes.py` 13 passed，关联后端用例合计 86 passed / 1 skipped；插件 `npm run build` 通过、124 passed。
- 已完成（端到端）：用真实后端动作驱动插件运行时跑通全链路。后端 `run_workflow` 产出 `local_runtime` 动作（`command: ["npm","run","test"]`、`operation: unit_test`），插件 `AgentHostRuntime.poll()` 解析并执行成功（`status: passed`、`exit_code: 0`），结果以 `kind:"tool_result"` 提交回 `POST /agent/host/sessions/{id}/events`，workflow 由 `waiting_local_validation` 推进到 `completed`。
- 已完成（多 scope 回归）：新增 `test_multiple_validation_scopes_run_one_round_at_a_time`，验证 `local_runtime`、`local_e2e` 两个 scope 每轮只下发一条动作、各自带正确 `validation_scope`，全部回传后 workflow 完成且动作队列清空。

---

### P0-2 请求无超时，半开连接使轮询永久挂起

**影响**: 服务端接受 TCP 连接后不返回响应时，插件的整个轮询循环停在一次 `await` 上，不再恢复。

**证据**

- `CloudConnection.request`（`connection.ts:586-640`）只透传 `AbortSignal`，没有超时包装。
- `nodeFetch`（`node-fetch.ts:5-40`）同样没有超时，只在 `signal.aborted` 时 `destroy`。
- 轮询循环 `extension.ts:375-390` 串行 `await hostRuntime.poll()`，`pollOnce` 等待 `fetchAgentHostActions` 返回；请求不返回则 `finally` 不执行，后续 `setTimeout` 永不安排。

实测（`/tmp/opencode/verify_no_timeout_recheck.mjs`）：启动一个接受连接但不响应的服务端后调用 `fetchPendingActions()`，4 秒竞速仍为 `HUNG`，请求没有自行结束。同样场景下 `webview-bridge.ts:42` 的 `request(timeoutMs=10_000)` 有超时保护，说明仓库已有正确范式。

**修复建议**

在 `request` 内为每次 fetch 增加可配置超时（默认 10-15 秒），超时后走现有 `network_unavailable` 分支并允许重试；`streamAgentPrompt` 使用独立的空闲超时，避免误伤长流。

---

## P1 级

### P1-1 变更型 POST 自动重放

**位置**: `connection.ts:612-621`、`:676-678`

`isRetryableStatus` 对 408、429、≥500 一律返回可重试，`request` 不区分方法。已验证：`controlSession("cancel")` 遇到 503 时发出 2 次 POST，第二次成功并返回结果。

受影响操作包括 pause/resume/cancel、快照回滚、历史删除、缓存清空、决策提交、结果提交。重复执行可能造成错误状态或误删。读取操作用 408/429/5xx 重试则符合预期。

**修复建议**: 仅对 GET/HEAD 重试；变更型请求遇到 408/429 时返回可操作错误，由用户决定重试。

### P1-2 编排流 POST 在 5xx 被重放

**位置**: `connection.ts:481-486`

`streamAgentPrompt` 复用同一个 `request`，`isRetryableStatus` 对 5xx 的重试与方法无关，因此流式 POST 会被重发。真实 HTTP 复现（`/tmp/opencode/recheck_stream_503.mjs`）：首次返回 503，本应只发 1 次，实测发出 2 次 POST，第二次返回 200 后正常收到 `done`。

与 P1-1 不同，直接连接错误不会重放：生产 `nodeFetch` 抛普通 `Error`，`isNetworkError` 返回 false（见 P2-1）。已验证真实 socket reset 时 `posts = 1`。

风险场景：反向代理在已把首次请求转发给后端之后返回 503（后端已建任务、代理判定失败），插件重放会再建一次订阅。后端有「每用户一个 running 会话」与「活跃连接返回 409」守卫，能拦住大部分重复；一旦首次任务的连接状态被判定为 stale，`_supersede_running_generation` 会停掉旧任务再启动新任务，用户看到的是任务被打断。

**修复建议**: 流式编排请求禁用 5xx 自动重试，失败后提示用户从会话历史确认或恢复。

### P1-3 畸形 SSE 帧中断整条流

**位置**: `connection.ts:502-509`、`:670-674`

`parseStreamEvent` 直接 `JSON.parse`，无 `try/catch`。已验证：`data: {not-json}` 使流以 `stream failed: SyntaxError` 终止。

对比 Flutter `sse_parser.dart:60-72` 会把解析失败降级为 `message` 事件继续消费。插件一旦遇到单个坏帧，后续 `done`/`error` 全部丢失，面板停在中间状态，服务端任务继续运行。

**修复建议**: 解析失败时跳过该帧或转成可记录的诊断事件，保持消费循环继续。

### P1-4 无令牌刷新与重新握手，30 分钟后永久离线

**位置**: `extension.ts:190-195`、`:273-287`、`:375-390`

- 访问令牌 30 分钟过期（`app/core/config.py:47`、`app/utils/security.py:79-84`），插件把 `accessToken` 作为构造参数固定传入，没有刷新逻辑。
- Host 会话 30 分钟过期（`app/api/v1/agent_host.py:257`、`:304-305` 返回 410），插件不重新握手；`heartbeat` 路由（`:427-449`）只刷新 `ProjectSession.last_activity_at`，不会延长 Host 会话的 `expires_at`，且插件从不调用它（全仓 `rg heartbeat src` 仅命中前端事件过滤）。
- 过期后每次请求抛错，`poll` 的 `catch` 只把状态置为 offline（`extension.ts:381-385`），下一轮仍用同一失效凭据与失效会话，永久离线。

**修复建议**: 401 时用 refresh token 刷新；410 时重新握手并更新 `connection.sessionId`；后端如需长会话，应在 heartbeat 或任意已认证 Host 请求中滑动延长 `expires_at`。

### P1-5 Flutter 退出不撤销服务端令牌

**位置**: `flutter_client/lib/infrastructure/auth/cloud_auth_client.dart:310-319`

`logout()` 只做本地清理：`_epoch++`、清空内存会话、清 Cookie、删本地凭据。全仓 `rg "/logout" flutter_client/lib` 无命中。既有测试 `test/auth_session_test.dart:538-559`「logout during refresh fences late response and never calls backend logout」断言的是刷新竞态下不发请求（该场景合理），但普通退出路径同样不发，属于缺口。

后端实际已提供 `POST /api/v1/logout`（路由 `app/api/v1/auth.py:517`，前缀注册见 `app/main.py:327`），会写入 Redis 吊销黑名单。文档 `.monkeycode/docs/INTERFACES.md:38` 原记录的「服务端 logout 接口尚未找到」已与代码不符，本轮已更正。

**影响**: 退出后旧 access token 在剩余有效期（最长 30 分钟）内仍可用。

**修复建议**: `logout()` 在清理本地状态前调用一次 `POST /api/v1/logout`（需 Bearer 与 `X-CSRF-Token`，`auth.py:517-521`），失败也继续本地清理；刷新竞态场景保持静默，仅补普通退出的调用。

---

## P2 级

### P2-1 真实网络错误不触发重试

**位置**: `connection.ts:623-634`、`:680-683`

`isNetworkError` 只认 `CloudConnectionError(network_unavailable)` 与 `TypeError`。生产默认 `nodeFetch` 在连接拒绝时抛普通 `Error`（`node-fetch.ts:33`），因此重试分支不进入。已验证：连接拒绝时 `attempts:1`，直接返回 `network_unavailable`。

`submitResult` 的落队分支仍然有效（外层已包装为 `CloudConnectionError`），实测返回 `{status:"queued"}`，队列计数 1。故影响限于「可恢复的网络抖动不会重试」。

**修复建议**: 识别 `Error` 上的 `code`（`ECONNRESET`、`ECONNREFUSED`、`ETIMEDOUT`、`EPIPE`）或统一在 `nodeFetch` 中包装为 `CloudConnectionError`。

### P2-2 webview pending 表无超时

**位置**: `workbench-html.ts:119-125`

`request` 把 `resolve/reject` 存入 `pending`，仅在收到 `workbench_response` 时删除（`:425-430`）。宿主 `handleRequest`（`agent-workbench.ts:184-205`）在 `onRequest` 挂起时不发响应；结合 P0-2 的无超时云端请求，条目与 Promise 永久悬挂，`runRequest` 的错误处理永不触发。

**修复建议**: 给 `request` 增加超时并在超时时删除条目、reject；宿主侧为 `onRequest` 增加总超时。

### P2-3 动作 ack 从未调用

**位置**: `app/api/v1/agent_host.py:355-370`；插件全仓无 `actions/ack` 调用

后端拉取动作时把 pending 移入 in-flight（`:344-352`），仅当收到 `message_id` 以 `:result` 结尾的 `tool_result` 才清理（`:414-423`）。插件 `fetchAgentHostActions`（`connection.ts:206-213`）拉取后不 ack；本地验证结果又走 P0-1 的错误路径，这两类动作会永久留在 in-flight。进程重启时 `_get_session` 把 in-flight 重新放回 pending（`:309-314`），历史动作会被再次执行。非验证类动作经 `submitEvent` 提交 `:result` 事件，不受影响。

**修复建议**: 动作执行完成后调用 ack，或在结果提交成功后按 `action_id` 清理。

### P2-4 `AuthState.copyWith` 丢字段

**位置**: `flutter_client/lib/application/auth_controller.dart:24-36`；消费点 `lib/app.dart:58`

`copyWith` 不接收也不透传 `isRestoring`，返回的新状态恒为默认 `false`。`onSessionChanged`（`:42-50`）与 `logout`（`:107-109`）构造状态时另有处理，当前 `restore()` 路径暂未触发可见故障；这是字段级隐患，一旦恢复期间调用 `copyWith`，`app.dart` 会提前切到登录页。

**修复建议**: 增加 `isRestoring` 参数并透传，补一条恢复期间调用 `copyWith` 的回归用例。

### P2-5 base URL provider 从不更新

**位置**: `flutter_client/lib/application/auth_controller.dart:147-149`、`generation_flags_controller.dart:52-55`

`apiBaseUrlProvider` 默认 `http://127.0.0.1:8080`，全仓无 `.notifier` 写入。用户登录其他地址时 `CloudAuthClient.baseUrl` 更新，provider 保持默认值。业务请求走 `auth.baseUrl` 不受影响，但偏好作用域键 `'$baseUrl|${session.username}'` 使用默认地址，不同服务器上的同名账号会共用同一份生成开关偏好。

**修复建议**: 登录成功后写入真实 origin，或者偏好键改用 `CloudAuthClient.baseUrl`。

### P2-6 无配置变更监听

**位置**: `vscode-extension/src/extension.ts`（全仓无 `onDidChangeConfiguration`）

修改 `codingmatrix.agent.apiUrl` / `accessToken` 后不会自动重连，需要执行 `codingmatrix.reconnectAgentSession` 或重载窗口。

**修复建议**: 监听相关配置项，变化时调用现有 `reconnectConfiguredSession`。

---

## 已复核为正常的点

为避免误报，以下曾被怀疑的项经实跑或契约核对后确认无缺陷：

| 项 | 结论 |
|----|------|
| `AgentStreamClient` 认证与超时 | 生产注入的是 `AuthenticatedClient`（`workbench_controller.dart:458-462`），`open()` 走 `httpClient.send()`，`_send` 统一注入 Bearer/CSRF、做 401 刷新与代际检查；流空闲超时取 `auth.timeout`（20 秒），后端每 5 秒发心跳，正常场景足够。5 分钟 `streamTimeout` 只作用于 chat 的 `sendJsonStream` |
| Flutter SSE 畸形帧 | `sse_parser.dart:60-72` 捕获 `FormatException` 并降级为 `message` 事件，流继续 |
| webview XSS | `workbench-html.ts` 全量使用 `textContent`，无 `innerHTML` |
| 决策提交契约 | Flutter `{choices}` 与插件 `Record<string,string>` 均与后端 `dict[str,str]` 一致（`orchestrate_endpoints.py:2227-2247`） |
| `submitResult` 网络落队 | 真实 `nodeFetch` 连接拒绝时仍正确返回 `{status:"queued"}`，持久化队列可用 |
| `nodeFetch` 流中断 | abort 后读者收到 `error:aborted`，回落行为正常 |

---

## 复现与验证命令

```bash
# Flutter 基线
cd flutter_client
/tmp/opencode/flutter-sdk/flutter/bin/flutter test
/tmp/opencode/flutter-sdk/flutter/bin/flutter analyze lib test

# 插件基线
cd vscode-extension
NODE_OPTIONS=--dns-result-order=ipv4first npm run build
NODE_OPTIONS=--dns-result-order=ipv4first node --test test/*.test.mjs

# P0-1 结果路径
node /tmp/opencode/verify_result_path.mjs

# P0-1 动作解析
node /tmp/opencode/verify_local_validation_chain.mjs

# P2-1 真实网络错误
node /tmp/opencode/verify_submit_real_network.mjs

# P0-2 无超时
node /tmp/opencode/verify_no_timeout_recheck.mjs

# P1-1 变更型 POST 重放 / P1-2 5xx 流重放
node /tmp/opencode/recheck_503_real.mjs
node /tmp/opencode/recheck_stream_503.mjs

# P1-3 畸形 SSE
node /tmp/opencode/recheck_sse.mjs
```

---

## 修复优先级建议

1. 先修 P0-1：这是「本地验证」功能的唯一通路，四处断裂需要一起改，否则单点修复仍不可用。
2. 再修 P0-2：给所有云端请求补超时，顺带解决 P2-2 的上游悬挂。
3. 然后修 P1-1 / P1-2：把重试策略按方法收敛，消除重复副作用。
4. P1-4 / P1-5 涉及认证生命周期，建议与后端令牌刷新、Host 续期一起排期。
5. P2 项可随对应模块迭代顺带处理。
