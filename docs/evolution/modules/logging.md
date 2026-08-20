# logging.py + structured_logging.py 日志双轨

> 第一百二十四轮补扫 | v1.125 | 2026-08-17 | 分析对象：`app/utils/logging.py`（238 行，JsonFormatter + RequestLoggingMiddleware）+ `app/utils/structured_logging.py`（171 行，StructuredLogger + RequestContextLogger）
>
> 结论：**日志双轨——两模块提供三套 JSON 日志工具（JsonFormatter / StructuredLogger / RequestContextLogger）+ app/core/logging_config.py 标准 handler 配置——格式互不兼容，且 JSON 字符串被当消息二次序列化导致日志不可检索**。

## 一、模块定位

| 组件 | 位置 | 格式特征 |
|------|------|----------|
| JsonFormatter | logging.py:58 | timestamp/level/service/logger/module/function/line + request_id/user_id |
| RequestLoggingMiddleware | logging.py:126 | 纯 ASGI 中间件（注释解释了不用 BaseHTTPMiddleware 的原因） |
| StructuredLogger | structured_logging.py:31 | timestamp/level/logger/message + request_id |
| RequestContextLogger | structured_logging.py:94 | timestamp/message + request_id + context |

## 二、缺陷清单

### P2（3 项）

- **LOG1 [P2] 请求日志把完整 query_params 写入日志——敏感查询参数落盘**——logging.py:168 `"query_params": _parse_query(query_string)` + :215-220 结束日志——**URL 查询串含 token/api_key/email 等敏感参数时全文写入日志文件**——日志轮转保留期间敏感数据长期落盘（配合 :174-181 响应头注入 request_id 可串关联）。修复方向：敏感键（token/password/secret/api_key/code）值脱敏打码。
- **SLG1 [P2] `json.dumps` 结果作为日志消息二次序列化——嵌套 JSON 字符串日志不可检索**——structured_logging.py:76 `self.logger.log(level, json.dumps(formatted))`、RequestContextLogger :120 同——msg 是 JSON 字符串——logger 配置的 handler formatter（JsonFormatter/logging_config）**再把字符串当 message 字段包一层**——输出 `{"message": "{\"timestamp\":...}"}`——**日志检索/解析工具（ES/文本搜索）无法解析嵌套字符串化 JSON**——结构化日志名存实亡。修复方向：改用 `logger.log(level, msg, extra=...)` + handler 层统一 formatter。
- **SLG2 [P2] 三套日志工具并存——JSON 格式互不兼容——统一检索困难**——logging.py（9 字段含 service/function/line）vs StructuredLogger（4 字段）vs RequestContextLogger（3 字段）+ logging_config.py 标准 handler——同一服务日志三种 schema——检索/告警规则需适配多种格式。修复方向：统一到一套结构化格式（extra 注入 + 单一 formatter）。

### P3（4 项）

- **LOG2 [P3] RequestLoggingMiddleware 手动构造 LogRecord + 直接调用 JsonFormatter——绕过 logger 的 handler/filter 链路**——logging.py:205-227——logger.error(JsonFormatter().format(record))——**字符串直接作 msg**——若 logger 已配置其他 handler（文件/安全审计）→ 该日志不按配置 formatter 输出（嵌套问题同 SLG1）；手动 LogRecord 绕过 filter。修复方向：`self.logger.log(level, "请求结束", extra={"extra_data": {...}})`。
- **LOG3 [P3] `log_error` 同样直接 `logger.error(formatter.format(record))`——双层序列化**——logging.py:104-123——与 LOG2/SLG1 同族。
- **LOG4 [P3] RequestLoggingMiddleware 只 set request_id 不 set user_id——日志 user_id 字段恒空**——logging.py:152 `set_request_context(request_id)`（未传 user_id）——:77-79 `get_user_id()` 恒 None——user_id 追踪字段形同虚设。修复方向：认证后注入 user_id。
- **SLG3 [P3] `datetime.utcnow()` 弃用（Python 3.12+）**——structured_logging.py:48/:109（与 security_audit SA3 同族）。

## 三、全库交叉确认

- **日志安全家族**：LOG1（敏感参数落盘）与 security_audit（登录事件）、guardrails（输入净化）同属敏感数据日志链——**当前日志体系无脱敏层**。
- **双轨模式**：SLG2 三套日志工具与加密双轨（crypto/encryption）、缓存双轨（cached/cache_response）、错误码双轨（error_codes）同族——**本库「同类多实现」已是系统性模式**（第八处双轨以上）。
- **日志链路一致性**：RequestLoggingMiddleware 用 get_json_logger（独立 StreamHandler），业务 logger 用 logging_config 配置——**中间件日志与业务日志走不同 handler 链**——同请求日志分散两处。

## 四、测试状态

零单元测试。LOG1 敏感参数落盘、SLG1 嵌套 JSON、SLG2 格式不一致均无测试约束。修复建议：① 敏感参数脱敏测试（token/api_key 值打码断言）；② JSON 日志单层解析测试（message 字段为纯文本）；③ request_id 全链路串联测试；④ user_id 注入测试。
