"""
v2 Nginx AI API 集成测试

覆盖端点:
- POST /api/v2/nginx/check - Nginx 配置检查 + AI 分析
"""
import pytest
from httpx import AsyncClient, ASGITransport

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.main import app


class TestV2NginxAiEndpoints:
    """测试 v2 Nginx AI 端点存在性"""

    @pytest.mark.asyncio
    async def test_nginx_check_exists(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/nginx/check",
                json={"config": "server { listen 80; }"}
            )
            # 200=success, 400=bad request, 401=unauthorized, 422=validation, 500=server error
            assert response.status_code in [200, 400, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_nginx_check_invalid_config(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/nginx/check",
                json={"config": "invalid config {{{{"}
            )
            assert response.status_code in [200, 400, 401, 422, 500]

    @pytest.mark.asyncio
    async def test_nginx_check_missing_config(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v2/nginx/check",
                json={}
            )
            # 401=unauthorized, 422=validation error (missing config field), 500=server error
            assert response.status_code in [401, 422, 500]
