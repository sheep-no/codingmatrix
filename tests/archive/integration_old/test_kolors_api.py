"""
Kolors 图像生成 API 单元测试
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


class TestKolorsEndpointsExist:
 @pytest.mark.asyncio
 async def test_text_to_image_endpoint_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/kolors/text-to-image", json={"prompt": "test"})
 assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_image_to_image_endpoint_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/kolors/image-to-image", json={"prompt": "test"})
 assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_inpaint_endpoint_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/kolors/inpaint", json={"prompt": "test"})
 assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_avatar_endpoint_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/kolors/avatar", json={"prompt": "test"})
 assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_config_endpoint_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/kolors/config", headers={"Authorization": f"Bearer {auth_token}"})
 assert response.status_code in [200, 401, 500]


class TestKolorsAuthentication:
 @pytest.mark.asyncio
 async def test_text_to_image_requires_auth(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/kolors/text-to-image", json={"prompt": "test"})
 assert response.status_code == 401

 @pytest.mark.asyncio
 async def test_image_to_image_requires_auth(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post("/api/v1/kolors/image-to-image", json={"prompt": "test"})
 assert response.status_code == 401
