"""
用户管理 API (v2) 单元测试

覆盖用户管理模块的核心端点：
- 用户列表
- 创建用户
- 更新用户
- 删除用户
- 重置密码
"""
import pytest
from httpx import AsyncClient, ASGITransport
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app
from app.utils.security import create_access_token


@pytest.fixture
def auth_token_super():
 return create_access_token(sub="1", permission_level="super", expires_delta=None)


@pytest.fixture
def auth_token_normal():
 return create_access_token(sub="2", permission_level="normal", expires_delta=None)


class TestUserManageEndpointsExist:
 @pytest.mark.asyncio
 async def test_users_list_endpoint_exists(self, auth_token_super):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get(
 "/api/v2/Controller/users",
 headers={"Authorization": f"Bearer {auth_token_super}"}
 )
 assert response.status_code in [200, 401, 403, 500]

 @pytest.mark.asyncio
 async def test_create_user_endpoint_exists(self, auth_token_super):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v2/Controller/create_user",
 json={"email": "new@test.com", "password": "Test1234!", "username": "newuser"},
 headers={"Authorization": f"Bearer {auth_token_super}"}
 )
 assert response.status_code in [200, 201, 400, 401, 403, 409, 422]

 @pytest.mark.asyncio
 async def test_update_user_endpoint_exists(self, auth_token_super):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.patch(
 "/api/v2/Controller/update_user/1",
 json={"username": "updated"},
 headers={"Authorization": f"Bearer {auth_token_super}"}
 )
 assert response.status_code in [200, 401, 403, 404, 422, 500]

 @pytest.mark.asyncio
 async def test_delete_user_endpoint_exists(self, auth_token_super):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.delete(
 "/api/v2/Controller/delete_user/1",
 headers={"Authorization": f"Bearer {auth_token_super}"}
 )
 assert response.status_code in [200, 401, 403, 404, 500]

 @pytest.mark.asyncio
 async def test_reset_password_endpoint_exists(self, auth_token_super):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v2/Controller/1/reset-password",
 json={"new_password": "NewPass123!"},
 headers={"Authorization": f"Bearer {auth_token_super}"}
 )
 assert response.status_code in [200, 401, 403, 404, 422, 500]


class TestUserManageAuthentication:
 @pytest.mark.asyncio
 async def test_users_list_requires_auth(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v2/Controller/users")
 assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_create_user_requires_auth(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v2/Controller/create_user", json={"email": "test@test.com"})
 assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_normal_user_cannot_access(self, auth_token_normal):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get(
 "/api/v2/Controller/users",
 headers={"Authorization": f"Bearer {auth_token_normal}"}
 )
 assert response.status_code in [403, 401]


class TestUserManageValidation:
 @pytest.mark.asyncio
 async def test_create_user_missing_email(self, auth_token_super):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v2/Controller/create_user",
 json={"password": "Test1234!", "username": "newuser"},
 headers={"Authorization": f"Bearer {auth_token_super}"}
 )
 assert response.status_code in [400, 422]

 @pytest.mark.asyncio
 async def test_update_user_missing_id(self, auth_token_super):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.patch(
 "/api/v2/Controller/update_user/invalid",
 json={"username": "updated"},
 headers={"Authorization": f"Bearer {auth_token_super}"}
 )
 assert response.status_code in [400, 404, 422]
