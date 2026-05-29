"""
调试搜索功能 - 检查搜索是否真正执行
"""

import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from app.main import app
from app.utils.security import create_access_token

# 启用详细日志
logging.basicConfig(level=logging.DEBUG)

@pytest.fixture
def auth_token():
    return create_access_token(sub="1", permission_level="normal")

@pytest.fixture
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.mark.asyncio
async def test_debug_search_execution(auth_headers):
    """调试搜索是否真正执行"""
    
    print("\n" + "=" * 80)
    print("🔍 调试搜索执行流程")
    print("=" * 80)
    
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        query = "广州铁路职业技术学院计算机应用技术专业"
        
        payload = {
            "prompt": query,
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "stream": False,
            "enable_search": True,  # 明确启用搜索
            "search_count": 5
        }
        
        print(f"\n📝 查询：{query}")
        print(f"🔍 enable_search: True")
        print(f"📊 search_count: 5")
        
        response = await client.post(
            "/api/v1/code",
            json=payload,
            headers=auth_headers,
            timeout=120.0
        )
        
        print(f"\n✅ 状态码：{response.status_code}")
        
        data = response.json()
        
        print("\n" + "-" * 80)
        print("📦 完整响应")
        print("-" * 80)
        
        # 检查是否有搜索相关字段
        for key, value in data.items():
            if 'search' in key.lower() or 'context' in key.lower():
                print(f"{key}: {value}")
        
        print("\n" + "-" * 80)
        print("💬 AI 回答")
        print("-" * 80)
        print(data.get("response", "No response"))
        
        # 关键问题检查
        print("\n" + "=" * 80)
        print("❓ 问题检查")
        print("=" * 80)
        
        response_text = data.get("response", "")
        
        # 1. 检查是否有搜索结果
        if "[网络搜索结果]" in response_text:
            print("✅ 响应中包含搜索结果标记")
        else:
            print("❌ 响应中**没有**搜索结果标记")
        
        # 2. 检查是否有提示词泄漏
        if "user\n" in response_text or "请回答以下问题" in response_text:
            print("❌ 发现提示词泄漏！")
        else:
            print("✅ 没有提示词泄漏")
        
        # 3. 检查回答完整性
        if "以下几个方面" in response_text and response_text.count("1") > 2:
            print("❌ 回答不完整（提到'以下几个方面'但没有列出）")
        else:
            print("✅ 回答完整")
        
        # 4. 检查是否有具体信息
        keywords = ["课程", "学校", "培养", "专业", "学习"]
        has_info = any(kw in response_text for kw in keywords)
        if has_info:
            print(f"✅ 包含具体信息")
        else:
            print("❌ 缺少具体信息")
        
        print("\n" + "=" * 80)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
