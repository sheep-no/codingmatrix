# Frontend 第 164 轮复扫记录

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：前端应用第 164 轮只读复核
> 基线：`frontend_batch_rescan.md`、`frontend_bootstrap.md`、`frontend_state.md`、`frontend_surface.md`
> 范围：组件交互、API 契约、构建测试部署、认证会话边界

## 1. 扫描方法

本轮分四批独立复核，并使用全库 `rg` 交叉核对生产消费方、后端路由、配置引用和测试入口；最终跨批次去重。每个文件先判断模块定位与三态：活跃、未接入、废弃。

| 批次 | 范围 | 复核重点 | 结果 |
|---|---|---|---|
| 一 | components、views、模板交互 | XSS、错误态、键盘操作、表单标签、弹窗语义 | 新增活跃 9 项 |
| 二 | API 客户端、请求封装、后端路由 | Response 解析、状态码、参数、路径和 schema | 新增活跃 4 项，未接入 2 项 |
| 三 | Vite、ESLint、CI、Docker、Nginx | 构建产物、权限、触发范围和 source map | 新增活跃 5 项，扩展 1 项 |
| 四 | token、Pinia 持久化、WebSocket 生命周期 | 跨账户缓存、登出清理、手动断线和重连 | 新增活跃 4 项 |

## 2. 新增活跃问题

### 组件与交互批次

#### FRESCAN-28 [P1] 历史会话标题直接进入 `v-html`

`src/components/HistoryItem.vue:12-21,35-41` 将接口或本地会话标题传入 `v-html`；搜索高亮只转义关键词，未转义原始标题。`VirtualHistoryList.vue` 和 `leftlist.vue` 在活跃历史链消费该组件，恶意标题可在登录态页面注入 HTML/脚本。

#### FRESCAN-29 [P2] PPT 预览失败落入空数据状态

`src/views/PPTPreview.vue:120-149,192-200` 在 HTML 预览和传统幻灯片加载失败后仅记录错误，模板统一展示“暂无幻灯片数据”。用户无法区分空数据、网络错误和服务端错误，也没有重试入口。

#### FRESCAN-30 [P1] Agent 下载失败后仍结束会话

`src/views/AgentDashboard.vue:206-228` 将下载和 `backend.stopSession()` 放在同一流程；下载失败进入捕获逻辑后仍会继续结束会话。生成文件可能随会话清理，用户失去可用副本。

#### FRESCAN-31 [P2] 多个活跃交互仅支持鼠标点击

`AgentSidebar.vue:12-18,49-63`、`AgentWorkspace.vue:33-53,100-112,137-149,166-178`、`ModelSelector.vue:4-5,59-64`、`ChartEditorPage.vue:55-56`、`ImageGenerate.vue:33-42` 和 `VirtualGirl.vue:102-105` 使用可点击 `div`，缺少原生控件语义、焦点入口和键盘事件。键盘及辅助技术用户无法稳定完成会话、文件、模型、上传或搜索操作。

#### FRESCAN-32 [P2] Agent 发送和停止按钮缺少可访问名称

`src/components/agent/AgentInputBar.vue:32-46` 的发送、停止按钮只包含 SVG，没有文本、`aria-label` 或 `title`。屏幕阅读器无法识别操作用途。

#### FRESCAN-33 [P2] 图片生成结果和历史图片缺少 `alt`

`src/views/ImageGenerate.vue:34,192,216` 的三处图片只绑定 `src`。参考图、生成结果和历史图片均缺少替代文本，辅助技术无法理解内容与操作上下文。

#### FRESCAN-34 [P2] 活跃表单标签未关联控件

`UserManagement.vue`、`NginxConfig.vue`、`APIKeyManager.vue`、`DynamicProviderManager.vue`、`VirtualGirl.vue` 和 `ChartEditorPage.vue` 的多处 `label` 缺少匹配的 `for`/`id`。输入目的主要依赖邻近文本或 placeholder，表单导航和错误定位不稳定。

#### FRESCAN-35 [P2] 自定义弹窗缺少 dialog 语义和焦点管理

`UserManagement.vue`、`VirtualGirl.vue`、`ServiceManager.vue` 和 `agent/modals/UploadModal.vue` 的弹窗根节点缺少 `role="dialog"`、`aria-modal`、标题关联、Escape 处理和关闭后的焦点回归。仓库中的共享 `ui/Modal.vue` 已具备部分语义，形成实现分裂。

#### FRESCAN-36 [P2] 设置和 Agent 初始化失败静默显示为空配置

`APIKeyManager.vue:288-292`、`DynamicProviderManager.vue:150-153` 和 `AgentDashboard.vue:355-378` 对初始化接口使用空 catch。请求失败、超时或认证失败会显示空列表或默认配置，没有错误状态和重试入口。

### API 契约批次

#### FRESCAN-37 [P1] 任务列表活跃页面把 `Response` 当作 JSON 数据

`src/components/TaskQueue.vue:169-180` 直接读取 `api.request()` 的 `data.tasks`；`src/utils/api/base.js:139-169` 返回原生 `Response`，页面没有调用 `await data.json()`。后端 `GET /api/v1/tasks` 返回包含 `tasks` 的 JSON，任务队列页面因此保持空列表。

#### FRESCAN-38 [P1] 任务取消 204 响应被强制解析为 JSON

`src/utils/api/task.js:36-46` 对取消成功响应调用 `response.json()`；后端 `app/api/v1/task_queue.py:227,253-263` 声明 `204` 且没有 body。JSON 解析抛错后客户端返回失败，页面不会刷新，继续显示已取消任务。

#### FRESCAN-39 [P1] 项目文件预览缺少后端必填参数

`ProjectGenerator.vue:1155-1163` 调用 `api.getProjectFiles()` 时未传 `project_path`；`473-484` 将单个字符串传给 `readProjectFile()`。后端 `generate_endpoints.py:167-176,208-223` 要求 `project_path`，读取还要求 `file_path`，活跃预览链会返回 422 或错误查询键。

#### FRESCAN-40 [P1] 快照对比参数位置错位

`ProjectGenerator.vue:1193-1201` 调用 `getSnapshotDiff(tag1, tag2)`，而 `src/utils/api/agent.js:51-56` 签名为 `(sessionId, fromTag, toTag)`。请求会把标签当作 session ID，并发送 `to_tag=undefined`；后端 `orchestrate_endpoints.py:1226-1244` 将三项均视为必填。

#### FRESCAN-41 [P1] 活跃 API Key 客户端默认固定请求本机后端

`src/utils/request.ts:6` 的 fallback 是 `http://localhost:8000`，`src/api/apikey.js` 及 `stores/apikey.js` 活跃消费该客户端。其他客户端使用 `VITE_API_BASE` 或相对 `/api/v1`，生产环境未显式设置 `VITE_API_BASE_URL` 时 API Key 页面会请求用户本机后端。

#### FRESCAN-42 [P1] 合并镜像以非特权用户启动 Nginx 80 端口

`Dockerfile:80-91` 切换到 `USER appuser` 后启动 Nginx；`configs/nginx.conf:7,88` 监听 80 并设置 `user root`。镜像没有低端口授权或高位端口方案，合并运行拓扑可能无法绑定 80 或创建 PID 文件。

#### FRESCAN-43 [P2] ESLint 配置遗漏 TypeScript 解析范围

`src/eslint.config.js:11-12` 的文件匹配仅包含 Vue/JavaScript 扩展，`src/utils/request.ts:8-15,36,65` 含 interface、类型注解和泛型；`src/package.json:10` 与前端 CI 直接执行 `eslint .`。TypeScript 文件可能解析失败或缺少规则覆盖。

#### FRESCAN-44 [P2] 前端 CI 触发范围遗漏部署与运行时配置

`.github/workflows/frontend-ci.yml:3-11` 的路径过滤仅包含 `src/**`。Dockerfile、Compose、Nginx 和 scripts 的产物路径、upstream、端口或启动链变更不会触发前端构建门禁。

#### FRESCAN-45 [P3] 生产构建默认暴露 source map

`src/vite.config.js:77-81` 设置 `build.sourcemap: true`；`configs/nginx.conf:91-103` 将构建目录作为静态根目录且未拒绝 `.map`。生产产物可能暴露源码、模块路径、内部 API 结构和注释信息。

### 认证与会话批次

#### FRESCAN-46 [P2] Agent 会话历史跨账户复用

`stores/agentSession.js:7,37-67` 使用固定 `agent_project_sessions` 键保存 prompt、时间和状态；`stores/user.js:59-73` 注销不清理该键。用户 A 退出后，用户 B 在同一浏览器初始化 Agent 页面可看到 A 的本地会话元数据并进入旧上下文。

#### FRESCAN-47 [P2] API Key、供应商和模型覆盖缓存跨账户复用

`stores/apikey.js:12-14,36-83` 与 `stores/providers.js:12,18-33` 使用固定 localStorage 键并在认证状态建立前恢复；注销流程不清理。A 的 token、供应商地址、模型映射可能在 B 的请求完成前展示、回退使用或继续写回。

#### FRESCAN-48 [P2] 管理日志持久化状态跨账户复用

`stores/logs.js:90-140` 将最多 500 条系统日志和筛选状态写入固定 `systemLogsState`；`SystemLogs.vue:356-373` 恢复与保存；注销流程未调用清理。新账户连接建立前可能看到旧账户日志及过滤状态。

#### FRESCAN-49 [P2] 手动断开 WebSocket 后仍会自动重连

`src/utils/api/websocket.js:86-92` 所有 `onclose` 都调用 `attemptReconnect()`；`disconnect():99-110` 只清理定时器并关闭连接，没有手动关闭标记。系统监控、日志组件卸载或隐藏后，异步 close 事件可能重新建立连接并继续运行心跳。

## 3. 未接入方法问题

#### FRESCAN-50 [P3，未接入方法] Kolors 历史分页参数使用 `limit`

`src/utils/api/kolors.js:90-99` 发送 `page, limit`，后端 `app/api/v1/kolors_history.py:40-69` 只消费 `page_size`。该方法全库无生产消费方，当前活跃图像页面使用另一条请求链。

#### FRESCAN-51 [P3，未接入方法] AiCloud 历史搜索参数名不匹配

`src/utils/api/aicloud.js:73-82` 发送 `query`，后端 `app/api/v1/aicloud.py:715-770` 要求必填 `keyword`。方法全库无生产消费方，未来直接接入会收到 422。

## 4. 既有问题扩展与排除项

- FRESCAN-23：`configs/nginx.conf:76-78,106-110` 对 `/api/` 全局使用 `proxy_read_timeout 60s`，SSE 没有独立超时；本轮将“缺少运行时验收”扩大为明确的长时间无数据断连风险。
- FESURF-008：旧 `AgentInputPanel.vue`、`_deprecated/ChartEditor.modal.vue` 存在鼠标专用交互，均为未接入/废弃代码，不计入活跃新增。
- `AgentFilePanel.vue:20` 的既有 `v-html` 继续保持待实测，Highlight.js 输出链证据不足以单独确认 XSS。
- FEBOOT-01 至 06、FRESCAN-12 至 27 及既有 WebSocket 无 token、任务 WS 无认证、PPT 历史越权项本轮均已排除重复登记。

## 5. 统计与证据边界

去重后新增活跃问题 22 项：P1 8 项、P2 13 项、P3 1 项；另有未接入方法问题 2 项。FRESCAN-23 属于既有问题范围扩展，不新增 Backlog 编号。第 164 轮新增 Backlog 使用 `#1370-#1391`，累计为 P0 1、P1 47、P2 481、P3 814，Backlog 共 1391 项。

本轮完成源码、全库引用、后端路由和配置静态核对；未启动 Vite、FastAPI、Docker、Nginx、浏览器或屏幕阅读器。source map 内容、容器低端口能力、SSE 心跳、跨账户浏览器时序、下载后的会话清理和实际 API 响应仍需运行验证。

## 6. 修复顺序

1. 先处理安全与账户边界：FRESCAN-28、FRESCAN-46、FRESCAN-47、FRESCAN-48、FRESCAN-41。
2. 再处理核心功能契约：FRESCAN-30、FRESCAN-37、FRESCAN-38、FRESCAN-39、FRESCAN-40、FRESCAN-49。
3. 接着统一生产部署和构建门禁：FRESCAN-42、FRESCAN-44、FRESCAN-45、FRESCAN-23。
4. 最后收敛可访问性、错误态和未接入方法：FRESCAN-31 至 36、FRESCAN-43、FRESCAN-50、FRESCAN-51。
