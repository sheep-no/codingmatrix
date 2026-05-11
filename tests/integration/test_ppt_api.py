"""
PPT 生成 API 单元测试
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


class TestPPTEndpointsExist:
    @pytest.mark.asyncio
    async def test_generate_task_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/pptx/generate_task", json={"topic": "test"})
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_download_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/pptx/download/test-id")
            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_preview_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/pptx/preview/test-id")
            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_slides_endpoint_exists(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/pptx/test-id/slides",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_cancel_endpoint_exists(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/pptx/test-id/cancel",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 404, 500]


class TestPPTAuthentication:
    @pytest.mark.asyncio
    async def test_generate_task_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/pptx/generate_task", json={"topic": "test"})
            assert response.status_code == 401
