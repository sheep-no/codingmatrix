# 用户指令记忆

本文件记录用户的指令、偏好与项目知识，供未来交互参考。条目按模块归并，只保留无法从代码直接得知、且能指导后续操作的要点。

## 格式

### 用户指令条目
- Date: [YYYY-MM-DD]
- Context: [场景或时间]
- Instructions:
  - [教导或指示内容]

### 项目知识条目
- Date: [YYYY-MM-DD]
- Context: [任务描述]
- Category: [代码结构|代码模式|构建方法|测试方法|依赖关系|环境配置|工作流与协作]
- Instructions:
  - [知识点]

## 去重策略

- 添加前检查是否已有相似条目；重复则跳过或合并，并更新上下文与日期。
- 文件超过 150 行时，合并同模块规则并保留关键信息。

## 条目

### 协作与沟通规范
- Date: 2026-08-29 ~ 2026-09-13
- Instructions:
  - SDD 需求澄清采用一问一答：每轮只提一个问题，等回答后再继续。
  - 用户只要方案时先给方案，明确说「开始」后再改代码。
  - 智谱 / Agent 排障保持模型 `max_tokens`、thinking、温度和角色分工，修契约、限流和热更新。
  - 任务范围内有明确后续步骤时持续推进；只在真实歧义会改变方向时请求澄清。
  - 前端深扫按入口认证、状态组合、视图 API、构建部署四批次执行，每批用全库引用、后端路由和配置交叉核验，最后跨批去重。
  - 客户端位于 `flutter_client/`；功能分析与实现以前端为主（设置页、供应商与 Key 状态、模型选择、流式展示、错误反馈、响应式布局、前端测试），后端只改链路必需的最小范围。
  - 修改前先读项目记忆与 Git 状态，保留已有改动；手动编辑统一用 apply_patch。
  - 测试与构建用受控后台终端执行（先 background_terminal_list 查占用），命令先 `cd /workspace/flutter_client`。
  - 用户只要 Agent 验收时，范围是 Agent 页与代码生成管线（工程师工具调用、MCP、沙箱、Skills、Host）；图表、能力中心独立页、PPT/绘画/工作流、超管面板不计入。
  - Agent 实测用当前模型分工，禁止为单一语言或技术栈新增门禁；入口骨架仅在架构明确框架时生成，依赖扫描保留未映射的第三方包名，关键决策与 Spec-First 仅在需求或复杂度出现鉴权、后端、存储信号时触发。

### 提交与分支流程
- Date: 2026-05-29 ~ 2026-09-19
- Instructions:
  - 提交完成后在用户明确要求时推送；同一功能分支可累积多个提交后一次推送。
  - 本仓 remote 是 GitHub，推送用 `git push origin <branch>`。GitHub 不支持 GitLab 的 `-o merge_request.*` push options：带这些选项会返回 `HTTP 500 ... sideband packet` 并使推送失败（且不产生远程变更），去掉后普通推送即可。
  - `.git/hooks/prepare-commit-msg` 会自动追加 `Co-authored-by: monkeycode-ai <monkeycode-ai@chaitin.com>`；手写同一条或 `--amend` / `rebase` 重放会重复。写提交信息时不要自带该 trailer（`-F` 的文件里只放正文），由钩子补一次即可；若已重复，用 `git commit --amend -F` 传一份去掉 trailer 的正文即可归一。
  - 拆分提交时，测试里对 UI 文案 / `Key` 的断言必须与引入该文案的源码同提交，否则中间提交失败、无法 bisect；中间提交也不能有悬空导入。
  - 未经用户明确要求不提交、不推送。

### 文档管理规范
- Date: 2026-05-13
- Instructions:
  - 项目文档集中在 `docs/`：功能 `docs/features/`、测试合并到 `docs/testing/TESTING.md`、架构与模型 `docs/architecture/`、指南 `docs/guides/`、规格 `docs/specs/`。
  - 项目知识只维护 `.monkeycode/MEMORY.md` 一处，不在 docs/ 留副本。

### 测试与验证流程
- Date: 2026-05-12 ~ 2026-09-15
- Category: 测试方法
- Instructions:
  - 后端 pytest + pytest-asyncio，Python 3.11+ 用 `asyncio.run()`；async fixture 必须 `@pytest_asyncio.fixture`；集成测试加 `@pytest.mark.skipif` 检查服务可用性。
  - 目录：单元 `tests/unit/`、集成 `tests/integration/`、E2E `tests/e2e/`；全量命令 `python3 -m pytest -q`（`test_ppt_unified_generation.py` 多模板用例 >90s，排除后约 76s）。
  - 根目录与 `src/node_modules` 同时装 Playwright 会触发 `Requiring @playwright/test second time`；E2E 必须让 CLI 与测试文件解析到同一份依赖，用根 `playwright.config.js`（`testDir=./tests/e2e`）并把 `PLAYWRIGHT_EXECUTABLE_PATH` 指向 ms-playwright chromium。
  - 误报类修复：先写确定性探针复现（不依赖 LLM / Playwright），再用单测固化「正确产物不被拒 + 真实错误仍被拒」；用 `git stash push <源文件>` 回退源码后新增用例必须失败；每处修复跑定向 + 全量，并把 `FAILED` 集合与失败基线 diff（只允许不变）。
  - 内存紧张时用 API / 确定性探针替代 Playwright，不启动浏览器。
  - 门禁误报的高频模式是把「执行环境状态」当「代码缺陷」：未安装的第三方 import、依赖清单缺失包、node 被信号终止都属环境状态；只有项目内模块/符号缺失才算缺陷，修一处后要顺带核对同类检查。
  - 声明式 `FrameworkProfile` 的 `build_command` / `test_command` / `validation_steps` 是项目级验证统一来源（Go stdlib 用 `go build ./...` 与 `go test ./...`）；运行前确认生成目录可作为命令工作目录并保留输出。
  - 本地起后端做联调无需 `.env`：`DATABASE_URL=sqlite+aiosqlite:////tmp/<name>.db ENV=development python3 -m uvicorn app.main:app --port 8000`，启动时 `create_all` 自动建表（`app/main.py:259`），SECRET_KEY 为空时开发环境用固定本地密钥。认证路由直接挂在 `/api/v1`（无 `/auth` 段）：`/api/v1/csrf-token`、`/api/v1/register`、`/api/v1/login`；注册需 CSRF（先取 `/csrf-token` 拿 cookie + token，再带 `X-CSRF-Token` 头），登录兼容明文 `email`+`password`。
  - agent host 会话不在数据库：存 JSON 文件于 `data/agent_host_sessions/`（可用 `AGENT_HOST_SESSION_DIR` 覆盖，已被 `.gitignore` 忽略）加内存字典，排查会话状态要查这里而非 SQLite。
  - VS Code 插件 e2e（`npm run e2e`）的后端会话段需 `CODINGMATRIX_E2E_API_URL` + `CODINGMATRIX_E2E_ACCESS_TOKEN`，缺任一个 `e2e/suite.mjs:36-38` 直接 `return` 且仍以退出码 0 结束——退出码 0 只证明扩展能加载与注册命令，不代表后端链路被覆盖。判定是否真跑了要查 `data/agent_host_sessions/` 是否新增 `workspace_id=fixtures` 记录及其 `control_status` 终态为 `cancelled`。
  - 插件 e2e 断言命令注册不要手写命令名清单，直接从 `package.json` 的 `contributes.commands` 读出来再和 `vscode.commands.getCommands(true)` 比对，否则 `package.json` 与 `activate()` 漂移（面板显示有、点了报错）不会被发现。
  - webview 面板打开后不会立刻出现在 `vscode.window.tabGroups.all` 里：`executeCommand` 返回时标签页可能尚未创建，直接断言会得到 0 个标签。要轮询等待（实测约 250ms 内出现），否则会把时序问题误判成「面板没打开」。

### Flutter 客户端验证约束
- Date: 2026-09-08 / 2026-09-09
- Category: 测试方法
- Instructions:
  - 直接验证可用 `FLUTTER_ALLOW_ROOT=1 flutter analyze` / `FLUTTER_ALLOW_ROOT=1 flutter test`。
  - 修改后执行 `dart format`（只格式化本次改动文件，全量会因本地 SDK 与仓库格式不一致产生无关改动）→ `flutter analyze` → 定向测试 → 全量 `flutter test`，修完再返回。
  - 账号切换竞态统一守卫是自增 epoch 快照：`NotifierProvider` 重建会复用 notifier 实例，`ref.onDispose` 里置位的一次性布尔会永久生效并静默屏蔽后续请求；`StateNotifierProvider` 重建会新建实例，用 `mounted` 判断即可。
  - 区分度测试只用默认参数构造被测对象；使用新增命名参数会让旧代码编译失败而非干净失败，掩盖真实断言。
  - 测试坑：`Stream.timeout` 在响应体阻塞于永不完成的 await 且从未 yield 时不触发；流超时测试必须用真实 `StreamController` 作为响应体，否则测试永久挂起。
  - 测试坑：`flutter test` 默认 Ahem 字体每个字符等宽且宽度等于字号，窄屏溢出像素数会被显著放大，不能直接用该数值推断真机行为；判断窄屏风险要看布局结构（无弹性的 `Row` 配可变长文本）并按真实字体宽度估算。反向也成立：空数据下页面多为空态，其窄屏冒烟通过不能代表真机安全（GirlAI 状态行就是空态通过、有数据时溢出的例子），修法是改用 `Wrap`。
  - `AlertDialog` 溢出只发生在 `content` 是 `Column` 的时候（固定高度子项无法压缩）。`content` 为单个 `SelectableText`/`Text`/`TextField` 时它们内部自带滚动，超长内容会被裁切但可滚动查看，不会报溢出——所以排查完 `Column` 就可以停手，不必把每个对话框都包 `SingleChildScrollView`。要证明「长内容真的看得到」而不是「只是没报错」，断言对话框子树里 `Scrollable` 的 `maxScrollExtent > 0`，只断言无异常会漏掉内容被裁掉的情况。
  - Android 打包受环境限制：`flutter build apk` 由 AGP 触发 NDK 下载（需 strip native 库），NDK 27 解压约 2.9G；本机根分区 20G 无法容纳，构建会把磁盘压到 0 可用并在中断时留下 `$ANDROID_SDK/.temp` 残留。移除 `jni`（例如 pin `path_provider_android: 2.2.20`）不能免除该需求，已回滚该覆盖。
  - 不依赖 NDK 的 Android 验证用 `flutter build bundle --target-platform android-arm64`（验证 Android 目标 Dart 编译），产物在 `build/flutter_assets`。环境无 Android 设备或模拟器，真机联调不在此环境进行。
  - Android 原生/Kotlin/Manifest 改动在本环境无法编译验证：`:app` 在配置阶段即报 `NDK not configured`，`flutter build bundle` 只编译 Dart 资产、不触发 Kotlin。安全探测用 `./gradlew :app:compileDebugKotlin --offline`，会快速失败而不下载 2.9G NDK；这类改动只能靠静态一致性核对（namespace == Kotlin `package` == 源码目录路径，Manifest 用 `.MainActivity` 相对 namespace 解析）。
  - Android SDK 不入库且 `/tmp` 会被清理：`android/local.properties` 的 `sdk.dir` 指向 `/tmp/opencode/android-sdk`，重建需 cmdline-tools 11076708 加 `sdkmanager "platform-tools" "platforms;android-36" "build-tools;36.0.0"`，并设 `JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`。
  - Linux 桌面产物验证：`flutter build linux --debug`（工具链 clang/cmake/ninja/gtk+-3.0 齐全）产出 `build/linux/x64/debug/bundle/flutter_client`；无 GPU 时用 `LIBGL_ALWAYS_SOFTWARE=1 GALLIUM_DRIVER=llvmpipe` 加自建 `Xvfb :99 -screen 0 1280x800x24` 启动，用 `xwininfo -root -tree` 确认 1280x720 窗口已映射、进程存活、日志无 Dart 异常即为通过。注意 shell 里 `cmd &` 会绑定整个 `&&` 链导致工作目录错乱，后台任务用 `( cmd & )` 分组。
  - 无 keyring 的环境（容器/WSL/纯 WM）会打印 `libsecret_error: Failed to unlock the keyring`：安全存储读写失败会让登录与服务会话全链路不可用（`CloudAuthClient._accept` 里 `saveSession` 抛错即 `logout()`），所以这不是能忽略的噪声。凭据层已把它归类为 `SecureStorageUnavailableException` 并给出对应提示。要在本环境实跑登录，需先 `apt-get install -y gnome-keyring libsecret-1-0 libsecret-tools dbus-x11`，用 `eval "$(dbus-launch --sh-syntax)"` 建立会话总线，`printf 'testpass' | gnome-keyring-daemon --unlock --replace --components=secrets` 解锁，再在同一 DBUS 会话里启动客户端。注意 `dbus-launch` 会把总线地址写进 X11 根窗口属性，同一 DISPLAY 上后续启动的进程仍能找到该总线并弹出「解锁密钥环」对话框；密钥环处于锁定态时该读取会一直挂起，应用停在启动加载态。
  - headless UI 实测：`apt-get install -y xdotool`。截图用 `python3 -c "from PIL import ImageGrab; ImageGrab.grab(xdisplay=':99').save(p)"`（无需 ImageMagick/xwd），点击与输入用 `xdotool mousemove X Y click 1` / `xdotool type`。无窗口管理器时 `xdotool windowactivate` 因缺 `_NET_ACTIVE_WINDOW` 报错，坐标点击仍有效。
  - 验证内置字体是否真的生效：临时用 `FONTCONFIG_FILE` 指向只含 Latin 目录（dejavu/liberation）的自定义 fonts.conf 启动，`fc-list` 确认看不到任何 CJK 字体后再截图。这样不必卸载系统字体。字体族在 `app.dart` 里按 `Platform.isLinux` 选择，Android 渲染行为不变；但 pubspec 声明的字体资源会打进所有平台产物，Android APK 同样 +3.1MB。`flutter build bundle` 可单独校验资源打包（比整包构建快得多，磁盘紧张时优先用）。
  - 侧栏导航坐标会随滚动或窗口尺寸偏移：点击后要以后端请求日志（如 `GET /api/v1/github/config`）或标题截图确认真正落到了哪一项，不能按截图顺序推断，否则会漏测页面且不自知。
  - 真机实测依赖的后端与 Redis 必须在受管后台终端里启动（`timeout` 上限 1 小时）：超时被杀后客户端每个页面都显示「网络请求失败，请重试」，此时先看后端日志尾部时间戳，不要先怀疑客户端。`GET /api/v1/tasks` 依赖 Redis，无 Redis 会被静默降级成同一个通用网络错误，重启 `redis-server --port 6379 --save '' --appendonly no --maxmemory 128mb` 即恢复。
  - 写后端冒烟脚本要自己登录：客户端登录路径是 `/api/v1/login`（CSRF 双提交，先 `GET /api/v1/csrf-token` 取 cookie 与 `csrf_token`，再带 `X-CSRF-Token` 头 POST），`/api/v1/auth/login` 返回 405。客户端重启后只靠 keyring 里的 refresh token 免登录，不会再发登录请求。

### Flutter 与后端契约坑位
- Date: 2026-09-06 ~ 2026-09-19
- Category: 代码模式
- Instructions:
  - FastAPI 参数位置要与客户端对齐：`kolors_api.py` 的 `/text-to-image`、`/image-to-image`、`/inpaint` 收 JSON body，而 `/avatar`、`/landscape`、`/icon` 把 `prompt`、`style` 声明为标量（query），发 JSON body 会 422。
  - Pydantic 别名：`PPTGenerationRequest.topic` 带 `alias="prompt"` 且 `populate_by_name`，两种字段名都收；`ppt_outline.py` 的 `OutlineCreateRequest.topic` 无别名，只能发 `topic`。
  - 响应字段名要对照后端：`GET /pptx/history` 返回 `records`；`POST /api/v1/history` 与 `/conversation/history` 返回 `items`，每条是 `prompt` + `response`（无 `role`/`content`），会话详情要展开成问答两条；fixture 必须用后端真实 payload。
  - 下载路由区分取现有与按需转换：`GET /pptx/download/{ppt_id}?format=pdf` 只服务已存在的 `.pdf`（任务固定输出 pptx，必然 404），PDF 走 `GET /pptx/download/{ppt_id}/pdf`。
  - 后端用 HTTP 200 + `error` 字段表达业务失败：`POST /api/v1/chat` 空回复返回 `{response:"", conversation_id:null, error:"AI 生成响应为空，未保存历史记录"}`，流式同样以 `{"error": ...}` 帧表达，客户端必须读取 `error`。
  - 文件上传响应是 `File.to_dict()`（`id`/`filename`/`file_size`/`content_type`/`created_at`/`download_url`，无 `server_path`/`name`）；`/upload/init` 命中秒传放在 `existing_file`、`/upload/merge` 放在 `file`，客户端统一展平；下载用整型数据库 id；附件 `FileAttachment.server_path` 可填 `filename`。
  - 页面 `_resetAccount()` 的职责是「清本地草稿 + 重新拉当前账号数据」：切账号重建 controller 会清空 state，依赖列表的页面必须重新 `load()`（`virtual_girl_page` 曾遗漏角色列表重载）。
  - 服务端枚举型契约按字段独立校验：`critical_decision.py` 的 `state_management` 模板默认 `Pinia` 而选项只含 `Pinia/Vuex`，客户端直接拿 `default` 当选中值会触发 Flutter 断言。
  - 编排流请求体含七个布尔开关，默认全 `true`：`enable_review`、`enable_validation`、`enable_error_recovery`、`enable_memory`、`enable_skills`、`spec_first`、`dependency_graph`（`OrchestratorRequest`）；开关在生成开始时取值，进行中修改不影响本次，客户端按 `<baseUrl>|<username>` 作用域持久化。
  - SSE 开流失败必须在打开阶段抛出：`AgentStreamClient.open()` 非 200 抛 `AgentStreamException(statusCode)`；`startGeneration()` await `open()` 失败时置 `disconnected` 并 rethrow，调用方各自反馈，避免未处理异步异常。
  - 后端 `reconnectable` 仅当前进程存活、未结束、且无订阅连接；恢复只重放未消费事件，已消费事件/决策不可重放。
  - 流式空闲超时与普通请求分离：`sendJsonStream` 用独立 `streamTimeout`（默认 5 分钟，逐事件重置），不复用 `auth.timeout`（20s），否则首个 token 静默 >20s 会被误判为「响应连接中断」。
  - 工作台模块入口来自 `lib/application/capability_registry.dart`；组件测试打开模块用 `capabilityNav_<id>` 键（窄屏先点 `Icons.menu` 打开抽屉）。

### 后端关键链路与结构
- Date: 2026-05-12 ~ 2026-09-06
- Category: 代码模式
- Instructions:
  - 生图 Provider Key：取 `/api/v1/agent/apikey/public-key`，用 RSA OAEP SHA-256 加密原始 Key，提交 `/api/v1/agent/apikey`，把返回的 `api_key_token` 传给生图接口；直接设 `SILICONFLOW_API_KEY` 不能证明前端加密与 Redis token 解析链路。动态供应商 `POST /api/v1/providers` 只认 `encrypted_api_key`，发明文 `api_key` 会因缺字段被拒。
  - Agent 模型路由限流：Spec-First 已连续使用 `Qwen/Qwen3-8B`，其他阶段避免集中路由到同一模型；调整分工要兼顾质量、跨模型负载分散与供应商限流。智谱免费档 `glm-4.7-flash=1`、`glm-4-flash-250414=20`、`glm-z1-flash` 未单独限流（代码默认 6，受全局信号量 6 约束）；`glm-4.7-flash` 易触发上游 429（code 1305）并在 `_analyze_changes_with_architect` 硬失败而非降级，重跑前冷却数分钟。
  - 切角色实测前先备份快照：`set_roles.py` 的 `set` 会用当前角色覆盖 `orig_roles.json`，连续两次 `set` 后 `restore` 回不到默认。默认值 architect `qwen3-8b` / frontend `deepseek-r1` / backend `qwen3.5-4b` / reviewer `glm-z1-9b` / fallback `qwen3-8b`；跑全量 unit 前必须处于默认值，否则 `test_multi_model_agent` 多一条失败。
  - 活管线重试要把上游 429（code 1305）、流式 180s 超时、架构师输出缺 `project_spec` 都按瞬时错误处理，否则单次抖动就中断实测。
  - Skill 按当前需求明确匹配后才加载，禁止批量注入无关正文；RAG 查询用用户原始需求，结合目标文件、文件职责和当前生成阶段构造。Core 适配器在每个文件生成前用本地 `RetrievalService` 装配需求、契约和架构上下文，并把来源数量、ID 与降级状态写入 `retrieval_status`；外部 MCP Server 当前全部未启用，可用本地 Retriever 独立确认注入路径。
  - 增量修改：`OrchestratorAgent(incremental=True)` 经 SessionManager 检测变更、CodePatcher 生成 unified diff；测试优先 DockerRunner，回退 IsolatedTestRunner（临时 venv + 项目副本，用完清理）；每次生成/修改后 `_git_save_snapshot` 自动 commit。
  - `ProjectProfiler` 支持 python/javascript/go/rust/java 五种 `LanguageProfile`，调用方必须传 `language`（或用 `detect_project_language()` 自动检测）；语言检测优先 manifest 文件，其次扩展名计数；JS init_file 支持 index.{js,ts,jsx,tsx,mjs,cjs}。
  - 安全防护在 `app/utils/guardrails.py`：Prompt 注入检测（正则 + 关键词密度 + 结构异常）、会话 ID `^[-a-zA-Z0-9]{5,128}$`（禁 `sys_/admin_/internal_/test_` 前缀）、路径安全检查、磁盘低于 1GB 或 10% 拒绝新请求、默认每用户每 60 秒 10 个 stream、session action 端点校验 `user_id` 所有权。
  - bcrypt 算法限制密码 72 字节，`hash_password` / `verify_password` 都要 `[:72]` 截断，否则抛 `ValueError`。
  - 既有数据库首次接入 Alembic：先 `alembic stamp <baseline>` 登记基线，再 `alembic upgrade head` 验证幂等。
  - `CodeValidator` 在后端进程内 `exec` 生成项目代码；生成项目与 Agent 包同名（如 `app/`）时，`sys.modules` 已缓存同名包会导致假的 "cannot import name from 'app'"，排错先确认是否受同名缓存影响。

### 扫描与定级方法
- Date: 2026-08-26
- Instructions:
  - 扫描每个文件先确定「实际作用」，判定三态：活跃（路由已挂载且有生产消费方）/ 未接入（设计存在但路由未挂载或符号零消费）/ 废弃（被新体系取代的残留）。
  - 三态决定缺陷定级与修复方向：活跃面缺陷正常定 P 级；未接入/废弃面标注「未接入/废弃代码内逻辑缺陷」，修复方向是接线或迁移仍活跃部分后整体退役，而非逐条修缺陷。
  - 判定要点：router 是否被 main.py 或上游 router include、文件内符号全库引用数、是否存在新副本（双轨）、文件头注释路径与真实路径是否一致、是否被新体系取代。

### 项目结构与技术债务快照
- Date: 2026-06-09
- Category: 代码结构
- Instructions:
  - 规模与结构以 `docs/README.md` 与 `docs/PROJECT-STRUCTURE.md` 的当前基线为准，本条目不再维护具体数字。
  - 已知重复实现：`app/utils/rate_limiter.py`(slowapi) vs `app/middleware/rate_limiter.py`；`app/db/models.py` vs `app/models/`；`src/utils/crypto.js` vs `src/utils/encryption.js`；`src/composables/useAgentSession.js` 是 `stores/agentSession.js` 的薄包装。
  - 废弃前端组件：`AgentHeader.vue` 与 `AgentTopBar.vue` 重叠；`AgentInputPanel.vue` 与 `AgentInputBar.vue` 重叠。
  - 待拆分的 1000+ 行单文件：`agent_core.py`、`aiGeneratorPptx.py`、`orchestrate_endpoints.py`、`cross_validator.py`、`dependency_graph.py`、`tools.py`。
