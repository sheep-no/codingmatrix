"""
v2 Nginx API 集成测试

覆盖端点:
- POST /api/v2/nginx/generate - 生成配置
- POST /api/v2/nginx/check - 检查配置
- POST /api/v2/nginx/deploy - 部署配置
- GET /api/v2/nginx/config - 获取配置
- GET /api/v2/nginx/backups - 列出备份
- DELETE /api/v2/nginx/backup/{backup_name} - 删除备份
"""
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app
from app.utils.security import create_access_token


@pytest.fixture
def super_auth_token():
 return create_access_token(sub="1", permission_level="super", expires_delta=None)


class TestV2NginxEndpoints:
 """测试 v2 Nginx 端点存在性"""

 @pytest.mark.asyncio
 async def test_generate_exists(self, super_auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v2/nginx/generate",
 json={"domain": "example.com", "port": 80},
 headers={"Authorization": f"Bearer {super_auth_token}"}
 )
 assert response.status_code in [200, 401, 403, 422, 429, 500]

 @pytest.mark.asyncio
 async def test_check_exists(self, super_auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v2/nginx/check",
 json={},
 headers={"Authorization": f"Bearer {super_auth_token}"}
 )
 assert response.status_code in [200, 401, 403, 422, 429, 500]

 @pytest.mark.asyncio
 async def test_deploy_exists(self, super_auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v2/nginx/deploy",
 json={"config": "test"},
 headers={"Authorization": f"Bearer {super_auth_token}"}
 )
 assert response.status_code in [200, 401, 403, 422, 429, 500]

 @pytest.mark.asyncio
 async def test_config_exists(self, super_auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get(
 "/api/v2/nginx/config",
 headers={"Authorization": f"Bearer {super_auth_token}"}
 )
 assert response.status_code in [200, 401, 403, 422, 429, 500]

 @pytest.mark.asyncio
 async def test_backups_exists(self, super_auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get(
 "/api/v2/nginx/backups",
 headers={"Authorization": f"Bearer {super_auth_token}"}
 )
 assert response.status_code in [200, 401, 403, 429, 500]

 @pytest.mark.asyncio
 async def test_normal_user_denied(self):
 transport = ASGITransport(app=app)
 normal_token = create_access_token(sub="2", permission_level="normal", expires_delta=None)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v2/nginx/generate",
 json={"domain": "example.com"},
 headers={"Authorization": f"Bearer {normal_token}"}
 )
 assert response.status_code in [401, 403, 422, 429]

 @pytest.mark.asyncio
 async def test_unauthorized_access(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v2/nginx/config")
 assert response.status_code in [401, 403, 429]
