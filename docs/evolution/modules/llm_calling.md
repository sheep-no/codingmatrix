# aicloud/llm_caller.py + prompt_builder.py + prompt_loader.py LLM 家族

> 第一百二十九轮补扫 | v1.130 | 2026-08-17 | 分析对象：`app/utils/aicloud/llm_caller.py`（438 行，统一模型调用入口）+ `app/utils/prompt_builder.py`（241 行，KV Cache 提示词构建器）+ `app/utils/prompt_loader.py`（161 行，提示词加载器）+ `app/utils/llm_caller.py`（15 行，转发封装）
>
> 结论：**call_llm 是全局模型调用核心（30+ agent 模块消费）——信号量管理存在泄漏风险（流式断连/获取不对称）；prompt_builder 零消费死代码；prompt_loader 被 frontend/backend/architect 消费——但 load() 存在任意文件读取路径穿越**。

## 一、模块定位

| 组件 | 位置 | 消费状态 |
|------|------|----------|
| call_llm（统一入口） | aicloud/llm_caller.py:179 | **30+ 模块消费**（spec_first_generator/task_planner/react_agent/ppt_agent/llm_client/nginx_api 等） |
| app/utils/llm_caller.py（转发） | 15 行 | 从 aicloud 再导出 |
| PromptBuilder | prompt_builder.py:35 | **零业务消费**——死代码 |
| PromptLoader | prompt_loader.py:16 | frontend_engineer/backend_engineer/architect 真实消费 |

## 二、缺陷清单

### P2（5 项）

- **LMC6 [P2] 流式迭代信号量泄漏——SSE 断连/消费者提前 break 永不释放**——llm_caller.py:159-176——`_SemaphoreWrappedAsyncIterator.__anext__` **只在 StopAsyncIteration 或异常时释放信号量**——若客户端中断流（浏览器断开、请求取消）→ `__anext__` 不再被调用 → **信号量永不释放**——全局/模型并发额度逐步耗尽直至占满（并发请求全被阻塞）。修复方向：`finally` 中 aclose + 释放，或加弱引用/超时回收机制。**这是全库最活跃调用路径上的并发泄漏**。
- **LMC4 [P2] 信号量获取不对称——model_sem.acquire 抛异常 → global_sem 泄漏**——llm_caller.py:313-316——`await global_sem.acquire()` 成功后 `await model_sem.acquire()` 若抛（取消/中断）→ global_sem 已占未释放。修复方向：两级获取统一 try/except 或一次性获取组合信号量。
- **PL2 [P2] PromptLoader.load 路径穿越——可控 path 读取任意文件（内容进 LLM 上下文）**——prompt_loader.py:30-33 `PROMPTS_ROOT / path`——path 含 `../` 或绝对路径 → **读取任意文件返回给调用方（再拼进 prompt 发往 LLM）**——任意文件读取 + 敏感信息外泄链。修复方向：`(PROMPTS_ROOT / path).resolve()` 后校验 `is_relative_to(PROMPTS_ROOT)`。
- **PL1 [P2] PromptLoader.format 的 `str.format(**kwargs)` 只 catch KeyError——模板/变量含大括号抛 ValueError 未捕获传播**——prompt_loader.py:57-61——`template.format(**kwargs)` 遇未闭合 `{` 或 kwargs 含特殊序列 → **ValueError 未捕获 → 调用方崩溃**（frontend_engineer/backend_engineer 等直接受影响）。修复方向：catch (KeyError, ValueError) 并返回 None，或改用占位符替换。
- **PB2 [P2] prompt_builder `_clean_dynamic_variables` 正则误删正常文本——任意 8+ 十六进制字符串被删除**——prompt_builder.py:48-52 `[0-9a-f-]{8,}`——**commit id / hash / base64 片段 / token 片段 / 用户正常文本中的十六进制串全部被删除**——消息内容被篡改、信息丢失（虽当前零消费，一旦接入即内容破坏）。修复方向：精确匹配 timestamp/uuid 格式，不泛匹配十六进制串。

### P3（9 项）

- **LMC1 [P3] `_user_adapter_cache` 值含明文 api_key 内存驻留——进程转储泄露面**——llm_caller.py:43/:144（键为 hash 但 ProviderConfig 值含明文 Key——最多 256 份驻留）。
- **LMC3 [P3] `_retry_on_rate_limit` 只重试 429——5xx/连接超时不重试**——llm_caller.py:70-79。
- **LMC7 [P3] `_get_provider_base_url` 硬编码供应商 URL——与 config 的 provider registry 不一致时过期**——llm_caller.py:428-438。
- **LMC8 [P3] 信号量不可用 `except Exception: pass` 静默降级**——llm_caller.py:309-310。
- **LMC9 [P3] 429 检测用 `"429" in error_str` 字符串匹配——脆**——llm_caller.py:72（错误文本中其他 "429" 会误触发重试）。
- **PL3 [P3] PromptLoader 每次 load 读盘无缓存**——prompt_loader.py:36。
- **PB1 [P3] get_prompt_builder 单例无锁**——prompt_builder.py:236-241（DCC1 家族）。
- **PB4 [P3] 静态前缀单槽缓存——多项目（不同 spec_cache_content）场景缓存抖动**——prompt_builder.py:123-125/:144-146。
- **PB6 [P3] append_history 无上限——conversation_history 无限增长**——prompt_builder.py:199-204。

## 三、全库交叉确认

- **全局核心链路**：call_llm 是 30+ 模块的共同依赖——**LMC6 信号量泄漏影响全站 LLM 并发能力**（最活跃路径缺陷，修复优先级最高）。
- **死代码家族**：prompt_builder 与 retry/sentry/startup_alert/task_dispatcher/resume_manager 同族——「完备封装但未接入」累计第七处。
- **任意文件读取新类**：PL2 是本库首个「路径穿越→敏感内容进 LLM 上下文」链（对比 RM2 路径穿越但零消费未暴露）——**prompt_loader 是活跃消费，PL2 真实可利用**。
- **并发信号量链**：call_llm 信号量（llm_client.get_model_semaphore）与 dynamic_model_router/rate_limiter 三层并发防线——**LMC6 直接破坏该防线**。

## 四、测试状态

零单元测试。信号量泄漏、路径穿越、format 异常、正则误删均无测试约束。修复建议：① **LMC6 流式断连信号量释放测试（模拟迭代器提前 close 断言信号量归还）**；② PL2 路径穿越测试（`../` 与绝对路径断言拒绝）；③ PL1 大括号模板异常测试；④ PB2 正则误删回归测试。
