# Frontend Surface 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：前端表面 / FESURF
> 路径：`src/views/`、`src/components/`、`src/utils/api/`、`src/api/`、关键 utils、`tests/frontend/test_components.py`
> 规划参照：[`AGENT-FRONTEND.md`](../AGENT-FRONTEND.md)；本文记录实际实现、调用关系与缺陷

## 1. 模块作用与功能

### 1.1 模块定位与三态判定

前端表面由 Vue Router 视图、首页工具组件、Agent 组件、设置/管理组件、API 客户端和浏览器侧状态工具组成。后端是 FastAPI，开发链路由 Vite `3000` 端口代理 `/api/v1`、`/api/v2` 到 `localhost:8000`。

三态判定规则：活跃 = 路由或生产组件实际消费；未接入 = 文件存在但无生产引用；废弃 = 明确位于 `_deprecated` 或被新实现取代。

| 面 | 状态 | 实际证据 |
|---|---|---|
| 首页对话面 | 活跃 | `/` 路由加载 `components/index.vue`（`src/router/index.js:8-11`）；组合 `leftlist`、`centerContent`、`bottominput`，并消费 `/conversation/history`、`/agent/orchestrate/stream`、`/code`（`src/components/index.vue:370-503`） |
| Agent 面 | 活跃 | `/agent` 路由加载 `views/AgentDashboard.vue`（`src/router/index.js:42-45`）；组装 6 个 composables、顶栏、侧栏、工作区、输入栏、文件面板和 6 个 modal（`src/views/AgentDashboard.vue:100-141`） |
| 设置面 | 活跃 | `/settings` 路由加载 `views/Settings.vue`；providers、apikey、agent、admin、unified 五个 tab 直接挂载设置组件（`src/views/Settings.vue:26-55`） |
| 管理面 | 活跃 | `/admin` 与 `/admin/dashboard` 路由活跃；`AdminPanel` 实际挂载 `SystemLogs`、`UserManagement`、`NginxConfig`、`ServiceManager`、`ResourceControl`、`AdminModelManager`（`src/components/AdminPanel.vue:524-552`） |
| PPT、绘图、工作流、AiCloud、GitHub、图表 | 活跃 | 分别有 Router 视图或首页工具入口（`src/router/index.js:18-93`、`src/components/index.vue:59-114`） |
| `AgentHeader.vue`、`AgentInputPanel.vue` | 未接入/旧 Agent 双轨 | 全库无生产导入；活跃链路使用 `AgentTopBar.vue`、`AgentInputBar.vue`（`src/views/AgentDashboard.vue:114-124`） |
| `_deprecated/ChartEditor.modal.vue` | 废弃 | 全库无引用；活跃图表入口是 `/chart-editor` → `views/ChartEditorPage.vue`（`src/router/index.js:90-93`） |

### 1.2 视图和组件功能

| 区域 | 实现 |
|---|---|
| 主导航与对话 | `components/index.vue` 延迟加载工具组件；`leftlist.vue` 管理历史和工具导航；`centerContent.vue` 展示消息；`bottominput.vue` 发送、停止和编辑 |
| Agent | `AgentDashboard.vue` 负责组装；`AgentSidebar.vue` 管理会话/固定分类文件树；`AgentWorkspace.vue` 展示阶段、决策、thinking、步骤、日志、测试和验证；`AgentFilePanel.vue` 只读高亮预览；`modals/` 提供上传、设置、学习、性能、版本和 diff 弹窗 |
| 业务视图 | `PPTGenerate.vue`/`PPTPreview.vue` 处理 PPT 生成和预览；`ImageGenerate.vue` 处理 Kolors；`Workflow.vue` 执行工作流；`Docs.vue` 为内置文档；`ChartEditorPage.vue` 为图表编辑；`AdminDashboard.vue` 为管理仪表盘 |
| 首页工具 | `VirtualGirl`、`Aicloud`、`ImageGenerator`、`ProjectGenerator`、`EphemeralWorkflow`、`TaskQueue`、`ServiceManager`、`NginxConfig`、`Dockerfile` 等由 `components/index.vue` 按导航状态挂载 |
| 设置/管理 | `APIKeyManager`、`AgentModelConfig`、`DynamicProviderManager`、`MCPSettings`、`AdminModelManager`、`UnifiedModelConfig` 对接 v1/v2 配置和密钥端点；`SystemMonitor`/`SystemLogs` 使用 v2 WebSocket |

### 1.3 API 与工具入口

- 统一客户端入口：`src/utils/api/index.js:68-100` 创建 `window.api`；各模块以对象展开方式合并到同一客户端。
- v1 客户端：认证、Agent、项目、工作流、聊天、文件、任务、PPT、Kolors、AiCloud、GitHub 等模块均由 `src/utils/api/index.js:28-43` 导入。
- v2 客户端：`src/utils/api/admin.js` 使用绝对 `/api/v2/...` 路径，模型配置和 MCP 设置也直接使用 v2 路径。
- 独立密钥 API：`src/api/apikey.js` 使用 `src/utils/request.ts`，与 `window.api` 的认证和 URL 体系分离。
- 关键浏览器工具：`csrf.js` 管理 Cookie 双重提交；`tokenManager.js` 管理内存、sessionStorage 和 localStorage；`streamManager.js` 管理流状态、AbortController 和队列；`chatDatabase.js` 使用 IndexedDB；`theme.js` 管理主题；`taskNotification.js` 向任务 store 发布事件；`errorHandler.js` 提供统一提示接口；`crypto.js` 与 `encryption.js` 提供两套 RSA 相关能力。

## 2. 调用链与依赖关系

### 2.1 页面到 API

```text
Vue Router
  -> views/index.vue 或首页工具组件
  -> window.api Proxy
  -> createBaseClient + 业务 client
  -> /api/v1 或 /api/v2
  -> Vite proxy（/api/v1、/api/v2）
  -> app/main.py include_router
  -> FastAPI route
```

主要链路：

- 首页对话：`index.vue:370-503` → `api.stream('/code')` 或 `api.stream('/agent/orchestrate/stream')` → `app/api/v1/Aicode.py:709`、`app/api/v1/ai_agent/orchestrate_endpoints.py:507`。
- 对话历史：`index.vue:1022-1067` → `api.post('/conversation/history')` → `app/api/v1/auth.py:328`。
- Agent 项目：`AgentDashboard.vue:136-141` → composables → `project.js:10-182` → `app/api/v1/ai_agent/generate_endpoints.py` 和 `orchestrate_endpoints.py`。
- PPT：视图 → `api.ppt.*` → `ppt.js:19-196` → `app/api/v1/aiGeneratorPptx.py:790-2029`。该链路存在 FESURF-001。
- 管理服务：`AdminPanel.vue`/`ServiceManager.vue`/`ResourceControl.vue` → `admin.js` → `app/api/v2/guardian_router.py`；ServiceManager 的参数和返回契约存在 FESURF-004。
- Agent 设置：设置组件 → `/api/v1/models`、`/api/v2/model-config/*` 或 `/api/v2/models/*` → `model_manager.py`、`model_config_api.py`、`model_admin.py`。旧 `model_admin.py` 文件声明废弃，但部分兼容端点仍被 `AdminModelManager` 消费。

### 2.2 流、认证和浏览器状态

- `main.js:10-11` 初始化 API 客户端；`App.vue:3-11` 初始化主题。
- `base.js:75-169` 负责 token、CSRF、刷新和普通请求；`base.js:180-238` 负责 POST 流式请求。
- `streamManager` 在 `index.vue:388-503` 保存请求状态，并在 `index.vue:982-985` 中断请求；页面刷新后的 AbortController 只能清理代理记录，无法恢复原生控制器（代码已有明确注释）。
- `SystemMonitor.vue:267-305` 和 `SystemLogs.vue:193-270` 构造 v2 WebSocket；`WebSocketManager:155-168` 自动重连。重连传递链存在 FESURF-003。

### 2.3 后端端点交叉验证

- v1 路由由 `app/main.py:304-316` 挂载；任务 WebSocket 是 `/api/v1/tasks/ws/{user_id}`（`app/api/v1/task_queue.py:338`）。
- v2 路由由 `app/main.py:317-329` 挂载；系统状态和日志 WebSocket 是 `/api/v2/Controller/sys-status`、`/api/v2/Controller/logs`（`app/api/v2/Controller.py:90-158`）。
- AiCloud 后端定义聊天、读写、历史、审查列表和模型端点（`app/api/v1/aicloud.py:72-865`），未发现 `/aicloud/reviews/toggle`；前端消费形成 FESURF-006。
- API Key 路由自身带 `prefix='/api/v1/agent/apikey'`（`app/api/v1/apikey.py:32`），其列表端点定义为 `@router.get('s')`（`app/api/v1/apikey.py:279`），因此 `/api/v1/agent/apikeys` 的路径拼接与前端声明一致。

## 3. 已探明 Bug

判定标签说明：`实码可证` = 静态代码和全库引用已经足以确定；`实测` = 本轮通过运行/网络交互确认；`待实测` = 需要浏览器、服务端或构建运行确认。本轮未启动服务，以下缺陷均标为 `实码可证`，运行影响仍建议补充 `待实测` 回归。

### FESURF-001 [P0] PPT 客户端导出形状与活跃消费者不一致（实码可证）

- **现象**：`PPTGenerate.vue`、`PPTPreview.vue`、`HistoryPanel.vue` 调用 `api.ppt.getTemplates/getHistory/downloadPPT` 等。
- **Bug 代码**：`src/utils/api/index.js:72-86` 通过对象展开把 `createPptClient(baseClient)` 的方法平铺到 `window.api`，没有创建 `api.ppt` 属性；消费点见 `src/views/PPTGenerate.vue:391-462`、`src/views/PPTPreview.vue:123-173`、`src/components/HistoryPanel.vue:180-243`。
- **根因**：客户端导出契约是 `api.getTemplates`，组件契约是 `api.ppt.getTemplates`。
- **影响**：PPT 模板、历史、下载、分析和修改等活跃操作在调用 `api.ppt` 时触发 `TypeError`。
- **验证方式**：运行前端后进入 `/ppt-generate` 或首页历史面板，检查 `window.api.ppt`；补充 API 客户端形状单测。

### FESURF-002 [P1] 独立 API Key 客户端绕过代理且读取错误 token 键（实码可证）

- **Bug 代码**：`src/utils/request.ts:6` 默认 `BASE_URL` 为 `http://localhost:8000`，`src/utils/request.ts:53-59` 只读取 `localStorage.auth_token`；统一 token 管理器实际写入 `access_token`（`src/utils/tokenManager.js:39-50`）。调用方为 `src/api/apikey.js:4-96`，活跃消费者为 `src/stores/apikey.js:9`。
- **根因**：密钥 API 保留独立旧请求封装，未接入相对 `/api` 代理和当前 token 存储契约。
- **影响**：在通过预览域名访问时请求目标指向浏览器所在机器的 `localhost:8000`；即使目标可达，API Key 管理请求也无法自动带当前登录 token。
- **验证方式**：预览域名打开设置/API Key，观察 Network 的请求主机和 Authorization；补充部署域名下登录后密钥 CRUD 测试。

### FESURF-003 [P1] WebSocket 自动重连丢失认证 token（实码可证）

- **Bug 代码**：首次连接由 `SystemMonitor.vue:303-304`、`SystemLogs.vue:269-270` 传 token；`WebSocketManager:164-166` 的重连回调调用 `this.connect()`，没有复用 token。
- **根因**：token 只作为 `connect(token)` 的临时参数，管理器实例没有保存认证 token。
- **影响**：连接断开后重连 URL 会清掉 `{token}` 占位符；后端 v2 WebSocket 使用 token 查询参数，重连容易以 1008 权限失败。调用方自己的 `scheduleReconnect()` 与管理器 `onclose` 自动重连还可能形成重复调度。
- **验证方式**：浏览器中断系统日志/状态 WebSocket，检查第二次连接 URL 和关闭码；补充 token 保留、手动 disconnect 不重连、单次调度测试。

### FESURF-004 [P1] ServiceManager 调用参数和 admin 客户端契约错位（实码可证）

- **Bug 代码**：`src/components/ServiceManager.vue:554-567` 向 `api.updateFuseConfig` 传 3 个参数，`src/utils/api/admin.js:100-111` 只接收 `(port, fuseConfig)`，因此 `process_signature` 被作为 `fuse_config`；重命名同样发生于 `ServiceManager.vue:598-610` 与 `admin.js:86-98`。此外 admin 方法返回解析后的对象，组件却在 `ServiceManager.vue:569-574`、`612-618` 检查 `result.ok` 和 `result.data`。
- **根因**：组件沿用了带 `process_signature` 的旧接口形状，客户端已改为另一签名和 JSON 返回形状。
- **影响**：熔断配置/服务重命名请求体不符合后端 `guardian_router.py:109-129` 所需参数；即便后端成功，组件也会按 `result.ok` 缺失显示失败。
- **验证方式**：管理员打开服务管理并执行重命名、熔断配置，检查请求 JSON、响应处理和 UI 提示。

### FESURF-005 [P1] 备份下载方法吞掉 Blob，资源控制再把布尔值当 JSON 下载（实码可证）

- **Bug 代码**：`admin.js:439-452` 已创建下载链接并返回 `true`；`ResourceControl.vue:1298-1310` 又把返回值作为 `data`，执行 `JSON.stringify(data)` 后生成 JSON 文件。
- **根因**：`downloadBackup` 同时承担下载副作用和数据返回两种契约，消费方按“返回备份数据”实现。
- **影响**：用户点击资源控制的备份下载时，实际下载的第二个文件内容是 `true`，无法得到预期 JSON 备份内容；恢复流程 `ResourceControl.vue:1322-1333` 也会把 `true` 传给恢复 API。
- **验证方式**：管理员创建备份后分别点击下载和恢复，检查下载文件内容及 `/admin/backup/restore` 请求体。

### FESURF-006 [P1] AiCloud review toggle 前端调用后端未定义端点（实码可证）

- **Bug 代码**：`src/components/Aicloud.vue:650-662` 调用 `api.toggleReview`；其实现为 `src/utils/api/aicloud.js:162-174` 的 `POST /aicloud/reviews/toggle`。后端 `app/api/v1/aicloud.py` 定义 reviews 查询、approve、reject，但全库路由检索未发现 toggle 端点。
- **根因**：前端客户端扩展了后端尚未挂载的能力。
- **影响**：AiCloud 审查开关请求返回 404；组件 catch 后仍更新本地 `reviewEnabled`，造成界面状态与服务器状态分离。
- **验证方式**：打开 AiCloud 的审查开关，检查响应 404 及刷新后的状态恢复。

### FESURF-007 [P2] 基础客户端无法保留调用方自定义 headers（实码可证）

- **Bug 代码**：`base.js:133-137` 用新建的 `headers` 覆盖 `options.headers`；`base.js:201-205` 的 stream 也只发送内部 headers。
- **根因**：请求选项展开时没有合并调用方 headers。
- **影响**：未来或现有需要额外请求头的客户端无法通过 `client.request`/`client.stream` 传递该头；当前多数模块把认证和 CSRF写在基础客户端内，因此具体受影响调用需运行时确认。
- **验证方式**：对 `client.request('/x', { headers: { 'X-Test': '1' } })` 和 stream 使用 fetch mock 断言；全库检索后将该项标为接口级风险，当前业务影响 `待实测`。

### FESURF-008 [P2] Agent 组件存在双轨未接入实现（实码可证）

- **状态**：`AgentHeader.vue`、`AgentInputPanel.vue` 全库无生产引用；活跃页面使用 `AgentTopBar.vue`、`AgentInputBar.vue`。`_deprecated/ChartEditor.modal.vue` 也无引用，路由已切换到 `ChartEditorPage.vue`。
- **影响**：修改旧 Agent 组件无法改变线上行为，维护者容易误修；重复输入/顶栏实现扩大事件契约漂移面。
- **判定**：属于未接入/废弃面结构问题，按三态规则记录为迁移/退役工作，不按活跃 P 级运行缺陷计数。
- **验证方式**：本轮全库 `rg` 已确认零生产引用；删除或迁移需要独立变更授权，本轮不修改。

## 4. 潜在问题与未知点

- 本轮是静态扫描，未启动 Vite、FastAPI、浏览器或真实 WebSocket；所有“请求会失败”的运行表现应在浏览器回归中复核。
- `src/utils/api/client.js:3-16` 的 `createClient(config)` 完全忽略 `config`，当前主要消费者 `AdminDashboard.vue` 未证明依赖该参数；接口设计风险待运行和调用约定确认。
- `src/utils/api/workflow.js:34-47` 读取 token 后交给 `client.post`，读取结果未使用；基础客户端仍会自行读取 token，属于重复认证逻辑，未单独计缺陷。
- `src/components/ResourceControl.vue:984-985` 的 `handleLogToFileChange` 和 `1229-1230` 的 `handleFeatureToggle` 为空函数；是否有模板事件实际绑定需结合完整模板交互回归确认。
- `src/components/agent/AgentFilePanel.vue:20` 使用 `v-html` 渲染高亮内容。内容来源和高亮转义策略需要运行时检查；当前静态材料不足以判定为 XSS 缺陷。
- `src/utils/streamManager.js` 将流状态写入 `localStorage`，但恢复逻辑只恢复元数据，无法恢复网络流；恢复 UI 的完整行为待刷新中断场景实测。

## 5. 修改建议

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应缺陷 |
|---|---|---|---|---|---|
| 1 | P0 | 统一 PPT 客户端导出形状，或统一改用平铺方法并加 API shape 单测 | 恢复 PPT 模板、历史、预览和生成链路 | `src/utils/api/index.js`、PPT 视图/HistoryPanel | FESURF-001 |
| 2 | P1 | 将 `src/api/apikey.js` 迁移到相对 `/api/v1`、共享基础客户端和 `access_token` 契约；修正 GET 参数传递 | 使预览域名和登录态下 API Key 管理可用 | `src/api/apikey.js`、`src/utils/request.ts` | FESURF-002 |
| 3 | P1 | 在 WebSocket 管理器保存 token 并让重连复用；集中重连调度 | 保证 v2 状态/日志连接断线恢复且只调度一次 | `src/utils/api/websocket.js`、`SystemMonitor.vue`、`SystemLogs.vue` | FESURF-003 |
| 4 | P1 | 选择一套 ServiceManager 参数/返回契约，按 FastAPI schema 对齐 | 修复服务重命名与熔断配置 | `src/components/ServiceManager.vue`、`src/utils/api/admin.js` | FESURF-004 |
| 5 | P1 | 让备份 API 明确返回 Blob 数据或由 API 独占下载副作用；资源控制按同一契约处理 | 修复备份下载和恢复 | `src/utils/api/admin.js`、`src/components/ResourceControl.vue` | FESURF-005 |
| 6 | P1 | 增加后端 toggle 端点并补权限/持久化，或移除前端伪开关 | 使审查开关状态与服务器一致 | `src/utils/api/aicloud.js`、`src/components/Aicloud.vue`、`app/api/v1/aicloud.py` | FESURF-006 |
| 7 | P2 | 合并 `options.headers` 与内部 headers；为 request/stream 增加 mock 测试 | 保留调用方扩展请求头能力 | `src/utils/api/base.js` | FESURF-007 |
| 8 | P2 | 对 Agent 旧双轨组件建立退役记录并在确认后统一删除/迁移 | 降低维护误用和组件契约漂移 | `AgentHeader.vue`、`AgentInputPanel.vue`、`_deprecated/ChartEditor.modal.vue` | FESURF-008 |

## 6. 测试缺口

- `tests/frontend/test_components.py` 只有 18 行占位 pytest，断言恒为 `True`；文件自身说明真实测试应在 `src/tests/` 使用 Vitest + `@vue/test-utils`（`tests/frontend/test_components.py:1-18`）。
- 缺少 Router smoke tests：应覆盖 `/`、`/agent`、`/settings?tab=apikey`、`/ppt-generate`、`/ppt-preview/:id`、`/admin`、`/chart-editor` 的组件加载和权限守卫。
- 缺少 API shape tests：至少断言 `window.api` 是否包含 PPT 方法、API Key 客户端是否使用正确 base URL/token、GET 参数是否进入 URL、错误响应是否保持一致形状。
- 缺少端点契约测试：从前端消费清单生成 v1/v2 route 对照，重点覆盖 `AiCloud reviews/toggle`、Agent session、PPT 下载/历史、服务管理和备份恢复。
- 缺少组件交互测试：ServiceManager 的参数和成功/失败提示、ResourceControl 的下载/恢复、Settings tab、Agent 输入快捷键和文件删除确认。
- 缺少 WebSocket 测试：token 注入、断线重连、1008 不重试、手动 disconnect 不触发重连、系统日志过滤器消息格式。
- 缺少浏览器安全/状态测试：CSRF Cookie 双重提交、token 刷新、IndexedDB 30 天过期清理、流刷新后恢复/中断、主题 `theme-auto` 监听清理。
- 缺少静态消费扫描：应在 CI 检查未接入组件、`api.ppt` 这类导出形状漂移，以及 `_deprecated` 目录是否仍被生产代码引用。

## 7. 演化方向关联

- **拆分解耦**：统一 `window.api`、`src/api/apikey.js` 和 `request.ts` 的请求契约，移除独立认证/URL 双轨；把 WebSocket token 与重连策略收敛到单一管理器。
- **统一收敛**：合并 Agent 顶栏/输入栏双轨，明确活跃组件；将 v1 兼容模型端点和 v2 model-config 的消费边界写入契约测试。
- **智能增强**：`AgentWorkspace` 当前是阶段时间线、thinking 和日志聚合，`AgentFilePanel` 当前是单文件只读高亮；`AGENT-FRONTEND.md` 中的对话流、行级 diff、多文件预览属于后续规划，不作为本次实现缺陷重复计数。
- **平台化**：建立前端调用端点清单、API response shape 约束和 Vitest/Playwright smoke 层，覆盖路由、组件、认证、流式请求和 WebSocket。

## 8. 扫描结论

确定性活跃缺陷 7 项：P0 1 项、P1 5 项、P2 1 项；未接入/废弃结构问题 1 项，单列为迁移/退役事项。实测问题计数为 0，本轮实测状态为“待实测”，因为未启动服务或浏览器；主要证据来自 `src/router/index.js`、`src/vite.config.js`、`src/utils/api/index.js`、`src/utils/request.ts`、相关活跃组件，以及 `app/main.py` 和 v1/v2 路由定义。

## 9. 第 163 轮分批重扫修订

- FESURF-001 至 FESURF-008 全部保留；FESURF-004 的影响范围扩大到 `admin.js` 多组缺少 `/Controller` 前缀的管理端点。
- 新增 API、组件和凭证问题见 [frontend_batch_rescan.md](frontend_batch_rescan.md) 的 FRESCAN-12 至 FRESCAN-16。
- `AgentFilePanel.vue` 的 `v-html` 继续保持待实测安全风险等级，当前证据不足以升级为确定缺陷。
