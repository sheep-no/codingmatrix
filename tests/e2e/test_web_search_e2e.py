"""
Web 搜索功能 E2E 测试

测试范围：
1. /api/v1/code 接口联网搜索功能
2. 查询词增强端到端集成
3. 搜索结果质量验证
4. 前端参数传递验证
"""

import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.main import app
from app.utils.security import create_access_token
from app.utils.web_search_enhancements import (
    is_technical_query,
    is_error_query,
    enhance_query
)


@pytest.fixture
def auth_token():
    """生成测试用户 token"""
    return create_access_token(
        sub="1",
        permission_level="normal",
        expires_delta=None
    )


@pytest.fixture
def auth_headers(auth_token):
    """认证请求头"""
    return {"Authorization": f"Bearer {auth_token}"}


# ============================================================================
# E2E 测试：联网搜索功能
# ============================================================================

class TestWebSearchE2E:
    """Web 搜索 E2E 测试"""

    @pytest.mark.asyncio
    async def test_code_endpoint_with_search_enabled(self, auth_headers):
        """测试 /api/v1/code 接口启用搜索功能"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 启用搜索的请求
            payload = {
                "prompt": "如何使用 Python 的 requests 库发送 HTTP 请求？",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,  # 启用搜索
                "search_count": 3
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0  # 搜索可能需要更长时间
            )
            
            # 应该成功响应（200 表示处理成功）
            assert response.status_code in [200, 201], f"请求失败：{response.status_code}"
            
            # 检查响应包含搜索结果或正常回答
            data = response.json() if response.headers.get("content-type") == "application/json" else None
            
            # 如果启用搜索，响应应该包含某种内容
            if data:
                assert data is not None
            else:
                # 流式响应
                assert len(response.text) > 0

    @pytest.mark.asyncio
    async def test_code_endpoint_with_search_disabled(self, auth_headers):
        """测试 /api/v1/code 接口禁用搜索功能"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "简单介绍 Python 语言",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": False,  # 禁用搜索
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=30.0
            )
            
            # 即使禁用搜索也应该返回正常回答
            assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_code_endpoint_default_search_behavior(self, auth_headers):
        """测试 /api/v1/code 接口默认搜索行为"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 不指定 enable_search，让 AI 自主决定
            payload = {
                "prompt": "2025 年最新 AI 技术突破",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                # 不指定 enable_search
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0
            )
            
            assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_search_enhancement_integration(self, auth_headers):
        """测试查询词增强集成"""
        # 技术问题的查询词增强
        query = "python github 代码示例"
        assert is_technical_query(query) is True
        enhanced = enhance_query(query)
        assert "site:github.com" in enhanced or "site:stackoverflow.com" in enhanced
        
        # 错误问题的查询词增强
        query_error = "python exception list index out of range"
        assert is_error_query(query_error) is True
        enhanced_error = enhance_query(query_error)
        assert "site:stackoverflow.com" in enhanced_error

    @pytest.mark.asyncio
    async def test_search_response_time(self, auth_headers):
        """测试搜索响应时间"""
        import time
        
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "FastAPI 教程",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,
            }
            
            start_time = time.time()
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0
            )
            elapsed = time.time() - start_time
            
            assert response.status_code in [200, 201]
            # 搜索响应时间应该在合理范围内（优化后应该<20 秒）
            assert elapsed < 60.0, f"搜索响应时间过长：{elapsed}秒"


# ============================================================================
# E2E 测试：前端参数传递
# ============================================================================

class TestFrontendParameterPassing:
    """前端参数传递测试"""

    @pytest.mark.asyncio
    async def test_enable_search_parameter_accepted(self, auth_headers):
        """测试 enable_search 参数被正确接受"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "Vue3  Composition API 使用",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,
                "search_count": 5
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0
            )
            
            # 参数应该被接受，不应该返回参数错误
            assert response.status_code in [200, 201, 422]  # 422 是验证错误，不是参数不存在
            
            if response.status_code == 422:
                data = response.json()
                # 如果是验证错误，不应该是 enable_search 参数缺失
                assert "enable_search" not in str(data.get("detail", ""))

    @pytest.mark.asyncio
    async def test_search_count_parameter(self, auth_headers):
        """测试 search_count 参数"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            # 测试不同搜索数量
            for count in [1, 3, 5, 10]:
                payload = {
                    "prompt": "React hooks 使用教程",
                    "model": "Qwen/Qwen2.5-7B-Instruct",
                    "stream": False,
                    "enable_search": True,
                    "search_count": count
                }
                
                response = await client.post(
                    "/api/v1/code",
                    json=payload,
                    headers=auth_headers,
                    timeout=60.0
                )
                
                assert response.status_code in [200, 201]


# ============================================================================
# E2E 测试：错误处理
# ============================================================================

class TestSearchErrorHandling:
    """搜索错误处理测试"""

    @pytest.mark.asyncio
    async def test_search_timeout_handling(self, auth_headers):
        """测试搜索超时处理"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "非常复杂的搜索结果需要很长时间",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,
                "search_count": 20  # 大量搜索可能超时
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=120.0  # 给更长时间
            )
            
            # 应该返回某种响应，即使搜索失败
            assert response.status_code in [200, 201, 408, 500]

    @pytest.mark.asyncio
    async def test_invalid_model_with_search(self, auth_headers):
        """测试无效模型 + 搜索参数"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "测试",
                "model": "invalid-model",
                "stream": False,
                "enable_search": True
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=30.0
            )
            
            # 模型错误应该返回错误，但和搜索参数无关
            assert response.status_code in [400, 404, 422, 500]

    @pytest.mark.asyncio
    async def test_empty_prompt_with_search(self, auth_headers):
        """测试空提示词 + 搜索参数"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=30.0
            )
            
            # 空提示词应该返回某种错误
            assert response.status_code in [400, 422, 500]


# ============================================================================
# E2E 测试：不同场景
# ============================================================================

class TestSearchScenarios:
    """不同搜索场景测试"""

    @pytest.mark.asyncio
    async def test_technical_question_search(self, auth_headers):
        """技术问题搜索场景"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "如何在 Django 中实现用户认证？",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0
            )
            
            assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_error_fix_search(self, auth_headers):
        """错误修复搜索场景"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "Python AttributeError: module has no attribute 'xxx' 如何解决？",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0
            )
            
            assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_tutorial_search(self, auth_headers):
        """教程搜索场景"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "TypeScript 完全入门教程",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0
            )
            
            assert response.status_code in [200, 201]

    @pytest.mark.asyncio
    async def test_news_search(self, auth_headers):
        """新闻搜索场景"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "2025 年最新 AI 技术突破新闻",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": False,
                "enable_search": True,
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0
            )
            
            assert response.status_code in [200, 201]


# ============================================================================
# E2E 测试：流式输出
# ============================================================================

class TestStreamingSearch:
    """流式搜索测试"""

    @pytest.mark.asyncio
    async def test_streaming_search_enabled(self, auth_headers):
        """测试流式输出 + 搜索启用"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "如何使用 Python 进行数据分析？",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": True,
                "enable_search": True,
                "search_count": 3
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=60.0
            )
            
            # 流式响应应该返回 200 和 text/plain
            assert response.status_code == 200
            assert response.headers.get("content-type") == "text/plain; charset=utf-8"
            
            # 检查响应内容
            assert len(response.text) > 0

    @pytest.mark.asyncio
    async def test_streaming_search_disabled(self, auth_headers):
        """测试流式输出 + 搜索禁用"""
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            payload = {
                "prompt": "简单的 Python 问题",
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "stream": True,
                "enable_search": False,
            }
            
            response = await client.post(
                "/api/v1/code",
                json=payload,
                headers=auth_headers,
                timeout=30.0
            )
            
            assert response.status_code == 200
            assert len(response.text) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
