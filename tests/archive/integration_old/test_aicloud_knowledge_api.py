"""
AI Cloud 知识库 API 集成测试

覆盖端点:
- POST /api/v1/aicloud/knowledge/upload - 上传文档
- GET /api/v1/aicloud/knowledge/docs - 获取文档列表
- DELETE /api/v1/aicloud/knowledge/docs/{doc_id} - 删除文档
- POST /api/v1/aicloud/knowledge/search - 检索知识库
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


@pytest.fixture
def super_auth_token():
 return create_access_token(sub="1", permission_level="super", expires_delta=None)


class TestAicloudKnowledgeEndpoints:
 """测试 AI Cloud 知识库端点存在性"""

 @pytest.mark.asyncio
 async def test_upload_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v1/aicloud/knowledge/upload",
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 422, 500]

 @pytest.mark.asyncio
 async def test_docs_list_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get(
 "/api/v1/aicloud/knowledge/docs",
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 500]

 @pytest.mark.asyncio
 async def test_delete_doc_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.delete(
 "/api/v1/aicloud/knowledge/docs/test_doc_id",
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 404, 500]

 @pytest.mark.asyncio
 async def test_search_exists(self, auth_token):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.post(
 "/api/v1/aicloud/knowledge/search",
 json={"query": "test"},
 headers={"Authorization": f"Bearer {auth_token}"}
 )
 assert response.status_code in [200, 401, 500]

 @pytest.mark.asyncio
 async def test_unauthorized_access(self):
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as client:
 response = await client.get("/api/v1/aicloud/knowledge/docs")
 assert response.status_code in [401, 403]
