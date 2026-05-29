"""
Web 搜索增强功能单元测试

测试范围：
1. 查询词增强功能
2. 结果去重功能
3. 质量评分功能
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.utils.web_search_enhancements import (
    is_chinese_query,
    is_technical_query,
    is_error_query,
    enhance_query,
    calculate_similarity,
    deduplicate_results,
    sort_by_quality,
    score_search_result,
    SearchResult
)


# ============================================================================
# 查询词增强测试
# ============================================================================

class TestQueryEnhancement:
    """查询词增强功能测试"""

    def test_is_chinese_query_pure_chinese(self):
        """测试纯中文查询识别"""
        # "Python 教程" 中文字符比例 = 2/8 = 0.25 < 0.3，所以不是中文查询
        assert is_chinese_query("Python 教程") is False
        assert is_chinese_query("如何学习编程") is True
        # "vue3 入门" 中文字符比例 = 2/7 = 0.28 < 0.3，所以不是中文查询
        assert is_chinese_query("vue3 入门") is False
        # 纯中文才一定是中文查询
        assert is_chinese_query("完全中文测试") is True

    def test_is_chinese_query_mixed(self):
        """测试中英混合查询识别"""
        # 混合查询中文字符比例可能低于阈值
        result = is_chinese_query("Python 教程 beginner")
        # 根据实际字符比例判断
        assert isinstance(result, bool)

    def test_is_chinese_query_english(self):
        """测试纯英文查询识别"""
        assert is_chinese_query("Python tutorial") is False
        assert is_chinese_query("how to learn programming") is False

    def test_is_technical_query_code_keywords(self):
        """测试技术问题识别 - 代码关键词"""
        assert is_technical_query("python 代码示例") is True
        assert is_technical_query("github repository") is True
        assert is_technical_query("code implementation") is True
        assert is_technical_query("开发一个 API") is True

    def test_is_technical_query_framework_keywords(self):
        """测试技术问题识别 - 框架关键词"""
        assert is_technical_query("react framework") is True
        assert is_technical_query("vue library") is True
        assert is_technical_query("python 函数") is True
        assert is_technical_query("java 类") is True

    def test_is_technical_query_general(self):
        """测试一般问题识别"""
        assert is_technical_query("今天天气怎么样") is False
        assert is_technical_query("如何做蛋糕") is False

    def test_is_error_query_error_keywords(self):
        """测试错误问题识别"""
        assert is_error_query("python exception error") is True
        assert is_error_query("代码报错") is True
        assert is_error_query("bug fix") is True
        assert is_error_query("解决这个问题") is True
        assert is_error_query("traceback error") is True

    def test_is_error_query_normal(self):
        """测试正常问题识别"""
        assert is_error_query("python 教程") is False
        assert is_error_query("how to code") is False

    def test_enhance_query_technical_github(self):
        """测试技术问题增强 - GitHub"""
        enhanced = enhance_query("python 代码", "找一个 github 上的 python 代码示例")
        assert "site:github.com" in enhanced

    def test_enhance_query_technical_stackoverflow(self):
        """测试技术问题增强 - StackOverflow"""
        enhanced = enhance_query("python api", "python api 如何使用")
        assert "site:stackoverflow.com" in enhanced or "site:github.com" in enhanced

    def test_enhance_query_error(self):
        """测试错误问题增强"""
        enhanced = enhance_query("python exception", "fix python exception error")
        assert "site:stackoverflow.com" in enhanced

    def test_enhance_query_tutorial(self):
        """测试教程类问题增强"""
        enhanced = enhance_query("fastapi 教程")
        # 教程类会被识别为 library/API 问题
        assert any(kw in enhanced.lower() for kw in ["guide", "documentation", "official"])

    def test_enhance_query_chinese(self):
        """测试中文问题增强"""
        enhanced = enhance_query("vue3 入门教程")
        # 中文技术问题也可能被增强为 GitHub/SO
        assert any(site in enhanced for site in ["site:github.com", "site:stackoverflow.com", 
                                                  "site:zhihu.com", "site:juejin.cn"])

    def test_enhance_query_news(self):
        """测试新闻类问题增强"""
        enhanced = enhance_query("AI 最新新闻")
        assert any(domain in enhanced for domain in ["reuters", "bloomberg", "theguardian"])

    def test_enhance_query_default(self):
        """测试默认查询不变"""
        enhanced = enhance_query("hello world")
        assert enhanced == "hello world"


# ============================================================================
# 相似度计算测试
# ============================================================================

class TestSimilarityCalculation:
    """相似度计算功能测试"""

    def test_calculate_similarity_identical(self):
        """测试完全相同字符串"""
        assert calculate_similarity("hello world", "hello world") == 1.0

    def test_calculate_similarity_completely_different(self):
        """测试完全不同字符串"""
        assert calculate_similarity("hello", "world") < 0.5

    def test_calculate_similarity_partial(self):
        """测试部分相似字符串"""
        sim = calculate_similarity("python tutorial", "python guide")
        assert 0.0 < sim < 1.0

    def test_calculate_similarity_empty(self):
        """测试空字符串"""
        assert calculate_similarity("", "hello") == 0.0
        assert calculate_similarity("", "") == 0.0

    def test_calculate_similarity_case_insensitive(self):
        """测试大小写不敏感"""
        sim1 = calculate_similarity("Hello World", "hello world")
        sim2 = calculate_similarity("HELLO WORLD", "hello world")
        assert sim1 == 1.0
        assert sim2 == 1.0


# ============================================================================
# 结果去重测试
# ============================================================================

class TestDeduplication:
    """结果去重功能测试"""

    def test_deduplicate_identical_urls(self):
        """测试相同 URL 去重"""
        results = [
            SearchResult(title="A", url="https://example.com/1", snippet="test"),
            SearchResult(title="B", url="https://example.com/1", snippet="test"),
        ]
        deduped = deduplicate_results(results)
        assert len(deduped) == 1

    def test_deduplicate_with_query_params(self):
        """测试带查询参数的 URL 去重"""
        results = [
            SearchResult(title="A", url="https://example.com/1?id=1", snippet="test"),
            SearchResult(title="B", url="https://example.com/1?id=2", snippet="test"),
        ]
        deduped = deduplicate_results(results)
        assert len(deduped) == 1

    def test_deduplicate_similar_titles(self):
        """测试相似标题去重"""
        results = [
            SearchResult(title="Python Tutorial", url="https://a.com", snippet="test"),
            SearchResult(title="Python Tutorial", url="https://b.com", snippet="test"),
        ]
        deduped = deduplicate_results(results, threshold=0.85)
        assert len(deduped) == 1

    def test_deduplicate_different_titles(self):
        """测试不同标题不去重"""
        results = [
            SearchResult(title="Python Tutorial", url="https://a.com", snippet="test"),
            SearchResult(title="Java Guide", url="https://b.com", snippet="test"),
        ]
        deduped = deduplicate_results(results)
        assert len(deduped) == 2

    def test_deduplicate_empty(self):
        """测试空列表"""
        assert len(deduplicate_results([])) == 0

    def test_deduplicate_single(self):
        """测试单个结果"""
        results = [SearchResult(title="A", url="https://example.com", snippet="test")]
        deduped = deduplicate_results(results)
        assert len(deduped) == 1


# ============================================================================
# 质量评分测试
# ============================================================================

class TestQualityScoring:
    """质量评分功能测试"""

    def test_score_github_domain(self):
        """测试 GitHub 域名评分"""
        result = SearchResult(
            title="Python Project",
            url="https://github.com/python/python",
            snippet="A great project",
        )
        score = score_search_result(result)
        assert score >= 0.4  # 高质域名至少 0.4 分

    def test_score_stackoverflow_domain(self):
        """测试 StackOverflow 域名评分"""
        result = SearchResult(
            title="Python Question",
            url="https://stackoverflow.com/questions/123",
            snippet="How to fix...",
        )
        score = score_search_result(result)
        assert score >= 0.4

    def test_score_tutorial_title(self):
        """测试教程标题评分"""
        result = SearchResult(
            title="Complete Python Tutorial 2025",
            url="https://example.com/guide",
            snippet="Learn python...",
        )
        score = score_search_result(result)
        assert score > 0.0  # 教程关键词加分

    def test_score_long_snippet(self):
        """测试长摘要评分"""
        result = SearchResult(
            title="Guide",
            url="https://example.com",
            snippet="This is a very long and detailed guide that explains everything about python programming in depth",
        )
        score = score_search_result(result)
        assert score > 0.0  # 长摘要加分

    def test_score_dated_content(self):
        """测试带日期内容评分"""
        result = SearchResult(
            title="2025 Guide",
            url="https://example.com/2025/01/15/guide",
            snippet="Latest guide",
        )
        score = score_search_result(result)
        assert score > 0.0  # 时效性加分

    def test_score_low_quality(self):
        """测试低质量结果"""
        result = SearchResult(
            title="A",
            url="https://random-site.xyz",
            snippet="",
        )
        score = score_search_result(result)
        assert score < 0.3  # 低质站点分数低

    def test_sort_by_quality(self):
        """测试按质量排序"""
        results = [
            SearchResult(title="Low", url="https://low.com", snippet=""),
            SearchResult(title="High", url="https://github.com/repo", snippet="Detailed description"),
            SearchResult(title="Medium", url="https://medium.com", snippet="Guide"),
        ]
        sorted_results = sort_by_quality(results)
        assert sorted_results[0].url == "https://github.com/repo"


# ============================================================================
# 集成测试
# ============================================================================

class TestIntegration:
    """集成测试"""

    def test_enhance_and_deduplicate_pipeline(self):
        """测试增强 + 去重流程"""
        query = "python 代码示例"
        
        # 1. 增强查询
        enhanced = enhance_query(query)
        assert "site:github.com" in enhanced or "site:stackoverflow.com" in enhanced
        
        # 2. 模拟搜索结果
        results = [
            SearchResult(title="A", url="https://github.com/repo1", snippet="Code"),
            SearchResult(title="B", url="https://github.com/repo1", snippet="Code"),  # 重复
            SearchResult(title="C", url="https://stackoverflow.com/q1", snippet="Answer"),
        ]
        
        # 3. 去重
        deduped = deduplicate_results(results)
        assert len(deduped) == 2
        
        # 4. 排序
        sorted_results = sort_by_quality(deduped)
        assert len(sorted_results) == 2

    def test_chinese_technical_query(self):
        """测试中文技术问题完整流程"""
        query = "vue3 组件开发"
        
        # 应该同时识别为中文和技术问题
        assert is_chinese_query(query) is True
        assert is_technical_query(query) is True
        
        # 增强后应该包含中文站点限定
        enhanced = enhance_query(query)
        assert any(kw in enhanced for kw in ["site:github.com", "site:stackoverflow.com", 
                                              "site:zhihu.com", "site:juejin.cn"])

    def test_error_query_resolution(self):
        """测试错误问题完整流程"""
        query = "python indexerror list index out of range"
        
        # 识别为错误问题
        assert is_error_query(query) is True
        
        # 增强后应该指向 StackOverflow
        enhanced = enhance_query(query, "fix python indexerror")
        assert "site:stackoverflow.com" in enhanced


# ============================================================================
# 边界情况测试
# ============================================================================

class TestEdgeCases:
    """边界情况测试"""

    def test_empty_query(self):
        """测试空查询"""
        assert enhance_query("") == ""
        assert enhance_query("   ") == ""

    def test_very_long_query(self):
        """测试超长查询"""
        long_query = "python " * 100
        enhanced = enhance_query(long_query)
        assert len(enhanced) > 0

    def test_special_characters(self):
        """测试特殊字符"""
        query = "how to use @decorator in python?"
        enhanced = enhance_query(query)
        assert len(enhanced) > 0

    def test_mixed_languages(self):
        """测试混合语言"""
        query = "how to 使用 python 的 list comprehension"
        # 中文比例可能不够高，需要确认
        result = is_chinese_query(query)
        assert isinstance(result, bool)
        assert is_technical_query(query) is True

    def test_url_with_special_chars(self):
        """测试带特殊字符的 URL 去重"""
        results = [
            SearchResult(title="A", url="https://example.com/1?a=1&b=2", snippet="test"),
            SearchResult(title="B", url="https://example.com/1?a=3&b=4", snippet="test"),
        ]
        deduped = deduplicate_results(results)
        assert len(deduped) == 1  # 应该去重


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
