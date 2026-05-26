"""
健康检查 API 集成测试

覆盖端点:
- GET /api/v1/health - 基础健康检查
- GET /api/v1/health/ready - 就绪检查
- GET /api/v1/health/live - 存活检查
"""
import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app


class TestHealthEndpoints:
    """测试健康检查端点存在性"""

    @pytest.mark.asyncio
    async def test_health_check_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
            assert response.status_code in [200, 500, 503]
            data = response.json()
            assert "status" in data
            assert "timestamp" in data

    @pytest.mark.asyncio
    async def test_health_ready_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            assert response.status_code in [200, 500, 503]
            data = response.json()
            assert "status" in data
            assert "checks" in data

    @pytest.mark.asyncio
    async def test_health_live_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/live")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "alive"

    @pytest.mark.asyncio
    async def test_health_detailed_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/detailed")
            assert response.status_code in [200, 500, 503]

    @pytest.mark.asyncio
    async def test_health_metrics_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/metrics")
            assert response.status_code in [200, 500]

    @pytest.mark.asyncio
    async def test_health_models_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/models")
            assert response.status_code in [200, 500]


class TestHealthResponseStructure:
    """测试健康检查响应结构"""

    @pytest.mark.asyncio
    async def test_health_returns_version(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
            data = response.json()
            if "status" in data and data["status"] == "healthy":
                assert "version" in data

    @pytest.mark.asyncio
    async def test_ready_checks_database_and_redis(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            data = response.json()
            if "checks" in data:
                assert "database" in data["checks"]
                assert "redis" in data["checks"]
