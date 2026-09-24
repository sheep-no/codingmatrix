# 待环境验收清单

> 核对日期：2026-09-22 | 范围：Flutter 双端（Android/Linux/Windows）与 VS Code 扩展

本文件记录该范围内已经完成的验证，以及需要外部条件才能继续的验收项。跨边界发现只在末尾存档，不在本范围修复。

下表中 Flutter 与插件各项已在当日对当前提交实跑复核（`flutter test --no-pub --concurrency=1` → 488 passed；`flutter analyze lib test` → 无问题；插件 `npm run build`、`npm test` → 103 passed / 0 fail）。构建产物类结果来自产出记录，未重复构建。

## 已经完成的验证

| 项 | 结果 | 证据 |
|---|---|---|
| Flutter 全量测试 | 488 passed | `flutter test --no-pub --concurrency=1` |
| Flutter 静态分析 | No issues found | `flutter analyze lib test` |
| Flutter 规模 | 71 个 `lib/**/*.dart` / 12,358 行、18 个页面、34 个测试文件 | `flutter_client/` |
| 未使用依赖清理 | 移除零引用依赖 `cupertino_icons`、`json_annotation`、`build_runner`、`json_serializable`（仓库无 `*.g.dart`/`*.freezed.dart` 生成产物），`flutter pub get` 减少 33 个传递依赖；清理后 `flutter analyze lib test` 无问题、488 项测试全过、Linux debug 构建成功 | `flutter_client/pubspec.yaml`；`rg` 全仓引用计数为 0 |
| 弹层控制器退场崩溃 | 已修并回归：管理员后台「创建用户」在提交失败（如后端 400）后关闭弹层会整屏红屏。根因是 `showDialog` 返回后立即 `dispose` 了 `TextEditingController`，退场动画期间 `TextField` 重建时 `addListener` 抛 `A TextEditingController was used after being disposed.`，级联为 `'_dependents.isEmpty': is not true.`。新增 `DialogControllers`（在子树的 `State.dispose()` 里释放，晚于退场动画），套用于 6 处弹层 | 回归测试 `test/admin_page_test.dart`「创建用户弹层随退场动画关闭时不释放仍在使用的控制器」；Linux 端实跑 400 场景不再红屏，显示「用户创建失败：请求失败（HTTP 400）…」，成功场景 `POST create_user` 200 且列表刷新 |
| 弹层控制器修复在 HEAD 产物上复验 | 用 `flutter run -d linux` 重新编译（`kernel_blob.bin` mtime 15:40 晚于最后一次源码改动）后重跑：六处弹层逐个开关共约 14 次，含「创建用户」空字段提交得 HTTP 422 失败路径连续 4 次、编辑用户、重置密码空提交、限流配置读取→保存→重开核对、沙箱配置、MCP 编辑，`flutter run` 日志始终 20 行、无 `disposed` / `_dependents` / `Unhandled exception` | 实跑记录见下文「Linux 实跑记录」；`/tmp/terminal_*.log` 中 `flutter run` 输出 |
| Provider 测试连接错误文案 | 设计内行为，非缺陷：`ProviderKeyClient.test()` 丢弃后端 `message`，页面统一显示「Provider Key 测试失败，请重试」。既有测试 `test/provider_key_test.dart:551`「测试连接网络断开显示测试失败」明确断言不出现 `connection lost` 与 `sensitive-token`，即刻意不向 UI 回显后端/网络细节。与 `dynamic_provider_client.dart:68`、`github_controller.dart:125-126` 展示后端原文的做法不同，属产品选择，不改 | `test/provider_key_test.dart:551-583` |
| VS Code 插件构建 | tsc 退出 0 | `npm run build` |
| VS Code 插件单测 | 103 passed / 0 fail | `npm test` |
| VS Code 插件 e2e（扩展加载） | 退出 0：扩展激活、`assertCompatible` 通过、`package.json` 声明的 5 个命令全部在运行时注册、打开工作台后 webview 面板实际出现 | `npm run e2e` |
| VS Code 插件 e2e（后端会话生命周期） | 真实本地后端上 `active → paused → active → cancelled` 全部通过 | `data/agent_host_sessions/` 中 `workspace_id=fixtures` 的会话记录终态为 `cancelled`；同目录另有一条更早运行的会话停留在 `active`，属运行残留（目录已忽略） |
| Linux 桌面构建与运行 | `flutter build linux --debug` 成功；Xvfb 下窗口已映射 | 窗口标题 `CodingMatrix Agent`，WM_CLASS `com.codingmatrix.agent` |
| Linux 端真实后端全流程 | 登录、会话恢复、13 个功能页渲染全部通过，客户端日志无异常 | 见下文「Linux 实跑记录」 |
| 对话框窄屏 + 键盘溢出 | 新增复现测试 7 项全过；`创建用户` 44px、`编辑用户` 36px、`MCP 编辑` 52px 三处溢出已修 | `test/narrow_dialog_test.dart`；`admin_page.dart`、`agent_history_page.dart`、`mcp_admin_page.dart` 的 `content` 外包 `SingleChildScrollView` |
| 对话框溢出全量排查（18 个对话框） | 仅 `content` 为 `Column` 的三处会溢出，已全部修复；其余 `content` 是单个 `SelectableText`/`Text`/`TextField`，这些控件自身可滚动，实测对话框内 `Scrollable.maxScrollExtent > 0`，长结果（60 行连接测试输出）完整可达，无需再改 | 审计依据：`AlertDialog` 的 `content` 处于 `Flexible` 内且文本类控件内部可滚动；断言见 `test/narrow_dialog_test.dart` 的「MCP 长连接测试结果」用例 |
| 底部弹层空列表 | 4 处「列表为空则弹层无任何可见内容」已修（任务事件、PPT 历史、快照、工作流历史），各补 1 项空态测试 | 完整列表空态改用仓库既有写法 `if (list.isEmpty) const ListTile(...)`；对应 `test/{task_queue,ppt_generation,agent_history,workflow}_test.dart`；Linux 端实跑 `暂无事件` 已截图确认 |
| 全部能力页多档视口布局 | 15 个能力页 × 5 档视口（1280x720、900x700、800x600、640x480、360x640）在完整工作台外壳内逐页打开，无布局溢出、无异常 | `test/workbench_shell_test.dart`「全部能力页在多档视口下渲染无溢出」；扫描经 `scrollUntilVisible` 覆盖抽屉内需滚动才构建的导航项 |
| 堆叠表单项浮动标签压边框 | 已修并回归：`workflow_page`、`image_generation_page`、`dynamic_provider_page`、`virtual_girl_page`（新建角色弹层）、`admin_page`（创建/编辑用户弹层）、`agent_history_page`（并发限制弹层）中相邻的 outlined 输入框之间没有间距，下一条字段的浮动标签会压在上一条边框上并被裁切。按仓库既有写法（`login_page`、`provider_settings_page`）在字段间补 `SizedBox(height: 12)` | 回归测试 `test/workflow_test.dart`「堆叠表单项之间保留间距，浮动标签不压住上方边框」；移除间距后该用例失败、加回后通过。Linux 端对「图片生成」「工作流执行」「动态 Provider」实跑截图放大核对 |
| Android 目标编译 | `flutter build bundle --target-platform android-arm64` 成功 | 产物 `build/flutter_assets` |
| 应用标识统一 | 三端一致为 `com.codingmatrix.agent` | Android `namespace`/`applicationId`、Linux `APPLICATION_ID`、窗口标题与 Windows 产品名 |

## Linux 实跑记录

在 Xvfb（1280x720）下用本地后端实跑，逐页截图核对：

- 登录页 → 真实登录（后端 `POST /api/v1/login` 200）→ 进入 Agent 工作台。
- 重启客户端后免登录恢复（后端 `POST /api/v1/refresh`），说明凭据已落在 keyring 并可复用。
- 逐页访问均正常渲染：Agent 工作台、聊天、会话历史、PPT、图片生成、工作流执行、GirlAI 伴侣、文件中心、任务队列、Provider 授权、模型列表、动态 Provider、GitHub 设置（最后一项以后端 `GET /api/v1/github/config` 被调用为证）。
- 普通权限账号只看到 13 个导航项，`admin`（管理）与 `mcp`（MCP 管理）按权限隐藏。
- 缩到 820x700（低于 900 断点）：左栏收进抽屉、汉堡按钮可用、生成选项换行，无溢出。
- 窗口高 720 时左栏可滚动到最后一项，属设计内行为。
- 超级管理员（`mr_yang`，权限 `superadmin`）可见左栏最末两项「管理员后台」「MCP 管理」，普通账号不可见，符合按权限隐藏的设计。
- 管理员后台真实数据：用户列表 `GET /api/v2/Controller/users` 返回 `用户总数：5` 并列出全部账号与角色；限流配置读取到真实值（全局 1000/60、IP 100/60、用户 50/60），保存后重开值一致；沙箱配置读到 `启用代码沙箱` + `python,javascript`；MCP 管理列出 4 个真实服务（filesystem、brave-search、sqlite、custom-http）。
- 用户名允许重复是后端文档化设计（`user_manage.py:123`「用户名可重复，邮箱唯一」）：实测用同名 `mr_yang` 创建成功，后台出现两行同名用户。不是缺陷，但后台弹层标题与主标识都用 username，重名时无法区分，属已知 UX 限制。

重要陷阱（本轮踩到）：`flutter build linux --debug` 打印 `✓ Built ...` 并不保证产物已更新。Dart 代码在 `bundle/data/flutter_assets/kernel_blob.bin`，本轮改动 `lib/**` 后该文件 mtime 仍停在旧时间，`touch` 源码后重建也不变，因此用旧 bundle 做的界面验证全部无效。做桌面功能复验前先确认 `kernel_blob.bin` mtime 晚于最后一次源码改动；`flutter run -d linux` 会强制重新编译并 `Syncing files to device`，且日志能实时捕获 Dart 异常，是更可靠的复验方式。

首轮实跑暴露两个 Linux 交付缺陷，均已修复并在同一环境复验：

| 缺陷 | 原因 | 修复 | 复验方式 |
|---|---|---|---|
| 未装 CJK 字体的主机上中文全部显示为方框 | 依赖系统字体渲染中文 | 随包内置 Noto Sans CJK SC 子集（ASCII + GB2312 + 常用标点，3.1 MB，OFL 1.1），仅 Linux 使用该字体族 | 用 `FONTCONFIG_FILE` 只暴露 Latin 字体后启动，中文仍正常渲染 |
| 首次启动误报「会话恢复失败，请重新登录」，且登录失败原因显示为网络问题 | 安全存储异常与其它失败混在同一分支 | 凭据层新增 `SecureStorageUnavailableException`，恢复/登录/退出分别给出对应提示 | 无可用密钥环时启动，横幅显示「系统安全存储不可用，登录状态无法在本机保存。请先安装并解锁系统密钥环，再重试。」 |

仍属环境依赖（不是代码缺陷）：会话持久化需要 Secret Service（libsecret + gnome-keyring）。密钥环已存在但处于锁定状态时，系统会弹出解锁对话框等待输入；无人值守环境里该读取会挂起，应用停在启动加载态。

## 待验收项

### 1. Android APK 构建

现象：`flutter build apk --debug --target-platform android-arm64` 在配置阶段即失败并报 `NDK not configured. Download it with SDK manager. Preferred NDK version is '27.0.12077973'.`（`android/build.gradle.kts:19`，`:app` 配置期）。NDK 27 解压约 2.9G；本机根分区 20G、可用约 1.6G（已用 92%），无法容纳。

阻塞原因：SDK 缺 `ndk` 目录且磁盘容量不足。移除 `jni`（例如 pin `path_provider_android`）无法免除该需求，已验证并回滚。项目未显式声明 `ndkVersion`，该值来自 Flutter 3.35.7 的 `FlutterExtension.kt:42`，与 AGP 8.9.1 的默认 NDK 一致。

解除条件：提供预装 NDK 27.0.12077973 的 SDK，或扩大根分区（需腾出约 2.5G 以上）。

验收命令：

```bash
ANDROID_HOME=/tmp/opencode/android-sdk flutter build apk --release --no-pub
```

安全探测：`./gradlew :app:compileDebugKotlin --offline` 会在配置阶段快速失败，不触发 2.9G 下载。

### 2. Android 真机验收

现象：环境无 Android 设备与模拟器，`android/` 的原生与 Kotlin 改动只能静态核对。

待验证项：`flutter_secure_storage` 的 `AndroidOptions(encryptedSharedPreferences: true)` 在设备 KeyStore 上可用；`android:usesCleartextTraffic="true"` 能连到用户自建的明文 HTTP 后端；会话恢复（refresh 验证）与「清除本地会话」在真机可用。

解除条件：接入设备或模拟器。

### 3. Windows 构建与运行

现象：Windows 目标无法在 Linux 上构建。

待验证项：`flutter build windows` 产物可启动；`Runner.rc` 版本资源（`FileDescription`、`ProductName`、`OriginalFilename`）正确写入产物；Windows Credential Manager 上的安全存储可用。

解除条件：Windows 主机加 VS Build Tools 与 Flutter SDK。

### 4. 真实 Provider、GitHub 与 LLM 联调

现象：本环境无真实凭据，客户端层只用 Mock HTTP 与 fixture 验证。

待验证项：`/api/v1/agent/orchestrate/stream` 与七个生成开关的真实链路；Provider 密钥的 RSA 加密提交（`encrypted_api_key`）与管理接口；GitHub 配置、`/api/v1/github/save` 与仓库分支提交读取。

解除条件：真实 Provider 凭据、GitHub Token 与可用的 LLM 端点。

### 5. GitHub 设置页验证状态不持久

现象：`GET /api/v1/github/config` 的 `verified` 恒为 `false`、`verification_status` 恒为 `not_performed`（`app/services/github_config_service.py`），而 `POST /api/v1/github/verify` 只返回结果、不落库（`app/api/v1/github.py:255`）。重开设置页永远显示「尚未验证」。

说明：这是后端缺陷，位于本范围之外。Flutter 客户端显示正确，无需改动。联调时若只看设置页回显会误判为客户端问题。

## 跨边界发现（本范围外，仅存档）

以下问题在核对中被确认存在，但属于后端或 Web 前端，未在本范围修复。

| 位置 | 问题 |
|---|---|
| `app/services/github_config_service.py` | `GET /config` 的 `verified` 硬编码 `false`，`POST /verify` 结果不落库 |
| `src/components/agent/modals/LearningModal.vue` | 读 `total_feedbacks` / `fixed_count` / `avg_fix_time` / `accuracy_improvement`，后端 `app/agent/feedback_learner.py:262` 返回 `learned_patterns` / `total_fixes_recorded` / `overall_success_rate`，导致恒显示「暂无学习数据」 |
| `src/components/agent/modals/SettingsModal.vue` | 读 `concurrentLimits.recommended` 与 `cacheStats.total_keys`，后端返回 `recommendations`（`orchestrate_endpoints.py:1940`）与 `cached_entries`（`app/agent/spec_cache.py`），导致并发与缓存两节不渲染 |
| `Makefile:71` | `clean` 调用 `./scripts/cleanup.sh`，该脚本不存在 |
| `app/main.py:197` | `allow_origin_regex=settings.ALLOWED_HOSTS.replace(",", "\|")` 未转义正则元字符 |
| `Dockerfile:23`、`:34` | 基础镜像 `python:3.10-slim`，与文档要求的 Python 3.11+ 不一致 |
| 应用挂载 | `AiProjectCode.py`、`nginx_ai.py` 未挂载 |

## 本地后端联调方法

无需 `.env` 即可起后端，用于扩展 e2e 与客户端联调。用独立临时库，避免污染仓库内 `app.db`。

```bash
# 启动后端（表在启动时自动创建）
DATABASE_URL=sqlite+aiosqlite:////tmp/opencode/agent-e2e.db ENV=development \
  python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 取 CSRF（同时写入 cookie 文件）
curl -s http://127.0.0.1:8000/api/v1/csrf-token -c /tmp/opencode/e2e-cookies.txt

# 注册临时用户拿 access_token（认证路由直接挂在 /api/v1，无 /auth 段）
curl -s -X POST http://127.0.0.1:8000/api/v1/register \
  -b /tmp/opencode/e2e-cookies.txt \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <上一步的 csrf_token>" \
  -d '{"username":"e2e_agent","email":"e2e_agent@example.com","password":"E2eTest#2026x"}'

# 带真实后端跑扩展 e2e
cd vscode-extension
CODINGMATRIX_E2E_API_URL=http://127.0.0.1:8000 \
CODINGMATRIX_E2E_ACCESS_TOKEN=<access_token> \
  npm run e2e
```

判定 e2e 是否真的覆盖了后端链路：缺少上述两个环境变量时 `e2e/suite.mjs` 会直接 `return` 且仍以退出码 0 结束，此时只证明扩展能加载与注册命令。真实覆盖要看 `data/agent_host_sessions/` 是否新增 `workspace_id=fixtures` 记录、且 `control_status` 终态为 `cancelled`。

agent host 会话存 JSON 文件（目录可用 `AGENT_HOST_SESSION_DIR` 覆盖，已被 `.gitignore` 忽略）加内存字典，不在 SQLite 中。
