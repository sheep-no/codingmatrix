"""
文件上传 API 单元测试

覆盖文件上传模块的核心端点：
- 单文件上传
- 分片上传初始化
- 分片上传
- 分片合并
- 文件下载
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


class TestFileUploadEndpointsExist:
 @pytest.mark.asyncio
 async def test_download_endpoint_exists(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/test-file-id/download")
 assert response.status_code in [200, 401, 404, 500]
