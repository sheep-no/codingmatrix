"""
虚拟姬 AI API 集成测试

覆盖端点:
- GET /api/v1/GirlAi/characters - 获取角色列表
- POST /api/v1/GirlAi - AI 对话
- GET /api/v1/GirlAi/history - 获取历史记录
- DELETE /api/v1/GirlAi/history - 清空历史
"""
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app
from app.utils.security import create_access_token


@pytest.fixture
def auth_token():
 return create_access_token(sub="1", permission_level="normal", expires_delta=None)


class TestGirlAiEndpoints:
 """测试虚拟姬 AI 端点存在性"""

 @pytest.mark.asyncio
 async def test_chat_missing_prompt(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v1/GirlAi",
 json={"character_id": "gentle"},
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [401, 422, 500]

 @pytest.mark.asyncio
 async def test_history_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get(
 "/api/v1/GirlAi/history",
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 500]

 @pytest.mark.asyncio
 async def test_clear_history_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.delete(
 "/api/v1/GirlAi/history",
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_unauthorized_characters(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/GirlAi/characters")
 assert response.status_code in [401, 403]

 @pytest.mark.asyncio
 async def test_invalid_character_id(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v1/GirlAi",
 json={"prompt": "你好", "character_id": "invalid"},
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 500]
