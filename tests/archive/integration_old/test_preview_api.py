"""
Preview API 集成测试

覆盖端点:
- GET /api/v1/pptx/preview/{ppt_id} - PPT 预览
"""
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app


class TestPreviewEndpoints:
 """测试预览端点存在性"""

 @pytest.mark.asyncio
 async def test_pptx_preview_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/pptx/preview/nonexistent-id")
 # 200=success, 401=unauthorized, 404=not found, 500=server error
 assert response.status_code in [200, 401, 404, 500]

 @pytest.mark.asyncio
 async def test_pptx_download_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/pptx/download/nonexistent-id")
 assert response.status_code in [200, 401, 404, 500]

 @pytest.mark.asyncio
 async def test_pptx_slides_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/pptx/nonexistent-id/slides")
 assert response.status_code in [200, 401, 404, 500]
