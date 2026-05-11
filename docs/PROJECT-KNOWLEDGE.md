# 项目知识库

本文档记录 CodingMatrix 项目开发过程中的重要知识、决策和用户教导。

## 目录

- [功能定位](#功能定位)
- [UI/UX 改进](#uiux-改进)
- [主题系统](#主题系统)
- [独立页面架构](#独立页面架构)
- [aicloud](#aicloud)
- [测试方法](#测试方法)
- [代码结构](#代码结构)
- [环境配置](#环境配置)
- [前端组件](#前端组件)
- [需求文档](#需求文档)

---

## 功能定位

### 新功能中文生图功能
- 本质是文生图（Kolors），AI 补全 prompt，不需要新增入口
- UI 草图转代码：是 AiProject 的功能，用户明确说要实现才生成代码，生成默认 HTML 除非用户要求 React
- 临时工作流：是新增功能，需要在工具入口添加

### AI 绘画（ImageGenerator）
- Prompt 艺术画廊，无需新增入口
- ProjectGenerator = UI 草图转代码功能，无需新增入口
- 只有临时工作流需要新增工具入口

---

## UI/UX 改进

### 工作流历史记录 (2026-05-08)
- **问题**: 历史记录区块在 `history.length === 0` 时完全隐藏，用户看不到历史入口
- **解决**: 移除 `v-if` 条件，显示空状态提示，区分未登录和无记录两种情况
- **文件**: `src/views/Workflow.vue`
- **API**: 需要 token 认证，未登录时不请求接口

### 左侧面板收缩 (2026-05-08)
- **适用页面**: 工作流页面 (Workflow.vue)、Agent 工作台 (ProjectGenerate.vue)
- **实现方式**:
  - 状态: `leftPanelCollapsed` ref 变量
  - 按钮: 顶部导航栏添加收缩/展开按钮 (带旋转箭头图标)
  - 动画: `grid-template-columns` 从 `380px 1fr` 过渡到 `0 1fr`
  - 面板: `opacity` + `pointer-events` 控制显隐，避免布局抖动
- **侧边栏**: `leftlist.vue` 的收缩状态通过 `localStorage.getItem('sidebar-collapsed')` 持久化

### 登录弹窗样式修复 (2026-05-08)
- **问题**: 黑底黑字不可见，CSS 变量引用错误
- **根本原因**: 组件使用了未定义的变量 (`--color-surface`, `--color-text`)，回退到默认黑色
- **修复**:
  - `--color-surface` → `--bg-primary` / `--bg-tertiary`
  - `--color-text` → `--text-primary`
  - `--color-border` → `--border-color`
  - Logo 渐变: `--color-primary` → `--color-primary-600` 到 `--color-primary-500`
- **文件**: `src/components/LoginDialog.vue`, `src/styles/variables.css`, `src/App.vue`

---

## 主题系统

### 三套主题定义
- **theme-light**: 明亮模式，蓝色系 (`#3b82f6`)
- **theme-default**: 默认模式，青色系 (`#14b8a6`)
- **theme-dark**: 暗色模式，深青系 (`#2dd4bf`)

### 关键 CSS 变量
| 变量 | 用途 | 示例值 (Light) |
|------|------|----------------|
| `--bg-primary` | 主背景 | `#ffffff` |
| `--bg-secondary` | 次背景 (侧边栏) | `#f8fafc` |
| `--bg-tertiary` | 输入框背景 | `#f1f5f9` |
| `--text-primary` | 主文字 | `#0f172a` |
| `--text-secondary` | 次要文字 | `#475569` |
| `--text-tertiary` | 提示文字 | `#94a3b8` |
| `--border-color` | 边框颜色 | `#e2e8f0` |
| `--shadow-color` | 阴影颜色 | `rgba(0,0,0,0.08)` |

### 主题切换逻辑
- **文件**: `src/utils/theme.js`
- **存储**: `localStorage` 保存 `app-theme` 键
- **系统跟随**: `theme-auto` 模式监听 `prefers-color-scheme`
- **过渡动画**: 切换时添加 `theme-transitioning` class (0.3s)

### 默认值回退 (2026-05-08 修复)
- `:root` 中增加明亮主题的默认值，确保主题 class 加载前页面可读
- 所有独立页面使用 `var(--bg-*)` 而非硬编码颜色，确保主题适配

---

## 独立页面架构

### 工具新标签页打开 (2026-05-08)
- **触发方式**: 点击工具集菜单中的 Agent 工作台、工作流、PPT、图像生成
- **实现**: `window.open()` 打开新标签页，保留主聊天界面状态
- **路由**: 
  - `/project-generate` → `views/ProjectGenerate.vue`
  - `/workflow` → `views/Workflow.vue`
  - `/ppt-generate` → `views/PPTGenerate.vue`
  - `/image-generate` → `views/ImageGenerate.vue`
- **权限**: 工具页面不设置 `requiresAuth`，避免新标签页 token 丢失导致跳转循环

### 角色可见性控制
- **AI 云助手**: 仅 admin/superadmin 可见 (`v-if="userStore.isAdmin"`)
- **管理员面板**: 路由守卫 `requiresSuper`，非管理员拒绝访问
- **普通工具**: 所有人可见，但未登录时点击触发登录弹窗

---

## aicloud

### 功能特点
- 是简易版 AI 助手，有 10 天记忆持久化
- 分组权限，独立于 openclaw
- 禁止访问系统文件：/etc/, /root/, .env, *.key, credentials.json
- 文件读写需 AI+人工审查过滤，人工审查可关闭，AI 审查不可关闭
- 仅限 super 用户调用（permission_level >= 999）
- 禁止修改当前项目，只能写入 sandbox 目录
- 上下文与主项目隔离

---

## 测试方法

### Selenium 测试
- 需要用 `def setup(self, driver):` 而不是 `def def setup`
- pytest fixture 用 `@pytest.fixture(autouse=True)` 自动执行
- 测试文件需要放在 tests/ 目录下
- 运行测试前需要加载环境变量：export $(cat .env.test | xargs)

### 前端测试
- 需要安装 selenium：pip3 install selenium
- Selenium 测试使用 CSS 选择器定位元素
- wait_for_element 和 wait_for_clickable 是常用辅助函数
- 测试完成后需要修复语法错误（def def setup）

---

## 代码结构

### SQLAlchemyError 导入
使用 SQLAlchemyError 的文件需要导入：
```python
from sqlalchemy.exc import SQLAlchemyError
```
需要导入的文件：Aicode.py, auth.py, kolors_api.py, GirlAi.py, AiProjectCode.py, task_queue.py, aiGeneratorPptx.py, file_upload.py

### 前端组件创建
- 新工具组件放在 src/components/tools/ 目录下
- 需要在 Sidebar.vue 的 tools 数组中添加入口
- 需要在 navigation.js 中添加 showXxx 状态和 hideTool 方法
- 需要在 index.vue 中导入组件并添加到模板

### 资源配置功能
- 前端组件：ResourceControl.vue
- AdminPanel.vue 集成：在 menuGroups 添加 'resource-control' 菜单项（仅 super 用户可见）
- 后端 API 路由：/api/v2/Controller/admin/config, /admin/stats, /admin/config/batch
- 功能开关使用 feature_ 前缀：feature_docker_enabled, feature_aicloud_enabled 等
- 数据库连接池配置：db_pool_size, db_max_overflow, db_pool_timeout（需重启生效）

---

## 环境配置

### Docker 网络配置
- Docker 网络默认禁用（network_mode=none）
- pip install 需要网络，但 network_mode=none 会阻止
- 解决：默认禁用网络，用户通过 docker_network_enabled 参数开启

### 启动脚本
- 启动脚本：start.sh（支持 Linux）/ start.bat（Windows）
- 启动命令：
  - ./start.sh - 启动全部（推荐）
  - ./start.sh api - 仅 API 服务
  - ./start.sh celery - 仅 Celery Worker
  - ./start.sh nginx - 仅 Nginx
  - ./start.sh build - 构建前端

### Nginx 配置
- 端口 80：前端静态文件
- /api/*：API 代理到 8080
- /ws/*：WebSocket 代理
- Gzip 压缩：已启用（minimum_size=500）

### 数据库与缓存
- 数据库索引：已完善（Task, User, File, History 等）
- Redis + Celery：任务队列（必须）
- Gunicorn：2 workers, 2 threads

### 健康检查
- /health, /health/ready, /health/live
- /health/detailed - 详细健康信息（管理员）

### 管理 API
- GET /api/v2/Controller/admin/backup - 创建备份
- GET /api/v2/Controller/admin/backup/list - 列出备份
- GET /api/v2/Controller/admin/backup/{timestamp} - 下载备份
- POST /api/v2/Controller/admin/backup/restore - 恢复备份
- DELETE /api/v2/Controller/admin/backup/{filename} - 删除备份

### 前端构建
- cd src && npm install && npm run build

### Docker Compose
- docker-compose.yml（可选部署方式）

### Sentry 错误追踪
- 安装：pip install sentry-sdk
- 配置：设置环境变量 SENTRY_DSN
- 初始化：from app.utils.sentry import init_sentry; await init_sentry()
- 使用：capture_error(), capture_message_sync(), set_user(), set_tag()

### 日志归档 LogArchiver
- 按大小轮转 + 按时间清理
- 支持 gz/zip 压缩
- 保留天数可配置
- 使用：from app.utils.log_archiver import get_log_archiver; archiver.archive_all()

---

## 前端组件

### Composables 模式 (2026-05-04 新增)
- **useToast** - 全局通知系统，通过 ToastContainer 组件自动渲染
- **useAuth** - 认证逻辑封装，登录/注册/Token 刷新
- **useStream** - 流式请求管理，含自动重试和错误恢复
- **useOfflineQueue** - 离线消息检测与排队
- **useClipboard** - 剪贴板操作，支持复制文本和格式化内容
- **useFocusTrap** - 焦点陷阱，用于模态框无障碍访问

### 组件拆分规范
- **模态框组件** (LoginDialog, MessageEditor, ShareDialog) 使用 Teleport 挂载到 body
- **全局通知** (ToastContainer) 在 main.js 全局注册
- **空状态** (EmptyState) 独立为组件，含打字机动画和粒子效果
- **列表项** (HistoryItem) 拆分为独立组件，支持搜索高亮
- **错误边界** (ErrorBoundary) 包裹重型组件，防止崩溃导致白屏
- **骨架屏** (SkeletonLoader, AppLoading) 用于加载过渡
- **虚拟列表** (VirtualHistoryList) 优化大数据量渲染

### 延迟加载规范
- 工具面板组件使用 `defineAsyncComponent` 延迟加载
- 13 个工具组件延迟加载，主包减少 74%
- 核心组件（Bottominput, CenterContent）立即加载

### 键盘快捷键
- 8 个常用快捷键，支持 `Ctrl+/` 查看帮助
- 所有交互元素支持键盘导航
- Skip Link 快速跳转到主要内容

### 无障碍访问 (a11y)
- 模态框使用 useFocusTrap 防止焦点逃逸
- 完善 ARIA 属性（角色、状态、标签）
- 颜色对比度符合 WCAG AA 标准
- 所有功能支持键盘操作

### Pinia 持久化
- 使用 `pinia-plugin-persistedstate` 自动持久化状态
- userStore: 持久化 `isLoggedIn`, `username`, `email`, `permissionLevel`
- navigationStore: 持久化 `isCollapsed`, `isBottomInputCollapsed`
- 移除手动 localStorage 读写，统一由插件管理

### 代码规范
- ESLint + Prettier 统一代码风格
- 保存时自动格式化
- Vue 3 Composition API 最佳实践

### E2E 测试
- 4 个 Playwright 测试文件，27 个测试用例
- 覆盖核心用户流程
- 测试命令：`npx playwright test`

### ResourceControl.vue 增强
- API 方法（api.js）：
  - getRateLimitStats() - 获取限流统计
  - updateGlobalRateLimit(limit, window) - 更新全局限流
  - updateIpRateLimit(limit, window) - 更新 IP 限流
  - updateUserRateLimit(limit, window) - 更新用户限流
  - toggleRateLimit(enabled) - 启用/禁用限流
- 新增 UI 区块：
  - API 限流配置 - 三级限流管理 + 实时统计
  - 熔断器状态 - 服务级熔断状态展示

---

## 需求文档

- 需求文档使用 EARS 模式编写
- 设计文档使用 Mermaid 图表
- 文档保存在 .monkeycode/specs/{feature-name}/ 目录下（已迁移到 docs/specs/）
- 需要创建 requirements.md 和 design.md 两个文件

---

## 生产环境基础保障

### API 限流 + 输入验证
多级限流策略（全局 → IP → 用户 → 端点）：
- 全局：1000次/60秒
- IP：100次/60秒
- 用户：50次/60秒
- 端点：可配置

**输入验证**:
- 请求参数类型检查
- 字符串长度限制
- 数值范围验证
- SQL 注入防护
- XSS 过滤

限流管理 API：
- GET /api/v2/Controller/admin/rate-limit - 获取限流配置
- PUT /api/v2/Controller/admin/rate-limit/global - 更新全局限流
- PUT /api/v2/Controller/admin/rate-limit/ip - 更新 IP 限流
- PUT /api/v2/Controller/admin/rate-limit/user - 更新用户限流
- PUT /api/v2/Controller/admin/rate-limit/endpoint - 更新端点限流
- DELETE /api/v2/Controller/admin/rate-limit/endpoint/{endpoint} - 删除端点限流
- PUT /api/v2/Controller/admin/rate-limit/enabled - 启用/禁用限流

### Redis 缓存层
- `app/utils/cache.py` - MemoryCache + RedisCache
- `app/utils/cache_decorator.py` - 装饰器模式缓存
- 支持自定义 TTL 和键前缀
- 自动序列化/反序列化
- 缓存穿透防护

### 结构化日志
- `app/utils/logging.py` - JSON 格式日志 + 链路追踪
- 包含 request_id, user_id, duration_ms 等上下文
- 日志轮转与归档

### 健康检查增强
HealthChecker 服务：
- /health - 综合健康检查（API、数据库、Redis、Celery、WebSocket、系统资源）
- /health/ready - K8s readiness probe
- /health/live - K8s liveness probe
- /health/detailed - 详细健康信息（管理员）
- 响应格式：{status, timestamp, checks: {api, database, redis, celery, websocket, system}}

### API 版本管理 + 错误码
- `app/utils/error_codes.py` - 统一错误码定义
- `app/utils/api_response.py` - 标准化响应格式
- `app/utils/pagination.py` - 分页参数验证与响应

### 优雅关闭
GracefulShutdownManager：
- 状态机：RUNNING → DRAINING → SHUTTING_DOWN → TERMINATED
- SIGTERM/SIGINT 信号处理
- Draining 模式：拒绝新请求（503），等待现有请求完成
- 连接池关闭：WebSocket（10s）、Celery（20s）、数据库（30s）

### CI/CD 配置
- `.github/workflows/ci.yml` - CI 流水线（检查、测试、构建）
- `.github/workflows/cd.yml` - CD 流水线（镜像构建、部署）
- `.github/workflows/security.yml` - 安全扫描（依赖、代码、密钥）
- `Dockerfile` - 生产镜像构建
- `docker-compose.prod.yml` - 生产环境编排

### 新增文件
- app/utils/cache.py - 缓存服务
- app/utils/cache_decorator.py - 缓存装饰器
- app/utils/logging.py - 结构化日志
- app/utils/health.py - 健康检查
- app/utils/error_codes.py - 错误码定义
- app/utils/api_response.py - 统一响应
- app/utils/pagination.py - 分页支持
- app/middleware/rate_limiter.py - 限流中间件
- .github/workflows/ci.yml - CI 工作流
- .github/workflows/cd.yml - CD 工作流
- .github/workflows/security.yml - 安全扫描
- Dockerfile - Docker 镜像
- docker-compose.prod.yml - 生产编排

---

## PPT 生成功能

### 视觉分析模块
- 文件：app/utils/visual/visual_analyzer.py
- ImageType 枚举：NONE, PHOTO, ILLUSTRATION, CHART, ICON, BACKGROUND, DIAGRAM, DECORATION
- ImagePosition 枚举：LEFT, RIGHT, CENTER, TOP, TOP_RIGHT, TOP_LEFT, BOTTOM, BACKGROUND, CORNER, INLINE
- 新增 TextStyle, TitleStyle, BulletStyleConfig 数据类支持多样化样式
- 支持多图片决策（主图片 + 装饰图片）
- JSON 解析增强：_fix_json_format() 和 _extract_json_by_regex() 处理格式错误
- prompt 增强：严格要求 JSON 格式，禁止尾随逗号，布尔值小写

### 布局决策器
- 文件：app/utils/visual/layout_decider.py
- _plan_with_image() 支持所有 ImagePosition 枚举值
- 新增位置处理：TOP(顶部居中)、TOP_RIGHT(右上图左下文字)、TOP_LEFT(左上图右下文字)、BOTTOM(底部图上方文字)、INLINE(上图下方文字)
- _plan_decoration_image() 处理装饰图片（支持 CORNER, TOP_RIGHT, TOP_LEFT, BOTTOM, TOP）
- 修复 Inches 运算 bug：CENTER 位置 content_top 计算使用 float 转换
- 修复 text_top 变量作用域：所有分支初始化默认值

### 视觉模型降级机制
- 文件：app/utils/vision.py
- 降级顺序：THUDM/GLM-4.1V-9B-Thinking → deepseek-ai/DeepSeek-OCR → Qwen/Qwen3.5-4B
- VISION_MODEL_FALLBACK 列表定义降级顺序
- _call_vision_model() 封装模型调用
- analyze_image() 自动尝试每个模型，失败时自动切换下一个
- 返回结果包含 model_used 字段，记录实际使用的模型

### 视觉模型分工
- THUDM/GLM-4.1V-9B-Thinking：首选视觉理解模型
- deepseek-ai/DeepSeek-OCR：OCR 专用模型（支持图片理解）
- Qwen/Qwen3.5-4B：最后降级通用模型

### ALLOWED_MODELS_LIST（9个）
- deepseek-ai/DeepSeek-R1-0528-Qwen3-8B
- deepseek-ai/DeepSeek-OCR
- Qwen/Qwen3.5-4B
- Qwen/Qwen3-8B
- Qwen/Qwen2.5-7B-Instruct
- THUDM/GLM-4.1V-9B-Thinking
- THUDM/GLM-4-9B-0414
- THUDM/GLM-Z1-9B-0414
- Kwai-Kolors/Kolors

### task_manager
- 文件：app/utils/task_manager.py
- 从内存存储改为 Redis 存储（支持多 worker 共享）
- 使用 Redis 存储任务状态，键格式：task:{task_id}
- 使用 Redis Set 存储用户任务列表，键格式：user_tasks:{user_id}
- 新增 get_task_info_async() 异步方法从 Redis 读取
- 新增 _cleanup_loop() 后台任务定期清理过期任务（保留 7 天）
- 任务 TTL 设置为 7 天

---

## 相关文档

- [索引](../INDEX.md)
- [开发指南](../development/DEVELOPER_GUIDE.md)
- [架构设计](../architecture/ARCHITECTURE.md)
