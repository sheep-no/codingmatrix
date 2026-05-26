"""
aicloud API 集成测试

注意：这些测试验证 API 端点的存在性和认证机制。
数据库相关功能（权限检查、受保护路径验证）通过单元测试覆盖。
"""
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app
from app.utils.security import create_access_token


@pytest.fixture
def auth_token_super():
 """生成超级用户 JWT token"""
 return create_access_token(
 sub="1",
 permission_level="super",
 expires_delta=None
 )


@pytest.fixture
def auth_token_normal():
 """生成普通用户 JWT token"""
 return create_access_token(
 sub="2",
 permission_level="normal",
 expires_delta=None
 )


class TestAicloudEndpointsExist:
 """测试 aicloud 端点存在性"""

 @pytest.mark.asyncio
 async def test_chat_endpoint_exists(self):
 """验证 chat 端点存在"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/aicloud/chat")
 assert response.status_code in [200, 401, 403, 422]

 @pytest.mark.asyncio
 async def test_history_endpoint_exists(self):
 """验证 history 端点存在"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/aicloud/history")
 assert response.status_code in [200, 401]

 @pytest.mark.asyncio
 async def test_read_endpoint_exists(self):
 """验证 read 端点存在"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/aicloud/read")
 assert response.status_code in [200, 401, 422]

 @pytest.mark.asyncio
 async def test_write_endpoint_exists(self):
 """验证 write 端点存在"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/aicloud/write")
 assert response.status_code in [200, 401, 422]

 @pytest.mark.asyncio
 async def test_reviews_endpoint_exists(self):
 """验证 reviews 端点存在"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/aicloud/reviews")
 assert response.status_code in [200, 401]

 @pytest.mark.asyncio
 async def test_reviews_approve_endpoint_exists(self):
 """验证 reviews/approve 端点存在"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/aicloud/reviews/approve")
 assert response.status_code in [200, 401, 422]

 @pytest.mark.asyncio
 async def test_reviews_reject_endpoint_exists(self):
 """验证 reviews/reject 端点存在"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/aicloud/reviews/reject")
 assert response.status_code in [200, 401, 422]

 @pytest.mark.asyncio
 async def test_audit_logs_endpoint_exists(self):
 """验证 audit-logs 端点存在"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/aicloud/audit-logs")
 assert response.status_code in [200, 401]


class TestAicloudAuthentication:
 """测试 aicloud 认证机制"""

 @pytest.mark.asyncio
 async def test_history_requires_auth(self):
 """测试 history 端点需要认证"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/aicloud/history")
 assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_chat_requires_auth(self):
 """测试 chat 端点需要认证"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v1/aicloud/chat",
 json={"message": "test", "session_id": "test"}
 )
 assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_reviews_requires_auth(self):
 """测试 reviews 端点需要认证"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/aicloud/reviews")
 assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_audit_logs_requires_auth(self):
 """测试 audit-logs 端点需要认证"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/aicloud/audit-logs")
 assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_read_requires_auth(self):
 """测试 read 端点需要认证"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v1/aicloud/read",
 json={"file_path": "/sandbox/1/test.txt"}
 )
 assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_write_requires_auth(self):
 """测试 write 端点需要认证"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v1/aicloud/write",
 json={"file_path": "/sandbox/1/test.txt", "content": "test"}
 )
 assert response.status_code == 401
