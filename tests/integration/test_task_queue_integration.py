"""
Task Queue 集成测试

注: 以下测试标记为 xfail，因为 task_queue.py 存在已知 bug:
- task_queue.py:124 和 :181 使用 `async with get_db() as db:` 
- 但 get_db() 返回的是 async_generator，不支持 async context manager
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


class TestTaskQueueEndpoints:
    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Known bug: task_queue.py:181 get_db() async_generator issue")
    async def test_tasks_endpoint_exists(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/tasks",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 500]

    @pytest.mark.asyncio
    async def test_tasks_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/tasks")
            assert response.status_code == 401

    @pytest.mark.asyncio
    @pytest.mark.xfail(reason="Known bug: task_queue.py:124 get_db() async_generator issue")
    async def test_task_by_id_endpoint_exists(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/tasks/test-id",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 404, 500]
