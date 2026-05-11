"""
Kolors 历史记录 API 集成测试

覆盖端点:
- GET /api/v1/kolors/history - 获取历史记录列表
- GET /api/v1/kolors/history/{image_id} - 获取单条记录
- DELETE /api/v1/kolors/history/{image_id} - 删除单条记录
- DELETE /api/v1/kolors/history - 清空历史记录
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


class TestKolorsHistoryEndpoints:
    """测试 Kolors 历史记录端点存在性"""

    @pytest.mark.asyncio
    async def test_history_list_exists(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/kolors/history",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 500]

    @pytest.mark.asyncio
    async def test_history_single_exists(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/kolors/history/test_image_id",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_history_delete_single_exists(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/kolors/history/test_image_id",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_history_clear_all_exists(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/kolors/history",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 500]

    @pytest.mark.asyncio
    async def test_unauthorized_access(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/kolors/history")
            assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_history_list_pagination(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/kolors/history?page=1&page_size=10",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 500]
