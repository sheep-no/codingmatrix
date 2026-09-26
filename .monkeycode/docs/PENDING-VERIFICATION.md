# 待环境验收清单

> 核对日期：2026-09-22 ~ 2026-09-26 | 范围：Flutter 双端（Android/Linux/Windows）与 VS Code 扩展

本文件记录该范围内已经完成的验证，以及需要外部条件才能继续的验收项。跨边界发现只在末尾存档，不在本范围修复。

下表中 Flutter 与插件各项已在当日对当前提交实跑复核（`flutter test` → 492 passed；`flutter analyze lib test` → 无问题；插件 `npm run build`、`node --test test/*.test.mjs` → 100 passed / 0 fail，两套 e2e 通过）。构建产物类条目已按 2026-09-25 的重新构建结果更新。

## 已经完成的验证

2026-09-25 插件补充核对：工作台实际为 7 个 tab、14 个请求资源（`WORKBENCH_RESOURCES` 与 `dispatchWorkbenchRequest` 的 14 个分支、webview 脚本内 14 处 `request`/`runRequest` 一一对应）；`performance` 资源同时请求 `/agent/performance` 与 `/agent/performance/trends`，故真实后端 HTTP 调用为 15 次。复用 `CloudConnection` 与 `dispatchWorkbenchRequest` 从真实后端取数，替换消息传输后在 Chromium 中执行原始 webview HTML，7 页均完成 DOM 读取与截图，无 JavaScript 异常。删除、回滚、清空缓存等写操作未执行。文件版本读取仍返回已知的 404。

本轮发现模型页把后端 `roles` 的字符串值当对象读取，五个角色均显示 `-`。已支持字符串映射，新增脚本级回归用例在修复前失败、修复后通过；TypeScript 构建通过，全量插件单测为 99 passed / 0 fail。Chromium 复验显示五个角色对应的真实模型标识。截图位于 `/tmp/opencode/tabs/`。

2026-09-25 真实 VS Code 宿主内逐页验收：用 CDP（`--remote-debugging-port=9222` + Node 全局 WebSocket）连接扩展宿主里 webview 的内层内容 frame，逐 tab 触发刷新并读取 DOM。7/7 页均无横向溢出、无 console error，状态行分别为「会话历史已更新」「模型配置已更新」「性能指标已更新」「学习统计已更新」「缓存与并发配置已更新」，空会话 ID 时「文件版本」页为「请先填写会话 ID」。截图见 `/tmp/opencode/host_tabs_host3/`（`Page.captureScreenshot` 以 webview 元素矩形为 clip）。

同轮修复两处 webview 显示缺陷并复验：学习页后端 `fix_description` 自带「修复」前缀，渲染后出现「修复：修复: …」，现剥离重复前缀；「文件版本」页提示语原称留空即用最近会话 ID，实际只在本次工作台完成生成后才自动填入，已改为与行为一致的文案。注意内联脚本位于模板字符串内，正则里的 `\s` 必须写成 `\\s`，否则会被折叠成字面 `s`（该缺陷先由新用例暴露）。回归用例 `test/workbench-log.test.mjs`「does not duplicate the fix prefix in learning stats」修前失败、修后通过；插件单测 99 → 100 passed / 0 fail。宿主内复验：学习页显示「修复：error1」；文件版本页填入 `llm-static-1790262394` 后状态为 `cloud request failed with status 404`（后端缺陷，见跨边界）；会话历史点「查看」加载出 `你：… / Agent：…`。截图见 `/tmp/opencode/host_tabs_host5/`。VSIX 已重新打包（54 files, 74.89 KB）。

2026-09-25 修复对话页「连接本地 Agent Host」死控件：「连接本地 Agent Host」按钮 post `workbench_ready`，但宿主 `AgentWorkbenchController` 只处理 `workbench_prompt`、`workbench_control`、`workbench_request`，该消息自引入（`b92280c`）起无接收方，点击只改本地状态文案、不触发任何连接。现新增 `onReady` 回调并在 `extension.ts` 接到已有的 `codingmatrix.reconnectAgentSession`，按真实结果发布 `progress`（「本地 Agent Host 已连接」）或 `error`（未配置凭据时提示先配置 `apiUrl` 与 `accessToken`）。回归用例 `test/agent-workbench.test.mjs`「routes the workbench connect button to the ready handler」修前失败、修后通过；插件单测 100 → 101 passed / 0 fail。宿主内实点按钮后日志显示 `progress：本地 Agent Host 已连接`。截图见 `/tmp/opencode/host_tabs_host6/connect.png`。VSIX 已再次重新打包。

2026-09-25 修复插件错误信息丢失后端可操作文案：`CloudConnection.request()` 在非 2xx 时直接抛 `cloud request failed with status <code>`，丢弃响应体里后端的说明。实测编排流在磁盘守卫不满足时返回 `507` 加 `{"message":"磁盘空间不足（可用：0.78 GB）"}`，用户侧只看到状态码。现新增 `describeFailure()`：尽力解析 JSON 错误体，取 `message` 或 `detail` 拼到通用信息后（非 JSON 或不可读时回退原信息，不影响既有分支）。回归用例 `test/connection.test.mjs`「surfaces the backend error message for non-retryable failures」修前失败、修后通过；插件单测 101 → 102 passed / 0 fail。宿主内实发需求复验：对话页错误为 `cloud request failed with status 507: 磁盘空间不足（可用：0.74 GB）`。截图见 `/tmp/opencode/host_tabs_drv5/send-error.png`。

2026-09-26 优化插件到 webview 的事件转发量：`thinking` 事件在增量 `message` 之外还带一份**全量累积**文本 `accumulated`，每个 chunk 重复整段，转发量随输出长度呈平方增长；webview 只渲染 `message`，`accumulated` 在 `src/` 与 `test/` 中零引用。实测真实 legacy 流 88.44MB，其中 `accumulated` 独占 65.87MB（首个样本只有 4 个字段，是字段并集统计才发现该字段，勿据单样本判定形状）。现于 `CloudConnection.parseStreamEvent()` 在 SSE 解析处剥离 `thinking` 的 `accumulated`（行为等价，其余字段与事件类型全部保留）。回归用例 `test/connection.test.mjs`「drops the redundant accumulated text from thinking chunks」修前失败、修后通过（反向验证：注释掉剥离行后重新失败）；插件单测 102 → 103 passed / 0 fail。用真实 `fix_stream.ndjson` 重放（`/tmp/opencode/verify_accumulated.mjs`）验证：源流 88.44MB → 转发 2.01MB（减少 97.7%），13780 个 thinking 全部无 `accumulated`，13 类事件计数不变。

2026-09-26 Android 无设备静态验收：模拟器路径在本环境不可用（宿主无 `/dev/kvm`，`/proc/cpuinfo` 无 `vmx`/`svm`，SDK 亦无 `emulator` 与 system-image，且根分区仅余约 0.8GB、可用内存约 1GB），改为对 release APK 做静态验收并修复其中发现的缺陷。验收结论（新产物 `app-release.apk` 57.9MB，SHA-1 `bc6278b2…7858250`）：`apksigner verify` 通过（v2 方案，签名 DN/SHA-256 与上表一致）；`zipalign -c -P 16 -v 4` 通过（`extractNativeLibs=false` 下 Android 15+ 要求的 16KB 页对齐成立）；三 ABI 齐备（`arm64-v8a`/`armeabi-v7a`/`x86_64`，各 4 个 `.so`）；`libapp.so` 存在且无 `kernel_blob.bin`（确认 AOT release 而非 JIT/debug 快照）；清单复核 `allowBackup=false`、`usesCleartextTraffic=true`（用户自建 HTTP 后端所需）、无 `debuggable` 属性、仅 `INTERNET` 权限 + AndroidX 注入的 `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`；`android/key.properties`、`local.properties`、`upload-keystore.jks` 全部被 git 忽略且未入库。发现并修复的缺陷：启动图标原为**传统 drawable**（`@drawable/ic_launcher`，无 `anydpi-v26` 变体），Android 8.0+ 启动器会把它当传统图标缩小并垫系统底板，出现可见白边/双底板；现新增自适应图标 `drawable-anydpi-v26/ic_launcher.xml`（`adaptive-icon` + `@color/ic_launcher_background` + `@drawable/ic_launcher_foreground`），保留 `drawable/ic_launcher.xml` 作为 API 24/25 回退。修复验证：先用 `aapt2 compile/link` 与合成清单确认 `drawable/ic_launcher` 具备 `(anydpi-v26)` 变体、`color/ic_launcher_background` 解析为 `#ff151923`；再实跑 `flutter build apk --release --no-pub`（1334.2s）重建产物，用 `aapt2 dump resources` 确认新 APK 的 `drawable/ic_launcher` 含 `(anydpi-v26)` 变体、`aapt2 dump xmltree` 确认该变体确为 `adaptive-icon`（background/foreground 均解析到预期资源）。`flutter analyze lib test` → No issues found。Dart 代码本轮未改动，其上一步已跑的 492 passed 仍适用。未覆盖项见「待验收项 · 2. Android 真机验收」。

2026-09-26 全量回归（除「待验收项」中列明的环境受限项外，其余可验收项全部重跑并通过）：**Flutter** —— `flutter test --no-pub --concurrency=1` → 492 passed；`flutter analyze lib test` → No issues found；`build/linux/x64/release/bundle/flutter_client` 在 Xvfb 下实跑，`xwininfo` 显示窗口 `"CodingMatrix Agent"` 映射为 1280x720（`WM_CLASS com.codingmatrix.agent`），进程存活。**VS Code 插件** —— `tsc -p tsconfig.json` 退出 0；`node --test test/*.test.mjs` → 103 passed / 0 fail；两套 e2e 入口均退出 0（`xvfb-run -a node e2e/run.mjs`；`xvfb-run -a node_modules/.bin/vscode-test` → `2 passing`，含扩展在真实工作区激活与工作台命令注册）。环境处理：`@vscode/test-electron` 把 `stable` 解析为 1.139.1 并尝试下载 326MB，被 CDN 反复中断（`Error: aborted`，三次重试均失败），只留下无 `is-complete` 的半成品目录；已手动断点续传补齐 `.vscode-test/vscode-linux-x64-1.139.1` 并写入 `is-complete`，两套入口随即离线复用缓存通过（该目录已被 `.gitignore` 忽略，不入库）。**插件宿主 7 tab 逐页验收** —— 真实 VS Code 宿主内通过 CDP 连接 webview 内容 frame，逐个切换 `chat/history/models/versions/performance/learning/settings` 并点击各自刷新按钮，7/7 页 `activeTab` 正确、**横向溢出 0、console error 0**；各页加载真实后端数据（会话历史 2 条真实会话、模型 5 个角色 `qwen3-8b`/`deepseek-r1`/`qwen3.5-4b`/`glm-z1-9b`/`qwen3-8b`、学习统计「已学习模式 46 / 累计修复记录 727」且错误前缀无重复、设置页 5 档并发限制 + 缓存命中率 66.7%）；「文件版本」页在空会话下显示守卫文案「请先填写会话 ID」（对真实会话的 404 属跨边界缺陷，见下）。截图与报告见 `/tmp/opencode/host_tabs_tabs1/`、`/tmp/opencode/host_report_tabs1.json`。**编排端到端（真实 LLM）** —— `POST /api/v1/agent/orchestrate/stream`（legacy 引擎、SiliconFlow 真实凭据）跑到 `done`：`success=true`、`project_path="1/llm-static-1790424943"`、`total_files_created=5`、`total_files_failed=0`、架构检查「通过=True, 违规=0, 一致性得分=1.00」，用时 358.5s；产物落盘 `/workspace/projects/1/llm-static-1790424943/`（`.dep_graph.json`、`app/command.py`、`docs/README.md`、`src/{index.html,style.css,app.js}`）。**磁盘** —— 验收前根分区仅余 796MB（编排会触发 507 守卫），清理纯构建产物 `flutter_client/build/app/intermediates`（717M）与可重下缓存 `/root/.gradle/caches`（2.9G）后升至 4.3GB，保留 APK 与 Linux bundle 作证据。

| 项 | 结果 | 证据 |
|---|---|---|
| Flutter 全量测试 | 492 passed | `flutter test --no-pub --concurrency=1` |
| Flutter 静态分析 | No issues found | `flutter analyze lib test` |
| Flutter 规模 | 71 个 `lib/**/*.dart` / 12,358 行、18 个页面、34 个测试文件 | `flutter_client/` |
| 未使用依赖清理 | 移除零引用依赖 `cupertino_icons`、`json_annotation`、`build_runner`、`json_serializable`（仓库无 `*.g.dart`/`*.freezed.dart` 生成产物），`flutter pub get` 减少 33 个传递依赖；清理后 `flutter analyze lib test` 无问题、488 项测试全过、Linux debug 构建成功 | `flutter_client/pubspec.yaml`；`rg` 全仓引用计数为 0 |
| 弹层控制器退场崩溃 | 已修并回归：管理员后台「创建用户」在提交失败（如后端 400）后关闭弹层会整屏红屏。根因是 `showDialog` 返回后立即 `dispose` 了 `TextEditingController`，退场动画期间 `TextField` 重建时 `addListener` 抛 `A TextEditingController was used after being disposed.`，级联为 `'_dependents.isEmpty': is not true.`。新增 `DialogControllers`（在子树的 `State.dispose()` 里释放，晚于退场动画），套用于 6 处弹层 | 回归测试 `test/admin_page_test.dart`「创建用户弹层随退场动画关闭时不释放仍在使用的控制器」；Linux 端实跑 400 场景不再红屏，显示「用户创建失败：请求失败（HTTP 400）…」，成功场景 `POST create_user` 200 且列表刷新 |
| 弹层控制器修复在 HEAD 产物上复验 | 用 `flutter run -d linux` 重新编译（`kernel_blob.bin` mtime 15:40 晚于最后一次源码改动）后重跑：六处弹层逐个开关共约 14 次，含「创建用户」空字段提交得 HTTP 422 失败路径连续 4 次、编辑用户、重置密码空提交、限流配置读取→保存→重开核对、沙箱配置、MCP 编辑，`flutter run` 日志始终 20 行、无 `disposed` / `_dependents` / `Unhandled exception` | 实跑记录见下文「Linux 实跑记录」；`/tmp/terminal_*.log` 中 `flutter run` 输出 |
| Provider 测试连接错误文案 | 设计内行为，非缺陷：`ProviderKeyClient.test()` 丢弃后端 `message`，页面统一显示「Provider Key 测试失败，请重试」。既有测试 `test/provider_key_test.dart:551`「测试连接网络断开显示测试失败」明确断言不出现 `connection lost` 与 `sensitive-token`，即刻意不向 UI 回显后端/网络细节。与 `dynamic_provider_client.dart:68`、`github_controller.dart:125-126` 展示后端原文的做法不同，属产品选择，不改 | `test/provider_key_test.dart:551-583` |
| VS Code 插件构建 | tsc 退出 0 | `npm run build` |
| VS Code 插件单测 | 103 passed / 0 fail | `npm test`（tsc + `node --test test/*.test.mjs`） |
| VS Code 插件 e2e（扩展加载） | 退出 0：扩展激活、`package.json` 声明的 5 个命令全部在运行时注册、打开工作台后 webview 面板实际出现 | `xvfb-run -a node e2e/run.mjs`（`e2e/suite.mjs`） |
| VS Code 插件 e2e（CLI 第二入口） | `Exit code: 0`，`2 passing`：扩展在真实 VS Code 工作区激活、工作台命令注册并可打开 | `node_modules/.bin/vscode-test`（读 `.vscode-test.mjs`，跑 `e2e/**/*.test.mjs`） |
| VS Code 插件 e2e（后端会话生命周期） | 真实本地后端上 `active → paused → active → cancelled` 全部通过 | `data/agent_host_sessions/` 中 `workspace_id=fixtures` 的会话记录终态为 `cancelled`；同目录另有一条更早运行的会话停留在 `active`，属运行残留（目录已忽略） |
| VS Code 插件孤儿模块清理 | 删除生产代码零引用的 `src/compatibility.ts`（65 行）与 `src/status-view.ts`（177 行）及各自单测；两者只被自身测试 import，`compatibility` 的握手校验与生产实际逻辑（`agent-host.ts:204` 的 `protocol_version` 单值比对）不一致，且 `EXTENSION_VERSION` 与 `package.json` 版本重复。同时移除 e2e 里「自造对象自测」的假断言（它从未触及真实握手路径） | 单测 103 → 95；`rg` 全仓引用计数为 0；删后 tsc 退出 0、两套 e2e 仍通过 |
| VS Code 插件重新打包 | `vsce package` 重建本地 vsix：包内 51 个 `dist/` 文件与当前源码 1:1，不再含已删模块（旧包为 9 月 7 日产物，`extension.js` 缺后续 52 行改动）。注意 tsc 不清理已删源码的 `dist/` 残留，打包前需手动清理 | `codingmatrix-local-validation-0.1.0.vsix`（54 files, 74.89 KB） |
| VS Code 插件工作台事件解包 | 已修并回归：编排流混用两种封包。`PASSTHROUGH_SSE_EVENTS`（thinking、file、file_diff、step_detail、model_info、pipeline_mode 等）原样透传、字段在顶层，而 progress、done、error、critical_decisions 包在 `{type, data}`。webview 只读 `value.data`，透传帧因此全部丢载荷：thinking 退化成 `thinking：thinking`（`orchestrator_progress.py:282` 的 `message` 在顶层，实测单轮约 2000 行），progress 丢掉 `step`/`phase`/`percentage`。现按有无 `data` 解包、扩展文本回退链、过滤 heartbeat，并把消息列表上限设为 100 条（与 Flutter 客户端 `workbench_controller.dart:93,160` 一致） | 新增 `test/workbench-log.test.mjs` 3 项（自建最小 DOM 直接执行内联脚本，覆盖 heartbeat 过滤、thinking/progress/file/step_detail 解包、100 条上限）；单测 95 → 98；`xvfb-run -a node e2e/run.mjs` 仍退出 0 |
| VS Code 插件接口契约核对 | 对真实本地后端逐个调用工作台 15 个请求：`history`、`conversation/history`、`models/agent-config`、`agent/token-usage`、`learning/stats`、`performance(+trends)`、`concurrent-limits/recommended`、`cache/stats`、`snapshots/{session}`。字段与插件解析层全部匹配（`connection.ts` 的 `optional*` 容错未触发静默回退）。唯一不可用的是「文件版本」tab，根因在后端 | 探测脚本 `/tmp/opencode/probe_workbench.py`；快照 404 详见「跨边界发现」 |
| Linux 桌面构建与运行 | `flutter build linux --debug` 成功；Xvfb 下窗口已映射 | 窗口标题 `CodingMatrix Agent`，WM_CLASS `com.codingmatrix.agent` |
| Linux 端真实后端全流程 | 登录、会话恢复、13 个功能页渲染全部通过，客户端日志无异常 | 见下文「Linux 实跑记录」 |
| 对话框窄屏 + 键盘溢出 | 新增复现测试 7 项全过；`创建用户` 44px、`编辑用户` 36px、`MCP 编辑` 52px 三处溢出已修 | `test/narrow_dialog_test.dart`；`admin_page.dart`、`agent_history_page.dart`、`mcp_admin_page.dart` 的 `content` 外包 `SingleChildScrollView` |
| 对话框溢出全量排查（18 个对话框） | 仅 `content` 为 `Column` 的三处会溢出，已全部修复；其余 `content` 是单个 `SelectableText`/`Text`/`TextField`，这些控件自身可滚动，实测对话框内 `Scrollable.maxScrollExtent > 0`，长结果（60 行连接测试输出）完整可达，无需再改 | 审计依据：`AlertDialog` 的 `content` 处于 `Flexible` 内且文本类控件内部可滚动；断言见 `test/narrow_dialog_test.dart` 的「MCP 长连接测试结果」用例 |
| 底部弹层空列表 | 4 处「列表为空则弹层无任何可见内容」已修（任务事件、PPT 历史、快照、工作流历史），各补 1 项空态测试 | 完整列表空态改用仓库既有写法 `if (list.isEmpty) const ListTile(...)`；对应 `test/{task_queue,ppt_generation,agent_history,workflow}_test.dart`；Linux 端实跑 `暂无事件` 已截图确认 |
| 全部能力页多档视口布局 | 15 个能力页 × 5 档视口（1280x720、900x700、800x600、640x480、360x640）在完整工作台外壳内逐页打开，无布局溢出、无异常 | `test/workbench_shell_test.dart`「全部能力页在多档视口下渲染无溢出」；扫描经 `scrollUntilVisible` 覆盖抽屉内需滚动才构建的导航项 |
| 堆叠表单项浮动标签压边框 | 已修并回归：`workflow_page`、`image_generation_page`、`dynamic_provider_page`、`virtual_girl_page`（新建角色弹层）、`admin_page`（创建/编辑用户弹层）、`agent_history_page`（并发限制弹层）中相邻的 outlined 输入框之间没有间距，下一条字段的浮动标签会压在上一条边框上并被裁切。按仓库既有写法（`login_page`、`provider_settings_page`）在字段间补 `SizedBox(height: 12)` | 回归测试 `test/workflow_test.dart`「堆叠表单项之间保留间距，浮动标签不压住上方边框」；移除间距后该用例失败、加回后通过。Linux 端对「图片生成」「工作流执行」「动态 Provider」实跑截图放大核对 |
| Android 目标编译 | `flutter build bundle --target-platform android-arm64` 成功 | 产物 `build/flutter_assets` |
| 应用标识统一 | 三端一致为 `com.codingmatrix.agent` | Android `namespace`/`applicationId`、Linux `APPLICATION_ID`、窗口标题与 Windows 产品名 |
| 真实 LLM 链路 | SiliconFlow 凭据有效（98 模型）、5 个 agent 角色模型可用、后端 chat 非流式与流式均真实返回、Provider RSA 提交与「测试连接」成功 | 本地后端实跑，详见「待验收项 4」 |
| 工作台进度契约修复 | 已修并回归：`WorkbenchController` 的 `progress` 分支只读 `stage`/`progress`/`session_id`，而后端 `ProgressMixin._report_progress` 实际发 `step`/`phase`/`current`/`total`/`percentage`（`app/agent/orchestrator_progress.py:150`），故真实运行时进度条恒 0%、阶段停在初始 `connecting`。同一字段缺失也让 `awaiting_user_decision` 判定恒不成立（死分支）：当前后端两种帧顺序下未造成可见故障，但顺序一旦互换就会把已下发的架构决策清空。现统一从 `step`/`phase`、`percentage` 读取，保留旧字段别名 | 新增 `test/agent_delivery_test.dart` 两项确定性用例（按真实 SSE 包封形状构造），修前必失败、修后通过（当次全量 490 passed） |
| 编排端到端与文件链路 | 真实跑到 `done`（`success=true`，4/4 文件），`done` 载荷形状与客户端一致；客户端文件列表/读取/下载三个接口对同一真实项目实测通过 | 详见「待验收项 4」 |
| 客户端死代码清理与失败原因展示 | `WorkbenchState.artifacts` / `Artifact`（`unified_models.dart:209`）无后端生产者也无渲染，已整体删除：模型类、状态字段与 `copyWith` 形参、SSE 收集分支、两处自测断言。同时后端 `error` 事件的原因原只存 `task.errorJson` 且 UI 从不读取，现于任务概览卡片展示为「失败原因」+ 可复制文本，仅在 `status == 'failed'` 时出现（`disconnected` 已有专门提示，不重复） | 新增 `test/widget_test.dart`「失败任务在概览卡片展示服务端失败原因」；移除展示代码后该用例在 `expect(find.text('失败原因'), findsOneWidget)` 失败、恢复后通过 |
| 事件卡不再渲染文件正文 | 已修并回归：`_EventsCard` 原先按 `event.type: event.raw` 整份渲染，而 `file`（`orchestrator_progress.py:196`）与 `file_diff`（`:224`）的载荷内嵌完整 `content` / `old_content` / `new_content`。现对这两类事件只显示 `type · path · operation · file_size_human` 摘要，其余事件保留原文但统一截断到 2000 字符并标注省略量 | 新增 `test/widget_test.dart`「文件事件只展示路径与大小，不渲染源码正文」（按后端顶层字段构造真实 SSE 帧，400 行正文）；把摘要分支临时禁用后该用例在 `expect(find.textContaining('12.4 KB'), findsOneWidget)` 失败、恢复后通过；全量 492 passed、`flutter analyze lib test` 无问题 |
| Android release APK 重建 | `flutter build apk --release --no-pub` 成功，57.9 MB（2026-09-26 二次重建后 SHA-1 `bc6278b2…7858250`）。`apksigner verify` 通过（v2 方案，v1/v3 未启用），签名 DN `CN=CodingMatrix Agent, OU=Mobile, O=CodingMatrix, L=Beijing, ST=Beijing, C=CN`、SHA-256 `1cace6b8…dddb3a`；`zipalign -c -P 16` 通过（16KB 页对齐）；`aapt2 dump badging/xmltree/resources` 复核三 ABI（`arm64-v8a`/`armeabi-v7a`/`x86_64`）、`minSdk 24`、`targetSdk 36`、`versionCode 1`/`versionName 1.0.0`、`package com.codingmatrix.agent`、label `CodingMatrix Agent`、`allowBackup=false`、`usesCleartextTraffic=true`、无 `debuggable`、仅 `INTERNET` 权限（另有一个同包签名级 `DYNAMIC_RECEIVER_NOT_EXPORTED_PERMISSION`，由 AndroidX 自动注入，非手工声明）；启动图标含 `anydpi-v26` 自适应变体（本轮修复） | `flutter_client/build/app/outputs/flutter-apk/app-release.apk` |
| Linux 发布产物重建与密钥环阻塞可见性 | 重建 `flutter build linux --release` bundle 并实跑：窗口映射、登录页完整渲染（含「系统安全存储不可用」横幅）。修复启动可见性缺陷：密钥环锁定弹出解锁框时，runner 只在首帧回调里 `gtk_widget_show`，而 `flutter_secure_storage` 经 libsecret 在平台线程上同步等待解锁，首帧永不产生，窗口停在 `IsUnMapped`、应用完全不可见。现于 `my_application.cc` 启动即 `gtk_widget_show(window)`，提示框挂起期间窗口已 `IsViewable`，解锁或取消后按降级路径正常渲染 | 修复前 `xwininfo` → `IsUnMapped`，修复后 → `IsViewable`；截图 `/tmp/opencode/linux_fixed_prompt.png`（提示框 + 可见窗口）、`/tmp/opencode/linux_fixed_render.png`（取消后登录页）；取消提示后日志 `libsecret_error: Failed to unlock the keyring` |
| Linux release bundle 真实后端全流程 | 在解锁的 Secret Service（独立 `dbus-run-session` + 全新 HOME + 非空密码 keyring）下用 release bundle 连本地后端实跑：UI 输入凭据登录（后端 `POST /api/v1/login` 200），进入工作台；逐页点击 12 个导航项全部渲染真实数据（会话历史载入真实会话、模型列表载入 8 个后端模型、Provider 授权显示「硅基流动」），12 张截图无 Flutter 溢出黄条、无错误红屏；关闭进程后重启，经 `POST /api/v1/refresh` 200 免密恢复到工作台；缩至 820x700 / 640x600 时左栏收进抽屉、生成选项换行、抽屉可打开，均无溢出 | 截图 `/tmp/opencode/e2e_01_login.png`、`e2e_03_afterlogin.png`、`e2e_page_*.png`、`e2e_montage.png`、`e2e_restore.png`、`e2e_narrow820.png`、`e2e_narrow640.png`、`e2e_drawer640.png`；后端日志 `POST /api/v1/login` / `POST /api/v1/refresh` 均 200 |

## 客户端代码发现（本范围内）

核对中确认以下客户端问题，处理状态见下表：

| 位置 | 发现 | 证据 |
|---|---|---|
| `workbench_controller.dart:146`、`WorkbenchState.artifacts`、`unified_models.dart:209` `Artifact` | **已删除**。不可达死代码：只有当 SSE 事件的 `data.artifact` 存在时才会收集，而后端全部 SSE 生产者都不产出 `artifact` 字段（`rg 'artifact' app` 无 SSE 命中）；且 `artifacts` 自引入起从未在 `lib/presentation` 被渲染（`git log -S artifacts -- flutter_client/lib/presentation` 无结果）。现状只被自身测试引用 | `git log -S artifacts -- flutter_client/lib/application/workbench_controller.dart` → `8f6c261`；删除后 `rg 'Artifact\|artifacts' flutter_client/lib` 无命中 |
| `agent_home_view.dart:473` | **已修复**。事件卡原先按 `event.type: event.raw` 原样渲染，而 `file` 事件（`orchestrator_progress.py:196`）的 `raw` 内含整份文件正文，`file_diff`（`:224`）内嵌 `old_content`/`new_content`。大文件会把整段源码塞进单个 `SelectableText`，滚动到时需整段排版，存在卡顿与内存风险。现对这两类事件只显示摘要，其余事件截断到 2000 字符 | 新增 `test/widget_test.dart`「文件事件只展示路径与大小，不渲染源码正文」；见上文已完成验证表 |
| `workbench_controller.dart:443`、`agent_home_view.dart:143` | **已修复**。后端 `error` 事件的原因文本原先只存入 `task.errorJson`，UI 从不读取：主状态区只显示 `task.status == 'failed'` 与本地 `actionError`（后者仅覆盖「停止未确认」「决策校验/超时」三种本地失败）。编排中断时的真实原因（如 `unknown file types were not inferred: vue.py`）只能在「实时事件」卡片的原始 JSON 里看到。现于 `_OverviewCard` 展示 `errorJson['error']` | 修复前 `rg errorJson lib/` 只有赋值（`:443`、`:256`、`:275`、`:287`）无读取；新增用例覆盖 |

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

2026-09-25 用重建后的 **release** bundle 复跑（独立 `dbus-run-session` + 可用 keyring）：UI 登录 → 12 页导航巡检 → 重启免密恢复 → 窄屏 820x700 / 640x600 + 抽屉，全部通过，详见上文已完成验证表。当时未能从 UI 驱动一次完整生成：编排磁盘守卫（`app/utils/guardrails.py:250`，要求可用空间 ≥ 1GB 且 ≥ 10%）在当前根分区只剩 873MB（4%）时必然返回 507。该环境容量限制已于 2026-09-25 晚清除（见「待验收项 4」磁盘守卫条目），随后 UI 完整生成已跑到 `done`。

重要陷阱（本轮踩到）：`flutter build linux --debug` 打印 `✓ Built ...` 并不保证产物已更新。Dart 代码在 `bundle/data/flutter_assets/kernel_blob.bin`，本轮改动 `lib/**` 后该文件 mtime 仍停在旧时间，`touch` 源码后重建也不变，因此用旧 bundle 做的界面验证全部无效。做桌面功能复验前先确认 `kernel_blob.bin` mtime 晚于最后一次源码改动；`flutter run -d linux` 会强制重新编译并 `Syncing files to device`，且日志能实时捕获 Dart 异常，是更可靠的复验方式。

首轮实跑暴露两个 Linux 交付缺陷，均已修复并在同一环境复验：

| 缺陷 | 原因 | 修复 | 复验方式 |
|---|---|---|---|
| 未装 CJK 字体的主机上中文全部显示为方框 | 依赖系统字体渲染中文 | 随包内置 Noto Sans CJK SC 子集（ASCII + GB2312 + 常用标点，3.1 MB，OFL 1.1），仅 Linux 使用该字体族 | 用 `FONTCONFIG_FILE` 只暴露 Latin 字体后启动，中文仍正常渲染 |
| 首次启动误报「会话恢复失败，请重新登录」，且登录失败原因显示为网络问题 | 安全存储异常与其它失败混在同一分支 | 凭据层新增 `SecureStorageUnavailableException`，恢复/登录/退出分别给出对应提示 | 无可用密钥环时启动，横幅显示「系统安全存储不可用，登录状态无法在本机保存。请先安装并解锁系统密钥环，再重试。」 |

仍属环境依赖：会话持久化需要 Secret Service（libsecret + gnome-keyring）。密钥环已存在但处于锁定状态时，系统会弹出解锁对话框等待输入；`flutter_secure_storage` 经 libsecret 在平台线程上同步等待，会阻塞首帧，此前表现不是「停在启动加载态」而是窗口根本不出现（`IsUnMapped`）。现已让 runner 启动即显示窗口（见上表），提示框挂起期间应用可见，解锁或取消后按降级路径渲染。

## 待验收项

### 1. Android APK 构建（已完成）

环境已装 NDK 27.0.12077973，release 构建通过：

```bash
export JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
export ANDROID_HOME=/tmp/opencode/android-sdk
cd /workspace/flutter_client
flutter build apk --release --no-pub
```

产物 `build/app/outputs/flutter-apk/app-release.apk`（57.9 MB），已核对：三 ABI（`arm64-v8a` / `armeabi-v7a` / `x86_64`）、`package com.codingmatrix.agent`、`versionCode 1`、`versionName 1.0.0`、`minSdk 24`、`targetSdk 36`、`application-label 'CodingMatrix Agent'`、仅 `INTERNET` 权限、`allowBackup=false`、`usesCleartextTraffic=true`、无 `debuggable`、16KB 页对齐、AOT（有 `libapp.so` 无 `kernel_blob.bin`）、启动图标含 `anydpi-v26` 自适应变体。图标层改动见「已经完成的验证」中 2026-09-26 条目。

Release 签名（`android/app/build.gradle.kts:11-63`）：读取 `android/key.properties` 与同目录 keystore，两者均被 `android/.gitignore` 排除、不入库。存在该文件时用自定义密钥签名（v2 方案，`minSdk 24` 足够）；缺失时回退 debug 签名，因此新克隆仍能 `flutter run --release`。两条路径均已实跑验证。

本地生成签名密钥（密码只写入被忽略的 `key.properties`，勿入库）：

```bash
cd /workspace/flutter_client/android/app
keytool -genkeypair -v -keystore upload-keystore.jks -keyalg RSA -keysize 2048 -validity 10000 -alias upload
```

`android/key.properties` 字段：`storePassword`、`keyPassword`、`keyAlias=upload`、`storeFile=upload-keystore.jks`（相对 `app/` 模块目录）。

发布提醒：递增 `pubspec.yaml` 的构建号（当前 `+1`），否则同 versionCode 无法覆盖安装；keystore 一旦丢失将无法更新已发布应用。

磁盘提示：SDK + NDK 27（约 2.0G）+ 构建中间产物会把根分区压到约 1.7G 可用（92%）。清理前 `:app:compileDebugKotlin --offline` 可在配置期快速探测 NDK 是否就绪。

### 2. Android 真机验收

现象：环境无 Android 设备；模拟器路径同样不可用——宿主无 `/dev/kvm`、CPU 无 `vmx`/`svm`，SDK 未安装 `emulator` 与任何 system-image，且根分区仅约 0.8GB 可用、可用内存约 1GB，x86_64 镜像无 KVM 无法加速、纯软件 TCG 在 1GB 内存下基本无法 boot。因此 `android/` 的原生与 Kotlin 改动只能静态核对（已完成的静态项见上）。

待验证项：`flutter_secure_storage` 的 `AndroidOptions(encryptedSharedPreferences: true)` 在设备 KeyStore 上可用；`android:usesCleartextTraffic="true"` 能连到用户自建的明文 HTTP 后端；会话恢复（refresh 验证）与「清除本地会话」在真机可用。

解除条件：接入设备或模拟器。

### 3. Windows 构建与运行

现象：Windows 目标无法在 Linux 上构建。

待验证项：`flutter build windows` 产物可启动；`Runner.rc` 版本资源（`FileDescription`、`ProductName`、`OriginalFilename`）正确写入产物；Windows Credential Manager 上的安全存储可用。

解除条件：Windows 主机加 VS Build Tools 与 Flutter SDK。

### 4. 真实 Provider 与 LLM 联调（LLM 部分已完成）

2026-09-24 用真实 SiliconFlow 凭据对本地后端实跑，以下链路已通：

| 链路 | 结果 |
|---|---|
| Key 有效性 | `GET /v1/models` 200，98 个模型 |
| 角色模型可用性 | 5 个 agent 角色模型全部 200：`Qwen/Qwen3-8B`、`deepseek-ai/DeepSeek-R1-0528-Qwen3-8B`、`Qwen/Qwen3.5-4B`、`THUDM/GLM-Z1-9B-0414`（以及 `deepseek-ai/DeepSeek-V4-Flash`） |
| 后端 chat 非流式 | `POST /api/v1/chat` → 200，真实返回「1+1 等于2。」 |
| 后端 chat 流式 | `stream:true` → 200，真实 SSE chunk，`model=Qwen/Qwen2.5-7B-Instruct` |
| Provider 提交 | `GET /api/v1/public-key` → RSA-OAEP/SHA-256 加密 → `POST /api/v1/agent/apikey` → 200「API Key 提交成功」 |
| Provider 测试连接 | `POST /api/v1/agent/apikey/test` → 200 `{success:true, message:"连接成功"}`，与客户端「测试连接」按钮同路径 |

复现方式：`DATABASE_URL=sqlite+aiosqlite:////tmp/opencode/llm_test.db ENV=development SILICONFLOW_API_KEY=<key> python3 -m uvicorn app.main:app --port 8000`，注册/登录后调上述端点。Provider 提交与测试连接依赖 Redis（未起时提交返回 403），需先 `redis-server --port 6379 --save '' --appendonly no --maxmemory 128mb`。

`/api/v1/agent/orchestrate/stream` 端到端已实跑两次（2026-09-24，真实 SiliconFlow 凭据）。

第一次（Python 需求，session `llm-e2e-1790257115`）：SSE 传输层全通，收到 `pipeline_mode`、`progress`、`step_detail`、`thinking`（1753 条）、`heartbeat`（135 条）、`critical_decisions` 与 `error` 各 1 条；`.dep_graph.json` 已落盘（20 文件节点），但生成在依赖图校验阶段中断，`error` 为 `unknown file types were not inferred: vue.py`，无源码产出。

第二次（纯静态站需求，session `llm-static-1790262394`）跑到 `done`，`success=true`：4/4 文件生成成功（`src/index.html`、`src/style.css`、`src/app.js`、`app/command.py`），项目级沙箱验证通过，交叉验证在两版之间选定 A 版。收到的事件类型覆盖 `pipeline_mode`、`progress`(28)、`step_detail`(2)、`thinking`(1867)、`heartbeat`(85)、`model_info`(4)、`file`(4)、`critical_decisions`(1)、`validation_results`(1)、`cost_update`(1)、`performance_metrics`(1)、`done`(1)。`done` 载荷带 `project_path="1/llm-static-1790262394"`、`session_id`、`files`、`validation`、`cost`、`performance` 等 23 个字段，正是客户端 `WorkbenchState.projectPath` 与文件页所依赖的形状。

客户端下游接口对同一真实项目实测通过：`GET /api/v1/agent/generate/files` 返回 4 个文件；`GET /api/v1/agent/generate/read` 返回文件正文；`GET /api/v1/agent/generate/download/1/llm-static-1790262394` 返回 200、3544 字节的合法 zip（`testzip()` 通过）。生成完成后 `agent_home_view.dart:133` 用 `projectPath` 打开文件页的链路完整。

两次运行差异说明（对验收有用）：Python 那次之所以中断，是因为 Architect 模型（`Qwen/Qwen3-8B`）对「hello world」需求幻觉出含 `vue.py` 的 Web 架构，而 `.py` 在 `EXTENSION_TYPE_MAP` 里没有兜底。改用全部扩展名都有兜底的 `.html/.css/.js/.md` 静态站需求后即可跑到 `done`。要在当前后端上拿到 `done`，需求与产物应避开 `unknown` 类型的文件。

仍待验证：GitHub 配置、`/api/v1/github/save` 与仓库分支提交读取（需真实 GitHub Token）。

磁盘守卫：该端点可用空间 <1GB 或可用率 <10% 直接返回 507（`app/utils/guardrails.py:250`），且写 `./projects`。2026-09-25 删除 `/workspace/flutter_client/build/app/intermediates`、`/workspace/flutter_client/build/test_cache`、`/root/.gradle/caches`，可用空间由 788MB（96%）升到 4.5GB（24%），守卫不再返回 507（保留 `build/linux` 的 release bundle 与 `build/app/outputs` 的 APK 作为证据）。

2026-09-25 磁盘腾空后从真实 VS Code 宿主 UI 驱动完整生成，先卡在后端 Architect 契约校验，修复后端后全链路跑通到 `done`：

- 卡点现象：宿主内 UI 发送需求 2 次（Python CLI 脚本、静态网页）、后端接口直连 2 次（`engine=core` 静态网页、默认 legacy 多语言 Flask 项目）都以 `architect architecture did not include a project_spec` 失败；architect 模型 `Qwen/Qwen3-8B` 返回合法 JSON（含 `project_type`、`file_plan`、`api_spec`、`db_schema`、`dependencies`），但缺少提示词要求的 `project_spec`。
- 根因：提交 `a476327` 把「`project_spec` 缺失时用 `_build_default_project_spec` 兜底」的静默回退改成硬 `raise`（`app/agent/architect.py:364`、`:689`）。2026-09-24 同一模型仍能返回 `project_spec`（见上文 `llm-static-1790262394`），如今稳定缺失，推测与模型服务端版本更新有关。
- 修复（经用户批准跨界）：两处恢复「缺失即用空 `project_spec`（`{"default": {"terminology": {}}}`）兜底并打 `warning` 日志」，不发明框架或存储；更新两条锁定 raise 的单测为断言兜底。commit `6801118`。
- 反向验证：临时改回 `raise` 后两条新用例双双失败，恢复后通过；`tests/unit/test_orchestrator_files.py`、`test_architect_canonicalize.py`、`test_language_adapter_boilerplate.py` 共 180 passed。
- API 层复验：`POST /api/v1/agent/orchestrate/stream`（真实 SiliconFlow、legacy 引擎）跑到 `done`，`success=true`、`total_files_created=7`、`total_files_failed=0`、`project_path=1/fix-check`、`architecture_check.alignment_score=1.0`；产物 `/workspace/projects/1/fix-check/`（`index.html`、`style.css`、`app.js`、`src/index.js`、`src/utils/utils.js`、`src/models/page_model.js`、`app/command.py`）。原始流 `/tmp/opencode/fix_stream.ndjson`。
- UI 层复验：真实 VS Code 宿主内发送需求，状态由「Agent 正在处理」→「服务端等待架构决策，最多等待 120 秒」→「Agent 已完成」；`done` 回填增量提示「可增量修改：1/vscode-agent-fixtures-1790385675739」，增量复选框由禁用变可用；后端 `生成完成 files=7/0`；7 个产物落盘。截图 `/tmp/opencode/host_tabs_ui2/full-generation.png`、报告 `/tmp/opencode/host_report_ui2.json`。
- 环境前提：后端需注入 `SILICONFLOW_API_KEY`（否则 LLM 报 `Provider siliconflow is not configured`）；E2E 宿主 harness 的等待上限须大于生成耗时（原 600s 短于约 11 分钟的生成，会提前退出导致误判）。

### 5. GitHub 设置页验证状态不持久

现象：`GET /api/v1/github/config` 的 `verified` 恒为 `false`、`verification_status` 恒为 `not_performed`（`app/services/github_config_service.py`），而 `POST /api/v1/github/verify` 只返回结果、不落库（`app/api/v1/github.py:255`）。重开设置页永远显示「尚未验证」。

说明：这是后端缺陷，位于本范围之外。Flutter 客户端显示正确，无需改动。联调时若只看设置页回显会误判为客户端问题。

## 跨边界发现（本范围外，仅存档）

以下问题在核对中被确认存在，但属于后端或 Web 前端，未在本范围修复。

| 位置 | 问题 |
|---|---|
| `app/services/github_config_service.py` | `GET /config` 的 `verified` 硬编码 `false`，`POST /verify` 结果不落库 |
| `app/agent/architect.py:364`、`:689` | `project_spec` 缺失时由默认兜底改为硬失败（`a476327`），当前 `Qwen/Qwen3-8B` 稳定不返回该字段。2026-09-25 经用户批准跨界修复，恢复空兜底，详见「待验收项 4」 |
| `src/components/agent/modals/LearningModal.vue` | 读 `total_feedbacks` / `fixed_count` / `avg_fix_time` / `accuracy_improvement`，后端 `app/agent/feedback_learner.py:262` 返回 `learned_patterns` / `total_fixes_recorded` / `overall_success_rate`，导致恒显示「暂无学习数据」 |
| `src/components/agent/modals/SettingsModal.vue` | 读 `concurrentLimits.recommended` 与 `cacheStats.total_keys`，后端返回 `recommendations`（`orchestrate_endpoints.py:1940`）与 `cached_entries`（`app/agent/spec_cache.py`），导致并发与缓存两节不渲染 |
| `Makefile:71` | `clean` 调用 `./scripts/cleanup.sh`，该脚本不存在 |
| `app/main.py:197` | `allow_origin_regex=settings.ALLOWED_HOSTS.replace(",", "\|")` 未转义正则元字符 |
| `Dockerfile:23`、`:34` | 基础镜像 `python:3.10-slim`，与文档要求的 Python 3.11+ 不一致 |
| 应用挂载 | `AiProjectCode.py`、`nginx_ai.py` 未挂载 |
| `app/agent/dependency_graph.py:1208` + `app/agent/dependency_rules.py:189` | `_infer_file_type` 对 `.py` 无扩展名兜底：`EXTENSION_TYPE_MAP` 没有 `.py`（只有 `.vue`、`.js` 等），Python 适配器的 `infer_file_type` 也只在目录名/文件名命中规则时才给类型。任何非常规命名的 `.py`（`vue.py`，甚至 `hello.py`）推断为 `unknown`，`_infer_unknown_file_types` 随即 `RuntimeError` 中止整轮编排（`spec_first_generate.py:1955`） |
| `app/agent/architect.py:1341` | `_ensure_file_plan_completeness` 会把 Architect 幻觉出的模块自动补进 file_plan（上例中 Vue 风格的 `vue.py`、`app/api.py`），放大上一条的爆炸半径；角色分配中 architect 是 `Qwen/Qwen3-8B`（`data/unified_model_config.yaml:356`），它对简单 Python 需求产出了 Web 架构 |
| `app/api/v1/ai_agent/schemas.py:237,239` | `OrchestratorRequest.framework` 与 `runtime` 只在 schema 声明，`app/api/v1/ai_agent/` 全目录无消费点（`rg '\.framework|\.runtime' app/api/v1/ai_agent` 无命中），客户端也不发送。即调用方无法指定目标框架/运行时，架构完全交给模型发挥 |
| 项目打包 | `GET /api/v1/agent/generate/download/{project}` 打出的 zip 含内部文件与构建残留：本轮含 `.dep_graph.json` 与 `app/__pycache__/command.cpython-311.pyc`（校验时编译产生）。用户下载到的产物里混入平台内部文件，与 `generate/files` 列表接口的过滤行为不一致 |
| 生成覆盖率 | 静态站那次 `success=true`，但需求要求的根级 `index.html` 与 `README.md` 未按约产出（实际把 `index.html` 放进 `src/`，且完全没有 README），反而多出需求未提的 `app/command.py`。`requirement_coverage` 未据此判失败，属模型质量与覆盖校验缺口 |
| `app/api/v1/ai_agent/orchestrate_endpoints.py:1855` | 快照接口在 `orchestrator/{session_id}` 或 `user_uploads/{session_id}` 下找项目目录，而编排实际写入 `projects/{user_id}/{session_id}`（`done` 载荷 `project_path="1/llm-static-1790262394"`，落盘 `projects/1/llm-static-1790262394`）。实测 `GET /api/v1/agent/snapshots/llm-static-1790262394` 返回 404「项目目录不存在」。叠加编排产物未初始化 git 仓库（该目录无 `.git`），插件「文件版本」tab 对任何真实生成会话都不可用；`/rollback`（`:1878`）、`/snapshot/diff`（`:1905`）同样按错误路径查找 |

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
