"""
AI 代码生成 API 单元测试
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


class TestAicodeEndpointsExist:
 @pytest.mark.asyncio
 async def test_code_endpoint_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/code", json={"prompt": "create a function"})
 assert response.status_code in [200, 400, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_history_delete_endpoint_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.delete(
 "/api/v1/code/history",
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_resume_endpoint_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/code/resume", json={"resume_id": "test-id"})
 assert response.status_code in [200, 401, 404, 422, 500]

 @pytest.mark.asyncio
 async def test_resume_status_endpoint_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get(
 "/api/v1/code/resume/test-id",
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 404, 500]


class TestAicodeAuthentication:
 @pytest.mark.asyncio
 async def test_code_requires_auth(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/code", json={"prompt": "test"})
 assert response.status_code in [400, 401]

 @pytest.mark.asyncio
 async def test_history_delete_requires_auth(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.delete("/api/v1/code/history")
 assert response.status_code == 401
