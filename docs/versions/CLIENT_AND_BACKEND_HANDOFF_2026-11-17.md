# 客户端修复与后端待办（2026-11-17）

本轮客户端共修复 5 个缺陷并解决 1 个构建阻塞；后端四项问题已由 `6d925c19` 修复，客户端补了一处兼容解析。全部通过 PR 合入 `master`。

## 客户端已修复

| 编号 | 问题 | 处理 | PR |
| --- | --- | --- | --- |
| F1 | 模型服务未配置时页面无引导 | 新增 `modelServiceStatusProvider` 双探测，聊天、Agent 首页、虚拟女仆、动态 Provider 页接入提示 | #454 |
| F2 | Provider 授权失败只显示笼统错误 | 新增 `failure_text` 解析错误信封，透出根因并提示 Redis 不可用 | #455 |
| F3 | 工作流流式响应 gzip 错标、导入非法 JSON 无提示 | 请求声明 `Accept-Encoding: identity`；导入弹窗本地校验并保留输入 | #456 |
| F4 | Agent 统计弹窗错误被硬截断、实体未解码 | 四卡片布局，错误摘要可展开，解码 HTML 实体并兼容未知字段 | #457 |
| F5 | 并发限制输入 0 静默失败 | 弹窗内校验角色与正整数，失败保留输入，成功后才关闭 | #457 |
| F6 | release APK 构建 Java heap OOM | Gradle 堆上限 1G 提到 2G，`.gitignore` 覆盖本地 build 软链 | #458 |
| F7 | 后端 503 的字典 detail 被展示成 Python repr | 解析嵌套 detail 与 repr 中的 message | #461 |

验证记录：`flutter analyze` 无告警；全量 `flutter test` 532 passed / 3 skipped；`flutter build apk --release --target-platform android-x64` 成功产出 17.3MB。

## 后端待处理

### B1 apikey 存储故障返回 503（已修复）

`app/api/v1/apikey.py` 现在把 Redis 与网络故障统一映射为 503「Key 存储服务暂不可用」，并带 `Retry-After: 5`。

遗留：全局异常处理 `app/utils/error_handler.py:117` 用 `str(detail)` 处理字典，响应 message 变成 Python repr；`:121` 只透传 429 的 `Retry-After`，503 的该头部会被丢掉。客户端 #461 已兼容解析 repr 中的 message，建议后端把 `code` 与 `message` 平铺到信封，并在 503 分支保留 `Retry-After`。

### B2 GZipMiddleware 压缩 NDJSON 流（已修复）

`app/main.py` 把 `application/x-ndjson` 加入 `DEFAULT_EXCLUDED_CONTENT_TYPES`。线上复测：响应不再带 `Content-Encoding`，响应体为可直接解析的明文 NDJSON；客户端 `Accept-Encoding: identity` 可继续保留。

### B3 并发限制缺少上限校验（已修复）

`app/api/v1/ai_agent/orchestrate_endpoints.py:2135` 增加 `MAX_LIMIT = 100` 上限，超过返回 400「限制值不能超过 100」。客户端本地校验保持不变。

### B4 top_errors 保存原始实体与超长文本（已修复）

`app/agent/feedback_learner.py` 落库前用 `_sanitize_error_message` 解码 HTML 实体、折叠空白并限制 200 字符。线上复测 `top_errors` 最长 200 字符，未再出现 `&#10;`。
