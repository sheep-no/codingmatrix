# 客户端修复与后端待办（2026-11-17）

本轮客户端共修复 5 个缺陷并解决 1 个构建阻塞，全部通过 PR 合入 `master`。后端问题只做定位与记录，未修改任何 `app/` 代码。

## 客户端已修复

| 编号 | 问题 | 处理 | PR |
| --- | --- | --- | --- |
| F1 | 模型服务未配置时页面无引导 | 新增 `modelServiceStatusProvider` 双探测，聊天、Agent 首页、虚拟女仆、动态 Provider 页接入提示 | #454 |
| F2 | Provider 授权失败只显示笼统错误 | 新增 `failure_text` 解析错误信封，透出根因并提示 Redis 不可用 | #455 |
| F3 | 工作流流式响应 gzip 错标、导入非法 JSON 无提示 | 请求声明 `Accept-Encoding: identity`；导入弹窗本地校验并保留输入 | #456 |
| F4 | Agent 统计弹窗错误被硬截断、实体未解码 | 四卡片布局，错误摘要可展开，解码 HTML 实体并兼容未知字段 | #457 |
| F5 | 并发限制输入 0 静默失败 | 弹窗内校验角色与正整数，失败保留输入，成功后才关闭 | #457 |
| F6 | release APK 构建 Java heap OOM | Gradle 堆上限 1G 提到 2G，`.gitignore` 覆盖本地 build 软链 | #458 |

验证记录：`flutter analyze` 无告警；全量 `flutter test` 532 passed / 3 skipped；`flutter build apk --release --target-platform android-x64` 成功产出 17.3MB。

## 后端待处理

### B1 apikey 接口强依赖 Redis，缺失时返回 500/403

`app/api/v1/apikey.py:320` 在读取失败时返回 500「获取 Key 列表失败」，`:230` 在写入失败时返回 403「Key 存储失败」。两种响应都把存储不可用与业务失败混在一起，客户端只能靠文案判断。

建议：Redis 不可用时统一返回 503，`details.reason` 标记 `storage_unavailable`，与鉴权类 403 区分。

### B2 GZipMiddleware 压缩 NDJSON 流并错误标记 Content-Encoding

`app/main.py:251` 全局启用 `GZipMiddleware(minimum_size=500)`，`/api/v1/workflow/execute` 的 NDJSON 流被标记为 `Content-Encoding: gzip`，但响应体是明文，客户端解压抛 `FormatException` 后表现为连接中断。

建议：对流式响应排除压缩，至少覆盖 `application/x-ndjson` 与 `text/event-stream`。客户端已用 `Accept-Encoding: identity` 规避。

### B3 并发限制契约缺少上限与取值范围说明

`app/api/v1/ai_agent/orchestrate_endpoints.py:2128` 只校验 `new_limit >= 1`，其余取值直接写库。客户端已本地拦截 0、负数和非数字。

建议：补充上限校验与错误文案，或在接口文档中明确取值范围。

### B4 top_errors 保存原始实体与超长文本

`app/agent/feedback_learner.py:247-262` 返回的 `error_message` 可能包含 `&#10;` 等 HTML 实体，长度可达 1658 字符。客户端已做实体解码、摘要折叠和长度裁剪。

建议：落库前归一化换行与实体，并限制单条长度，避免把展示层问题留给每个客户端。
