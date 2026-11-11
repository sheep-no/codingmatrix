# Frontend 第 165 轮四批次复扫记录

> 版本：v0.4 | 扫描日期：2026-11-10 | 状态：扫描完成，阶段 0-3 已修复（容器与 CI 实跑待环境复验）
> 归属：前端应用第 165 轮复扫
> 基线：`frontend_bootstrap.md`、`frontend_state.md`、`frontend_surface.md`、`frontend_batch_rescan.md`、`frontend_batch_rescan_164.md`
> 范围：入口认证、状态与组合逻辑、视图与 API 契约、构建测试部署
> 证据口径：静态源码 + 全库引用 + 后端路由核对。未启动 Vite、FastAPI、Docker、Nginx、浏览器。

## 1. 扫描方法

本轮按四批次独立复核，每个文件先判定三态（活跃 / 未接入 / 废弃），再用全库 `rg` 核对生产消费方、后端路由、配置引用和测试入口，最后跨批次去重并回写旧 ID 状态。

| 批次 | 范围 | 复核重点 | 结果 |
|---|---|---|---|
| 一 | `src/components`、`src/views`、模板交互 | 登出、登录后刷新、错误态、弹窗语义、表单标签 | 新增 4 项 |
| 二 | `src/utils/api`、后端路由 | 命名空间、同名覆盖、参数契约、响应形状 | 新增 4 项 |
| 三 | Vite、ESLint、CI、Docker、Nginx、Compose | 镜像构建、WS 代理、测试门禁、拓扑漂移 | 新增 4 项 |
| 四 | token、Pinia 持久化、跨账户缓存 | 注销清理、会话恢复、图片历史与本地缓存 | 新增 7 项 |

## 2. 旧编号状态校准

行号以本轮实码为准，历史文档中的行号普遍漂移。

| 编号 | 状态 | 本轮证据 |
|---|---|---|
| FEBOOT-01 | 已修 | `src/router/index.js:105-120` 的 `resolveRouteAccess` 对 `requiresAuth` 无 token 时返回首页并带 `redirect`。 |
| FEBOOT-02 | 已修 | `src/vite.config.js:87-89` `build.outDir: 'dist'`，产物 `src/dist` 与 Nginx 静态根目录一致。 |
| FEBOOT-03 | 已修 | `src/utils/tokenManager.js:11-12,120-165` 使用 `inFlightRefresh` 单飞刷新。 |
| FEBOOT-04 | 已修 | `src/composables/useAuth.js:29` 注册走 `/register`。 |
| FEBOOT-05 | 已修 | `src/App.vue` 背景合并为单条带 fallback 声明。 |
| FESTATE-01 | 已修 | `src/stores/agentSession.js:149-165,237-254` 提供真实快照保存与恢复。 |
| FESTATE-02 | 已修 | `src/components/index.vue:836-842` 注册离线发送回调，`useOfflineQueue.js:87-103` 挂载补发。 |
| FESTATE-03 | 已修 | `src/components/SystemLogs.vue:411-429` 使用 `toRefs` 后的 refs 监听。 |
| FESTATE-04 | 已修 | `src/composables/useAgentStreaming.js:6,473` 接入 `sseParser.js`。 |
| FESTATE-05 | 已修 | `useAgentBackend.copySettingsToClipboard` 已 `await` 并处理失败。 |
| FESTATE-06 | 已修 | `src/stores/navigation.js:203-206` 的 `activeTool` 覆盖 `projectGenerator`。 |
| FESTATE-07 | 已修 | `src/stores/github.js` 仅持久化用户名与开关，token 留在内存。 |
| FESURF-001 | 已修 | `src/utils/api/index.js:87` 显式创建 `ppt` 命名空间。 |
| FESURF-002 | 已修 | `src/utils/request.ts` 已删除，`src/api/apikey.js` 走统一客户端。 |
| FESURF-003 | 已修 | `src/utils/api/websocket.js:47,51,98-110` 保存 token 并区分主动断开。 |
| FESURF-004 | 已修 | `admin.js` 的 `renameService`/`updateFuseConfig` 已按三参签名返回 JSON。 |
| FESURF-005 | 已修 | `downloadBackup` 返回备份数据，`ResourceControl.vue` 按数据消费。 |
| FESURF-006 | 已修 | `toggleReview` 已删除。 |
| FESURF-007 | 已修 | `base.js` 请求与流式请求均合并调用方 headers。 |
| FRESCAN-24 | 已失效 | `src` 下现有 70 个 `*.test.js`，“测试入口为空”不再成立；问题转为 CI 不执行测试，见 FRESCAN-66。 |
| FRESCAN-25 | 部分失效 | `src/package.json:40` 已声明 `@playwright/test`；两份 Playwright 配置仍并存（根 `playwright.config.js:1-40`、`src/playwright.config.js:1-33`），版本为 `1.64.1` 与 `^1.62.1`。 |
| FRESCAN-29 | 保留 P2 | `src/views/PPTPreview.vue:83-92` 失败与空数据仍共用「暂无幻灯片数据」，`:266-277` 静默返回 false。 |
| FRESCAN-34 | 保留 P2 | 标签关联缺口仍存在，本轮扩大证据见 FRESCAN-67。 |
| FRESCAN-35 | 已失效（误判） | 原文称组件已删除；实际 `UserManagement.vue`、`VirtualGirl.vue`、`ServiceManager.vue` 均存在且挂载（`AdminPanel.vue:531,541`）。缺口转为 FRESCAN-63。 |
| FRESCAN-36 | 已修 | `APIKeyManager.vue:294-302` 与 `DynamicProviderManager.vue:158-166` 均写入 `loadError` 并用 `role="alert"` 展示。 |
| FRESCAN-44 | 已修 | `.github/workflows/frontend-ci.yml` 的 `paths` 已扩展到 `src/**`、`configs/nginx*.conf`、`Dockerfile`、`docker-compose*.yml`，由 `src/tests/frontend-ci-contract.test.js` 锁定。 |
| FRESCAN-46/47/48 | 已修 | `src/stores/user.js:74-88` 注销清理 Agent、API Key、供应商、模型覆盖与日志状态。 |
| FRESCAN-49 | 已修 | `src/utils/api/websocket.js:47-51,98-110` 的 `_manualClose` 守卫生效。 |
| FRESCAN-50 | 已修 | `src/utils/api/kolors.js` 的 `getHistory` 已改发 `page_size`，并由 `src/utils/api/kolors.test.js` 锁定；第 165 轮阶段 2 随 FRESCAN-70 完成。 |
| FRESCAN-51 | 已修 | `src/utils/api/aicloud.js` 的 `searchHistory` 改发后端要求的 `keyword`，`src/utils/api/aicloud.test.js` 新增参数契约用例，回退源码后失败。 |

## 3. 新增问题

### 批次一：入口认证与组件交互

#### FRESCAN-53 [P1] 管理员面板登出绕过服务端吊销和 store 清理

- 定位：`src/components/AdminPanel.vue:922-935`。
- 缺陷：只删除 `access_token` 与 `permission_level` 后 `router.push('/')`，未调用 `api.logout()`、未调用 `userStore.clearUser()`、未清理 `tokenManager` 内存态与 `permissionLevel` ref。
- 影响：access token 在剩余有效期内仍可被服务端接受；前端 `isLoggedIn`、`permissionLevel` 保持旧值，路由守卫继续认为当前是超管；同浏览器持久化缓存全部保留。其他页面登出路径（`leftlist.vue:694-704`、`useAuth.js:44-53`）都已清理 store，管理面板成为唯一例外。
- 证据：实码可证；token 实际吊销需运行验证。
- 修复状态：已修复。`handleLogout` 在用户确认后调用 `api.logout()`，随后断开 WebSocket、执行 `userStore.clearUser()` 并跳转 `/`；服务端吊销失败仍完成本地清理。新增 `src/components/AdminPanel.logout.test.js` 三条用例，回退源码后对应用例失败。

#### FRESCAN-54 [P1] 首页未绑定左栏登录/登出事件导致登录后历史不刷新

- 定位：`src/components/index.vue:22-33`；`src/components/leftlist.vue:374,389,641-642,703`。
- 缺陷：`Leftlist` 声明了 `login`/`logout` 事件并实际 `emit`，父组件只绑定 `select-history`、`delete-history`、`new-conversation`、`use-tool`。
- 影响：登录成功后左栏不重新执行 `fetchHistory`，历史列表保持登录前的空状态，用户需要刷新页面；登出后父组件也不会重置会话状态。
- 证据：实码可证；登录后的列表表现需浏览器确认。
- 修复状态：已修复。`index.vue` 绑定 `@login`/`@logout`：登录后清空当前会话与 `conversationHistoryMap` 并调用 `leftlist.fetchHistory(true)`，登出后重置工作区并 `navigationStore.hideAllTools()`。`index.test.js` 新增两条用例，回退源码后失败。

#### FRESCAN-63 [P2] 管理页与虚拟姬弹窗缺少 dialog 语义和键盘退出

- 定位：`src/components/UserManagement.vue:136,175,210,234`；`src/components/ServiceManager.vue:251,306,346`；`src/components/VirtualGirl.vue:261`。
- 缺陷：弹窗根节点只有 `modal-overlay`/`modal-content` 样式类，缺少 `role="dialog"`、`aria-modal`、标题关联、Escape 关闭与焦点回归；共享组件 `src/components/ui/Modal.vue:7-8` 已具备这些语义。
- 影响：屏幕阅读器无法识别弹窗边界，键盘用户无法用 Escape 关闭；同一交互出现两套实现。
- 证据：实码可证；读屏行为需辅助技术实测。
- 修复状态：已修复。新增共享 composable `src/composables/useDialogA11y.js`（Escape 关闭、Tab 首尾循环、`visible` 变化时焦点进入与回归）；`UserManagement.vue`、`ServiceManager.vue`、`VirtualGirl.vue` 的 8 个弹窗补齐 `role="dialog"`、`aria-modal`、`aria-labelledby`、`tabindex="-1"` 并接入该 composable。`useDialogA11y.test.js`、`UserManagement.test.js`、`ServiceManager.test.js` 覆盖键盘与属性；回退源码后相关用例失败。

#### FRESCAN-64 [P2] 首页挂载的多个工具组件没有任何 UI 入口

- 定位：`src/components/index.vue:111-145,221-229`；`src/stores/navigation.js:19,30,43-52,169-190`。
- 缺陷：`TaskQueue`、`ServiceManager`、`Aicloud`、`ProjectGenerator`、`EphemeralWorkflow`、`ImageGenerator` 六个组件由 navigation store 标志控制挂载，但 `leftlist.vue:80-270` 的工具菜单只提供图表、Docker、Nginx、管理台、虚拟姬、PPT、AI 绘画、临时工作流与搜索历史入口；`showTool` 虽有对应分支，全库没有 UI 写入（`ImageGenerator` 的 AI 绘画入口走 `window.open('/image-generate')` 打开独立路由，不设置该标志）。
- 影响：`ProjectGenerator` 的恢复逻辑还在 `navigation.js:19,176` 被强制置 false；`bottominput.vue:253` 仍读取该恒 false 状态作为输入模式条件，形成无效分支。相关组件缺陷无法通过正常交互触达。
- 判定：属于未接入/接线缺失，按结构事项记录，不按活跃运行缺陷计数。
- 修复状态：已修复。出口统一为路由或管理台：`TaskQueue` 加入 `leftlist.vue` 工具菜单；`ServiceManager` 仅由 AdminPanel 的 `service-manager` 菜单进入；`Aicloud`、`ImageGenerator`、`ProjectGenerator` 有独立路由，故从 `index.vue` 卸载，并删除 `navigation.js` 中对应标志、`activeTool` 分支与持久化字段。`EphemeralWorkflow` 经全库复核没有任何路由或宿主引用（`/workflow` 渲染的是 `views/Workflow.vue`），已在卸载后成为未接入组件，保留文件待死代码清理批次处理。`bottominput.vue` 的 `projectGeneratorMode` 死分支一并删除。`navigation.test.js`、`leftlist.test.js`、`index.test.js`、`bottominput.test.js` 覆盖；回退源码后相关用例失败。

### 批次二：API 客户端与后端契约

#### FRESCAN-56 [P2，宿主未接入] `api.aicloud` 命名空间不存在导致整页调用全部抛错

- 定位：`src/utils/api/index.js:90`；`src/components/Aicloud.vue:308,390,404,421,446,467,520,587`。
- 缺陷：工厂返回值被平铺进根对象（`...createAiCloudClient(baseClient)`），只有 `ppt` 显式建了命名空间。八个调用点全部使用 `api.aicloud.*`，运行时读取 `undefined` 后立即 `TypeError`。
- 影响：知识库列表/删除、代码执行、模型列表、历史加载、流式聊天、审查列表全部不可用；`index.vue:123-127` 的挂载存在，入口缺失见 FRESCAN-64。
- 附带：AiCloud 后端全部端点要求 admin（`app/utils/aicloud/permission.py:47-67`，`aicloud.py:100` 等），即使修好命名空间，普通用户仍会收到 403。能力中心的同名平铺方法（`listKnowledgeDocs`、`executeCode` 等）仍可用，见 FRESCAN-62。
- 定级：宿主组件只有 navigation 标志、没有 UI 入口，当前只能由持久化的 `navigationState` 或开发工具触发；按未接入面定 P2。一旦补入口，本项立即升级为 P1。
- 证据：实码可证。
- 修复状态：已修复。`createDefaultClient` 显式挂载 `aicloud: createAiCloudClient(baseClient)`，同时保留平铺方法供能力中心使用。`apiShape.test.js` 断言命名空间与方法存在，回退源码后失败。宿主入口缺失仍见 FRESCAN-64。

#### FRESCAN-57 [P1] `searchKnowledge` 同名覆盖导致普通用户知识库检索失效

- 定位：`src/utils/api/agent.js:80-82`；`src/utils/api/aicloud.js:217-227`；`src/utils/api/index.js:81,90`；`src/views/CapabilityCenter.vue:276-279`。
- 缺陷：两个客户端导出同名方法，`createAiCloudClient` 后展开，覆盖 `createAgentClient` 的版本。最终 `api.searchKnowledge` 请求 `POST /aicloud/knowledge/search`（admin 专用，body `query`），而普通用户应走 `GET /agent/knowledge/search`（参数 `q`）。
- 影响：普通用户在能力中心检索知识库时收到 403，客户端吞错后返回 `{results: []}`，界面表现为“无结果”。管理员路径能返回 `{query, results, total_found}`，与消费方 `.results` 匹配。
- 附带契约缺陷：`agent.js` 默认返回 `{results: []}`，但后端 `knowledge_endpoints.py:77-100` 返回裸数组；即使不发生覆盖，`ProjectGenerator.vue:1239-1240` 读取 `.results` 也恒为空。
- 证据：实码可证；403 表现需登录普通账户实测。
- 修复状态：已修复。客户端组合次序改为 `...createAgentClient` 最后展开，根级 `searchKnowledge` 走 `GET /agent/knowledge/search`；`agent.js` 改用 `q` 参数并把裸数组归一为 `{ results }`；AiCloud 版本保留在 `api.aicloud.searchKnowledge`。`apiShape.test.js`、`agent.test.js` 覆盖两条契约，回退源码后失败。

#### FRESCAN-58 [P1] 快照回滚把标签对象拼进 URL，且后端默认删除分支

- 定位：`src/composables/useAgentBackend.js:246-257`；`src/views/AgentDashboard.vue:138,521`；`src/components/agent/modals/VersionHistoryModal.vue:9`；`src/utils/api/agent.js:39-49`；`app/api/v1/ai_agent/orchestrate_endpoints.py:2003-2010`。
- 缺陷：弹窗发出字符串 `snap.tag`，`AgentDashboard` 原样透传，`useAgentBackend` 改为 `{ tag }` 对象传给 `rollbackToSnapshot(sessionId, tag)`；客户端执行 `encodeURIComponent(tag)` 得到 `%5Bobject%20Object%5D`。
- 影响：回滚请求带错误 `target_tag`，后端查不到快照返回 404。后端 `delete_branch` 默认 `True`，一旦标签匹配会执行破坏性分支删除；参数错误反而阻止了误删。
- 附带：`ProjectGenerator.vue:1187-1188` 使用旧签名 `rollbackToSnapshot(sessionId, tag)` 且传的是字符串，本身正确；但它与 `useAgentBackend` 的调用形态不一致，回归时需同时覆盖两条链。该组件当前不可达（FRESCAN-64）。
- 证据：实码可证；回滚端到端需运行验证。
- 修复状态：已修复。`useAgentBackend` 直接传字符串标签并显式 `deleteBranch: false`；`agent.js` 用 `URLSearchParams` 构造 `target_tag` 与可选 `delete_branch`。`agent.test.js`、`useAgentBackend.rollback.test.js` 覆盖标签与分支参数，回退源码后失败。

#### FRESCAN-65 [P2] GitHub 客户端依赖从未赋值的 store 引用和不存在的前端路由

- 定位：`src/utils/api/github.js:18,32`；`src/utils/api/base.js:51`；`src/utils/api/index.js:70-101`；`src/router/index.js:97-101`。
- 缺陷：token 首选 `window.api?._userStore?.getAccessToken?.()`，但全库没有给 `window.api._userStore` 赋值（`base.js:81` 设置的是 `window.userStore`）；`base.js` 第二优先级分支同样恒空。401 时跳转 `/login`，路由表中无该路径，只由 catch-all 重定向回首页。
- 影响：当前依赖 `localStorage.access_token` 兜底仍能带上 token；一旦 token 只存在于内存或刷新失败，GitHub 面板会以匿名请求 401，并被静默送回首页，用户看不到“会话过期”提示。
- 证据：实码可证；token 失效路径待实测。
- 修复状态：已修复。`base.js` 导出 `handleSessionExpired(store)`，统一执行 `clearUser()` 并广播 `session-expired` 事件；请求与流式请求的 401/4001 分支全部改走该函数。`github.js` 改用 `getValidToken()`，401 不再删除单个键或跳转不存在的 `/login`。`App.vue` 监听事件并弹出会话过期提示。`github.test.js` 覆盖 token 取值与 401；回退源码后相关用例失败。

### 批次三：构建、测试与部署

#### FRESCAN-52 [P0，待实测] 镜像构建引用不存在的 `nginx` 系统账号

- 定位：`Dockerfile:42-48,68-79,96-98,109`；`configs/nginx.conf:7`。
- 缺陷：基础镜像为 `python:3.11-slim`（Debian），`:47-48` 只创建 `appuser`，`:70` 才安装 Debian `nginx` 包；Debian 包使用 `www-data`，不创建 `nginx` 账号。`:98` 执行 `chown -R nginx:nginx /var/log/nginx /var/lib/nginx /var/run`，`nginx.conf:7` 又声明 `user nginx;`。
- 影响：`chown` 在 `nginx` 用户不存在时直接失败，镜像构建中止；若账号存在但配置的 worker 用户不可用，Nginx 也无法启动 worker。
- 证据：静态链路可证；Debian 包账号创建行为与构建结果需在有 Docker 的环境实测。
- 修复状态：已修复，随 FRESCAN-69 拓扑收敛解决。运行镜像不再安装或启动 Nginx，账号创建、`chown nginx:nginx` 与 `nginx.conf` 复制均已删除，构建链不再依赖 `nginx` 系统账号；Nginx 由独立 `nginx:alpine` 服务承担，`configs/nginx.conf:7` 的 `user nginx;` 在该镜像内成立。`docker build` 与容器内 `nginx -t` 仍需在有 Docker 的环境复验。

#### FRESCAN-60 [P2] 生产 Nginx 的 `/api/` 未透传 Upgrade 导致 PPT WebSocket 失败

- 定位：`configs/nginx.conf:103-116`；`src/views/PPTGenerate.vue:908-911`；`app/api/v1/aiGeneratorPptx.py:3732`。
- 缺陷：`/ws/` 配有 `proxy_http_version 1.1`、`Upgrade`、`Connection "upgrade"` 和 86400 秒读超时；`/api/` 只设置 `Connection ""`。PPT 进度 WS 地址是 `/api/v1/ws/ppt/{taskId}`，命中 `/api/` 分支。
- 影响：经生产 Nginx 的握手请求不携带 Upgrade 头，服务端无法完成协议升级，PPT 生成页收不到进度事件；Vite 开发代理 `/api/v1` 已开 `ws: true`（`vite.config.js:62-71`），问题只在生产拓扑出现。
- 证据：配置与地址实码可证；握手失败需 Nginx 实测。
- 修复状态：已修复（待 Nginx 实测）。`configs/nginx.conf` 新增 `map $http_upgrade $connection_upgrade`，`/api/` 分支补 `proxy_http_version 1.1`、`Upgrade`、`Connection $connection_upgrade` 与 86400 秒读超时；新增 `src/tests/nginx-websocket.test.js` 锁定配置，回退源码后该用例失败。经 Nginx 的 101 握手仍需在有 Docker 的环境复验。

#### FRESCAN-66 [P2] 前端 CI 从不执行单元测试，E2E 门禁非阻塞

- 定位：`.github/workflows/frontend-ci.yml:6-11,54-60`；`.github/workflows/e2e.yml:25`；`src/package.json:14`。
- 缺陷：`src` 下已有 59 个 `*.test.js`，`frontend-ci.yml` 只跑 `npm run lint`（实际为 `eslint . --fix`）与 `npm run build`，没有 `npm run test:run`；`e2e.yml:25` 设置 `continue-on-error: true`。
- 影响：任何前端单元回归都不会阻断合并；lint 步骤还会改写源码。`paths` 仍只覆盖 `src/**`，Dockerfile/Compose/Nginx 变更不触发该工作流（FRESCAN-44）。
- 证据：工作流与脚本实码可证；实际 CI 结果未运行。
- 修复状态：已修复（CI 实跑通过）。`src/package.json` 新增只检查的 `lint:check`，`frontend-ci.yml` 在构建前执行 `npm run lint:check` 与 `npm run test:run`，`paths` 扩展到 `configs/nginx*.conf`、`Dockerfile`、`docker-compose*.yml`；新增 `src/tests/frontend-ci-contract.test.js` 断言测试步骤先于构建且不再使用 `--fix`。阶段 3 已评估 E2E：GH runner 的 chromium `page.goto: Page crashed` 属既有基础设施问题（PR #437），check run 会标为 failure 但工作流 run 的 `conclusion` 为 success，因此不阻塞合并；保留 `continue-on-error` 并维持报告可见。

#### FRESCAN-69 [P3] 单镜像运行拓扑与 Compose 拓扑漂移

- 定位：`Dockerfile:107-109`；`docker-compose.yml:35,55-67,102-117`；`docker-compose.prod.yml:18-19,81-82,128-129,196-225`。
- 缺陷：Dockerfile 的 CMD 同时启动 Nginx 与 Uvicorn；两个 Compose 文件都为 `api`/`celery`/`scheduler` 设置 `command:`，覆盖该 CMD，并由独立 `nginx:alpine` 容器提供静态与代理。
- 影响：单镜像拓扑实际不可用也不会被测试覆盖；`docker-compose.yml` 还把 API 绑定到 `127.0.0.1:8080`，期望“只起 api 容器即可访问”的场景不成立。
- 判定：部署结构一致性问题，非当前默认拓扑故障。
- 修复状态：已修复（待容器实测）。`Dockerfile` 删除 Nginx 安装、账号、配置复制与 `nginx && ...` 启动分支，只保留 Uvicorn 的 `CMD` 并改为 `EXPOSE 8080`；基础与生产 Compose 继续由独立 `nginx:alpine` 服务使用 `configs/nginx-upstream-compose.conf` 代理 `api:8080`；宿主机 `scripts/start.sh` 安装 `configs/nginx-upstream-local.conf` 到 `/etc/nginx/conf.d/upstream.conf`。新增 `src/tests/container-topology.test.js` 锁定镜像无 Nginx、两份 Compose 使用 Compose 上游、宿主机脚本安装本地上游；回退 `Dockerfile` 或 `start.sh` 后对应用例失败。`docs/guides/SERVICES.md`、`docs/guides/PRODUCTION.md`、`docs/guides/GETTING-STARTED.md`、`container_runtime.md`、`runtime_cross_review.md` 已同步为单一拓扑描述。

### 批次四：会话边界、缓存与图片历史

#### FRESCAN-55 [P1] 注销清理遗漏六类跨账户浏览器缓存

- 定位：`src/stores/user.js:59-89`。
- 缺陷：`clearUser()` 已清理 token、用户名、Agent 会话、API Key、供应商、模型覆盖与日志状态，仍未清理：`chatState`（`index.vue:354-361`）、`streamRequestState`（`utils/streamManager.js:11`）、`offlineMessageQueue`（`composables/useOfflineQueue.js:4`）、`image-generate-session-v1`（`ImageGenerate.vue:255`，sessionStorage）、`aicloud_session_id`（`Aicloud.vue:433-436`）、`navigationState`（`stores/navigation.js:6,163`）。
- 影响：同一浏览器切换账户后，新账户可能看到上一账户的会话正文、流式恢复提示、离线待发消息、图片生成提示词与结果、AiCloud 会话标识以及打开的工具栏状态；`restoreStateFromStorage`（`index.vue:364-448`）会在挂载时直接复用 `chatState`。
- 证据：写入点与恢复点实码可证；跨账户时序需浏览器验证。
- 修复状态：已修复。`clearUser()` 新增清理 `chatState`、`streamRequestState`、`offlineMessageQueue`、`aicloud_session_id`、`image-generate-session-v1`，并调用 `navigationStore.clearNavigationStorage()` 与 `hideAllTools()`。`user.logout.test.js` 新增一条覆盖六类键的用例，回退源码后失败。

#### FRESCAN-59 [P1] `ChatDatabase` 类未导出导致删除会话本地缓存静默失效

- 定位：`src/utils/chatDatabase.js:6,296`；`src/components/leftlist.vue:618-626`。
- 缺陷：模块只导出单例 `chatDB`，`class ChatDatabase` 未加 `export`；删除历史时动态导入后执行 `new chatDb.ChatDatabase()`，构造器为 `undefined`，抛 `TypeError` 后被 `catch` 吞掉，只留一条 `console.error`。
- 影响：服务端删除成功、界面移除条目，IndexedDB 中的 `conversations` 记录与本地缓存继续保留；重新打开同会话可能读到已删除内容。
- 证据：实码可证；IndexedDB 残留需浏览器确认。
- 修复状态：已修复。`leftlist.vue` 删除链路改用已导出的 `chatDB` 单例并直接调用 `deleteConversation`；新增 `leftlist.test.js` 用例断言 `chatDB.deleteConversation(7)` 被调用且条目移除，回退源码后该用例失败。

#### FRESCAN-61 [P2] 图片历史把 base64 写入数据库，文件删除路径永远不命中

- 定位：`app/api/v1/kolors_api.py:141-152,483`；`app/api/v1/kolors_history.py:28-37,114,141`；`app/api/v1/kolors_api.py:353-378`；`src/views/ImageGenerate.vue:601-615`。
- 缺陷：文生图与图生图响应同时包含 `images`（`data:image/...;base64,...`）与 `paths`（文件系统路径）；历史落库使用 `result.get("images", result["paths"])`，实际写入 base64。删除历史时 `_delete_image_files` 把每个字符串当 `Path` 处理，data URL 与相对路径都不指向 `generated_images` 下的真实文件。
- 影响：`ImageGenerationHistory.image_urls` 单行可达数 MB，历史列表随生成次数膨胀；磁盘图片文件永不回收。前端历史缩略图当前依赖 base64 显示，因此能显示但代价高。
- 附带：归属校验的 `GET /kolors/resources/{filename}` 全库无前端消费方，前端直读 `image_urls[0]`；一旦后端改为只存路径，历史图会变成不可访问的相对路径。
- 证据：实码可证；数据体积需实际库统计。
- 修复状态：已修复。新增 `app/services/image_history_refs.py` 统一文件名归一与根目录解析；`save_image_generation_history` 落库改存 `normalize_image_references(image_paths)`，五处生成调用改传 `paths`；`kolors_history._delete_image_files` 与 `generated_asset_retention` 改用 `resolve_reference`；`get_generated_resource` 增加 `ImageGenerationHistory.image_urls` 文件名归属兜底。新增 `tests/unit/test_image_history_refs.py` 覆盖归一、解析、归属与外来记录拒绝，回退 `get_generated_resource` 后归属用例失败。

#### FRESCAN-62 [P2] 能力中心知识库与沙箱页缺少权限门禁

- 定位：`src/views/CapabilityCenter.vue:96-121,149,180-300`；`app/utils/aicloud/permission.py:47-67`；`app/api/v1/aicloud_knowledge.py:77,221,260,301`；`app/api/v1/aicloud.py:94`。
- 缺陷：知识库与沙箱 tab 对所有登录用户展示，加载与执行直接调用 admin-only 端点；异常只把 `error.message` 写进面板。
- 影响：普通用户看到“知识库加载失败”“代码执行失败”，无法得知需要管理员权限，也没有升级入口；页面看起来是功能故障。
- 证据：路由 meta 仅 `requiresAuth`（`router/index.js:92-95`），后端权限实码可证；实际 403 文案需实测。
- 修复状态：已修复。`CapabilityCenter.vue` 读取 `userStore.isAdmin`，知识库与沙箱在无权限时不渲染表单并展示升级提示，加载函数与 tab 监听同时短路；新增两条用例分别断言普通用户不触发管理端点、管理员正常加载，回退源码后两条均失败。

#### FRESCAN-67 [P3] 活跃表单的 `label` 与控件缺少关联

- 定位：`src/components/NginxConfig.vue`（94 处 `<label>`，0 处 `for`，如 `:115,125,130,139`）；`src/components/UserManagement.vue`（12 处 `<label>`，0 处 `for`）；`src/components/settings/DynamicProviderManager.vue:16,20,24,31`（4 处 `<label>`，0 处 `for`）；`src/components/VirtualGirl.vue:265,269,273,277,281,285`（6 处 `<label>`，0 处 `for`）；`src/views/ChartEditorPage.vue:141,148,155,171,175`（8 处 `<label>`，0 处 `for`）。
- 影响：点击标签不聚焦控件，屏幕阅读器读不到控件名称；表单错误定位依赖视觉邻近。
- 判定：可用性缺陷，不阻断主流程。
- 修复状态：已修复。`NginxConfig.vue`（71 处）、`UserManagement.vue`（12 处）、`DynamicProviderManager.vue`（4 处）、`VirtualGirl.vue`（6 处）、`ChartEditorPage.vue`（5 处）为控件补稳定 `id` 并与 `label for` 关联；包裹式 radio/checkbox/toggle 保持原结构。新增 `src/tests/form-label-association.test.js`，回退源码后 5 条用例失败。

#### FRESCAN-68 [P3] AiCloud 历史失败返回值形状与数组契约不一致

- 定位：`src/utils/api/aicloud.js:61-82`；`src/components/Aicloud.vue:441-472`。
- 缺陷：成功时 `getHistory()` 返回后端数组，失败时返回 `{ messages: [] }` 对象；`loadCurrentSession` 直接 `sessions?.find(...)`，对象上没有 `find`，抛错后被外层 catch 吞掉并把消息清空；`loadHistory` 直接把对象赋给 `historySessions`，模板 `v-for` 按对象值迭代。
- 影响：网络失败或 403 时历史面板渲染异常或为空，且不显示失败原因。
- 修复状态：已修复。`aicloud.js` 的 `getHistory()` 成功与失败都返回数组（失败向上抛错）；`Aicloud.vue` 新增 `historyError` 与 `.history-error[role="alert"]` 失败态及重试入口。`aicloud.test.js` 两条新用例覆盖成功数组与失败抛错。

#### FRESCAN-70 [P2] 图片生成页面绕过统一客户端，错误全部静默

- 定位：`src/views/ImageGenerate.vue:408-447,601-645`；`src/utils/api/kolors.js:1-140`；`src/utils/api/base.js:139-158`。
- 缺陷：文生图、图生图、历史分页、删除单条、清空历史五处直接 `fetch(`${API_BASE}/...`)`，只手工拼 `Authorization`；`loadHistory`/`deleteHistory`/`clearHistory` 的 `catch` 全部为空注释，失败时界面无任何提示。统一客户端已有的 token 刷新、CSRF、错误归一化与 401 处理全部不生效。
- 影响：access token 过期时图片页不会自动刷新，只会静默显示空历史或“生成失败”；后端改为 `csrf_protect` 或调整返回结构时，这一页不会随客户端一起适配。`kolors.js` 里的同名封装没有生产消费方。
- 证据：实码可证；token 过期时的实际表现需运行验证。
- 修复状态：已修复。`kolors.js` 的 `textToImage`/`imageToImage` 改走 `client.request` 以支持 FormData、认证头与中止信号，`getHistory` 改用 `page_size`，失败统一抛错，新增 `getResourceBlob`；`index.js` 显式挂载 `api.kolors` 命名空间；`ImageGenerate.vue` 五处裸 `fetch` 收敛到 `api.kolors.*`，历史与生成图经认证端点转 objectURL 并在刷新、卸载时释放，失败写入可见错误；会话持久化改存文件名 `ref`，刷新后经认证端点重新取回，不再丢失最后一张图。新增 `src/utils/api/kolors.test.js`、命名空间断言与更新后的 `ImageGenerate.test.js`，回退源码后相关用例失败。

## 4. 统计与证据边界

本轮新增 19 项：P0 1 项、P1 6 项、P2 9 项、P3 3 项；其中 FRESCAN-64 属未接入/接线事项，计入 P2 结构类，不按活跃运行缺陷计。旧编号中 FEBOOT-01~05、FESTATE-01~07、FESURF-001~007、FRESCAN-05/06/07/28/30/31/36/37/39/40/42/45/46/47/48/49 复核为已修；FRESCAN-24、FRESCAN-35 判定失效；FRESCAN-25 部分失效。

第 165 轮新增 Backlog 使用 `#1392-#1410`。累计 P0 2、P1 53、P2 490、P3 817；Backlog 共 1410 项。

本轮完成源码、全库引用、后端路由与配置静态核对。阶段 0 修复后执行了 `src` 依赖安装与受影响单测：`leftlist.test.js`、`AdminPanel.logout.test.js`、`user.logout.test.js` 共 12 条用例通过，并在回退源码态确认新增 3 条用例失败。阶段 1 新增 9 条用例，全量单测 63 个文件 / 297 条用例通过，`npm run build` 成功；回退源码态确认阶段 1 的 9 条用例失败。阶段 2 新增 14 条前端用例与 5 条后端用例，全量单测 66 个文件 / 311 条用例通过，`kolors` 相关后端 39 条用例通过，后端全量 5173 passed / 4 skipped（6 条 `conversation_store` Redis 用例因本机无 Redis 失败），`npm run build` 成功；回退源码态阶段 2 前端 18 条用例失败、后端归属兜底用例失败。未执行 Docker 构建、Nginx 运行、浏览器与辅助技术验证；FRESCAN-52 的容器构建、FRESCAN-55 的跨账户时序、FRESCAN-58 的端到端回滚、FRESCAN-60 的 Nginx WS 握手仍保留待实测标记。

## 5. 分阶段修复规划

### 阶段 0：阻断项（立即）

1. FRESCAN-52：统一 Nginx 运行账号。二选一：改用 Debian 的 `www-data`；或显式创建 `nginx` 账号并同步 `configs/nginx.conf:7`。验收：`docker build` 通过；容器内 `nginx -t` 通过；`docker run` 后 worker 进程属主与 `nginx.conf` 一致。
2. FRESCAN-53：管理面板登出改为复用 `useAuth().logout()` 或 `userStore.clearUser()`，补 `api.logout()` 服务端吊销。验收：登出后 `getAccessToken()` 为空、`permissionLevel` 为 `normal`、旧 token 调受保护接口返回 401；新增 `AdminPanel.logout.test.js`。
3. FRESCAN-59：修正 `chatDatabase` 消费方式。验收：删除会话后 IndexedDB 中对应记录不存在；新增针对 `leftlist` 删除链的单元测试，断言不进入 catch。

### 阶段 1：认证与会话边界（1-2 天）

1. FRESCAN-54：为 `Leftlist` 绑定 `@login`/`@logout`，登录后执行 `fetchHistory(true)`，登出后重置会话与历史。
2. FRESCAN-55：把六类键合并进 `clearUser()`；`clearUser` 同时调用 `navigationStore.clearNavigationStorage()`，并清理 sessionStorage 中的图片会话。
3. FRESCAN-56：`index.js` 改为 `aicloud: createAiCloudClient(baseClient)`，并补全局 API shape 单测，断言 `ppt`/`aicloud` 命名空间存在且方法为函数。
4. FRESCAN-57：把 AiCloud 的检索方法改名为 `searchKnowledgeDocs`（或按命名空间拆分），恢复 `api.searchKnowledge` 走 agent 端点；同时修正 `agent.js` 返回值归一为 `{ results }` 以匹配消费方。
5. FRESCAN-58：`useAgentBackend` 直接传字符串 `tag`；后端调用显式传 `delete_branch=false`，把删除分支变成独立确认操作。验收：回滚请求 URL 中 `target_tag` 等于快照标签；补契约单测断言调用参数。
6. 验收标准：新增 `src/stores/user.logout.test.js` 用例覆盖全部键；`src/utils/api/apiShape.test.js` 覆盖命名空间；回退源码后对应用例必须失败。

### 阶段 2：核心可用性与部署（3-5 天）

1. FRESCAN-60：在 `/api/` 分支补 `proxy_http_version 1.1`、`Upgrade`、`Connection "upgrade"` 与长读超时，或把 PPT WS 迁到 `/ws/`。验收：经 Nginx 连接 `/api/v1/ws/ppt/{id}` 返回 101；补一条 Nginx 配置断言测试。状态：已修复，配置断言通过，101 握手待实测。
2. FRESCAN-61：历史落库改存 `paths`（相对 `generated_images` 的文件名），`_delete_image_files` 按文件名拼接根目录后删除；前端历史改用 `/kolors/resources/{filename}`。验收：新生成记录的 `image_urls` 不含 `data:`；删除历史后文件不存在；历史缩略图可加载。状态：已修复，归一/解析/归属用例通过。
3. FRESCAN-62：能力中心按 `userStore.isAdmin` 隐藏或禁用知识库/沙箱，并对 403 给出明确升级提示。状态：已修复，普通用户与管理员两条用例通过。
4. FRESCAN-70：`ImageGenerate.vue` 五处 `fetch` 改走统一客户端（`api.kolors.*` 或新增带 `page_size` 的封装），失败时给可见提示；同步修正 `kolors.js` 的分页参数。验收：token 过期时图片页自动刷新重试；断网时出现错误提示而非空列表。状态：已修复，客户端契约与页面交互用例通过；token 过期刷新依赖基础客户端既有链路，端到端待实测。
5. FRESCAN-66：`frontend-ci.yml` 增加 `npm run test:run`（CI 使用不带 `--fix` 的 `npm run lint:check`）；评估把 E2E 从 `continue-on-error` 提升为阻塞。状态：已修复，CI 契约用例通过；E2E 阻塞化留待阶段 3。
6. 验收标准：新增 Nginx 配置测试与图片历史契约测试；CI 在仅前端单元测试失败时变红。状态：配置与契约测试已落地；CI 变红行为待实际工作流运行确认。

### 阶段 3：结构收敛与可用性（1 周）

1. FRESCAN-63：三个弹窗迁移到 `ui/Modal.vue` 或补齐 `role`/`aria-modal`/Escape/焦点回归；补组件测试断言属性。状态：已修复，采用共享 `useDialogA11y` composable，8 个弹窗补齐语义与键盘行为。
2. FRESCAN-64：为六个已挂载工具选定出口：加入工具菜单，或从 `index.vue` 卸载并删除 navigation 标志；同时清理 `bottominput.vue:253` 的死分支。状态：已修复，`TaskQueue` 加入工具菜单，其余走路由或管理台，首页卸载并删除导航标志。
3. FRESCAN-65：token 读取统一到 `base.js` 的 `getValidToken()`；401 处理改为 `clearUser()` + 跳转 `/` 并提示会话过期。状态：已修复，401 统一调用 `handleSessionExpired()` 并广播 `session-expired`，由 `App.vue` 弹提示；当前停留在原页面，跳转 `/` 未采用。
4. FRESCAN-67：批量补 `label for`/控件 `id`，优先设置页与管理页。状态：已修复，5 个表单页共补 98 处关联。
5. FRESCAN-68：AiCloud 历史失败统一返回数组，并补失败态提示。状态：已修复，客户端失败抛错，页面显示 `role="alert"` 失败态与重试。
6. FRESCAN-69：明确保留单一拓扑：删除 Dockerfile 中未使用的 `nginx` 启动分支，或让 Compose 复用该 CMD；同步更新 README 部署说明。状态：已修复，镜像只保留 API，Nginx 统一为独立 Compose 服务。
7. 验收标准：可访问性项用组件测试锁定属性；拓扑项在文档与 Compose 中只保留一种描述。状态：已达成，新增 `useDialogA11y.test.js`、`form-label-association.test.js`、`container-topology.test.js`。

### 测试与验证建议

1. 环境具备 `node_modules` 后执行 `cd src && npm run test:run`，记录 59 个测试文件的基线。
2. 使用 `npm run build` 验证 Vite 产物；容器项在具备 Docker 的环境执行 `docker build` 与 `nginx -t`。
3. 认证类修复用普通账户与管理员账户各跑一遍登录、登出、刷新、切换账户。
4. 图片历史修复后用一条新记录验证：数据库无 base64、文件存在、删除后文件与记录同时消失。
