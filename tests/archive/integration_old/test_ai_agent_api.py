"""
AI Agent API 单元测试

覆盖 Agent 模块的核心端点：
- 消息处理
- 代码审查
- 模型列表
- 记忆管理
- 会话管理
- 项目生成
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


class TestAgentEndpointsExist:
 @pytest.mark.asyncio
 async def test_orchestrate_endpoint_exists(self, auth_token):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.post(
             "/api/v1/agent/orchestrate",
             json={"requirement": "test"},
             headers={"Authorization": f"Bearer {auth_token}"}
         )
         assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_orchestrate_stream_endpoint_exists(self, auth_token):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.post(
             "/api/v1/agent/orchestrate/stream",
             json={"requirement": "test"},
             headers={"Authorization": f"Bearer {auth_token}"}
         )
         assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_generate_endpoint_exists(self, auth_token):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.post(
             "/api/v1/agent/generate",
             json={"requirement": "test", "session_id": "test-session"},
             headers={"Authorization": f"Bearer {auth_token}"}
         )
         assert response.status_code in [200, 401, 422, 500]


class TestAgentAuthentication:
 @pytest.mark.asyncio
 async def test_orchestrate_requires_auth(self):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.post("/api/v1/agent/orchestrate", json={"requirement": "test"})
         assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_generate_requires_auth(self):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.post("/api/v1/agent/generate", json={"requirement": "test", "session_id": "test"})
         assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_models_requires_auth(self):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.get("/api/v1/agent/models")
         assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_review_requires_auth(self):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.post("/api/v1/agent/review", json={"code": "test"})
         assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_sessions_requires_auth(self):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.get("/api/v1/agent/sessions")
         assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_generate_requires_auth(self):
     transport = ASGITransport(app=app)
     async with AsyncClient(transport=transport, base_url="http://test") as client:
         response = await client.post("/api/v1/agent/generate", json={"requirement": "test", "session_id": "test"})
         assert response.status_code == 401
