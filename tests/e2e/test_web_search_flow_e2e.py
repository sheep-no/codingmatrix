"""
Web 搜索增强功能 E2E 测试（简化版）

不依赖完整 app，直接测试搜索模块的端到端流程
"""

import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.utils.web_search import FreeWebSearch, SearchResult as WebSearchResult
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
# E2E 测试：完整搜索流程
# ============================================================================

class TestCompleteSearchFlow:
    """完整搜索流程测试"""

    @pytest.mark.asyncio
    async def test_search_with_query_enhancement(self):
        """测试带查询词增强的完整搜索流程"""
        # 1. 用户输入技术问题
        original_query = "python github 代码示例"
        
        # 2. 识别为技术问题
        assert is_technical_query(original_query) is True
        
        # 3. 增强查询词
        enhanced_query = enhance_query(original_query)
        assert "site:github.com" in enhanced_query
        
        # 4. 执行搜索（使用增强后的查询词）
        search_engine = FreeWebSearch()
        results = await search_engine.search(enhanced_query, count=3)
        
        # 5. 验证搜索结果
        assert isinstance(results, list)
        # 可能有结果或降级结果
        if len(results) > 0:
            # 如果有结果，验证质量（使用 web_search 的 SearchResult）
            for result in results:
                assert isinstance(result, WebSearchResult)
                assert len(result.title) > 0
                assert len(result.url) > 0 or result.source == "System"

    @pytest.mark.asyncio
    async def test_search_with_deduplication(self):
        """测试带去重的完整搜索流程"""
        search_engine = FreeWebSearch()
        
        # 使用普通查询
        query = "python tutorial"
        results = await search_engine.search(query, count=5)
        
        # 即使有结果，也应该已经去重
        urls = [r.url for r in results if r.url]
        assert len(urls) == len(set(urls)), "搜索结果 URL 有重复"

    @pytest.mark.asyncio
    async def test_search_quality_sorting(self):
        """测试搜索结果质量排序"""
        search_engine = FreeWebSearch()
        
        # 使用高质量查询
        query = "github repository"
        results = await search_engine.search(query, count=5)
        
        if len(results) > 1:
            # 验证结果按质量排序
            sorted_results = sort_by_quality(results)
            # 验证排序后的分数递减
            scores = [score_search_result(r) for r in sorted_results]
            for i in range(len(scores) - 1):
                assert scores[i] >= scores[i + 1] or sorted_results[i].source == "System"


# ============================================================================
# E2E 测试：不同场景
# ============================================================================

class TestSearchScenariosE2E:
    """不同搜索场景 E2E 测试"""

    @pytest.mark.asyncio
    async def test_technical_question_scenario(self):
        """技术问题搜索场景"""
        query = "如何修复 python indexerror"
        
        # 识别
        assert is_technical_query(query) is True
        assert is_error_query(query) is True
        
        # 增强
        enhanced = enhance_query(query)
        assert "site:stackoverflow.com" in enhanced or "site:github.com" in enhanced
        
        # 搜索
        search_engine = FreeWebSearch()
        results = await search_engine.search(enhanced, count=3)
        
        # 验证
        assert len(results) > 0
        # 至少应该有降级结果
        assert results[0].source in ["Bing", "DuckDuckGo", "GitHub", "StackOverflow", "System"]

    @pytest.mark.asyncio
    async def test_chinese_question_scenario(self):
        """中文问题搜索场景"""
        query = "vue3 组件开发教程"
        
        # 识别
        assert is_technical_query(query) is True
        
        # 增强
        enhanced = enhance_query(query)
        # 技术问题会被增强为 GitHub/SO
        assert any(site in enhanced for site in ["site:github.com", "site:stackoverflow.com"])
        
        # 搜索
        search_engine = FreeWebSearch()
        results = await search_engine.search(enhanced, count=3)
        
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_error_fix_scenario(self):
        """错误修复场景"""
        query = "AttributeError module has no attribute fix"
        
        # 识别
        assert is_error_query(query) is True
        
        # 增强
        enhanced = enhance_query(query)
        assert "site:stackoverflow.com" in enhanced
        
        # 搜索
        search_engine = FreeWebSearch()
        results = await search_engine.search(enhanced, count=3)
        
        assert len(results) > 0


# ============================================================================
# E2E 测试：性能测试
# ============================================================================

class TestSearchPerformance:
    """搜索性能测试"""

    @pytest.mark.asyncio
    async def test_search_response_time(self):
        """测试搜索响应时间"""
        import time
        
        search_engine = FreeWebSearch()
        query = "python tutorial"
        
        start_time = time.time()
        results = await search_engine.search(query, count=3)
        elapsed = time.time() - start_time
        
        # 优化后的搜索应该在 15 秒内完成
        assert elapsed < 20.0, f"搜索响应时间过长：{elapsed}秒"
        
        # 验证结果
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_multi_query_enhancement_performance(self):
        """测试多查询词增强性能"""
        import time
        
        queries = [
            "python github 代码",
            "java exception fix",
            "vue3 教程",
            "AI news 2025",
            "rust programming guide"
        ]
        
        start_time = time.time()
        
        for query in queries:
            enhanced = enhance_query(query)
            assert len(enhanced) > 0
        
        elapsed = time.time() - start_time
        
        # 查询词增强应该很快（<1 秒）
        assert elapsed < 1.0, f"查询词增强过慢：{elapsed}秒"


# ============================================================================
# E2E 测试：边界情况
# ============================================================================

class TestSearchEdgeCases:
    """搜索边界情况测试"""

    @pytest.mark.asyncio
    async def test_empty_query_handling(self):
        """测试空查询处理"""
        search_engine = FreeWebSearch()
        results = await search_engine.search("", count=3)
        
        # 空查询应该返回降级结果
        assert len(results) > 0
        assert results[0].source == "System"

    @pytest.mark.asyncio
    async def test_very_long_query_handling(self):
        """测试超长查询处理"""
        search_engine = FreeWebSearch()
        long_query = "python " * 100
        results = await search_engine.search(long_query, count=3)
        
        # 应该返回某种结果（可能降级）
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_special_characters_query(self):
        """测试特殊字符查询"""
        search_engine = FreeWebSearch()
        query = "how to use @decorator in python?"
        results = await search_engine.search(query, count=3)
        
        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_mixed_language_query(self):
        """测试混合语言查询"""
        query = "how to 使用 python list comprehension"
        
        # 识别
        is_tech = is_technical_query(query)
        assert is_tech is True
        
        # 增强
        enhanced = enhance_query(query)
        assert len(enhanced) > 0
        
        # 搜索
        search_engine = FreeWebSearch()
        results = await search_engine.search(enhanced, count=3)
        
        assert isinstance(results, list)


# ============================================================================
# E2E 测试：集成验证
# ============================================================================

class TestIntegrationValidation:
    """集成验证测试"""

    @pytest.mark.asyncio
    async def test_all_enhancements_working_together(self):
        """测试所有增强功能协同工作"""
        # 1. 查询词识别
        query = "github python repository"
        assert is_technical_query(query) is True
        
        # 2. 查询词增强
        enhanced = enhance_query(query)
        assert "site:github.com" in enhanced
        
        # 3. 搜索执行
        search_engine = FreeWebSearch()
        results = await search_engine.search(enhanced, count=5)
        
        # 4. 结果去重
        deduped = deduplicate_results(results)
        assert len(deduped) <= len(results)
        
        # 5. 质量排序
        sorted_results = sort_by_quality(deduped)
        assert len(sorted_results) == len(deduped)
        
        # 6. 验证最终结果
        if len(sorted_results) > 0:
            # 高质量结果应该排在前面
            high_quality_sources = ["GitHub", "StackOverflow", "Bing", "DuckDuckGo"]
            first_source = sorted_results[0].source
            assert first_source in high_quality_sources + ["System"]

    @pytest.mark.asyncio
    async def test_fallback_mechanism(self):
        """测试降级机制"""
        search_engine = FreeWebSearch()
        
        # 使用不可能有结果的查询（超随机字符串）
        impossible_query = "xyzabc123nonexistent999test"
        results = await search_engine.search(impossible_query, count=3)
        
        # 应该返回某种结果
        assert len(results) > 0
        # 可能是降级结果，也可能是 Bing 的空结果
        # 重点是验证不会崩溃
        assert results[0].source in ["System", "Bing", "DuckDuckGo"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
