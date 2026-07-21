"""
广州铁路职业技术学院搜索测试

测试 /api/v1/code 接口对特定搜索词的处理
"""

import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# 尝试导入 app，如果失败则只测试搜索模块
try:
    from app.main import app
    from app.utils.security import create_access_token
    from app.utils.web_search import FreeWebSearch
    from app.utils.web_search_enhancements import (
        is_chinese_query,
        is_technical_query,
        is_error_query,
        enhance_query,
        deduplicate_results,
        sort_by_quality,
        score_search_result
    )
    APP_AVAILABLE = True
except Exception as e:
    print(f"⚠️  无法导入完整 app: {e}")
    print("ℹ️  将只测试搜索模块功能")
    APP_AVAILABLE = False
    
    from app.utils.web_search import FreeWebSearch
    from app.utils.web_search_enhancements import (
        is_chinese_query,
        is_technical_query,
        is_error_query,
        enhance_query,
        deduplicate_results,
        sort_by_quality,
        score_search_result,
        SearchResult
    )


@pytest.fixture
def auth_token():
    """生成测试用户 token"""
    if APP_AVAILABLE:
        return create_access_token(
            sub="1",
            permission_level="normal",
            expires_delta=None
        )
    return None


@pytest.fixture
def auth_headers(auth_token):
    """认证请求头"""
    if auth_token:
        return {"Authorization": f"Bearer {auth_token}"}
    return {}


# ============================================================================
# 测试特定搜索词：广州铁路职业技术学院计算机应用技术专业
# ============================================================================

class TestGuangzhouRailwaySearch:
    """广州铁路职业技术学院搜索测试"""

    @pytest.mark.asyncio
    async def test_search_query_enhancement(self):
        """测试查询词增强 - 广州铁路职业技术学院"""
        query = "广州铁路职业技术学院计算机应用技术专业"
        
        # 1. 识别为中文查询
        assert is_chinese_query(query) is True, "应该识别为中文查询"
        print(f"\n✅ 查询识别：中文字符比例 > 30%")
        
        # 2. 识别为技术问题（包含"计算机"、"应用技术"等关键词）
        is_tech = is_technical_query(query)
        print(f"✅ 技术查询识别：{is_tech}")
        
        # 3. 查询词增强
        enhanced = enhance_query(query)
        print(f"✅ 原始查询：{query}")
        print(f"✅ 增强后的查询：{enhanced}")
        
        # 4. 非技术查询应追加官网或站点限定
        assert any(kw in enhanced for kw in [
            "官网",
            "site:zhihu.com", 
            "site:juejin.cn",
            "site:github.com",
            "site:stackoverflow.com"
        ]), f"增强查询应该包含官网或站点限定：{enhanced}"
        
        print("✅ 查询词增强验证通过")

    @pytest.mark.asyncio
    async def test_search_execution(self):
        """测试实际搜索执行 - 广州铁路职业技术学院"""
        query = "广州铁路职业技术学院计算机应用技术专业"
        
        # 增强查询词
        enhanced = enhance_query(query)
        
        # 执行搜索
        search_engine = FreeWebSearch()
        
        start_time = time.time()
        results = await search_engine.search(enhanced, count=5)
        elapsed = time.time() - start_time
        
        print(f"\n✅ 搜索执行时间：{elapsed:.2f}秒")
        print(f"✅ 搜索结果数量：{len(results)}")
        
        # 验证结果
        assert isinstance(results, list), "搜索结果应该是列表"
        assert len(results) > 0, "应该有搜索结果"
        
        # 打印结果
        for i, result in enumerate(results[:3], 1):
            print(f"\n📄 结果 {i}:")
            print(f"   标题：{result.title}")
            print(f"   来源：{result.source}")
            print(f"   URL: {result.url[:80]}..." if len(result.url) > 80 else f"   URL: {result.url}")
            if result.snippet:
                print(f"   摘要：{result.snippet[:100]}..." if len(result.snippet) > 100 else f"   摘要：{result.snippet}")
        
        # 验证质量
        if len(results) > 1:
            sorted_results = sort_by_quality(results)
            print(f"\n✅ 质量排序完成，最高分：{score_search_result(sorted_results[0]):.2f}")
        
        print("✅ 搜索执行验证通过")

    @pytest.mark.asyncio
    async def test_search_deduplication(self):
        """测试搜索结果去重 - 广州铁路职业技术学院"""
        query = "广州铁路职业技术学院计算机应用技术专业"
        enhanced = enhance_query(query)
        
        search_engine = FreeWebSearch()
        results = await search_engine.search(enhanced, count=5)
        
        # 模拟添加重复结果
        if len(results) > 0:
            # 复制第一个结果作为"重复"
            from app.utils.web_search import SearchResult as WebSearchResult
            duplicate = WebSearchResult(
                title=results[0].title,
                url=results[0].url.split('?')[0] + "?param=test",  # 相同基础 URL，不同参数
                snippet="duplicate test"
            )
            results.append(duplicate)
        
        # 去重
        deduped = deduplicate_results(results)
        
        print(f"\n✅ 去重前：{len(results)}个结果")
        print(f"✅ 去重后：{len(deduped)}个结果")
        
        # 验证去除了重复
        assert len(deduped) < len(results), "应该去除了重复结果"
        print("✅ 去重验证通过")

    @pytest.mark.asyncio
    async def test_api_endpoint_if_available(self, auth_headers):
        """测试 /api/v1/code 接口 - 广州铁路职业技术学院"""
        if not APP_AVAILABLE:
            pytest.skip("⚠️  App 不可用，跳过 API 测试")
            return
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            query = "广州铁路职业技术学院计算机应用技术专业"
            
            payload = {
                "prompt": query,
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,
                "search_count": 5
            }
            
            print(f"\n🔍 测试 /api/v1/code 接口")
            print(f"📝 查询词：{query}")
            
            start_time = time.time()
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=120.0
            )
            elapsed = time.time() - start_time
            
            print(f"✅ 响应状态码：{response.status_code}")
            print(f"✅ 响应时间：{elapsed:.2f}秒")
            
            # 验证响应
            assert response.status_code in [200, 201], f"请求失败：{response.status_code}"
            
            # 检查响应内容
            if response.headers.get("content-type") == "application/json":
                data = response.json()
                print(f"✅ 响应数据：{str(data)[:200]}...")
            else:
                print(f"✅ 响应文本长度：{len(response.text)}字符")
            
            print("✅ API 测试通过")


# ============================================================================
# 运行测试
# ============================================================================

if __name__ == "__main__":
    print("=" * 70)
    print("广州铁路职业技术学院计算机应用技术专业 - 搜索功能测试")
    print("=" * 70)
    
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-s",  # 打印输出
        "-k", "not api_endpoint" if not APP_AVAILABLE else ""
    ])
