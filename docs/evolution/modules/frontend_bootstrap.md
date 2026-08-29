# Frontend Bootstrap 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-29 | 状态：已完成
> 归属：前端应用 / FEBOOT
> 路径：`src/main.js`、`src/App.vue`、`src/router/index.js`、`src/vite.config.js`、`src/vite-temp.config.js`、`src/index.html`、`src/package.json`、`src/eslint.config.js`（435 行）
> 索引：`[TASKS.md](tasks.md)`

## 1. 模块作用与功能

### 模块定位与状态判定

- `main.js`、`App.vue`、`router/index.js`、`vite.config.js`、`index.html`、`package.json`、`eslint.config.js` 构成活跃的前端入口、应用壳、路由和构建契约。
- `vite-temp.config.js` 与 `vite.config.js` 存在重复的 Vue/Vite 构建配置；全库 `rg` 未发现 `vite-temp.config.js` 的调用方，按“无消费引用且由默认 `vite.config.js` 承担同职责”判定为废弃候选。该替代关系属于实码可证的结构判断，实际文件是否由外部命令调用仍待实测。

### 核心职责

- `src/main.js:1-34` 创建 Vue 应用，注册 Pinia、持久化插件、Vue Router、Element Plus、全局组件和全局样式，并初始化用户 Store 与 API 客户端后挂载应用。
- `src/App.vue:1-36` 提供应用壳、主题初始化、固定加载态、错误边界和 `router-view`。
- `src/router/index.js:4-101` 声明首页、Agent、工作流、PPT、绘图、AI Cloud、GitHub 配置、设置、管理员、文档和图表编辑路由。
- `src/vite.config.js:24-95` 提供 Vue 插件、`@` 别名、Vitest 配置、开发服务器、API/SSE/WebSocket 代理和生产构建分包配置。
- `src/index.html:1-32` 提供 SPA 宿主节点、跳过链接、favicon、页面标题和 `main.js` 模块入口。
- `src/package.json:6-14` 定义开发、构建、预览、Lint、格式化和 Vitest 命令。
- `src/eslint.config.js:6-35` 定义 ESLint flat config、Vue 规则、浏览器/Node 全局变量及忽略目录。

### 调用链

```text
index.html
  -> main.js
     -> createApp(App)
     -> createPinia + persistedstate
     -> app.use(router)
     -> useUserStore()
     -> initApiClient(userStore) -> window.api
     -> userStore.restoreUser()
     -> app.mount('#app')
        -> App.vue
           -> initTheme()
           -> ErrorBoundary -> router-view
              -> router/index.js 的异步路由组件
```

### 对外接口与内部子功能

- 应用入口：`src/index.html:28-30` 的 `#app` 与 `/main.js`。
- 路由入口：`src/router/index.js:104-125` 的全局认证/超级管理员守卫。
- API 初始化入口：`src/main.js:28-29` 调用 `initApiClient(userStore)`；`src/utils/api/index.js:90-100` 将组合客户端挂载为 `window.api`，并以 Proxy 导出延迟访问的 `api`。
- 开发代理：`src/vite.config.js:54-75` 转发 `/api/v1`、`/api/v2` 到 `http://localhost:8000`，并对 SSE 响应关闭缓存和 Nginx 缓冲。
- 生产服务契约：`src/vite.config.js:77-94` 输出到 `../dist`；`configs/nginx.conf:91-108` 期望从 `/workspace/src/dist` 提供静态文件并代理 `/api/`。

## 2. 依赖与被依赖

### 导入依赖

- 运行时：Vue、Pinia、`pinia-plugin-persistedstate`、Element Plus、Vue Router。
- 入口内部：`App.vue`、`router/index.js`、`stores/user.js`、`utils/api/index.js`、`components/ToastContainer.vue`、全局 CSS。
- 应用壳：`utils/theme`、`components/ErrorBoundary.vue`、`components/AppLoading.vue`。
- 构建与测试：Vite、`@vitejs/plugin-vue`、Vitest、jsdom、ESLint Vue flat config。

### 生产使用方

- `src/main.js:7-10` 直接消费应用壳、路由、用户 Store 和 API 初始化函数。
- `src/router/index.js:10,20,26,32,38,44,50,56,62,68,74,80,86,92` 异步消费各页面/组件。
- API Proxy 的生产消费方至少包括 `src/components/index.vue:133`、`src/views/PPTPreview.vue:98`、`src/components/AdminPanel.vue:620` 及全库多个 API/组件模块；全库 `rg` 共确认多个 `@/utils/api/index` 引用。
- `src/composables/useAuth.js:6-13` 被 `src/components/LoginDialog.vue:3,11` 消费；该组件在 `src/components/leftlist.vue:416-429` 挂载。

### 测试覆盖

- `tests/frontend/test_components.py:1-18` 只是 pytest 占位测试，声明实际前端测试应位于 `src/tests/`，但当前工作区未发现 `src/**/*.spec.js`。
- `tests/e2e/` 多处检查 `#app`、页面导航和前端交互，例如 `tests/e2e/core.spec.js:32-48`、`tests/e2e/02-core-navigation.spec.js:110-122`；这些属于 E2E 消费方，未形成入口、路由守卫、代理和构建输出的完整契约测试。
- `tests/e2e/` 之外，全库未发现针对 `router.beforeEach`、`initApiClient`、`vite.config.js` 代理规则或 `vite-temp.config.js` 的专门测试。

## 3. 已探明 Bug（含 bug 代码）

### FEBOOT-01 [P1] 认证守卫对匿名访问放行

- **状态**：活跃代码；实码可证，运行结果待实测。
- **现象**：所有带 `meta.requiresAuth` 的普通路由在没有 token 时执行 `next()`，因此匿名用户可以进入首页、工作流、PPT、Agent、AI Cloud、设置等页面。首页通过页面层登录弹窗补救，其他页面没有统一的登录重定向契约。
- **Bug 代码**：

```js
// src/router/index.js:104-115
const token = userStore.getAccessToken() || localStorage.getItem('access_token')

if (to.meta.requiresAuth) {
  if (!token) {
    // 未登录，直接访问首页（首页会自动弹出登录框）
    next()
    return
  }
}
```

- **根因**：缺少 token 的分支与受保护路由的成功导航等价，守卫没有返回登录路由、登录状态或统一匿名入口。
- **影响**：认证边界由页面 API 请求被动承担；受保护页面可能先渲染、触发无 token 请求并产生 401，管理员路由则继续依赖权限级别分支处理。
- **触发条件**：清空 `access_token` 后直接打开任意 `requiresAuth: true` 路径，例如 `/workflow` 或 `/settings`。
- **验证方式**：浏览器清空 `localStorage.access_token` 与 Pinia 状态后访问受保护路径，记录最终 URL、页面渲染和首个 API 响应；补充无 token 的路由单元测试。

### FEBOOT-02 [P1] 构建输出目录与运行时静态根目录不一致

- **状态**：活跃构建/部署契约；实码可证，构建产物与启动结果待实测。
- **现象**：Vite 从 `/workspace/src` 执行构建时将产物写入 `/workspace/dist`；启动脚本检查 `/workspace/src/dist`，Nginx 也从 `/workspace/src/dist` 提供静态文件。成功构建后的部署检查可能报告失败，Nginx 可能继续服务旧产物或空目录。
- **Bug 代码**：

```js
// src/vite.config.js:77-80
build: {
  outDir: '../dist',
  assetsDir: 'static',
}
```

```bash
# scripts/start.sh:61-71
cd "$PROJECT_DIR/src"
npm run build
if [ -d "$PROJECT_DIR/src/dist" ]; then
    log_info "前端构建成功: $PROJECT_DIR/src/dist"
fi
```

```nginx
# configs/nginx.conf:91-93
root /workspace/src/dist;
index index.html;
```

- **根因**：构建配置、启动脚本校验路径和 Nginx `root` 没有共享同一输出目录契约。
- **影响**：生产静态页面、SPA fallback 和静态资源加载可能失败；部署脚本的成功判断不可信。
- **触发条件**：执行 `cd /workspace/src && npm run build`，随后运行 `scripts/start.sh` 或使用 `configs/nginx.conf` 启动 Nginx。
- **验证方式**：执行一次前端构建，分别检查 `/workspace/dist/index.html`、`/workspace/src/dist/index.html` 和 Nginx 实际返回的 HTML/资源状态；本轮未执行以保持源码与运行环境只读。

### FEBOOT-03 [P2] 应用初始化重复触发用户恢复和刷新请求

- **状态**：活跃消费链；实码可证，重复网络请求次数待实测。
- **现象**：入口初始化调用一次 `restoreUser()`；`LoginDialog` 通过 `useAuth()` 挂载时再次调用一次。用户信息存在但 access token 需要刷新时，两处逻辑可能并发请求 refresh。
- **Bug 代码**：

```js
// src/main.js:27-32
const userStore = useUserStore()
initApiClient(userStore)
userStore.restoreUser()
```

```js
// src/composables/useAuth.js:6-13
export function useAuth() {
  const userStore = useUserStore()
  onMounted(() => {
    userStore.restoreUser()
  })
}
```

- **根因**：全局启动层和认证弹窗 composable 同时拥有恢复职责；`LoginDialog` 在 `leftlist.vue:416-429` 作为子组件存在，登录弹窗可见性由内部 `v-if` 控制。
- **影响**：刷新接口重复、竞态刷新、无 refresh cookie 时重复失败日志；初始化行为变得依赖组件挂载时序。
- **触发条件**：localStorage 存在用户名而 access token 不在内存中，应用启动并挂载左侧列表。
- **验证方式**：对 `/api/v1/refresh` 做浏览器网络记录，使用“仅保存用户信息、移除 access token”的状态启动应用，确认请求数量和时序。

### FEBOOT-04 [P2，未接入代码内逻辑缺陷] `useAuth` 的注册与资料更新路径错误

- **状态**：未接入面；实码可证。全库仅确认 `LoginDialog` 消费 `useAuth().login`，未发现 `register` 或 `updateProfile` 的生产消费方。
- **现象**：注册请求拼成 `/api/v1/auth/register`，后端实际挂载为 `/api/v1/register`；资料更新请求拼成 `/api/v1/auth/profile`，后端实际路由为 `/api/v1/user/profile`。
- **Bug 代码**：

```js
// src/composables/useAuth.js:28-30,64-66
const response = await api.post('/auth/register', { username, email, password })
const response = await api.put('/auth/profile', updates)
```

- **对照依据**：`src/utils/api/auth.js:52-59` 已有可用的 `register()` 封装；`app/api/v1/auth.py:232` 注册路由为 `/register`，`app/api/v1/auth.py:444` 资料路由为 `/user/profile`。
- **根因**：`useAuth` 直接拼接了错误的 `auth/` 路径，并与 API 认证模块重复表达同一职责。
- **影响**：当前未影响已确认的登录消费方；未来启用这两个 composable 方法时会收到 404 或错误路由响应。
- **触发条件**：调用 `useAuth().register()` 或 `useAuth().updateProfile()`。
- **验证方式**：接入调用方后使用浏览器 Network 或 API mock 验证 URL；当前可用静态路由对照确认问题，尚无生产调用实测。

### FEBOOT-05 [P3] 应用壳重复声明背景导致第一层样式配置被覆盖

- **状态**：活跃应用壳；实码可证，视觉效果待实测。
- **现象**：`.app-container` 连续声明两次 `background`，第二条渐变背景覆盖第一条次级背景声明。
- **Bug 代码**：

```css
/* src/App.vue:29-34 */
.app-container {
  background: var(--bg-secondary);
  background: var(--gradient-bg);
}
```

- **根因**：同一 CSS 属性重复赋值，缺少明确的 fallback 写法或层叠目的说明。
- **影响**：`--gradient-bg` 未定义、主题切换或浏览器不支持该变量时，预期的 `--bg-secondary` fallback 不会按声明顺序提供稳定兜底。
- **触发条件**：渐变变量缺失或主题变量初始化异常。
- **验证方式**：在浏览器删除 `--gradient-bg`，检查应用根节点计算后的背景值；补充主题变量缺失的组件测试。

### FEBOOT-06 [P3，废弃候选配置] `vite-temp.config.js` 形成未接入的构建双轨

- **状态**：废弃候选；全库 `rg` 未发现该文件的消费方，重复职责属于实码可证，外部显式 `--config` 调用待实测。
- **现象**：文件保留独立的 Vue/Vite 构建配置，但缺少活跃 `vite.config.js` 中的开发服务器、代理、测试和 `allowedHosts` 契约；若被外部命令选用，构建/开发行为会与默认配置分叉。
- **Bug 代码**：

```js
// src/vite-temp.config.js:5-24
export default defineConfig({
  plugins: [vue()],
  resolve: { alias: { '@': fileURLToPath(new URL('.', import.meta.url)) } },
  build: { outDir: '../dist', assetsDir: 'static', sourcemap: true },
  publicDir: 'public'
})
```

- **根因**：重复配置未被纳入统一构建入口；全库静态引用仅找到 `src/vite.config.js` 的默认配置消费契约，未找到 `vite-temp.config.js` 的脚本或 CI 引用。
- **影响**：显式使用该配置时，`/api/v1`、`/api/v2` 代理、SSE 处理、Vitest 配置和允许的预览 Host 均缺失，可能导致开发请求失败或预览被拒绝。
- **触发条件**：执行 `vite --config vite-temp.config.js`，或 CI/容器外部工具通过配置文件路径调用它。
- **验证方式**：检查所有 CI、容器入口和部署命令后执行一次显式配置启动；本轮静态扫描未发现仓库内消费方，因此未运行该命令。

## 4. 潜在问题与未知点

- **待实测：Vite HMR**：`src/vite.config.js:50-52` 固定使用 `hmr.protocol: 'wss'`，本地 `http://localhost:3000` 场景的 WebSocket 是否成功需要浏览器控制台和 Network 实测。
- **待实测：SSE 代理**：`selfHandleResponse: true` 配合 `configureSseProxy` 手动写响应；需在真实 SSE 端点验证断连、错误响应、重复 `end` 和代理头行为。
- **待实测：API 基址覆盖**：多个模块读取 `VITE_API_BASE`，而 Vite 代理只对相对 `/api/v1`、`/api/v2` 请求生效；配置绝对 API 地址时需确认 CORS、Cookie 和 CSRF 行为。
- `index.html:28` 的跳过链接固定指向 `#main-content`；该 ID 在首页 `components/index.vue:16` 和 `centerContent.vue:66` 可见，其他路由是否提供同一目标未形成统一壳层契约。
- ESLint `lint` 脚本使用 `--fix`（`src/package.json:10`），属于带写操作的校验命令；当前未执行，以满足本次只修改 Markdown 的范围。
- `vite-temp.config.js` 无引用结果来自全库静态搜索；仍需核对外部 CI、容器或人工命令是否通过 `--config` 显式调用。

## 7. 第 163 轮分批重扫修订

- `FEBOOT-02` 保留 P1，Vite 与 FastAPI 都使用 `/workspace/dist`；启动脚本、Nginx、Compose 和 CI 仍使用 `src/dist`，问题范围收窄为部署消费链路。
- `FEBOOT-03` 保留 P2，新增 `leftlist.vue` 第三处 `restoreUser()` 消费证据。
- `FEBOOT-05` 保留 P3，正常主题变量存在，问题属于变量缺失时的 fallback 健壮性风险。
- `FEBOOT-06` 保留 P3 信息项，仓库内没有 `vite-temp.config.js` 消费方。
- 新增认证复核项见 [frontend_batch_rescan.md](frontend_batch_rescan.md) 的 FRESCAN-01 至 FRESCAN-04。

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | 将缺 token 的 `requiresAuth` 导航统一返回登录入口，或建立明确的匿名入口；守卫使用真实登录状态和 token 有效性 | 让路由层成为可验证的认证边界，避免匿名渲染受保护页面 | `src/router/index.js:104-124` | FEBOOT-01 |
| 2 | P1 | 统一 `vite.config.js`、`scripts/start.sh`、Nginx 的单一输出目录，并在部署检查中验证同一 `index.html` | 让构建、启动校验和静态服务使用同一产物 | `src/vite.config.js:77-80`、`scripts/start.sh:61-71`、`configs/nginx.conf:91-93` | FEBOOT-02 |
| 3 | P2 | 保留一个全局 `restoreUser` 调用；移除 `useAuth` 的挂载恢复，或由 composable 接收已初始化状态 | 消除重复 refresh 和初始化竞态 | `src/main.js:27-32`、`src/composables/useAuth.js:6-13` | FEBOOT-03 |
| 4 | P2 | 让 `useAuth` 复用 `api.register`，将资料更新改为 `/user/profile`；在未接入功能明确前完成接线或整体退役 | 修正 API 路径并收敛认证职责 | `src/composables/useAuth.js:28-30,64-66`、`src/utils/api/auth.js:52-59` | FEBOOT-04 |
| 5 | P3 | 将背景声明改为明确 fallback 方案，并补充主题变量契约 | 保证主题变量异常时仍有稳定背景 | `src/App.vue:29-34` | FEBOOT-05 |
| 6 | P3 | 确认 `vite-temp.config.js` 的外部调用后删除重复配置或标注唯一用途 | 减少双轨构建配置和误用风险 | `src/vite-temp.config.js` | FEBOOT-06 |

## 6. 演化方向关联

- **拆分解耦**：将入口初始化、认证恢复、API 客户端初始化收敛为单一 bootstrap 协议，避免 `main.js` 与 `useAuth` 双重负责。
- **统一收敛**：统一 token 来源、API 基址、路由认证判定和构建输出目录；路由、Vite、启动脚本与 Nginx 应共享可测试的契约。
- **智能增强**：将加载态从固定 800ms（`App.vue:13-15`）演进为实际 bootstrap 状态驱动，覆盖主题、用户恢复和 API 初始化完成状态。
- **平台化**：为入口、路由守卫、API 初始化、代理/SSE、构建产物和 SPA fallback 建立 Vitest 与 Playwright 契约测试，并将构建产物路径作为 CI 部署验收项。
