# Web 搜索增强功能

> 最后更新：2026-05-27 | 版本：v5.10.0

## 概述

Web 搜索增强模块 (`app/utils/web_search_enhancements.py`) 提供智能化的搜索查询优化和结果处理能力，提升搜索结果的质量和相关性。

## 核心功能

### 1. 查询词增强

自动识别查询类型并优化搜索词：

| 查询类型 | 检测方式 | 增强策略 |
|----------|----------|----------|
| 中文查询 | 字符比例检测 (>30%) | 添加中文搜索优化 |
| 技术查询 | 关键词匹配 | 添加技术文档站点限定 |
| 错误查询 | 错误关键词检测 | 添加解决方案关键词 |

### 2. 结果去重

基于 URL 和标题相似度进行智能去重：
- URL 完全匹配去重
- 标题相似度计算（编辑距离）
- 保留质量更高的结果

### 3. 质量评分

对搜索结果进行多维度评分：

| 评分维度 | 权重 | 说明 |
|----------|------|------|
| 来源权威性 | 30% | 官方文档、GitHub、Stack Overflow 等 |
| 内容完整性 | 25% | 摘要长度、格式完整性 |
| 时效性 | 20% | 发布时间、更新时间 |
| 相关性 | 25% | 与查询词的匹配度 |

## 使用方式

```python
from app.utils.web_search_enhancements import (
    enhance_query,
    deduplicate_results,
    score_results
)

# 增强查询词
enhanced_query = enhance_query("Python 连接 MySQL 报错")

# 去重结果
unique_results = deduplicate_results(results)

# 质量评分
scored_results = score_results(unique_results, query)
```

## 集成说明

搜索增强功能已集成到 `app/utils/web_search.py` 的 `search_web()` 函数中，自动对所有搜索请求生效。

## 相关文件

- `app/utils/web_search_enhancements.py` - 增强功能实现
- `app/utils/web_search.py` - 搜索主模块
- `tests/unit/test_web_search_enhancements.py` - 单元测试
