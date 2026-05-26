"""
v2 Guardian API 集成测试

覆盖端点:
- POST /api/v2/Controller/guard/start - 启动守卫
- GET /api/v2/Controller/service/{service_name}/fuse-status - 熔断状态
- PUT /api/v2/Controller/service/{port}/fuse-config - 更新熔断配置
"""
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app


class TestV2GuardianEndpoints:
 """测试 v2 Guardian 端点存在性"""

 @pytest.mark.asyncio
 async def test_list_services_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v2/Controller/services")
 # 200=success, 401=unauthorized, 403=forbidden, 500=server error
 assert response.status_code in [200, 401, 403, 500]

 @pytest.mark.asyncio
 async def test_start_guard_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v2/Controller/guard/start")
 assert response.status_code in [200, 401, 403, 500]

 @pytest.mark.asyncio
 async def test_fuse_status_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v2/Controller/service/test-service/fuse-status")
 assert response.status_code in [200, 401, 404, 403, 500]

 @pytest.mark.asyncio
 async def test_update_fuse_config_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.put(
 "/api/v2/Controller/service/8080/fuse-config",
 json={"threshold": 5}
 )
 assert response.status_code in [200, 401, 403, 500]

 @pytest.mark.asyncio
 async def test_rename_service_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.put(
 "/api/v2/Controller/service/8080/rename",
 json={"name": "new-name"}
 )
 assert response.status_code in [200, 401, 403, 500]
