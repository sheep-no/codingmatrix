# 多供应商适配器（base + anthropic + dashscope + deepseek + dynamic + openai + siliconflow + zhipu）

> 第一百三十九轮补扫 | v1.140 | 2026-08-24 | 分析对象：`app/utils/aicloud/adapters/` 8 文件——`base.py`（141 行）+ `anthropic.py`（134 行）+ `dashscope.py`（143 行）+ `deepseek.py`（140 行）+ `dynamic.py`（210 行）+ `openai.py`（140 行）+ `siliconflow.py`（256 行）+ `zhipu.py`（140 行），共 1304 行 + 消费方 `app/utils/aicloud/llm_caller.py`（438 行）、`app/utils/aicloud/http_client.py`（139 行）、`app/api/v1/providers.py`、测试 `test_adapters.py`
>
> 结论：**适配器层「模板方法名存实亡」——基类 `_validate_api_key`/`_get_headers`/`_parse_response_content` 零生产消费（死代码），四个官方 OpenAI 兼容适配器逐行复制粘贴且把 SiliconFlow 专属字段注入官方请求体；timeout 参数全链路失效（调用方传的超时从未作用于 HTTP 请求）；Anthropic 流式不转换 SSE 格式致消费方输出全丢；llm_caller 硬编码 Anthropic base_url 缺 `/v1` 用户 Key 路径 404**。并对第一百三十七轮 HC2「`_max_concurrent_calls` 死常量」误判做出修正（实为全部 8 适配器活跃消费的全局并发信号量）。

## 一、模块定位

| 组件 | 位置 | 接线状态 |
|------|------|----------|
| BaseProviderAdapter（抽象基类） | base.py:17 | 8 适配器全部继承 |
| `_validate_api_key` | base.py:29 | **全库零消费——死方法**（7 子类各自首行 RuntimeError 自检，无任何子类调用基类方法） |
| `_build_messages` / `_build_request_body` | base.py:88/:104 | 4 个 OpenAI 兼容适配器消费（openai/dashscope/deepseek/zhipu）；siliconflow/anthropic/dynamic 各自重写 |
| `_parse_response_content` | base.py:96 | **生产零消费——死方法**（仅 test_adapters.py:49/:59/:70 引用） |
| `_is_reasoning_model`（关键词版） | base.py:133 | 4 个官方适配器经 _build_request_body 使用；siliconflow 重写为配置文件版 |
| `_get_headers`（抽象） | base.py:139 | 仅 anthropic.py:46 真实调用；openai/zhipu/dashscope/deepseek/siliconflow/dynamic 定义后从不调用（内联构造 headers）——**死方法 ×6** |
| OpenAIAdapter / DashScopeAdapter / DeepSeekAdapter / ZhipuAdapter | openai.py:19 等 | llm_caller ADAPTER_FACTORIES（:31-36）注册，四文件逐行复制粘贴 |
| AnthropicAdapter | anthropic.py:22 | llm_caller 注册；非流式转 OpenAI 兼容，流式不转（见 ADP3） |
| SiliconFlowAdapter | siliconflow.py:23 | llm_caller 注册；256 行最重实现，重写消息构建/推理判断/降级重试 |
| DynamicAdapter | dynamic.py:22 | llm_caller.py:225/:262 + api/v1/providers.py 动态供应商消费；`provider=SILICONFLOW` 伪赋值（见 ADP12） |
| `_max_concurrent_calls = Semaphore(20)` | http_client.py:19 | **全部 8 适配器 `async with` 活跃消费（非死常量，修正 HC2）** |
| `get_http_client`（共享客户端 Timeout(300.0)） | http_client.py:26 | 全部适配器真实消费；**300s 固定超时使各适配器 timeout 参数失效**（见 ADP1） |

## 二、缺陷清单

### P2（5 项）

- **ADP1 [P2] 适配器 timeout 参数全链路失效——调用方传的超时从未作用于 HTTP 请求**——openai.py:47 `timeout = Timeout(self.timeout, connect=10.0)` 构造后**从不使用**（同 zhipu.py:47 / dashscope.py:50 / deepseek.py:47 / anthropic.py:48 / dynamic.py:71/:130，siliconflow 甚至不构造）——所有请求走 `get_http_client()` 共享客户端（http_client.py:33 `Timeout(300.0, connect=10.0)`）——**llm_caller.py:226/:247/:263/:273 的 `adapter.timeout = timeout` 赋值全部空转**——`call_llm(timeout=...)` 参数（默认 360.0）被接受但被忽略，慢请求可挂满共享客户端 300s（「规划功能未生效」家族）。
- **ADP2 [P2] base._build_request_body 把 SiliconFlow 专属字段注入 4 个官方 OpenAI 兼容适配器请求体**——base.py:122-129 对非 reasoning 模型加 `body["enable_thinking"] = False`、对 reasoning 模型加 `body["extra_body"] = {"thinking_budget": ...}`——`enable_thinking` 是 SiliconFlow/Qwen 特有参数，**OpenAI/DeepSeek 官方 API 拒收未知字段 → 400**；`extra_body` 是 OpenAI SDK 客户端参数，直接发 JSON 时作为字面字段发送（非官方 API 字段）——四个官方适配器（openai/dashscope/deepseek/zhipu）经 `_build_request_body` 构造的请求体含非官方字段——**而 SiliconFlow 生产代码重写了自己的 data 构造（siliconflow.py:101-119）从不走 base 版本**——base 模板方法与生产路径脱节。
- **ADP3 [P2] Anthropic 流式路径不转换为 OpenAI 兼容 SSE——消费方输出全丢**——anthropic.py:65-84 流式把 `data:` 后 chunk 原样 yield（`yield f"{chunk}\n"`），**没有**像非流式（:105-119）那样把 content blocks 拼接为 `{"choices":[{"message":{"content":...}}]}`——Anthropic SSE 的 `data:` 是 `{"type":"content_block_delta","delta":{...}}` 结构——下游 aicloud.py:345-347 `chunk.get("choices",[{}])[0].get("delta",{}).get("content","")` 解析恒空——**Anthropic 模型流式聊天输出全部为空**（非流式/流式处理不对称）。
- **ADP4 [P2] llm_caller 硬编码 Anthropic base_url 缺 `/v1`——用户自定义 Key 路径 404**——llm_caller.py:436 `ModelProvider.ANTHROPIC: "https://api.anthropic.com"` 与 anthropic.py:27 `BASE_URL = "https://api.anthropic.com/v1"` **不一致**（其余 5 供应商两者一致）——用户 Key 路径（llm_caller.py:241-245 用 `_get_provider_base_url(provider)` 作 base_url）→ `user_config.base_url = "https://api.anthropic.com"` → AnthropicAdapter 用 `self.base_url`（非空，不走 BASE_URL 兜底）→ 请求 `{base_url}/messages` = `https://api.anthropic.com/messages` **缺 /v1** → 官方 404——**用户自带 Anthropic Key 的调用必然失败**（base_url 双源漂移，双轨家族第 21 处）。
- **ADP5 [P2] 基类 `_validate_api_key` 死方法 + 子类错误类型不一致**——base.py:29-39 定义 `_validate_api_key`（抛 HTTPException 401），docstring（:31-32）声称「子类在 call_llm 入口处调用」——但 grep 全库确认**无任何子类调用**——7 个适配器各自在 call_llm 首行 `if not self.api_key: raise RuntimeError(...)`（openai:38/anthropic:42/dashscope:41/deepseek:38/zhipu:38/dynamic:49）——**基类 401 语义从未兑现，子类抛 RuntimeError(500 类)**——实际靠 llm_caller.py:298-299 的 `ProviderAPIKeyNotConfiguredError`（401）兜底才不产生错误状态码漂移（死代码家族第 26 处）。

### P3（9 项）

- **ADP6 [P3] 修正第一百三十七轮 HC2 误判：`_max_concurrent_calls` 非死常量**——http_client.py:19 被 **8 个适配器文件全部 `async with _max_concurrent_calls:` 真实消费**（openai:62/:82/:120 等）——HC2 结论「定义后从未使用」错误——真实问题转为：**三层并发限制叠加**——llm_caller 的 global_sem + model_sem（llm_client）+ http_client 的全局 Semaphore(20)——流式期间三把信号量同时持有（HC4 并发控制双轨延伸）。
- **ADP7 [P3] 四官方适配器逐行复制粘贴 + 基类模板方法未复用**——openai/dashscope/deepseek/zhipu 四文件 call_llm/call_embedding 仅 BASE_URL/provider/错误文案不同（各 ~140 行近乎逐行相同）——基类 `_get_headers` 仅 anthropic 真实调用，其余 6 适配器定义后从不调用（内联构造 headers）——死方法 ×6（死代码家族第 27 处）；`_parse_response_content` 生产零消费（死代码家族第 28 处）。
- **ADP8 [P3] siliconflow._is_reasoning_model 同步 open 读盘 + 相对路径脆弱 + 静默降级**——siliconflow.py:44-55 `os.path.join(os.path.dirname(__file__), "../../../../data/agent_model_config.json")`——基于 `__file__` 上溯 4 级（当前尚解析到项目根 data/ 但路径结构一变即碎）+ async 函数内同步 `open()` 阻塞事件循环 + `except Exception: pass` 静默降级到硬编码兜底集（:57-58）（GRD3/EC3 家族）。
- **ADP9 [P3] siliconflow._unsupported_thinking 注释「避免跨请求污染」与事实相反**——siliconflow.py:36-38 声称「实例级字段，每个 Adapter 独立持有」——但 llm_caller.py:42/:127 `_adapter_cache[SILICONFLOW]` **全局单例缓存默认适配器**——`_unsupported_thinking` 集合被全站用户共享——**用户 A 触发某模型 enable_thinking 400 后，全站该模型永久跳过重试**（注释与实现漂移）。
- **ADP10 [P3] siliconflow.call_llm 无 api_key 预检**——siliconflow.py:73 直接 `logger.info` 后用 `self.api_key` 构造 headers（空则 `Bearer None`）——其余 6 适配器均在 call_llm 首行检查——依赖 llm_caller:298 兜底，自身防护缺失。
- **ADP11 [P3] 四官方适配器流式路径无非 200 检查——错误 JSON 当 SSE 逐行 yield**——openai.py:64-78 等流式 `async with client.stream` 后直接 `aiter_lines()` 解析，**没有**像 siliconflow.py:132-138 的 `status_code != 200` 显式检查——4xx/5xx 错误响应体被当 SSE chunk 逐行产出给消费方。
- **ADP12 [P3] DynamicAdapter `provider = ModelProvider.SILICONFLOW` 伪赋值**——dynamic.py:25 注释「基类要求，实际通过 protocol 区分」——llm_caller.py:299 空 Key 报错 `ProviderAPIKeyNotConfiguredError(adapter.provider.value)` 会误报「siliconflow 供应商」——实际可能是 anthropic 协议动态供应商——错误归属误导。
- **ADP13 [P3] test_adapters.py 用 SiliconFlowAdapter 实例测 base 模板方法，与生产路径脱节**——测试引用 `_build_messages/_parse_response_content/_build_request_body`（test_adapters.py:23/:49/:79 等）——但 SiliconFlow 生产 call_llm 自建 messages/data（siliconflow.py:79-119）从不走这些 base 方法——**测试测的模板与线上执行路径不一致**（测试失真家族）。
- **ADP14 [P3] 四官方适配器流式/非流式超时参数、重试语义各带一份重复实现**——`call_with_retry`（http_client.py:47）被每个适配器 `max_retries=3` 重复调用 + llm_caller._retry_on_rate_limit 外层 429 重试——**双重重试叠加**（LMC3 家族，流式路径无任何重试）。

## 三、全库交叉确认

- **调用方引用 API 全部真实存在**（第一百二十七轮补扫模式）：openai/zhipu/dashscope/deepseek/anthropic/siliconflow 的 `call_llm/call_embedding` 签名与 llm_caller 调用点（:320/:378）一致；`get_provider_adapter` 名称不存在，实际工厂是 llm_caller.ADAPTER_FACTORIES（:30-37）与 `get_adapter`（:113）——适配器层无「调用不存在符号」断裂。
- **timeout 失效链**：`call_llm(timeout=360.0)` → `adapter.timeout = timeout`（llm_caller:226 等）→ 适配器构造 `Timeout(self.timeout)` 局部变量后**丢弃** → 实际走共享客户端 300s——**参数被接受但整条链路不生效**。
- **Anthropic 流式失效链**：AnthropicAdapter 流式 yield Anthropic 原生 SSE → aicloud.py:345-347 按 OpenAI `choices[0].delta.content` 解析恒空 → **用户看到的 Anthropic 流式回复为空**（nginx_ai.py:67 / Aicode.py:571 等所有 stream=True 消费方同受影响）。
- **base_url 双源**：llm_caller._get_provider_base_url（:428-437 硬编码表）vs 各适配器 BASE_URL 类常量——5 个供应商一致、**ANTHROPIC 缺 /v1**——双源漂移第 21 处（ADP4）。
- **死代码家族累计第 26/27/28 处**：ADP5（_validate_api_key）、ADP7（_get_headers ×6 + _parse_response_content）。
- **双轨家族第 21 处**：ADP4（base_url 双源）；并发控制三层叠加延续 HC4。
- **「规划功能未生效」家族新增 ADP1**（timeout 参数失效）——家族累计 GC2/PM2/TDC1/LLM2/CON1/DT1/CI1/SO1/KP2/ADP1。
- **与第一百三十七轮衔接**：aicloud_core.md 的 HC2（`_max_concurrent_calls` 死常量）为误判，本轮 ADP6 修正；MR1（模型名分裂）在此印证——适配器层本身路由正确，问题在上层 provider_router/model_registry。

## 四、测试状态

`test_adapters.py`（198 行）覆盖：base 模板方法（_build_messages/_parse_response_content/_build_request_body/_is_reasoning_model）、SiliconFlow 默认/自定义配置、Anthropic _get_headers 与 call_embedding NotImplementedError。**零覆盖**：各适配器 call_llm/call_embedding 真实 HTTP 路径、timeout 参数生效性、Anthropic 流式格式、_validate_api_key 生命周期、_max_concurrent_calls 并发限流——ADP1/ADP2/ADP3/ADP4 全部实码可证无任何用例保护，且测试测的模板方法在生产多不执行（ADP13）。修复建议：① ADP1 适配器构造请求时显式传 `timeout=self.timeout`（或删除失效参数）；② ADP2 base._build_request_body 只加各供应商官方字段，enable_thinking/extra_body 收敛进 SiliconFlowAdapter；③ ADP3 Anthropic 流式逐 chunk 转 OpenAI 兼容格式；④ ADP4 统一 base_url 单源（_get_provider_base_url 补 `/v1` 或直接引用各适配器 BASE_URL）；⑤ ADP5 删 _validate_api_key 或强制子类调用并统一错误类型；⑥ 下轮转 pptx/ 12 文件或 validators/ 5 文件。
