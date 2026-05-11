# CodingMatrix 前端架构

## 技术栈

- **框架**: Vue 3 (Composition API, `<script setup>`)
- **构建**: Vite 5
- **UI**: Element Plus + Tailwind CSS
- **路由**: Vue Router 4
- **状态**: Pinia + pinia-plugin-persistedstate
- **HTTP**: Axios
- **图表**: ECharts
- **Markdown**: markdown-it

## 前端结构

```
src/
├── App.vue                    # 根组件 (主题初始化)
├── main.js                    # 应用入口
├── router/                    # 路由配置
│   └── index.js               # 路由守卫、权限验证
├── stores/                    # Pinia 状态管理
│   ├── user.js                # 用户状态、JWT Token、权限等级
│   ├── navigation.js          # 侧边栏状态、工具面板可见性
│   └── task.js                # 任务状态
├── components/                # Vue 组件 (50+ 个)
│   ├── index.vue              # 主页面 (聊天界面)
│   ├── leftlist.vue           # 左侧边栏 (导航、历史记录)
│   ├── layout/Sidebar.vue     # 响应式侧边栏
│   ├── LoginDialog.vue        # 登录弹窗 (Teleport 到 body)
│   ├── AdminPanel.vue         # 管理员面板 (系统监控、资源配置)
│   ├── Bottominput.vue        # 底部输入区
│   ├── CenterContent.vue      # 聊天内容区
│   ├── MessageEditor.vue      # 消息编辑器
│   ├── tools/                 # 工具组件 (13 个，延迟加载)
│   │   ├── NginxConfig.vue    # Nginx 配置生成
│   │   ├── Dockerfile.vue     # Docker 配置生成
│   │   ├── VirtualGirl.vue    # AI 虚拟对话
│   │   └── TaskQueue.vue      # 任务队列管理
│   └── ErrorBoundary.vue      # 错误边界组件
├── views/                     # 独立页面视图
│   ├── ProjectGenerate.vue    # AI 项目生成 (独立新标签页)
│   ├── Workflow.vue           # 智能工作流 (独立新标签页)
│   ├── ImageGenerate.vue      # AI 图像生成 (独立新标签页)
│   └── PPTGenerate.vue        # PPT 生成 (独立新标签页)
├── composables/               # 可复用逻辑
│   ├── useAuth.js             # 认证逻辑 (登录/注册/Token 刷新)
│   ├── useStream.js           # 流式请求管理
│   ├── useToast.js            # 全局通知系统
│   ├── useOfflineQueue.js     # 离线消息排队
│   └── useFocusTrap.js        # 焦点陷阱 (无障碍)
├── utils/                     # 工具函数
│   ├── api.js                 # Axios 封装 (拦截器、Token 管理)
│   ├── sse.js                 # SSE 事件流
│   ├── theme.js               # 主题切换 (light/default/dark)
│   └── crypto.js              # RSA/AES 加密
├── assets/                    # 静态资源
└── styles/                    # 全局样式
    ├── variables.css          # CSS 变量 (三套主题)
    └── base.css               # 基础重置、工具类
```

## 核心特性

### 1. 加密通信
- 登录使用 RSA-OAEP 加密密码
- AES-CBC 加密敏感数据传输
- CSRF Double-submit Cookie 防护

### 2. SSE 实时流
- AI 代码生成流式输出
- 项目生成进度推送
- PPT 生成异步状态推送

### 3. 多模态预览
- 图片预览 (JPEG/PNG/GIF/WebP/SVG)
- 文档预览 (PDF/Word/Excel)
- 代码高亮预览
- 视频/音频播放

### 4. 独立页面架构 (2026-05-08 新增)
- **工具新标签页打开**: Agent 工作台、工作流、PPT、图像生成均在独立新标签页运行
- **保留主会话**: 使用工具时不影响主聊天界面的对话状态
- **路由权限控制**: 管理员页面使用 `requiresSuper` 元数据守卫
- **角色可见性过滤**: AI 云助手、管理员面板仅对 admin/superadmin 可见

### 5. 主题系统
- **三种主题**: `theme-light` (明亮蓝), `theme-default` (默认青), `theme-dark` (暗色)
- **CSS 变量驱动**: 所有组件使用 `var(--bg-*)`, `var(--text-*)` 等变量
- **平滑过渡**: 切换主题时 0.3s 渐变动画
- **系统自动跟随**: 支持 `prefers-color-scheme` 自动检测
- **登录弹窗适配**: 使用全局变量确保任何主题下对比度可读

### 6. 面板收缩功能
- **左侧面板可收缩**: 工作流页面、Agent 工作台支持面板收缩/展开
- **平滑动画**: grid-template-columns 从 380px 过渡到 0
- **状态保持**: 侧边栏收缩状态通过 localStorage 持久化

### 7. 三级权限 UI
- normal: 基础 AI 功能
- admin: 管理面板、用户管理
- super: 系统配置、限流管理

### 8. 分片上传
- 大文件分片上传 (可配置大小)
- 断点续传支持
- 上传进度显示

## 构建配置

- **开发**: `npm run dev` (Vite Dev Server, HMR)
- **生产**: `npm run build` (输出到 `dist/`)
- **预览**: `npm run preview`

## 前端与后端交互

| 功能 | 前端组件/页面 | 后端端点 |
|------|--------------|----------|
| 登录 | LoginDialog.vue | POST /api/v1/login |
| 代码生成 | CodeGenerator.vue | POST /api/v1/code |
| 项目生成 | views/ProjectGenerate.vue | POST /api/v1/agent/generate |
| AI 对话 | VirtualGirl.vue | POST /api/v1/GirlAi |
| PPT 生成 | views/PPTGenerate.vue | POST /api/v1/pptx/generate |
| 图像生成 | views/ImageGenerate.vue | POST /api/v1/kolors/text-to-image |
| 工作流 | views/Workflow.vue | POST /api/v1/workflow/execute |
| 工作流历史 | views/Workflow.vue | GET /api/v1/workflow/history |
| 系统监控 | AdminPanel.vue | GET /api/v2/Controller/admin/stats |
| 管理员面板 | AdminPanel.vue | GET /api/v2/Controller/admin/config |
