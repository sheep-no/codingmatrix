# Frontend 分批重扫记录

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：前端应用第 163 轮分批复核
> 基线：第 162 轮 `frontend_bootstrap.md`、`frontend_state.md`、`frontend_surface.md`
> 范围：入口认证、状态组合逻辑、视图组件 API、构建测试部署

## 1. 扫描方法

本轮将前端拆成四个批次。每个批次独立读取源码，并使用全库 `rg` 核对生产消费方、后端路由、配置引用和测试入口；最终按跨批次重复项去重。

| 批次 | 范围 | 复核重点 | 结果 |
|---|---|---|---|
| 一 | `main.js`、`App.vue`、Router、认证 composable/store、认证后端 | token、refresh、路由守卫、注册资料接口 | 旧问题复核 6 项，新增认证问题 4 项 |
| 二 | `stores/`、`composables/`、AgentDashboard、首页流式链 | 快照、队列、Pinia 解包、SSE、并发和会话所有权 | 旧问题复核 7 项，去重后新增 7 项 |
| 三 | `views/`、`components/`、API 客户端、浏览器工具和 v1/v2 路由 | API 形状、路径、响应、凭证和旧组件 | 旧问题复核 8 项，新增 5 项 |
| 四 | Vite、脚本、CI、Docker/Compose、Nginx、前端测试和 E2E | 构建产物、代理、端口、测试执行链 | 旧问题复核 3 项，新增 10 项 |

## 2. 上一轮结论修订

| 编号 | 修订后结论 | 证据 |
|---|---|---|
| FEBOOT-01 | 保留 P1。缺 token 仍允许进入 `requiresAuth` 路由 | `src/router/index.js:103-124` |
| FEBOOT-02 | 保留 P1，范围收窄为 Vite/后端使用 `/workspace/dist`，启动脚本、Nginx、Compose、CI 使用 `src/dist` | `src/vite.config.js:77-80`、`app/main.py:334-348`、`scripts/start.sh:61-71`、`configs/nginx.conf:91-93`、`.github/workflows/frontend-ci.yml:57-64` |
| FEBOOT-03 | 保留 P2，重复恢复链由两处扩大为入口、`LoginDialog`、`leftlist` 三处 | `src/main.js:27-32`、`src/composables/useAuth.js:6-13`、`src/components/leftlist.vue:742-755` |
| FEBOOT-05 | 保留 P3，主题正常加载时变量存在，问题属于条件性 fallback 健壮性风险 | `src/App.vue:28-35`、`src/styles/variables.css` |
| FEBOOT-06 | 保留 P3 信息项，仓库内无消费方，外部显式 `--config` 调用待确认 | `src/vite-temp.config.js:1-25`、全库引用扫描 |
| FESTATE-04 | 保留 P2，当前后端单行 `data: ` 兼容，解析器仍缺标准 SSE 空行、多行和尾帧处理 | `src/composables/useAgentStreaming.js:284-315`、`app/api/v1/ai_agent/orchestrate_endpoints.py:763-820` |
| FESURF-004 | 保留 P1，并扩大为多组管理 API 缺少 `/Controller` 前缀，参数和返回形状也存在错位 | `src/utils/api/admin.js:66-164`、`app/api/v2/guardian_router.py:25,85-196` |

## 3. 去重后的新增问题

### 认证与入口批次

#### FRESCAN-01 [P3] 未接入 refresh 封装缺少 CSRF Header

`src/utils/api/auth.js:62-75` 的 `refreshToken()` 只发送 Cookie 凭证，没有 `X-CSRF-Token`；后端 `app/api/v1/auth.py:360-365` 要求 CSRF 校验。当前生产刷新链使用 `tokenManager.js:117-163`，该封装无生产消费方，按未接入代码缺陷登记。

#### FRESCAN-02 [P3] 未接入 logout 封装调用不存在的后端端点

`src/utils/api/auth.js:78-85` 调用 `/api/v1/logout`，认证路由没有该端点。当前退出流程由 `useAuth.js` 和 `leftlist.vue` 清理本地状态完成，问题属于认证 API 双轨残留。

#### FRESCAN-03 [P2] access token 存储来源形成三轨

`tokenManager.js:39-50` 将 access token 写入 `localStorage.access_token`，同时保留内存和 sessionStorage 来源；`base.js`、Router、GitHub API 直接读取 localStorage。`user.js` 注释描述与实际行为不一致，清理、刷新和同源脚本读取风险由多套来源放大。

#### FRESCAN-04 [P3] 登录界面展示未接入的认证入口

`LoginDialog.vue:18,116-187` 的 `rememberMe` 没有参与请求，忘记密码链接为 `#`，GitHub/Google 登录按钮没有事件处理器；后端认证路由也没有对应流程。

### 状态与流式批次

#### FRESCAN-05 [P1] SSE 重连复用同一队列导致客户端竞争事件

`orchestrate_endpoints.py:822-830` 将队列写入 `_active_tasks`，重连路径 `:547-559` 继续读取同一 `asyncio.Queue`。多个客户端竞争 `queue.get()` 时，每条事件只会到达一个客户端，重连状态可能不完整。

#### FRESCAN-06 [P1] 审批/决策队列绕过 session 用户归属校验

`orchestrate_endpoints.py:1440-1447` 在存在审批或决策队列时直接放行；`session_action_endpoint` 与 `submit_decision_endpoint` 均调用该函数。已认证用户仅凭 session ID 可能操作他人的审批、决策或取消流程。

#### FRESCAN-07 [P1] 删除会话没有停止运行任务和清理内存状态

`orchestrate_endpoints.py:1455-1488` 删除数据库记录并清理少数目录，没有设置取消事件、停止 `_active_tasks`、清理审批/决策队列或移除 SessionManager 状态；运行任务可能继续写文件或回写已删除会话。

#### FRESCAN-08 [P1] 首页 `/code` 流按读取块解析，跨块 JSON 会丢失

`components/index.vue:550-635` 对每次 `reader.read()` 结果直接 `split('\n')`，没有跨 chunk buffer，也没有流式 decoder；`Aicode.py:590-619,762-779` 按 JSON 行输出，网络分片切断 JSON 时前端会丢失内容。

#### FRESCAN-09 [P2] Agent 工作区复制没有捕获异步剪贴板失败

`useAgentWorkspace.js:126-131` 使用 `await navigator.clipboard.writeText`，调用路径由 `AgentDashboard.vue:302` 消费，但没有 try/catch；权限拒绝会产生未处理 rejection。该问题与 FESTATE-05 的设置复制路径分开登记。

#### FRESCAN-10 [P2] 多 worker 会话创建锁无法提供全局互斥

`orchestrate_endpoints.py:130,532-546` 的 `_user_creation_locks` 是进程内字典，数据库查询只有 running 状态检查；多 worker/多实例部署可能同时创建同一用户的多个 running 会话。

#### FRESCAN-11 [P2] Agent 生成函数没有内部并发幂等保护

`useAgentStreaming.js:411-435` 每次调用都会新建请求并写入同一 files/workspace/generation 状态；按钮禁用只能降低重复点击，键盘或程序调用仍可形成多个并发消费者。

### 视图与 API 批次

#### FRESCAN-12 [P1] 管理客户端多组路径缺少 `/Controller` 前缀

`admin.js:66-164,341-391,417-563` 生成服务、健康、备份、日志和限流请求；活跃组件调用这些路径。后端 `guardian_router.py:25` 的真实前缀为 `/api/v2/Controller`，同一客户端还并存 `/api/v2/admin/*` 独立路由，路径体系分裂。

#### FRESCAN-13 [P1] API Key 批量导出 format 参数没有进入 URL

`src/api/apikey.js:95-97` 传入 `{ params: { format } }`，`src/utils/request.ts:62-86` 没有处理 params，因此后端 `apikey.py:513-579` 的 CSV/JSON 分支始终收到默认参数。

#### FRESCAN-14 [P1] PPT 创建模板字段名不匹配

`src/utils/api/ppt.js:26` 发送 `template_id`，后端 `PPTGenerationRequest` 在 `aiGeneratorPptx.py:83-100` 定义字段为 `template`；未知字段被 Pydantic 忽略后，模板选择可能静默回到 `modern`。

#### FRESCAN-15 [P1] 多个原生 fetch 绕过统一认证和 CSRF

`file.js:19-23,53-59`、`aicloud.js:197-204`、`Aicloud.vue:561-573`、`workflow.js:13-25` 使用独立请求路径；文件上传和工作流后端端点要求 JWT，统一基础客户端提供的 token refresh、CSRF 和 credentials 契约没有被完整复用。

#### FRESCAN-16 [P2] WebSocket 连接池是零消费的第二套实现

`src/utils/websocketPool.js` 提供 token、心跳和重连，但全库没有生产 import；系统监控和日志仍使用 `WebSocketManager`。重复实现增加连接行为分裂和误接线风险。

### 构建、测试与部署批次

#### FRESCAN-17 [P1] 生产 Compose 的 Nginx 缺少前端静态文件来源

`docker-compose.prod.yml:79-92` 的 Nginx 没有挂载前端产物；`Dockerfile:60-73` 只为镜像内路径建立 `/app/src/dist`，独立 Nginx 读取 `configs/nginx.conf:91-93` 的 `/workspace/src/dist`，两种部署拓扑没有共享机制。

#### FRESCAN-18 [P1] 容器 Nginx upstream 指向自身回环地址

`configs/nginx.conf:80-84` 使用 `127.0.0.1:8080`，Compose 中 Nginx 和 API 是独立容器，API 服务名为 `api`；容器内回环地址无法到达 API 容器。

#### FRESCAN-19 [P2] 健康检查路径与真实 FastAPI 路由不一致

真实健康路由是 `/api/v1/health`，Dockerfile 和生产 Compose 检查 `/health`；Nginx 的 `/health` 还可能命中 SPA fallback，形成 API 不健康但检查返回 200 的假象。

#### FRESCAN-20 [P2] 主启动脚本默认项目根目录推导错误

`scripts/start.sh:17-18` 将项目目录设为 `/workspace/scripts`，后续查找 `scripts/src/package.json`、`scripts/configs/nginx.conf` 和 `scripts/app`；从默认位置启动时无法可靠访问实际项目目录。

#### FRESCAN-21 [P2] 后端端口在开发、生产、CI 和状态脚本间分裂

开发脚本使用 8000，Gunicorn/Compose 使用 8080，E2E 启动 8000 却等待 8080，状态脚本只检查 8080；测试和运维状态因此可能互相矛盾。

#### FRESCAN-22 [P2] HTTP 开发环境固定使用 `wss` HMR

`src/vite.config.js:43-53` 在 HTTP 开发服务器上固定 `hmr.protocol: 'wss'`；本地和 CI 没有统一 TLS 终止配置，热更新连接需要浏览器实测确认。

#### FRESCAN-23 [P2] SSE 代理和生产 Nginx 缺少统一运行时验收

Vite 代理使用 `selfHandleResponse` 手动写 SSE，生产 Nginx 依赖全局代理配置；断连、错误响应、重复结束、响应头和缓冲行为没有专门 CI 门禁。

#### FRESCAN-24 [P2] Vitest 脚本存在但前端测试入口为空

`src/package.json:12-14` 声明 Vitest 命令，`src` 下没有 `*.test/spec.*` 文件，CI 只执行 lint/build。实际运行 `npm run test:run -- --passWithNoTests` 因缺少 `node_modules` 无法启动。

#### FRESCAN-25 [P1] Playwright 包声明、安装目录和执行目录断链

测试导入 `@playwright/test`，`src/package.json` 只声明 `playwright`；CI 在 `src` 安装后从仓库根目录执行 `npx playwright test`，仓库还存在三套 Playwright 配置。

#### FRESCAN-26 [P2] E2E 测试使用多套前后端地址

默认前端端口为 3000，CI 使用 5173；测试还混用后端 8000、8080、8002。单一启动拓扑无法稳定承载整套 E2E。

#### FRESCAN-27 [P3] lint 命令包含自动写操作

`src/package.json:10` 的 `lint` 实际执行 `eslint . --fix`，CI 直接运行该命令。校验过程可能改写源码，命令语义与只读检查不一致。

> 本节编号包含 27 条便于逐条追踪；FRESCAN-16 与上一轮已登记的旧组件双轨属于同一结构事项，统计时不重复计数。FRESCAN-23 将上一轮待实测的 SSE 代理风险通过部署配置核对提升为独立活跃问题。

## 4. 统计与证据边界

去重后新增活跃问题 26 项：P1 10 项、P2 12 项、P3 4 项。上一轮已有问题中，FESTATE-04、FESURF-007 和 HMR 属于范围扩展，已在对应条目中合并；FRESCAN-16 属于已有未接入结构事项的复核记录。

本轮通过静态源码、全库引用、后端路由和配置交叉核对确认问题。已执行的轻量验证包括 `bash -n scripts/start.sh`、配置语法检查和 `npm ci --dry-run --ignore-scripts`；真实构建、Vitest、Playwright、Docker、Nginx、浏览器 WebSocket/HMR/SSE 仍受环境依赖或服务未启动限制，相关结论保留待实测标记。

## 5. 修复顺序

1. 先处理安全与数据边界：FRESCAN-06、FRESCAN-07、FRESCAN-03、FRESCAN-15、FESURF-002。
2. 再处理核心可用性：FESURF-001、FESTATE-01、FRESCAN-05、FRESCAN-08、FRESCAN-12、FRESCAN-14。
3. 接着统一部署和测试契约：FEBOOT-02、FRESCAN-17、FRESCAN-18、FRESCAN-19、FRESCAN-25、FRESCAN-26。
4. 最后收敛双轨和待实测风险：FEBOOT-06、FRESCAN-16、FRESCAN-22、FRESCAN-23、FRESCAN-27。
