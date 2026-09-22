# llm_client.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：Agent 引擎 / 统一 LLM 调用层（B5 并发控制 + 成本追踪）
> 路径：`app/agent/llm_client.py`（397 行）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**统一 LLM 调用层**——封装顶层 `app.utils.call_llm`，添加并发控制、超时保护、成本追踪、动态路由器性能记录。

| 类 / 函数 | 位置 | 功能 |
|-----------|------|------|
| `get_global_semaphore` | :35-39 | 全局并发信号量（MAX_CONCURRENT_LLM_CALLS=6） |
| `get_model_semaphore` | :42-46 | 按模型并发信号量（MAX_CONCURRENT_PER_MODEL=2） |
| `LLMClientError` | :49-51 | 不可恢复错误（401/403/超时/通用失败） |
| `LLMClient.__init__` | :67-90 | model_config 来自 LayeredModelRouter；disable_fallback 来自 apikey_manager |
| `LLMClient.call` | :106-121 | 非流式调用（`_call_internal`，stream 参数忽略） |
| `LLMClient.call_stream` | :123-186 | 流式调用（`_consume_stream`，逐 token 回调） |
| `_consume_stream` | :188-287 | SSE chunk 消费（content/reasoning 分离 + usage 捕获） |
| `_record_usage` | :289-302 | 成本追踪（prompt/completion tokens × cost 单价） |
| `_call_internal` | :304-385 | 非流式核心（双信号量 + wait_for + 动态路由记录） |

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖（import）

- `app.utils`（:21）：`call_llm`（顶层体系，返回 OpenAI dict）
- `app.agent.dynamic_model_router`（:22）：`get_dynamic_router`（性能记录）/ `LayeredModelRouter.get_model_config`（模型配置）
- `app.services.apikey_manager`（运行时 :97）：降级链偏好检查
- 常量：MAX_CONCURRENT_LLM_CALLS=6 / MAX_CONCURRENT_PER_MODEL=2（:29-30 硬编码）

### 2.2 被消费方

| 使用方 | 位置 | 说明 |
|--------|------|------|
| `specialist_base.py:48` | 主路径 | Specialist 全体系的 LLM 客户端（每实例构造） |
| `spec_first_generate.py:1586` | 修复闭环 | 一处构造 |
| incremental_generate.py / orchestrator_files.py | 仅注释 | 提及「由 LLMClient 内部信号量控制并发度」 |

> **§10.1 关联**：26 个文件绕过 LLMClient 直连 call_llm——「统一层」实际使用面窄（主路径 specialist_base + spec_first 一处），并发控制仅在这些路径生效。

### 2.3 测试覆盖

- test_llm_client.py：**14 passed**——覆盖 call 成功/超时/认证/通用错误/成本/空 choices、信号量单例。**未覆盖**：流式路径、信号量获取顺序（LC2）、成本键缺失（LC1）、流式 usage（LC4）

## 3. 已探明 Bug（含 bug 代码）

### LC1 [P1] 成本追踪恒记 0 成本：model_config 无 cost 字段，`.get(..., 0.0)` 兜底

- **Bug 代码**（跨模块两处）：

```python
# llm_client.py:295-296 - _record_usage 期望 cost 字段
cost_per_1m_input = self._model_config.get("cost_per_1m_input", 0.0)
cost_per_1m_output = self._model_config.get("cost_per_1m_output", 0.0)

# dynamic_model_router.py:1022-1027 - get_model_config 返回仅 5 键，无 cost 字段
return {
    "temperature": ..., "max_tokens": ..., "thinking_budget": ...,
    "context_length": ctx_len, "timeout": ...,
}
```

- **根因**：`get_model_config`（dynamic_model_router.py:974-1027）返回 5 键，**无 `cost_per_1m_input`/`cost_per_1m_output`**；`_record_usage` 用 `.get(..., 0.0)` 兜底 → **cost_usd 恒 0** → `cost_tracker.add_usage(..., cost_usd=0)`
- **影响**：成本追踪形同虚设（走 LLMClient 的路径：specialist_base 主路径 + spec_first）
- **交叉回注（2026-08-09，orchestrator_progress.md OP1 实测确认）**：实测 `get_model_config("Qwen/Qwen3.5-4B")` 返回 dict 无成本键、`CostTracker.add_usage(1000+2000 token)` 后 `total_cost_usd` 恒 0.0（token 计数正确、金额恒零）。**新信息**：model_registry.py 的 `ln`（每百万输入 token 成本，元）字段存在但从未接入 llm_client，是现成的修复数据源。
- **触发条件**：任何带 cost_tracker 的 LLMClient 调用（test_call_with_cost_tracker :188 未断言 cost>0，故 14 passed 未暴露）

- **已修复（2026-09-22，含 LC1 与题面所述 `ln` 字段）**：`app/agent/dynamic_model_router.py` 的 `get_model_config` 末尾新增成本单价解析——按解析后的 `model_id` 从 `MODEL_REGISTRY`（唯一数据源，YAML 无 cost 字段）读取 `cost_per_1m_input`/`cost_per_1m_output`，并在返回 dict 追加同名字段（注册表缺失时兜底 `0.0`，动态/自定义供应商模型仍为 0）。`LLMClient._record_usage` 无需改动，`.get(..., 0.0)` 现在能取到真实单价 → `cost_usd` 与 `CostTracker.total_cost_usd` 正确累计。
- **测试**：`tests/unit/test_llm_client.py` 新增 2 项——`test_model_config_exposes_cost_rates`（真实模型配置暴露非零单价）、`test_record_usage_uses_registry_cost`（以 `deepseek-r1` 百万输入/输出 token 断言 `total_cost_usd == cost_in + cost_out`）；原文件 17 → 19 passed。

### LC2 [P1] 信号量获取顺序「全局→按模型」：全局槽被等待者占用 → 跨模型饿死

- **Bug 代码**：

```python
# llm_client.py:223-224（_call_internal 同构 :344-345）
await self._semaphore.acquire()        # 全局（6）
await self._model_semaphore.acquire()  # 按模型（2）
```

- **根因**：先占全局槽再等模型槽——模型 X 信号量满时，X 的等待任务**持有全局槽**等待模型信号量 → 全局 6 槽被 X 的等待者占满 → 其它模型请求全部饿死（优先级倒置）
- **建议**：先按模型后全局（`await model_sem.acquire()` → `await global_sem.acquire()`），等待模型槽时不占全局槽

- **已修复（2026-09-22）**：`call_stream` 与 `_call_internal` 两处嵌套顺序改为「先按模型后全局」——`async with self._model_semaphore: async with self._semaphore:`。等待模型额度时不再占用全局槽，某模型队列积压不再饿死其它模型。两处顺序一致，不存在反向加锁死锁。回归测试 `tests/unit/test_llm_client.py::TestConcurrencyOrdering` 的 2 项（非流式 + 流式）：全局 2 槽下同一模型排队时断言全局 `_value == 1`（还原旧顺序即失败为 0），并断言另一模型仍能立即开工。

### LC3 [P1] 流式消费循环无超时：wait_for 只覆盖获取迭代器阶段

- **Bug 代码**：

```python
# llm_client.py:226 - 超时只保护「获取 stream_iter」阶段
stream_iter = await asyncio.wait_for(_do_call_stream(), timeout=call_timeout)
...
# llm_client.py:241-286 - 之后的消费循环无超时保护
async for chunk_str in stream_iter:
    ...
```

- **根因**：`call_timeout` 仅覆盖首包获取（:226）；`async for` 消费循环（:241）在 LLM 流中途挂起时**无限等待**
- **影响**：流式调用（call_stream）在长生成或连接半开时无超时兜底

- **已修复（2026-09-22）**：`_consume_stream` 的消费循环由 `async for` 改为显式 `iterator.__anext__()` 并用 `asyncio.wait_for(..., timeout=call_timeout)` 逐块施加**空闲超时**。用逐块而非整体超时：连接半开/上游无响应会在「无下一个 chunk」时超时抛 `asyncio.TimeoutError`，由 `call_stream` 既有分支转成 `LLMClientError("LLM 流式调用超时...")`；而持续产出数据的长文本生成即使总时长超过 `timeout` 也不会被截断。回归测试 `tests/unit/test_llm_client.py::TestConcurrencyOrdering` 的 2 项（中途挂起超时、慢速但有进展不被截断）。

### LC4 [P2] 流式 usage 依赖末尾 chunk：cost 记录常缺失（叠加 LC1）

- **Bug 代码**：

```python
# llm_client.py:279-286 - usage 仅当 chunk 带 usage 才捕获
if chunk.get("usage"):
    last_meta = chunk
...
"usage": last_meta.get("usage", {}),   # 末尾无 usage chunk → 空
```

- **影响**：流式末尾 usage chunk 缺失（常见实现）→ usage={} → `_record_usage` 跳过 → **流式调用完全无成本记录**（即使 LC1 修复后）

- **已修复（2026-09-22，根因修正）**：消费侧 `_consume_stream` 早已对 usage-only chunk 兜底（`if not choices: ... if chunk.get("usage"): last_meta = chunk`），真正的缺口在**请求侧**——流式请求从未携带 `stream_options.include_usage`，OpenAI 兼容服务端默认不在流中返回 usage，故末尾无 usage chunk 可捕。修复落在平台模型唯一适配器 `app/utils/aicloud/adapters/siliconflow.py`：流式 payload 追加 `stream_options = {"include_usage": True}`；新增 `_StreamRequestError(status_code, body)` 使非 200 流式响应带上状态码，`generate()` 包一层——若回包 400 且 body 提及 `stream_options`，置 `self._stream_usage_supported = False` 并去掉该键重试一次（此后不再发送），否则按 `HTTP {status}: {body}` 抛出。回归测试 `tests/unit/test_aicloud_adapter_regressions.py` 新增 2 项（流式请求带 `include_usage`、400 回退重试并记忆），`tests/unit/test_llm_client.py` 新增 1 项（usage-only chunk 经 `_record_usage` 计入 `CostTracker.total_cost_usd`，用 `prompt=1M`/`completion=1M` × 单价 1.0/2.0 断言 3.0）

### LC5 [P2] 信号量泄漏：第二个 acquire 被取消时第一个槽不释放

- **Bug 代码**：

```python
# llm_client.py:223-224 - acquire 在 try/finally 之外
await self._semaphore.acquire()
await self._model_semaphore.acquire()   # 若此步被取消 → 全局槽永久泄漏
try:
    ...
finally:
    self._model_semaphore.release()
    self._semaphore.release()
```

- **根因**：两个 acquire 均在 try 外；第二个 acquire 抛 CancelledError 时第一个已获取的槽永不释放（re-act 循环取消场景）
- **建议**：`async with` 或 try 包裹两组 acquire

- **已核实为已修复（2026-09-22）**：原 Bug 代码片段（try 外手工 `acquire`）已不存在于当前实现。`call_stream`（llm_client.py:193）与 `_call_internal`（:430）均使用 `async with` 嵌套上下文，等待内层额度时被取消会由 `async with` 正常释放外层额度，不存在槽泄漏。本条为文档滞后，非新增改动。

### LC6 [P2] `call(stream=True)` 参数被静默忽略

- **Bug 代码**：:121 `_call_internal(..., stream=stream, ...)`，docstring :314「stream 参数被接受但忽略」——调用方传 `stream=True` 拿到非流式结果，无告警

### LC7 [P2] `thinking_budget` 直接下标 vs property 用 `.get` 不一致

- **Bug 代码**：:199/:319 `self._model_config["thinking_budget"]` 直接下标（缺键 KeyError）；:397 property 用 `.get("thinking_budget", 0)`（有默认）——契约脆弱（当前 get_model_config 保证有键）

### LC8 [P2] 模型信号量 dict 无界增长

- **Bug 代码**：:44-46 `_model_semaphores[model_name] = asyncio.Semaphore(...)`——模块级 dict 每个新模型名永久加一个 Semaphore，无清理机制

## 4. 潜在问题与未知点

- **§10.1 关联**：26 文件直连 call_llm（绕过本层）——LC1/LC2 的并发与成本控制只对 specialist_base 主路径生效，直连路径无并发控制
- `call_stream` 的 `start_call`/`record_call`（:149/:156）与 `_call_internal`（:317/:357）各自独立，无复用
- `_check_disable_fallback`（:92-104）每次构造查一次 apikey_manager（DB/缓存开销），无缓存
- 错误信息统一 `LLMClientError`（除 401/403 外），调用方无法区分超时/网络/模型失败

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P1 | LC1：get_model_config 补 cost_per_1m_input/output 字段（或 _record_usage 从全局成本表查） | 成本追踪真实有效 | dynamic_model_router.py:1022 / llm_client.py:295 | 新增 |
| 2 | P1 | ~~LC2：信号量获取顺序改为「先按模型后全局」~~ 已修 | 消除跨模型饿死 | llm_client.py:193/:430 | 新增 |
| 3 | P1 | ~~LC3：流式消费循环加 wait_for 超时~~ 已修 | 流式调用超时可控 | llm_client.py:292-298 | 新增 |
| 4 | P2 | LC4：流式结束后用 usage-only chunk 补记 | 流式成本记录 | llm_client.py:258-260/:283 | 新增 |
| 5 | P2 | ~~LC5：`async with` 或 try 包裹双 acquire~~ 经核实已由 `async with` 嵌套满足 | 杜绝信号量泄漏 | llm_client.py:193/:430 | 新增 |
| 6 | P2 | LC6：call 的 stream 参数改为抛错或移除 | API 语义清晰 | llm_client.py:121 | 新增 |
| 7 | P2 | LC7：统一下标访问方式 | 契约一致 | llm_client.py:199/:319/:397 | 新增 |

## 6. 演化方向关联

- **§10.1（26 文件直连）**：LLMClient「统一层」名不副实——LC1-LC3 修复受益面有限，阶段二收敛时应扩大本层使用面（#12）
- **B5 并发控制**：LC2 已修、LC5 经核实已满足；LC6/LC7 待评估
- **Backlog 关联**：#12，新增 LC1-LC7
