# llm_caller.py 演化深扫文档

> 版本：v0.1 | 扫描日期：2026-08-05 | 状态：已完成
> 归属：顶层体系 / 多供应商模型调用系统（统一 call_llm 入口）
> 路径：`app/utils/aicloud/llm_caller.py`（438 行；`app/utils/llm_caller.py` 15 行仅重导出）
> 索引：[TASKS.md](../TASKS.md)

## 1. 模块作用与功能

核心职责：**顶层统一模型调用**——`call_llm()` 自动路由供应商、故障转移、429 重试、用户自定义 API Key、并发信号量。

| 类 / 函数 | 位置 | 功能 |
|-----------|------|------|
| `ADAPTER_FACTORIES` | :30-37 | 6 供应商适配器工厂（siliconflow/dashscope/zhipu/deepseek/openai/anthropic） |
| `_retry_on_rate_limit` | :53-80 | 429 指数退避重试（3 次，2s-30s） |
| `LLMCallError` 及子类 | :83-103 | 401 认证 / 未配置异常 |
| `get_adapter` | :113-145 | 适配器实例缓存（平台默认按 provider / 用户自定义按 provider+key-hash，LRU 上限 256） |
| `_SemaphoreWrappedAsyncIterator` | :148-176 | 流式迭代期间持有信号量，结束/异常时释放 |
| `call_llm` | :179-403 | **核心**：4 级路由（动态供应商→用户 Key→动态供应商匹配模型→系统默认+fallback）→ 429 重试 → 信号量 → 流式包装 |
| `_get_user_api_key_from_token` | :406-425 | token → Redis 用户 API Key |
| `_get_provider_base_url` | :428-438 | 供应商 base_url 映射 |

### call_llm 路由优先级（:219-299）

1. `provider_id` 直接指定动态供应商
2. `api_key_token` → Redis 取用户 Key → ProviderRouter.route(model) 内置供应商
3. 动态供应商中匹配模型（`get_by_model`）
4. 系统默认路由 + fallback 链（`disable_fallback` 时直接抛错）

## 2. 依赖与被依赖（跨模块引用链）

### 2.1 依赖（import）

- `app.core.config`（:14）：settings.get_provider_registry()
- `app.utils.aicloud.providers / provider_router / adapters.* / dynamic_provider`：供应商体系
- `app.services.apikey_manager`（运行时 :420）：token→Key
- `app.agent.llm_client`（运行时 :306，延迟导入避免循环依赖）：get_model_semaphore / get_global_semaphore

### 2.2 被消费方

- **§10.1 的 26 个直连文件**（不经 LLMClient，`_skip_semaphore` 缺省 False → 走 call_llm 自身信号量）
- `app/utils/llm_caller.py`（重导出 `call_llm`/`get_adapter`/`ADAPTER_FACTORIES`）
- LLMClient（llm_client.py:202/:323，`_skip_semaphore=True` → LLMClient 内部已持锁，**避免嵌套**）
- ReActAgent（react_agent.py:16，`app.utils.call_llm`）

### 2.3 测试覆盖

- tests/unit/test_aicloud.py：**47 passed——全部是敏感信息过滤/路径保护测试**，**call_llm 的路由/信号量/fallback/429 重试逻辑零测试覆盖**（LCL1/LCL2 未暴露）

## 3. 已探明 Bug（含 bug 代码）

### LCL1 [P0] 直连路径信号量获取「全局→按模型」+ try 外泄漏（26 直连文件受影响）

- **Bug 代码**：

```python
# llm_caller.py:313-316 - acquire 在 try(:319) 之外，顺序「全局→按模型」
if global_sem:
    await global_sem.acquire()
if model_sem:
    await model_sem.acquire()
...
# :319 try 开始
try:
    result = await _retry_on_rate_limit(...)
```

- **根因**：与 llm_client.md LC2/LC5 **同构但作用面更大**——① 先占全局槽再等模型槽（模型信号量满时等待者占全局槽，跨模型饿死）；② acquire 在 try 外，第二个 acquire 被取消时全局槽泄漏
- **影响**：§10.1 的 26 个直连文件全部走此路径（LLMClient 因 `_skip_semaphore=True` 不受影响）；叠加 llm_client 的 LC2/LC5，**信号量缺陷在两条路径均存在**
- **关联**：llm_client.md LC2/LC5

### LCL2 [P1] 流式 fallback 用错 config：user_config 是 primary 的 Key/URL → 跨供应商 fallback 必失败

- **Bug 代码**：

```python
# llm_caller.py:354-361 - fallback 循环里用 primary 的 user_config 建 fallback adapter
primary_provider = router.route(model)
fallback_providers = router.get_fallback_providers(primary_provider)
for fallback in fallback_providers:
    fallback_adapter = await get_adapter(fallback, user_config)   # ← user_config 是 primary 的
```

- **根因**：`user_config`（:241-245）是 **primary provider** 的 ProviderConfig（primary 的 api_key/base_url）；传给 fallback provider 建 adapter（如 siliconflow→deepseek）→ DeepSeekAdapter 拿 siliconflow 的 key/base_url 请求 → **必然 401/404**
- **影响**：用户 Key 场景下流式 fallback 跨供应商**全部失败**（fallback 机制形同虚设）
- **佐证**：非流式 fallback（:286 `get_adapter(fallback)` 无 config）用平台默认——正确但忽略用户 Key

### LCL3 [P1] 非流式/流式 fallback 语义不一致：一个忽略用户 Key、一个用错 Key

- 非流式 fallback（:283-292）：`get_adapter(fallback)` 平台默认 → **用户 Key 场景 fallback 用平台 Key**（Key 语义漂移）
- 流式 fallback（:361）：用错 primary 的 user_config（LCL2）
- **影响**：同一调用内 fallback 行为不一致，且都未正确处理「fallback 供应商的用户 Key」

### LCL4 [P2] 信号量日志访问私有属性 `_value` + 高频 info 日志

- **Bug 代码**：:317 `global_sem._value`——asyncio.Semaphore 私有属性跨事件循环/线程不安全；且每次调用打 info 级日志（:317/:336/:344/:346），噪声大

### LCL5 [P2] 适配器缓存：全局锁 + FIFO 淘汰（非真 LRU）

- **Bug 代码**：:139-142 超上限时 `for _ in range(half): _user_adapter_cache.pop(next(iter(...)))`——dict 插入序淘汰（FIFO），清掉一半粗暴；`_adapter_cache_lock` 全局锁（:45）无读写分离
- **影响**：热用户 Key 适配器可能被 FIFO 淘汰重建（缓存命中率低）；全局锁串行化 get_adapter

### LCL6 [P2] 429 重试对流式迭代中途的 429 无效

- `_retry_on_rate_limit`（:320）只包 adapter.call_llm 的**首包获取**；流式迭代器产生后的 429 由 adapter 内部处理（不可见）——重试仅覆盖首包前

### LCL7 [P2] fallback 触发时机不一致

- 非流式：primary **adapter 创建/路由失败**时 fallback（:275-295）
- 流式：adapter.call_llm **抛异常**时 fallback（:352-403）
- 两处触发条件不同，流式多一次「streaming 已开始后」的 fallback 尝试窗口

## 4. 潜在问题与未知点

- **信号量嵌套关系**：LLMClient 路径 `_skip_semaphore=True`（不重复），但 call_llm 的 fallback 内部（:365-376）会**重新 acquire**——fallback 路径的信号量生命周期与 _SemaphoreWrappedAsyncIterator 的释放（:164-176）需仔细核对是否泄漏
- `_get_user_api_key_from_token`（:406）每次调用查 Redis（无缓存），高频调用下 Redis 压力
- `_make_user_cache_key` 用 SHA-256 前 16 字节（:109）——碰撞概率低但非零
- 异常类型：401 认证抛 LLMCallError（UserAPIKeyNotFoundError），其余网络错误不包装直接抛原始异常——调用方（LLMClient）会再包装为 LLMClientError

## 5. 修改建议（改什么 → 达成什么目的）

| # | 优先级 | 修改动作 | 达成目的 | 涉及位置 | 对应 Backlog |
|---|--------|---------|---------|---------|-------------|
| 1 | P0 | LCL1：信号量获取「先按模型后全局」+ try/async with 包裹 | 消除跨模型饿死与泄漏（直连 26 文件） | llm_caller.py:313-316 | 新增 |
| 2 | P1 | LCL2/LCL3：fallback 按 fallback provider 重建 ProviderConfig（用户 Key 用 hash 查）或统一用平台默认 | 跨供应商 fallback 真正可用、语义一致 | llm_caller.py:354-361/:283-292 | 新增 |
| 3 | P2 | LCL4：去掉 `_value` 日志，改事件级别 debug | 消除私有属性访问与日志噪声 | llm_caller.py:317 | 新增 |
| 4 | P2 | LCL5：改真 LRU（OrderedDict.move_to_end）或保留读锁 | 缓存命中率提升 | llm_caller.py:139-144 | 新增 |
| 5 | P2 | LCL6：流式迭代中途 429 在 _SemaphoreWrappedAsyncIterator 或 adapter 层处理 | 流式中途 429 可恢复 | llm_caller.py:53-80 | 新增 |

## 6. 演化方向关联

- **§10.1（26 文件直连）**：LCL1 是直连路径的信号量缺陷，与 llm_client LC2/LC5 同根——**信号量缺陷两条路径都存在**，统一收敛时应合并修复
- **LLMClient 嵌套**：LLMClient 用 `_skip_semaphore=True` 避免嵌套，但 call_llm 的 fallback 内部重新 acquire（:365-376）——嵌套边界需在收敛时统一
- **Backlog 关联**：#12，新增 LCL1-LCL5
