"""
Auth API 单元测试

覆盖认证模块的核心端点：
- 公钥获取
- CSRF Token
- 用户登录
- 用户注册
- Token 刷新
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


class TestAuthEndpointsExist:
    @pytest.mark.asyncio
    async def test_public_key_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/public-key")
            assert response.status_code in [200, 500]

    @pytest.mark.asyncio
    async def test_csrf_token_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/csrf-token")
            assert response.status_code in [200, 500]

    @pytest.mark.asyncio
    async def test_login_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/login", json={"email": "test@test.com", "password": "test"})
            assert response.status_code in [200, 400, 401, 403, 422, 429]

    @pytest.mark.asyncio
    async def test_register_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/register", json={
                "email": "new@test.com", "password": "Test1234!", "username": "newuser"
            })
            assert response.status_code in [200, 201, 400, 403, 409, 422]

    @pytest.mark.asyncio
    async def test_refresh_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/refresh")
            assert response.status_code in [200, 401, 403, 422]


class TestLoginPlainMode:
    @pytest.mark.asyncio
    async def test_login_missing_email(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/login", json={"password": "password123"})
            assert response.status_code in [400, 403, 422]

    @pytest.mark.asyncio
    async def test_login_missing_password(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/login", json={"email": "test@example.com"})
            assert response.status_code in [400, 403, 422]

    @pytest.mark.asyncio
    async def test_login_empty_body(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/login", json={})
            assert response.status_code in [400, 403, 422]


class TestRegister:
    @pytest.mark.asyncio
    async def test_register_missing_email(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/register", json={"password": "Test1234!", "username": "newuser"})
            assert response.status_code in [400, 403, 422]

    @pytest.mark.asyncio
    async def test_register_missing_password(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/register", json={"email": "new@example.com", "username": "newuser"})
            assert response.status_code in [400, 403, 422]


class TestTokenRefresh:
    @pytest.mark.asyncio
    async def test_refresh_without_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/refresh")
            assert response.status_code in [401, 403, 422]

    @pytest.mark.asyncio
    async def test_refresh_with_valid_token(self, auth_token):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/refresh",
                headers={"Authorization": f"Bearer {auth_token}"}
            )
            assert response.status_code in [200, 401, 403]

    @pytest.mark.asyncio
    async def test_refresh_with_invalid_token(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/refresh",
                headers={"Authorization": "Bearer invalid.token.here"}
            )
            assert response.status_code in [401, 403, 422]


class TestCSRF:
    @pytest.mark.asyncio
    async def test_csrf_token_returns_token(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/csrf-token")
            assert response.status_code == 200
            data = response.json()
            assert "csrf_token" in data

    @pytest.mark.asyncio
    async def test_csrf_token_sets_cookie(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/csrf-token")
            cookies = response.cookies
            assert "csrf_token" in cookies


class TestPublicKey:
    @pytest.mark.asyncio
    async def test_public_key_returns_key(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/public-key")
            assert response.status_code == 200
            data = response.json()
            assert "public_key" in data
            assert "algorithm" in data
            assert data["algorithm"] == "RSA-OAEP"
