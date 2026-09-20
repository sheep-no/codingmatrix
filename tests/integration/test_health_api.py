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
from app.utils.security import verify_token


@pytest.fixture
def auth_override():
    """/health/detailed 与 /health/metrics 需要鉴权，测试直接覆盖依赖。"""
    app.dependency_overrides[verify_token] = lambda: {"sub": "1"}
    yield
    app.dependency_overrides.clear()


class TestHealthEndpoints:
    """健康检查端点契约

    /health 与 /health/ready 在依赖故障时仍返回 200，健康状态由
    body.status 表达（healthy/unhealthy、ready/not_ready）。因此状态码
    必须严格断言 200，500/503 代表端点本身崩溃而非「依赖不健康」。
    """

    @pytest.mark.asyncio
    async def test_health_check_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in {"healthy", "unhealthy"}
            assert "timestamp" in data
            assert "version" in data

    @pytest.mark.asyncio
    async def test_health_ready_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] in {"ready", "not_ready"}
            assert "checks" in data
            assert "database" in data["checks"]
            assert "redis" in data["checks"]

    @pytest.mark.asyncio
    async def test_health_live_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/live")
            assert response.status_code == 200
            data = response.json()
            assert data.get("status") == "alive"

    @pytest.mark.asyncio
    async def test_health_detailed_exists(self, auth_override):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/detailed")
            assert response.status_code == 200
            data = response.json()
            assert "status" in data
            assert "checks" in data

    @pytest.mark.asyncio
    async def test_health_metrics_exists(self, auth_override):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/metrics")
            assert response.status_code == 200
            assert response.headers["content-type"].startswith("text/plain")

    @pytest.mark.asyncio
    async def test_health_models_exists(self):
        """模型健康端点依赖 Agent 动态路由，配置缺失时允许 500。"""
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
            assert response.status_code == 200
            data = response.json()
            assert "version" in data

    @pytest.mark.asyncio
    async def test_ready_checks_database_and_redis(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/health/ready")
            assert response.status_code == 200
            data = response.json()
            assert "database" in data["checks"]
            assert "redis" in data["checks"]
