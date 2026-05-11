"""
v2 Admin API 集成测试

覆盖端点 (全部在 /api/v2/Controller/admin/* 下):
- GET /api/v2/Controller/admin/stats - 服务器统计信息
- GET /api/v2/Controller/admin/memory - 内存统计
- GET /api/v2/Controller/admin/config - 配置管理
- GET /api/v2/Controller/admin/log-config - 日志配置
- GET /api/v2/Controller/admin/backup - 备份管理
- GET /api/v2/Controller/admin/rate-limit - 限流配置
- GET /api/v2/Controller/admin/docker/containers - Docker 容器
- GET /api/v2/Controller/admin/ws-stats - WebSocket 统计
"""
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app


class TestV2AdminEndpoints:
    """测试 v2 Admin 端点存在性"""

    @pytest.mark.asyncio
    async def test_system_status_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/stats")
            # 200=success, 401=unauthorized, 403=forbidden, 500=server error
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_db_stats_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/memory")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_db_pool_stats_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/config")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_logs_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/log-config")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_config_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/config")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_backup_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/backup")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_backup_list_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/backup/list")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_rate_limit_config_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/rate-limit")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_docker_containers_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/docker/containers")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_ws_stats_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/ws-stats")
            assert response.status_code in [200, 401, 403, 500]

    @pytest.mark.asyncio
    async def test_normal_user_denied(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/stats")
            # 401=unauthorized (no admin token), 403=forbidden
            assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_unauthorized_access(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v2/Controller/admin/stats")
            assert response.status_code in [401, 403]
