# Flutter 客户端

> 最后更新：2026-09-24 | 源码：`flutter_client/` | Dart：71 个 `lib/**/*.dart` / 12,358 行 | 页面：18 | 测试：34 个文件

`flutter_client` 是 CodingMatrix 的 Agent 工作台客户端，目标平台为 Android 与 Linux/Windows 桌面（`android/`、`linux/`、`windows/` 三个平台目录，无 iOS/macOS/Web），Dart 包名为 `codingmatrix_desktop`，应用标识为 `com.codingmatrix.agent`（Android `namespace`/`applicationId`、Linux `APPLICATION_ID`，窗口与产品名为 `CodingMatrix Agent`），版本 `1.0.0+1`，Dart SDK `^3.9.2`。客户端只调用现有 FastAPI 接口，使用 Cookie JWT、CSRF 和 RSA 加密登录，不单独实现业务引擎。Android 清单通过 `android:usesCleartextTraffic` 允许明文 HTTP，因为后端由用户自建、地址在登录页运行时填写。

## 分层

| 层 | 路径 | 职责 |
|----|------|------|
| domain | `lib/domain/` | 会话、任务、快照、交付物、工作流、PPT、GirlAI、GitHub 配置等模型 |
| application | `lib/application/` | Riverpod 状态、工作流/PPT/GirlAI/图片生成编排 |
| infrastructure | `lib/infrastructure/` | HTTP 客户端、SSE 解析、认证存储、文件上传 |
| presentation | `lib/presentation/` | 18 个页面与工作台导航 |

入口在 `lib/main.dart`。HTTP 统一走 `AuthenticatedClient`：自动带 Cookie、CSRF，401 时刷新 access token。

## 已接入页面

| 页面 | 文件 | 后端能力 |
|------|------|----------|
| 工作台 | `workbench_page.dart` | 常驻导航外壳，按权限显示模块入口；MCP 仅 `superadmin` |
| 登录 | `login_page.dart` | `/api/v1/public-key`、`/api/v1/csrf-token`、`/api/v1/login`、`/api/v1/refresh` |
| 聊天 | `chat_page.dart` | `/api/v1/chat`、`/api/v1/conversation/history` |
| 会话历史 | `agent_history_page.dart` | `/api/v1/agent/sessions`、`/sessions/{id}`、`/snapshots/{id}`、`/rollback`、`/snapshot/diff` |
| Agent 决策 | `agent_decision_page.dart` | `/api/v1/agent/session/{id}/decision` |
| 项目文件 | `project_files_page.dart` | `/api/v1/agent/generate/files|read|download`、`/api/v1/github/save` |
| PPT | `ppt_page.dart` | `/api/v1/pptx/*` 大纲、生成任务、质量报告、下载 |
| 图片生成 | `image_generation_page.dart` | `/api/v1/kolors/text-to-image|image-to-image|inpaint|resources` |
| 工作流 | `workflow_page.dart` | `/api/v1/workflow/execute|status|history|import|export` |
| GirlAI | `virtual_girl_page.dart` | `/api/v1/GirlAi/*` 角色、头像、对话、语音转写、记忆/偏好、自定义角色、历史 |
| 文件中心 | `file_center_page.dart` | `/api/v1/files` 列表、下载、删除；`/api/v1/files/upload` 与 `/upload/init|chunk|merge` 分片上传 |
| 任务队列 | `task_queue_page.dart` | `/api/v1/tasks` 列表、取消、重试、事件 |
| Provider 授权 | `provider_settings_page.dart` | `/api/v1/agent/apikeys` 与 `/api/v1/agent/apikey/*` 密钥管理、启停、测试 |
| 模型列表 | `model_list_page.dart` | `/api/v1/models/` |
| 动态供应商 | `dynamic_provider_page.dart` | `/api/v1/providers` 增删改、同步、测试、启停 |
| GitHub | `github_settings_page.dart` | `/api/v1/github/config|verify|repos|branches|commits|save` |
| 管理后台 | `admin_page.dart` | `/api/v2/Controller/users|create_user|update_user|delete_user|reset-password`；`/api/v2/Controller/admin/*`（含 `rate-limit`、`log-config` 写操作）；`/api/v2/admin/config|sandbox-config` |
| MCP 管理 | `mcp_admin_page.dart` | `/api/v2/mcp/servers` 列表、新增、编辑、启停、连接测试、删除 |

## 认证与权限

- 登录使用 RSA 加密载荷，请求带 CSRF Cookie 与 `X-CSRF-Token`。
- Token 与 CSRF 写入安全存储；后续请求由 `AuthenticatedClient` 附加。
- 管理后台入口对 `admin` / `superadmin` 可见。
- MCP 完整管理页仅 `superadmin` 可见。

## Agent SSE 重连

`AgentStreamClient.generate` 请求体包含 `is_resume`。会话详情页在 `reconnectable=true` 时提供「断开并重连」：先读 `GET /api/v1/agent/sessions/{id}`，再 `POST /api/v1/agent/orchestrate/stream` 且 `is_resume=true`。确认文案说明只接收后续及未消费事件。`reconnectable=false` 时重连按钮保持禁用。

## 生成选项与增量修改

工作台首页的提示卡片提供七个生成开关（审查、校验、错误恢复、记忆、Skills、先写规格、依赖图）和一个可选的「项目名称」输入，开关按账号持久化在本地，项目名随 `project_name` 发送。

当上一次生成以 `success` 结束时，下一次提交会自动转为增量修改：请求带 `incremental=true`、`engine=core`、`project_path=<上一次项目的相对路径>`，服务端据此走 IncrementalAdapter 只改受影响文件。停止并清理会把任务标记为 `cancelled`，因此后续提交回到全新生成，避免指向已删除的项目。

## GitHub 边界
设置页读写 `/api/v1/github/config`，并调用 `/verify` 与仓库/分支/提交列表。GET 不回传 Token；页面用 `has_token` / `credential_state` 显示凭据状态。验证成功后内存中 `verified` 为 true，GET 配置仍不落库。项目文件页在 `use_github` 开启时「推送到 GitHub」调用 `POST /api/v1/github/save`，请求省略 `github_config`。完整契约见 [GitHub 集成](GITHUB.md)。

## 管理后台边界

- 用户管理走 `/api/v2/Controller/create_user`、`update_user/{id}`、`delete_user/{id}`、`{id}/reset-password`。
- 运维配置读 `/api/v2/Controller/admin/*`：`system-config`、`stats`、`sandbox-config`、`mcp-servers`、`memory`、`rate-limit`、`log-config`。
- 沙箱配置先 GET `/api/v2/admin/sandbox-config` 回显当前 `enable_code_sandbox` / `sandbox_languages`，保存时 PUT 同一路径（语言列表以逗号拼接为字符串，服务端要求重启生效）。
- 限流配置先 GET `/api/v2/Controller/admin/rate-limit` 取 `config`，保存时依次 PUT `rate-limit/enabled`、`rate-limit/{global,ip,user}`（body 为 `limit` + `window`），要求均为正整数。
- 日志配置先 GET `/api/v2/Controller/admin/log-config` 回显 `global_level`，保存时 PUT `log-config/global-level?level=`，级别取 `DEBUG/INFO/WARNING/ERROR/CRITICAL`。
- MCP 写操作走 `/api/v2/mcp/servers`，与管理面 MCP 只读列表分开。

## 文件导出

下载类结果（文件中心、图片生成、PPT、项目 ZIP）先写入应用文档目录，`FileExporter` 再通过 `FilePicker.saveFile` 导出到用户选择的位置：Android 传 `bytes`（上限 128MB），桌面传路径并在选中后 `file.copy`。`SavedFileActions` 是统一的导出按钮，取消时提示「已取消导出」。

## 运行与验证

```bash
# 安装依赖
cd /workspace/flutter_client
flutter pub get

# 静态分析
flutter analyze --no-pub

# 测试（当前环境记录：2026-09-24，492 passed）
flutter test --no-pub --concurrency=1

# 启动桌面端（需本机已配置 Flutter 桌面目标）
flutter run -d windows
flutter run -d linux

# 启动 Android（需本机已配置 Android SDK；设备 id 先看 flutter devices）
flutter devices
flutter run -d <device-id>

# 构建 Linux 桌面产物，输出在 build/linux/x64/debug/bundle/flutter_client
flutter build linux --debug

# 构建 APK，需要 NDK 27（AGP 需 strip native 库）
flutter build apk --release

# release 签名读取 android/key.properties 与同目录 keystore，两者都被 gitignore 排除；
# 该文件缺失时回退 Android debug 签名，保证新克隆仍可构建

# 免 NDK 的 Android 目标编译校验，输出在 build/flutter_assets
flutter build bundle --target-platform android-arm64
```

测试文件位于 `flutter_client/test/`，共 34 个 `*_test.dart`。当前记录覆盖 Mock HTTP 与 widget 测试，不覆盖真实 Provider、GitHub、LLM 或 Android/Windows 真机。Linux 桌面已在本环境实际构建，接入本地后端跑通登录、会话恢复与 13 个功能页渲染；Android 已构建 release APK（三 ABI、`targetSdk 36`、自定义 release 签名）并核对清单、原生库与签名，尚缺真机安装启动。

### Linux 运行环境依赖

中文字体已内置于应用，不再是环境依赖：

- 应用随包携带 Noto Sans CJK SC 子集（ASCII + GB2312 + 常用中日韩标点，约 3.1 MB，SIL OFL 1.1）。字体选择由 `app.dart:13` 按平台决定：仅 Linux 使用该字体族，Android/Windows 保持系统字体，渲染行为不变。pubspec 中声明的字体资源会被打进所有平台产物，因此 Android APK 也会增加约 3.1 MB；若要拿掉这部分体积，需改用按平台分包的资源方案。源文件与许可证见 `flutter_client/assets/fonts/`，许可证同时注册为资源随产物分发。

凭据存储仍是环境依赖：

- 会话持久化依赖 Secret Service（libsecret + gnome-keyring）。缺失或未解锁时应用仍能启动并进入登录页，但会显示「系统安全存储不可用，登录状态无法在本机保存。请先安装并解锁系统密钥环，再重试。」，且登录不会成功（无法保存会话）。该失败在凭据层被归类为 `SecureStorageUnavailableException`，不会再被误报为「会话恢复失败」或「网络失败」。
- 密钥环处于锁定状态时，系统会弹出解锁对话框等待用户输入；在无人值守的 headless 环境里该读取会一直挂起，应用停留在启动加载态。这是 Secret Service 的交互行为，部署时需预先解锁密钥环。

## 相关文档

- [快速开始](../guides/GETTING-STARTED.md)
- [测试指南](../testing/TESTING.md)
- [API 文档](../api/API-DOCUMENTATION.md)
- [会话生命周期](SESSION-LIFECYCLE.md)
- [Agent 系统](AGENT.md)
- [模块说明](../architecture/MODULES.md)
