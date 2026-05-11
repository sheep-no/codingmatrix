# 免费搜索功能

## 概述

CodingMatrix 集成免费搜索能力，支持 Bing 和 DuckDuckGo 两种搜索引擎。

## 使用方式

### API

```python
from app.utils.web_search import WebSearch

search = WebSearch()
results = search.search(
    query="your query",
    engine="bing",  # or "duckduckgo"
    max_results=10
)
```

### 配置

```env
SEARCH_ENGINE=bing
BING_SEARCH_KEY=your-key  # 可选
MAX_SEARCH_RESULTS=10
```

## 搜索结果格式

```json
[
  {
    "title": "页面标题",
    "url": "https://example.com",
    "snippet": "摘要内容...",
    "source": "bing"
  }
]
```

## 限制

| 引擎 | 免费配额 | 限制 |
|------|----------|------|
| DuckDuckGo | 无限 | 可能被反爬 |
| Bing | 1000/月 (免费) | 需要 API Key |

## 应用场景

- AI Agent 外部知识获取
- 代码生成前的技术调研
- 问题诊断时的错误搜索
