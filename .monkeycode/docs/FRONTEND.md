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

## 状态持久化

`src/stores/agentSession.js` 使用 Pinia 和 `localStorage` 保存当前会话。历史会话最多保留 10 条，快照包含工作流阶段、生成文件、当前 Agent、当前模型、模型分配、模型配置版本、模型上下文 revision、fallback 历史和恢复次数。

模型上下文通过 `src/utils/api/project.js` 读写后端接口。`useAgentStreaming` 消费 SSE `model_info` 事件，合并当前模型、调用统计和降级记录，并在流结束时写回后端。模型上下文只保存模型标识和运行统计，供应商凭据由现有 Key Store 管理。

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
