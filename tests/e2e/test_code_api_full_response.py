"""
广州铁路职业技术学院 - Code API 完整响应测试

测试 /api/v1/code 接口在启用搜索后的完整返回内容
"""

import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.main import app
from app.utils.security import create_access_token
from app.utils.web_search import FreeWebSearch


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


@pytest.mark.asyncio
async def test_code_api_full_response(auth_headers):
    """测试 /api/v1/code 接口完整响应 - 广州铁路职业技术学院"""
    
    print("\n" + "=" * 80)
    print("🚀 /api/v1/code API 完整响应测试")
    print("=" * 80)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        query = "广州铁路职业技术学院计算机应用技术专业"
        
        print(f"\n📝 查询词：{query}")
        print(f"🔍 启用搜索：True")
        print(f"📊 搜索结果数：5")
        print(f"🤖 模型：Qwen/Qwen2.5-7B-Instruct")
        
        payload = {
            "prompt": query,
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "stream": False,
            "enable_search": True,
            "search_count": 5
        }
        
        import time
        start_time = time.time()
        
        response = await client.post(
            "/api/v1/code",
            json=payload,
            headers=auth_headers,
            timeout=120.0
        )
        
        elapsed = time.time() - start_time
        
        print("\n" + "-" * 80)
        print("📊 响应信息")
        print("-" * 80)
        print(f"✅ 状态码：{response.status_code}")
        print(f"⏱️  响应时间：{elapsed:.2f}秒")
        print(f"📄 Content-Type: {response.headers.get('content-type')}")
        
        # 解析响应
        if response.headers.get("content-type") == "application/json":
            data = response.json()
            
            print("\n" + "-" * 80)
            print("📦 完整响应 JSON")
            print("-" * 80)
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # 验证响应结构
            assert isinstance(data, dict)
            
            # 如果有 response 字段
            if "response" in data:
                print("\n" + "-" * 80)
                print("💬 AI 回答内容")
                print("-" * 80)
                print(data["response"])
            
            # 如果有 search_results 字段（搜索相关内容）
            if "search_results" in data:
                print("\n" + "-" * 80)
                print("🔍 搜索结果")
                print("-" * 80)
                print(json.dumps(data["search_results"], indent=2, ensure_ascii=False))
            
        else:
            print("\n" + "-" * 80)
            print("📄 完整响应文本")
            print("-" * 80)
            print(response.text)
        
        print("\n" + "=" * 80)
        print("✅ 测试完成")
        print("=" * 80 + "\n")
        
        # 断言
        assert response.status_code == 200, f"请求失败：{response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
