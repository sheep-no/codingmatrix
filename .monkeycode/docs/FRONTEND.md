# 前端架构

## 技术栈

前端位于 `src/`，使用 Vue 3、Vite、Vue Router、Pinia、Element Plus 和 Vitest。入口 `src/main.js` 创建 Vue 应用，注册 Pinia 持久化插件、路由、Element Plus 和全局样式，然后通过 `window.__appInitialization` 暴露用户状态恢复 Promise，供 `AppLoading` 管理首屏状态。

共享 Web 工作台基础位于 `src/styles/variables.css`、`src/styles/base.css` 和 `src/components/`：语义令牌覆盖 surface、content、accent、status、control 与 motion；`LoadingState`、`ErrorState`、`TaskStatus` 和 `NextAction` 统一反馈契约；全局焦点态、40px 最小交互尺寸和 reduced-motion 规则由基础样式提供。`src/utils/taskFeedback.js` 将 Agent、Workflow、PPT 和绘图的异构事件归一为 `status`、`stage`、`progress`、`elapsedMs`、`error` 和 `nextAction` 六字段模型，并兼容 PPT 事件回放与 `snapshot_recovery` 快照。`WorkbenchNav` 定义会话、项目、能力、文档和设置五个一级入口，首页侧栏与 Agent 会话侧栏复用同一导航顺序、活动态和折叠态可访问名称。

## 路由

路由定义在 `src/router/index.js`，使用 `createWebHistory`。主要页面如下：

| 路径 | 页面 | 认证 |
|---|---|---|
| `/` | `src/components/index.vue` | 否 |
| `/agent` | `src/views/AgentDashboard.vue` | 是 |
| `/workflow` | `src/views/Workflow.vue` | 是 |
| `/ppt-generate` | `src/views/PPTGenerate.vue` | 是 |
| `/ppt-preview/:id` | `src/views/PPTPreview.vue` | 是 |
| `/image-generate` | `src/views/ImageGenerate.vue` | 是 |
| `/aicloud` | `src/components/Aicloud.vue` | 是 |
| `/settings` | `src/views/Settings.vue` | 是 |
| `/admin` | `src/components/AdminPanel.vue` | `admin` 或 `superadmin` |
| `/admin/dashboard` | `src/views/AdminDashboard.vue` | `admin` 或 `superadmin` |
| `/docs` | `src/views/Docs.vue` | 是 |
| `/chart-editor` | `src/views/ChartEditorPage.vue` | 是 |

`/project-generate` 重定向到 `/agent`。路由守卫根据用户登录状态和 `admin`/`superadmin` 权限控制访问。

## 管理员面板

`src/components/AdminPanel.vue` 提供 `/admin`。工具集「管理员面板」仅超级用户可见，点击后 `window.open('/admin')`；`admin` 权限也可直接打开该路由。

管理员可见模块：系统监控、系统日志、用户管理、Nginx 配置、服务管理、资源配置。超级管理员额外可见模型管理（`src/components/settings/AdminModelManager.vue`）和并发管理仪表板（`/admin/dashboard`）。

当前菜单与搜索关键字写入 `localStorage` 键 `adminMenuState`，挂载时按权限白名单恢复。设置页「系统模型管理」和「统一模型配置 (v2)」同样只对超级用户开放。

## Agent 页面

`src/views/AgentDashboard.vue` 负责组装 Agent 页面，不承载具体业务服务。主要 composables 和组件如下：

- `useAgentSession`：会话创建、切换、删除、历史快照和恢复。
- `useAgentGeneration`：生成阶段、进度、停止和状态代理。
- `useAgentFiles`：生成文件、目录分类、选中文件和代码高亮。
- `useAgentWorkspace`：思考消息、执行步骤、日志、验证结果和待决策项。
- `useAgentStreaming`：SSE 事件解析、生成生命周期和模型上下文同步。
- `useAgentBackend`：设置、性能、学习、快照和后端管理操作。
- `AgentTopBar`：桌面端状态、费用、导入、设置和更多操作。
- `AgentSidebar`：共享一级导航、会话历史、搜索、文件树和 Skills。
- `AgentWorkspace`：进度、思考过程、执行日志、验证和审批内容。
- `AgentInputBar`：需求输入、模型选择、生成和停止操作。

首页 `bottominput` 与 `AgentInputBar` 共享输入状态语义、发送/停止操作反馈、键盘提示和可访问名称。发送与停止图标使用内联 SVG，按钮保留至少 40px 的触控尺寸，生成中状态统一显示为“正在生成”。

首页消息区域拆分为 `chat/MessageList`、`chat/MessageItem`、`chat/MessageAttachments` 与 `chat/MessageThinking`。消息列表负责可见消息迭代和虚拟索引，消息项负责 article 语义、状态标签与高度观测；附件和思考组件继续接收原消息对象字段，思考组件复用 `centerContent` 提供的净化 Markdown 渲染函数，兼容按 Agent 分组和旧版单块 reasoning 数据。

消息数超过 50 条后，`centerContent` 使用 `src/utils/messageVirtualizer.js` 计算窗口。未渲染消息先采用高度估算，已渲染消息由 `ResizeObserver` 提供实测高度；顶部和底部占位均位于滚动容器内，滚动事件通过 animation frame 合并。流式消息使用 `src/utils/streamUpdateBatcher.js` 聚合同一帧内的 response、reasoning 和 Agent thinking 增量，终止事件会立即冲刷尾部文本。

图片上传通过 `src/utils/imageThumbnail.js` 将预览限制在 320px 边界内，消息列表优先加载缩略图，并在用户打开原图时使用上传接口返回的 `download_url`。图片元素声明固定尺寸、原生懒加载和异步解码；缺失或加载失败的资源显示稳定占位。`MessageEditor` 与 `KeyboardShortcutsHelp` 和其他低频工具一样使用 async component，并在首次显示时挂载。
- `AgentFilePanel`：文件预览、diff、版本历史和下载。

桌面端使用 `src/styles/agent-layout.css` 的三栏布局。视口宽度小于等于 768px 时，工作区切换为单列视图，会话历史从左侧抽屉打开，文件预览从右侧抽屉打开，输入区保留底部安全区域。手机端状态和抽屉状态由 `AgentDashboard` 管理；Escape、遮罩关闭和触发按钮焦点恢复遵循同一抽屉协议。

## VS Code Agent 工作台

VS Code 扩展位于 `vscode-extension/`，使用原生 Webview 提供轻量 Agent 工作台。当前支持：

- 需求输入和云端 SSE 流式结果展示。
- Agent 会话暂停、恢复和取消。
- 本地 Agent Host 动作审批，包括批准和拒绝。
- 工作区授权、文件读写、诊断、终端和本地验证。
- Workspace Skills 自动发现与同步。
- 网络中断时本地验证结果持久化排队，恢复连接后补交云端。

VS Code 工作台与 Web 工作台共享 Agent Host 协议和云端 Agent API。Web 工作台继续承担完整的会话历史、模型选择、文件树、版本历史、性能面板和学习面板；VS Code 工作台聚焦本地执行环境与验证结果回传。

## 状态持久化

`src/stores/agentSession.js` 使用 Pinia 和 `localStorage` 保存当前会话。历史会话最多保留 10 条，快照包含工作流阶段、生成文件、当前 Agent、当前模型、模型分配、模型配置版本、模型上下文 revision、fallback 历史和恢复次数。

模型上下文通过 `src/utils/api/project.js` 读写后端接口。`useAgentStreaming` 消费 SSE `model_info` 事件，合并当前模型、调用统计和降级记录，并在流结束时写回后端。模型上下文只保存模型标识和运行统计，供应商凭据由现有 Key Store 管理。

## 图表编辑器

`src/views/ChartEditorPage.vue` 提供认证后的 `/chart-editor` 页面，使用 ECharts 渲染图表，使用 SheetJS 解析 XLSX、XLS、CSV 和 JSON 文件。当前支持柱状图、折线图、面积图、饼图、散点图和雷达图，以及求和、平均值、计数、最大值、最小值和不聚合等聚合方式；图表样式包括标题、颜色、图例、数值标签、平滑曲线和动画。

图表编辑器的数据源和图表配置遵循以下生命周期：

1. 用户选择文件后，文件内容只在当前页面会话中解析和使用。
2. 自动草稿写入用户作用域的 `localStorage` 键 `chart-editor-draft-v1:{username}`。
3. 草稿只保存文件名、字段头、缺失值统计、图表配置和选择状态，保存时间为两天滑动有效期；原始行数据不会写入草稿。
4. 页面恢复草稿后，数据源标记为“需要重新选择文件”；选择同名且字段头一致的文件后，程序重新解析并绑定已有图表。
5. “导出项目”生成 `chart-editor-project.json`，项目配置可通过“导入项目”迁移到另一个浏览器环境；导入结果同样需要重新关联原始文件。

刷新或关闭页面前，`beforeunload` 与 `pagehide` 会立刻调用 `persistDraftNow()`，避免 250ms 防抖导致标题丢失。

浏览器无法恢复用户设备的绝对文件路径，文件改名或文件字段头变化时需要重新选择并确认数据来源。撤销和重做历史保留在当前页面内存中，页面关闭后通过元数据草稿恢复图表结构。

## AI 绘画

`src/views/ImageGenerate.vue` 对应 `/image-generate`，调用 `POST /api/v1/kolors/text-to-image`，模型 `Kwai-Kolors/Kolors`。进行中的文生图会话写入 `sessionStorage` 键 `image-generate-session-v1`，有效期 30 分钟；刷新后恢复画布并重发请求。返回会中止进行中的请求并保留描述；图生图在没有参考文件时按文生图恢复。

## PPT 三步流程

`src/views/PPTGenerate.vue` 依次完成主题输入、大纲审阅和质量模式选择。大纲审阅支持页面类型、标题、核心结论和内容编辑，也支持新增、删除与上下重排；页面位置在结构变更后重新编号。任一页面缺少标题、核心结论或有效内容时，页面显示校验信息并禁用批准操作。

`src/views/PPTPreview.vue` 读取质量报告并展示整体质量分、逐页分、问题类型、规则修复动作、自动重排次数和人工复核页，同时允许针对问题页创建重新生成任务。对应 Vitest 位于 `src/views/PPTGenerate.test.js` 和 `src/views/PPTPreview.test.js`。

## Vite 开发服务

配置位于 `src/vite.config.js`：

- 监听 `0.0.0.0:3000`。
- `/api/v1` 和 `/api/v2` 代理到 `http://localhost:8000`。
- WebSocket 代理已开启。
- SSE 代理关闭缓存和 Nginx 缓冲影响。
- `allowedHosts` 包含 `localhost`、`127.0.0.1` 和 `.monkeycode-ai.online`。
- 生产构建输出到仓库根目录 `dist/`，静态资源目录为 `dist/static/`。
- 生产构建生成 `dist/.vite/manifest.json`；`src/scripts/check-performance-budget.js` 根据本次 manifest 计算首屏静态依赖和入口直接动态导入的路由 chunk，避免历史 hash 产物影响统计。
- 性能预算为首屏 JavaScript gzip 450 KiB、首屏 CSS gzip 100 KiB、最大图片原始体积 200 KiB、最大路由 chunk gzip 150 KiB；图片检查同时覆盖 manifest 资源和 `src/public/`。
- 首页低频编辑器与快捷键帮助分别生成独立动态 chunk，保持在入口静态依赖闭包之外。

## 性能采集

`src/utils/performanceMetrics.js` 由 `src/main.js` 在 Router 安装前启动。采集器使用 Vue Router 的 `beforeEach` 与 `afterEach` 记录成功导航耗时，并通过浏览器 `PerformanceObserver` 采集 LCP、INP 和 CLS。CLS 使用最大 session window，INP 按 `interactionId` 合并事件并计算近似第 98 百分位。

当前快照位于 `window.__performanceSnapshot`，同时通过 `codingmatrix:performance-snapshot` 自定义事件发布。快照包含 schema 和构建版本、当前路由、最近成功导航耗时、LCP、INP、CLS 与测量时间；未受浏览器支持的指标保持空值。采集器在 HMR dispose 时移除路由守卫、页面监听器和性能观察器。

## Capability Center

`src/views/CapabilityCenter.vue` 默认只渲染视觉工具面板。Skills、Agent Host 和知识库在用户首次进入对应 Tab 时请求数据，并在当前页面会话中缓存；面板上的刷新操作显式绕过缓存。Tab 请求相互隔离，单个面板的刷新不会清空其他面板数据。

当前五个面板为：视觉工具（`/api/v1/vision`）、知识库（`/api/v1/aicloud/knowledge`）、代码沙箱（`/api/v1/aicloud/execute`）、Skills（`/api/v1/skills`）和 Agent Host（`/api/v1/agent/host/sessions`）。

各面板维护独立的加载与错误状态。列表面板提供空状态和失败重试，视觉工具与代码沙箱保留最近一次操作参数用于重试，单个面板失败不会覆盖其他面板结果。

视觉工具和知识库使用统一拖拽区，同时支持点击选择文件。资源删除操作要求确认，列表刷新显式绕过面板缓存，结果内容通过独立结果区展示。

基础 API 客户端通过 `createAbortController` 提供取消入口，并将取消和网络失败归一化为带稳定 `code` 的 `ApiError`，领域 API 继续复用基础请求客户端。

Capability Center 组件测试覆盖 Tab 延迟加载与缓存、错误重试和删除确认；Playwright 用例覆盖移动端 Tab 切换、请求隔离与横向溢出。

## 搜索历史

`src/components/leftlist.vue` 工具集「搜索历史」打开侧栏搜索框。检索调用 `POST /api/v1/history`，请求体为 `prompt_keyword`、`limit` 和 `offset`。空关键词、清除或关闭搜索框后重新拉取全部会话。组件测试位于 `src/components/leftlist.test.js`，覆盖打开搜索框、关键词检索、失败重试和清除后拉全量。

首页 `src/components/index.vue` 在 768px 以下使用与 Agent Dashboard 一致的会话抽屉协议：顶部菜单打开左侧导航，遮罩或 Escape 关闭抽屉并恢复菜单按钮焦点。移动输入框保持至少 16px 字号，并通过 `safe-area-inset-bottom` 避让设备安全区。

首页与 Agent Dashboard 的组件测试分别位于 `src/components/index.test.js` 和 `src/views/AgentDashboard.test.js`，覆盖工作区结构、抽屉语义和焦点恢复。`tests/e2e/workbench-responsive.spec.js` 在 1440px、768px 和 390px 三档视口验证桌面栏位、移动抽屉、单列工作区、输入字号与横向溢出。

任务反馈归一化测试位于 `src/utils/taskFeedback.test.js`，覆盖四个任务领域、状态别名、零值与边界进度、工作流节点汇总、PPT 事件包装和恢复快照、错误提取及耗时计算。

## 任务反馈与恢复

`src/composables/useTaskFeedback.js` 管理任务反馈生命周期、运行耗时、连接状态和事件序列。`src/components/TaskFeedbackPanel.vue` 组合 `TaskStatus` 与 `NextAction`，在 Agent、Workflow、PPT 和绘图工作区统一展示当前阶段、状态、进度、耗时、错误、下一动作及连接恢复提示。

反馈面板通过 `actions` 接收 `{ key, label, variant }` 操作列表，并通过统一 `action` 事件回传操作键。页面层负责映射领域能力：Agent 支持停止、重试和下载项目；Workflow 与临时工作流支持取消、继续或重试和导出；PPT 支持取消、重试、在线预览和下载；绘图支持取消、重试和下载结果。Workflow 与绘图的进行中请求使用 `AbortController` 取消，取消后进入可重新执行的暂停状态。

普通流式事件通过 `mergeTaskFeedback` 局部合并，只更新事件携带的字段并保留工作区上下文。带序列号的事件会过滤重复或过期数据；发现序列缺口时进入恢复状态。PPT WebSocket 使用 `after_sequence` 请求服务端续传，连接中断后最多自动重连三次，并使用 `snapshot_recovery` 全量覆盖反馈快照和恢复结果；Agent 与 Workflow SSE 在协议没有事件重放能力时保留当前输入、消息和节点状态，同时明确展示连接中断状态。

对应单元与组件测试位于 `src/utils/taskFeedback.test.js`、`src/composables/useTaskFeedback.test.js` 和 `src/components/shared-state.test.js`，覆盖四领域状态归一化、局部合并、重复事件过滤、序列缺口、恢复快照、过期快照拒绝、终态断线保护、游标重置、终态计时停止、反馈面板增量渲染和多操作事件派发。

## 前端命令

在 `src/` 目录执行：

```bash
# 启动 Vite 开发服务
npm run dev

# 运行一次前端测试
npm run test:run

# 执行 lint
npm run lint

# 构建生产资源
npm run build

# 构建并执行性能预算检查
npm run build:budget

# 检查已有生产产物的性能预算
npm run budget:check
```

生成页用 `sessionStorage` 键 `ppt-generate-session-v1` 保存步骤、大纲和任务进度；同一标签刷新后恢复，生成中会重连 WebSocket。历史面板调用 `GET /api/v1/pptx/history`：预览进入 `/ppt-preview/{task_id}`，加载回填主题和下载 URL。

首页聊天 `src/components/centerContent.vue` 把非临时会话写入 IndexedDB 库 `AIChatDB`、对象仓库 `conversations`。写入前用 `cloneForIndexedDb` 做 JSON 往返，去掉 Vue 代理、函数，并把 `Error` 压成可克隆字段。
