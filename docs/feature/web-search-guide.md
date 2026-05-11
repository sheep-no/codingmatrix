# 网络搜索功能

## 概述

CodingMatrix 集成 Bing 和 DuckDuckGo 搜索引擎，为 AI Agent 提供实时外部知识获取能力。

## 搜索引擎

| 引擎 | 文件 | 说明 |
|------|------|------|
| Bing | `utils/web_search.py` | 需要 API Key，更稳定 |
| DuckDuckGo | `utils/web_search.py` | 免费，无需 Key |

## API 使用

```python
from app.utils.web_search import WebSearch

searcher = WebSearch(engine="duckduckgo")
results = await searcher.search("最新 AI 技术", max_results=5)
```

## Agent 集成

Agent 在执行任务时自动判断是否需要搜索:

```
用户提问 -> Agent 分析 -> 需要外部知识? 
    -> 是: WebSearch.search(query)
    -> 否: 直接回答
```

## 配置

```env
SEARCH_ENGINE=duckduckgo
MAX_SEARCH_RESULTS=5
SEARCH_TIMEOUT=10
```
