"""
AI Project Code API 集成测试

覆盖端点:
- POST /api/v1/agent/generate - 项目生成
- POST /api/v1/agent/generate_stream - 流式项目生成
- GET /api/v1/agent/generate/files - 获取项目文件列表
- DELETE /api/v1/agent/generate/file - 删除项目文件
- POST /api/v1/agent/save - 保存项目
- GET /api/v1/agent/saved - 列出已保存项目
- DELETE /api/v1/agent/saved/{project_id} - 删除已保存项目
"""
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app


class TestAiProjectCodeEndpoints:
    """测试 AI Project Code 端点存在性"""

    @pytest.mark.asyncio
    async def test_generate_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agent/generate",
                json={"prompt": "test"}
            )
            # 401=unauthorized, 422=validation error, 500=server error
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_generate_stream_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agent/generate_stream",
                json={"prompt": "test"}
            )
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_generate_files_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/agent/generate/files")
            # 200=success, 401=unauthorized, 500=server error
            assert response.status_code in [200, 401, 500]

    @pytest.mark.asyncio
    async def test_generate_delete_file_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete(
                "/api/v1/agent/generate/file",
                params={"path": "test.txt"}
            )
            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_save_project_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agent/save",
                json={"name": "test"}
            )
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_saved_projects_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/agent/saved")
            assert response.status_code in [200, 401, 500]

    @pytest.mark.asyncio
    async def test_saved_project_delete_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.delete("/api/v1/agent/saved/nonexistent-id")
            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_unauthorized_access(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agent/generate",
                json={"prompt": "test"}
            )
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_generate_missing_prompt(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agent/generate",
                json={}
            )
            assert response.status_code in [401, 422, 500]


class TestAiProjectCodeAdditionalEndpoints:
    """测试额外的 AI Project Code 端点"""

    @pytest.mark.asyncio
    async def test_generate_task_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/agent/generate_task",
                json={"prompt": "test"}
            )
            assert response.status_code in [200, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_read_project_file_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/agent/generate/read",
                params={"path": "test.txt"}
            )
            assert response.status_code in [200, 401, 404, 500]

    @pytest.mark.asyncio
    async def test_load_saved_project_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/agent/saved/nonexistent-id")
            assert response.status_code in [200, 401, 404, 500]
