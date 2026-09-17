# Web 搜索主链路

> 最后核对：2026-09-12

生产搜索入口是 `app/utils/web_search.py` 的 `FreeWebSearch`。聊天、PPT 大纲素材、Workflow 搜索节点和代码任务走这条实现。Agent 工具 `web_search` 走另一条 DuckDuckGo Instant Answer 调用。

## 调用方

| 调用方 | 用法 |
|--------|------|
| `app/api/v1/Aicode.py` | `FreeWebSearch` + `expand_relative_time` + `fetch_page_text` |
| `app/services/ppt_state_service.py` | `FreeWebSearch().search("{topic} 行业市场数据案例趋势", count=5)` |
| `app/utils/workflow/node_types/web_search.py` | `FreeWebSearch`、`fetch_page_text`、`summarize_page_with_llm` |
| `app/tasks/code_tasks.py` | `FreeWebSearch` |
| `app/agent/tools.py` `_tool_web_search` | `GET https://api.duckduckgo.com/`，`format=json`，读取 `RelatedTopics` |

## FreeWebSearch.search 顺序

1. 用 `search_query_variants` 展开查询（实体名、相对时间、原词）。
2. `_search_baidu` 请求 `https://www.bing.com/search`，解析 `li.b_algo`，来源标记为 Bing。
3. `filter_relevant_results` 按标题/摘要相关性打分，默认 `min_score=0.4`；`merge_results_by_url` 按规范化 URL 去重。
4. 能抽出实体时，再搜 Wikipedia 并发现官网方面页；命中则直接返回。
5. Bing 结果不足时请求 DuckDuckGo HTML：`https://html.duckduckgo.com/html/`。
6. 仍不足时用 `official_reference_results` 与 Wikipedia 补全。
7. 全部失败返回 `_fallback_results`。

可选 `search_with_summaries`：抓取页面文本后由 LLM 生成摘要。摘要模型走模块内默认推理模型。

## 与增强模块的边界

查询改写、Jaccard 去重和质量域名打分在 `app/utils/web_search_enhancements.py`。生产入口和 Workflow 节点都没有导入该文件。相关性过滤与 URL 去重已经写在 `web_search.py` 内部。增强模块仍由 `tests/unit/test_web_search_enhancements.py` 和若干 e2e 直接调用。详见 `docs/features/WEB-SEARCH-ENHANCEMENTS.md`。

## 实现备注

- `_search_baidu` 函数名保留旧称，实际请求 Bing。
- DuckDuckGo HTML 客户端当前 `verify=False`。环境变量 `WEB_SEARCH_DISABLE_SSL_VERIFY` 会赋给 `DISABLE_SSL_VERIFY`，搜索客户端没有读取该开关。
- 官网发现页 `_fetch_html` 使用默认 SSL 上下文，且只接受 `http`/`https`。
- 相关性与实体抽取有单元测试：`tests/unit/test_web_search_relevance.py`。

## 代码索引

- `app/utils/web_search.py`：生产 `FreeWebSearch`
- `app/utils/web_search_enhancements.py`：独立增强模块
- `app/agent/tools.py`：Agent Instant Answer 搜索工具
