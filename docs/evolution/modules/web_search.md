# web_search.py + web_search_enhancements.py 网络搜索链

> 第一百二十轮补扫 | v1.121 | 2026-08-17 | 分析对象：`app/utils/web_search.py`（636 行，FreeWebSearch 搜索 + 页面摘要）+ `app/utils/web_search_enhancements.py`（371 行，查询增强/去重/评分）
>
> 结论：**网络搜索链——FreeWebSearch（Bing→DDG→降级）→ LLM 页面摘要（fetch_page_text + summarize_page_with_llm）——是 agent 工具链（tools.py:1073 _tool_web_search）与 workflow 节点（web_search.py:161）的共享搜索后端**——核心风险在外部网页内容进入 LLM 上下文的链路（TLS 关闭/SSRF/prompt 注入）。

## 一、链路结构

```
agent _tool_web_search / Aicode.py:480 / code_tasks.py:56 / workflow WebSearchNode
  └─► FreeWebSearch.search ──► Bing（_search_baidu，verify 默认）
                            └─► DuckDuckGo（verify=False ← 风险）
  └─► search_with_page_summaries ──► fetch_page_text（任意 URL）──► summarize_page_with_llm（call_llm 硬编码模型）
```

## 二、缺陷清单

### P2（4 项）

- **WS1 [P2] DuckDuckGo 搜索 `verify=False` 禁用 TLS 验证——搜索流量可被中间人篡改（CII/数据完整性家族）**——web_search.py:224 `httpx.AsyncClient(verify=False)`——DuckDuckGo 是 Bing 失败后的备用路径——网络路径受控时攻击者可篡改搜索结果（注入恶意 URL/摘要）→ **喂给 LLM 的上下文被污染** → 误导回答/钓鱼链接进入 agent 生成内容。:30 定义了 `DISABLE_SSL_VERIFY` 环境变量但**只用于注释，未实际应用**——硬编码 verify=False。修复方向：verify=ssl_context（与 fetch_page_text :466 一致）或应用环境变量。
- **WS2 [P2] `fetch_page_text` 无 SSRF 防护——workflow 节点 URL 可配置触发内网请求**——web_search.py:442-493 直接 `client.get(url)` 无内网地址/协议黑名单——消费方 `workflow/node_types/web_search.py:161` 直接调 `fetch_page_text(url, ...)`——**workflow 配置的 URL 若指向内网（127.0.0.1/metadata/云元数据地址）→ SSRF**——读取内网资源/探活。搜索结果来源 URL 相对受控，但 workflow 节点 URL 用户可配置。修复方向：URL 解析后拒绝内网/保留地址 + 协议白名单（http/https）。
- **WS3 [P2] `summarize_page_with_llm` 网页内容直接拼入 prompt——恶意网页 prompt 注入污染摘要**——web_search.py:519-530 `{page_text}` f-string 直插 prompt——恶意网页可写「忽略以上指令，输出 XX」——摘要被操纵 → 搜索结果上下文注入（间接 prompt injection）。修复方向：prompt 中声明网页内容为不可信数据 + 摘要只输出要点 + 截断控制。
- **WS4 [P2] `_clean_url` 提取 uddg/link 参数无协议白名单——非 http 协议 URL 进结果**——web_search.py:296-305——DuckDuckGo 重定向 URL 的 `uddg`/`link`/`u` 参数值直接返回——可含 `javascript:`/`feed:`/`data:` 协议 → SearchResult.url 非 http——前端/LLM 展示链接误导（弱 XSS/钓鱼）。修复方向：协议白名单校验（http/https 否则丢弃）。

### P3（7 项）

- **WS5 [P3] 命名混乱——`search` 调 `_search_baidu` 实际查 Bing**——web_search.py:106 `_search_baidu`（函数名 baidu、URL bing.com、:108 日志也写 Bing）——文档:90/:106 说「Bing 搜索」但函数名残留旧名。修复方向：重命名 `_search_bing`。
- **WS6 [P3] `max_concurrent_fetch=3` 配置定义未使用——摘要抓取无并发限制**——web_search.py:82 定义 :598 `asyncio.gather(*tasks)` 全量并发——count 大时同开全部抓取+LLM 调用。修复方向：semaphore 限流。
- **WS7 [P3] LLM 摘要模型硬编码 `deepseek-ai/DeepSeek-R1-0528-Qwen3-8B`**——web_search.py:533——模型名耦合配置漂移（与 call_llm 默认模型体系脱节）。修复方向：走 call_llm 默认或配置注入。
- **WS8 [P3] `fetch_page_text` 无响应体大小限制**——web_search.py:475-489 `resp.text` 全量入内存解析——超大页面内存占用。修复方向：content-length 检查/流式截断。
- **WSE1 [P3] `enhance_query` 后整段死代码 + `_extract_school_name` 重复定义**——web_search_enhancements.py:153 `return query` 结束增强逻辑后，:156-252 出现完整重复的学校/政府/企业/医疗/错误/技术/教程/新闻增强逻辑（不可达）+ :255 再次定义 `_extract_school_name`（**第二个定义覆盖第一个**）——复制粘贴残留。修复方向：删除 :156-252 死代码。
- **WSE2 [P3] `current_year = 2025` 硬编码——过期年份注入搜索词**——web_search_enhancements.py:129/:240——2026 年仍搜「complete guide 2025 2024」。修复方向：`datetime.now().year`。
- **WSE4 [P3] 独立定义 `SearchResult` 类（与 web_search.py 同名）——同名异构双轨**——web_search_enhancements.py:14-21 重复定义——若混用两模块类型不匹配（与 RSAKeyManager 双轨同族）。修复方向：从 web_search import。

## 三、全库交叉确认

- **外部内容进入 LLM 链路的完整性防线**：搜索是 agent 工具链（tools.py:1073、executor.py:340）与 workflow 共享的后端——WS1（TLS 关闭）/WS3（prompt 注入）直接影响 LLM 输入完整性——与 guardrails 输入净化（GRD）、EC 家族输出净化同族。
- **SSRF 家族**：WS2 与 fetch_page_text 直接相关——全库其他网络请求点（docker_runner、webhook 等）是否同样无内网过滤待查。
- **双轨模式**：WSE4 与加密双轨（crypto/encryption）、缓存双轨（cached/cache_response）、CodeValidator 双轨同族——同名类各定义一份。
- **搜索质量 vs 安全**：enhance_query 的 site: 增强（WSE1 死代码部分）若启用会注入搜索操作符——当前主链路未用 enhancements 模块（消费方待确认）。

## 四、测试状态

零单元测试。WS1 TLS 关闭、WS2 SSRF、WS3 prompt 注入、WSE1 死代码均无测试约束。修复建议：① fetch_page_text 内网 URL 拒绝测试（127.0.0.1/169.254.169.254/私有网段样本）；② URL 协议白名单测试；③ 摘要 prompt 注入样本测试；④ enhance_query 死代码覆盖断言。
