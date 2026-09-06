# 前端架构

## 技术栈

前端位于 `src/`，使用 Vue 3、Vite、Vue Router、Pinia、Element Plus 和 Vitest。入口 `src/main.js` 创建 Vue 应用，注册 Pinia 持久化插件、路由、Element Plus 和全局样式，然后恢复用户认证状态。

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
| `/admin`、`/admin/dashboard` | 管理页面 | 管理员 |
| `/docs` | `src/views/Docs.vue` | 是 |
| `/chart-editor` | `src/views/ChartEditorPage.vue` | 是 |

`/project-generate` 重定向到 `/agent`。路由守卫根据用户登录状态和 `admin`/`superadmin` 权限控制访问。

## Agent 页面

`src/views/AgentDashboard.vue` 负责组装 Agent 页面，不承载具体业务服务。主要 composables 和组件如下：

- `useAgentSession`：会话创建、切换、删除、历史快照和恢复。
- `useAgentGeneration`：生成阶段、进度、停止和状态代理。
- `useAgentFiles`：生成文件、目录分类、选中文件和代码高亮。
- `useAgentWorkspace`：思考消息、执行步骤、日志、验证结果和待决策项。
- `useAgentStreaming`：SSE 事件解析、生成生命周期和模型上下文同步。
- `useAgentBackend`：设置、性能、学习、快照和后端管理操作。
- `AgentTopBar`：桌面端状态、费用、导入、设置和更多操作。
- `AgentSidebar`：会话历史、搜索和文件树。
- `AgentWorkspace`：进度、思考过程、执行日志、验证和审批内容。
- `AgentInputBar`：需求输入、模型选择、生成和停止操作。
- `AgentFilePanel`：文件预览、diff、版本历史和下载。

桌面端使用 `src/styles/agent-layout.css` 的三栏布局。视口宽度小于等于 768px 时，工作区切换为单列视图，会话历史从左侧抽屉打开，文件预览从右侧抽屉打开，输入区保留底部安全区域。手机端状态和抽屉状态仍由 `AgentDashboard` 管理。

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

浏览器无法恢复用户设备的绝对文件路径，文件改名或文件字段头变化时需要重新选择并确认数据来源。撤销和重做历史保留在当前页面内存中，页面关闭后通过元数据草稿恢复图表结构。

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
```
