"""
视觉分析 API 单元测试

覆盖视觉分析模块的核心端点：
- 图像分析
- OCR 识别
- 图像代码提取
- 图像安全检查
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


class TestVisionEndpointsExist:
    @pytest.mark.asyncio
    async def test_analyze_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/vision/analyze", json={"image": "base64data"})
            assert response.status_code in [200, 401, 422, 429, 500]

    @pytest.mark.asyncio
    async def test_ocr_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/vision/ocr", json={"image": "base64data"})
            assert response.status_code in [200, 401, 422, 429, 500]

    @pytest.mark.asyncio
    async def test_code_from_image_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/vision/code-from-image", json={"image": "base64data"})
            assert response.status_code in [200, 401, 422, 429, 500]

    @pytest.mark.asyncio
    async def test_check_safety_endpoint_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/vision/check-safety", json={"image": "base64data"})
            assert response.status_code in [200, 401, 422, 429, 500]


class TestVisionAuthentication:
    @pytest.mark.asyncio
    async def test_analyze_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/vision/analyze", json={"image": "base64data"})
            assert response.status_code in [401, 429]

    @pytest.mark.asyncio
    async def test_ocr_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/vision/ocr", json={"image": "base64data"})
            assert response.status_code in [401, 429]

    @pytest.mark.asyncio
    async def test_code_from_image_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/vision/code-from-image", json={"image": "base64data"})
            assert response.status_code in [401, 429]

    @pytest.mark.asyncio
    async def test_check_safety_requires_auth(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/vision/check-safety", json={"image": "base64data"})
            assert response.status_code in [401, 429]
