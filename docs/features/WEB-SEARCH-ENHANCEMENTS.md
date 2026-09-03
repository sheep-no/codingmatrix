# Web 搜索增强功能

> 最后核对：2026-09-03
> 状态：独立模块可用，生产搜索主链路未接入

## 当前状态

`app/utils/web_search_enhancements.py` 提供查询改写、结果去重和质量排序。当前生产搜索入口 `app/utils/web_search.py` 与 Workflow 搜索节点 `app/utils/workflow/node_types/web_search.py` 均未导入该模块，因此这些增强规则不会自动影响 Agent 或 Workflow 的搜索结果。

该模块目前由以下测试直接覆盖：

- `tests/unit/test_web_search_enhancements.py`
- `tests/e2e/test_web_search_e2e.py`
- `tests/e2e/test_web_search_flow_e2e.py`
- `tests/e2e/test_guangzhou_railway_search.py`

## 可用能力

### 查询增强

`enhance_query(query, prompt="", enable_enhance=True)` 根据错误、技术、政府、企业、教程、新闻和学校等关键词改写查询。调用方可通过 `enable_enhance=False` 保留原查询。

已知限制：教程类查询使用硬编码年份 `2025` 和 `2024`。截至 2026-09-03，该时效规则已经过期，接入生产链路前应改为运行时年份或配置值。

### 结果去重

`deduplicate_results(results, threshold=0.85)` 先移除查询参数后比较 URL，再使用标题词集合的 Jaccard 相似度过滤近似结果。

输入元素使用模块内的 `SearchResult` 类型，字段为 `title`、`url`、`snippet`、`source` 和 `summary`。

### 质量排序

`score_search_result(result)` 按域名、标题、摘要长度和日期线索计算分数。`sort_by_quality(results)` 按该分数降序排列。

质量域名列表和评分权重均为静态规则，接入生产环境时需要结合搜索提供方返回模型、业务区域和可信来源策略校准。

## 直接使用

```python
from app.utils.web_search_enhancements import (
    SearchResult,
    deduplicate_results,
    enhance_query,
    sort_by_quality,
)

query = enhance_query("FastAPI dependency injection")
results = [
    SearchResult(
        title="Dependencies - FastAPI",
        url="https://fastapi.tiangolo.com/tutorial/dependencies/",
        snippet="FastAPI dependency injection documentation",
    )
]
ranked = sort_by_quality(deduplicate_results(results))
```

## 接入边界

生产接入需要在搜索请求前显式调用 `enhance_query`，并将实际搜索结果转换为本模块的 `SearchResult` 后执行去重与排序。接入时还需要统一搜索结果类型，避免 `app/utils/web_search.py` 与增强模块各自维护数据模型。

旧文档中的 `score_results` 名称已经失效。当前公开函数名称为 `score_search_result` 和 `sort_by_quality`。

## 代码索引

- `app/utils/web_search_enhancements.py`：独立增强实现
- `app/utils/web_search.py`：当前生产搜索实现
- `app/utils/workflow/node_types/web_search.py`：当前 Workflow 搜索节点
