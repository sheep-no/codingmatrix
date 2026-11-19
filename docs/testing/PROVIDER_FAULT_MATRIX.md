# Provider 故障矩阵

统一约定：所有供应商失败都应保留 `provider`、`model`、`status_code`、`attempt`、`latency_ms`，认证类失败额外带 `error_code=LLM_AUTH_FAILED`，限流类失败带 `retry_after`。

| 场景 | 预期行为 | 错误码 / 异常 | 重试策略 | 现有覆盖 |
|---|---|---|---|---|
| 非流式 401/403 | 立即失败，提示检查 Key | `LLM_AUTH_FAILED` | 不重试 | `test_llm_caller_branches.py::test_auth_status_wrapped_as_fatal`；403 由本矩阵新增 |
| 非流式 429 | 释放信号量，按 `Retry-After` 冷却后重试 | `LLMCallError(status_code=429)` | 最多 3 次，冷却 15 到 60 秒 | `test_llm_rate_limit.py` |
| 非流式 5xx | 指数退避后重试，仍失败则抛出最后一错 | `httpx.HTTPStatusError` | 1/2/4 秒；503 为 3/6/12 秒 | `test_aicloud_http_client_branches.py::TestCallWithRetry` |
| 非流式超时 / 连接错误 | 指数退避后重试 | `httpx.TimeoutException` / `httpx.HTTPError` | 最多 3 次 | `TestCallWithRetry` |
| 流式非 200 | 不产出任何 chunk，读取错误体后抛错 | `httpx.HTTPStatusError`（官方适配器）或带 `status_code` 的异常（SiliconFlow） | 429 可重试，其余不重试 | `test_aicloud_adapter_regressions.py::test_official_adapter_stream_raises_on_non_200` |
| 流式首 chunk 前 429 | 关闭迭代器，冷却后重新发起 | `LLMCallError(status_code=429)` | 最多 3 次 | `test_llm_rate_limit.py::test_stream_429_waits_retry_after_seconds`；SiliconFlow 形态由本矩阵新增 |
| 流式中途断连 | 已产出 chunk 保持已交付，错误继续上抛 | `读取响应失败` / `服务器断开连接` | 不重试，避免重复输出 | 适配器层已有；首 chunk 后断连由本矩阵新增 |
| 流式 5xx | 立即上抛，不重试 | `httpx.HTTPStatusError` | 不重试 | 本矩阵新增 |
| 错误体过大 | 只保留前 500 字符 | 同流式非 200 | 同左 | 本矩阵新增 |
| 错误体读取失败 | 仍抛出状态错误，body 为空 | `httpx.HTTPStatusError` | 同左 | 本矩阵新增 |
| 200 但空流 | 当前视为成功的空输出 | 无 | 无 | 已知风险，未固化 |

## 已知不一致

- 官方适配器流式非 200 抛 `httpx.HTTPStatusError`，SiliconFlow 抛通用 `Exception` 并附加 `status_code`。调用方依赖 `status_code` 属性判断，已通过 `_is_rate_limit_error` 兼容，后续可统一为 `LLMCallError`。
- 空流当前按成功处理，调用方无法区分「模型返回空」和「供应商提前断开」。建议后续增加空流计数与告警。

## 新增回归

`tests/unit/test_provider_fault_matrix.py` 固化以下缺口：403 致命映射、SiliconFlow 429 可重试、首 chunk 后断连、流式 5xx 不重试、错误体截断、错误体读取失败。
