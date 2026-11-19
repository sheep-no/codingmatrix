# Provider 故障矩阵

统一约定：所有供应商失败都应保留 `provider`、`model`、`status_code`、`attempt`、`latency_ms`，认证类失败额外带 `error_code=LLM_AUTH_FAILED`，限流类失败带 `retry_after`。

| 场景 | 预期行为 | 错误码 / 异常 | 重试策略 | 现有覆盖 |
|---|---|---|---|---|
| 非流式 401/403 | 立即失败，提示检查 Key | `LLMCallError(code=LLM_AUTH_FAILED)` | 不重试 | `test_llm_caller_branches.py::test_auth_status_wrapped_as_fatal`；403 由本矩阵新增 |
| 非流式 429 | 释放信号量，按 `Retry-After` 冷却后重试 | `LLMCallError(status_code=429, code=LLM_RATE_LIMITED)` | 最多 3 次，冷却 15 到 60 秒 | `test_llm_rate_limit.py` |
| 非流式 5xx | 指数退避后重试，仍失败则抛出最后一错 | `LLMCallError(status_code=5xx)` | 1/2/4 秒；503 为 3/6/12 秒 | `test_aicloud_http_client_branches.py::TestCallWithRetry` |
| 非流式超时 / 连接错误 | 指数退避后重试 | `httpx.TimeoutException` / `httpx.HTTPError` | 最多 3 次 | `TestCallWithRetry` |
| 流式非 200 | 不产出任何 chunk，读取错误体后抛错 | `LLMCallError` | 429 可重试，其余不重试 | `test_aicloud_adapter_regressions.py::test_official_adapter_stream_raises_on_non_200` |
| 流式首 chunk 前 429 | 关闭迭代器，冷却后重新发起 | `LLMCallError(status_code=429, code=LLM_RATE_LIMITED)` | 最多 3 次 | `test_llm_rate_limit.py::test_stream_429_waits_retry_after_seconds`；SiliconFlow 形态由本矩阵新增 |
| 流式首 chunk 前连接失败 / 超时 | 尚无输出，释放信号量后重新发起 | `httpx.TransportError`（包装后按 `__cause__` 识别） | 1s、2s 退避，最多 3 次 | `test_provider_stream_fault_injection.py`；本矩阵新增 |
| 流式中途断连 | 已产出 chunk 保持已交付，错误继续上抛 | `读取响应失败` / `服务器断开连接` | 不重试，避免重复输出 | 适配器层已有；首 chunk 后断连由本矩阵新增 |
| 流式 5xx | 立即上抛，不重试 | `httpx.HTTPStatusError` | 不重试 | 本矩阵新增 |
| 错误体过大 | 只保留前 500 字符 | 同流式非 200 | 同左 | 本矩阵新增 |
| 错误体读取失败 | 仍抛出状态错误，body 为空 | `httpx.HTTPStatusError` | 同左 | 本矩阵新增 |
| 200 但空流 | 视为成功的空输出，累计 `empty_stream_total` 并打 WARNING | 无 | 无 | 本矩阵新增 |

## 统一约定

- 所有适配器的非 200 响应统一抛 `app.utils.aicloud.errors.LLMCallError`，携带 `status_code`、稳定 `code` 和可选的 `retry_after`。
- `llm_caller.call_llm` 对遗留的 `HTTPException`、`httpx.HTTPStatusError` 和带 `status_code` 的异常做最后归一化，公共调用方只需处理 `LLMCallError`。
- 流式传输错误只在首个 chunk 交付前重试；一旦有 chunk 交付就停止重试，避免重复输出。
- 空流保留成功语义，通过 `get_empty_stream_stats()` 和 `empty_stream` 日志观测；连续增长时再评估升级为错误。

## 新增回归

`tests/unit/test_provider_fault_matrix.py` 固化以下缺口：403 致命映射、SiliconFlow 429 可重试、首 chunk 前传输错误重试、首 chunk 后断连不重试、流式 5xx 不重试、错误体截断、错误体读取失败、429 元数据归一化、空流计数与告警。

`tests/integration/test_provider_stream_fault_injection.py` 通过本地真实 HTTP 服务注入 429 与中断连接，验证真实 `httpx` 流读取下的重试与不重试边界。
