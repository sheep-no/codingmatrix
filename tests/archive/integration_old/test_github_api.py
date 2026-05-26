"""
GitHub 集成 API 集成测试
测试 GitHub 配置管理和项目保存功能
"""
import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.utils.security import create_access_token


@pytest.fixture
def auth_headers():
 """生成认证头"""
 token = create_access_token(
 sub="test_user_1",
 permission_level="normal",
 )
 return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def client(auth_headers):
 """创建异步 HTTP 客户端"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as c:
 c.headers.update(auth_headers)
 yield c


class TestGithubConfigEndpoints:
 """GitHub 配置端点测试"""

 @pytest.mark.asyncio
 async def test_set_github_config(self, client):
 """测试设置 GitHub 配置"""
 config_data = {
 "username": "testuser",
 "token": "ghp_test_token_12345",
 "use_github": True,
 }

 response = await client.post("/api/v1/github/config", json=config_data)

 assert response.status_code == 200
 data = response.json()
 assert data["success"] is True
 assert data["username"] == "testuser"
 assert data["use_github"] is True

 @pytest.mark.asyncio
 async def test_set_github_config_disabled(self, client):
 """测试设置禁用的 GitHub 配置"""
 config_data = {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": False,
 }

 response = await client.post("/api/v1/github/config", json=config_data)

 assert response.status_code == 200
 data = response.json()
 assert data["use_github"] is False

 @pytest.mark.asyncio
 async def test_set_github_config_invalid_token(self, client):
 """测试无效 Token 时设置配置"""
 config_data = {
 "username": "",
 "token": "",
 "use_github": True,
 }

 response = await client.post("/api/v1/github/config", json=config_data)

 # 端点接受空配置
 assert response.status_code == 200

 @pytest.mark.asyncio
 async def test_get_github_config(self, client):
 """测试获取 GitHub 配置"""
 response = await client.get("/api/v1/github/config")

 assert response.status_code == 200
 data = response.json()
 assert "username" in data
 assert "token" in data
 assert "use_github" in data

 @pytest.mark.asyncio
 async def test_get_github_config_returns_defaults(self, client):
 """测试获取配置返回默认值"""
 response = await client.get("/api/v1/github/config")

 data = response.json()
 assert data["username"] == ""
 assert data["token"] == ""
 assert data["use_github"] is False

 @pytest.mark.asyncio
 async def test_set_config_without_auth(self):
 """测试未认证时设置配置"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as c:
 response = await c.post(
 "/api/v1/github/config",
 json={"username": "test", "token": "test", "use_github": True},
 )

 # FastAPI 的依赖注入会返回 403 或其他错误
 assert response.status_code in [401, 403, 422]

 @pytest.mark.asyncio
 async def test_get_config_without_auth(self):
 """测试未认证时获取配置"""
 transport = ASGITransport(app=app)
 async with AsyncClient(transport=transport, base_url="http://test") as c:
 response = await c.get("/api/v1/github/config")

 assert response.status_code in [401, 403, 422]


class TestSaveProjectToLocalGit:
 """本地 Git 保存测试"""

 @pytest.mark.asyncio
 async def test_save_to_local_git_success(self, client):
 """测试成功保存到本地 Git"""
 project_data = {
 "project_name": "test_project",
 "project_description": "A test project",
 "project_data": json.dumps({
 "main.py": "print('Hello, World!')",
 "README.md": "# Test Project",
 }),
 "github_config": {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": False,
 },
 }

 response = await client.post("/api/v1/github/save", json=project_data)

 assert response.status_code == 200
 data = response.json()
 assert data["success"] is True
 assert "本地 Git" in data["message"] or "local" in data["message"].lower()
 assert data["repo_url"] is not None
 assert data["commit_id"] is not None

 @pytest.mark.asyncio
 async def test_save_to_local_git_with_nested_files(self, client):
 """测试保存包含嵌套目录的项目"""
 project_data = {
 "project_name": "nested_project",
 "project_description": "Project with nested files",
 "project_data": json.dumps({
 "src/main.py": "from utils import helper",
 "src/utils/helper.py": "def helper(): pass",
 "tests/test_main.py": "def test_main(): pass",
 "README.md": "# Nested Project",
 }),
 "github_config": {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": False,
 },
 }

 response = await client.post("/api/v1/github/save", json=project_data)

 assert response.status_code == 200
 data = response.json()
 assert data["success"] is True

 @pytest.mark.asyncio
 async def test_save_to_local_git_empty_files(self, client):
 """测试保存空文件项目"""
 project_data = {
 "project_name": "empty_project",
 "project_description": "",
 "project_data": json.dumps({
 "empty.py": "",
 }),
 "github_config": {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": False,
 },
 }

 response = await client.post("/api/v1/github/save", json=project_data)

 assert response.status_code == 200
 data = response.json()
 assert data["success"] is True


class TestSaveProjectToGitHub:
 """GitHub 保存测试"""

 @pytest.mark.asyncio
 async def test_save_to_github_success(self, client):
 """测试成功保存到 GitHub"""
 mock_repo_response = MagicMock()
 mock_repo_response.status_code = 201
 mock_repo_response.json.return_value = {
 "clone_url": "https://github.com/testuser/test_project.git",
 }

 project_data = {
 "project_name": "test_project",
 "project_description": "Test project for GitHub",
 "project_data": json.dumps({
 "main.py": "print('Hello, GitHub!')",
 "README.md": "# Test Project",
 }),
 "github_config": {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": True,
 },
 }

 with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
 mock_post.return_value = mock_repo_response

 response = await client.post("/api/v1/github/save", json=project_data)

 assert response.status_code == 200
 data = response.json()
 assert data["success"] is True
 assert "GitHub" in data["message"]

 @pytest.mark.asyncio
 async def test_save_to_github_api_failure(self, client):
 """测试 GitHub API 调用失败"""
 mock_error_response = MagicMock()
 mock_error_response.status_code = 401
 mock_error_response.text = '{"message": "Bad credentials"}'

 project_data = {
 "project_name": "test_project",
 "project_description": "Test project",
 "project_data": json.dumps({"main.py": "print('hi')"}),
 "github_config": {
 "username": "testuser",
 "token": "invalid_token",
 "use_github": True,
 },
 }

 with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
 mock_post.return_value = mock_error_response

 response = await client.post("/api/v1/github/save", json=project_data)

 # API 失败应返回 400 或 500
 assert response.status_code in [400, 500]

 @pytest.mark.asyncio
 async def test_save_to_github_repo_exists(self, client):
 """测试仓库已存在时的处理"""
 mock_exists_response = MagicMock()
 mock_exists_response.status_code = 422
 mock_exists_response.text = '{"message": "name already exists on this account"}'

 project_data = {
 "project_name": "existing_project",
 "project_description": "Already exists",
 "project_data": json.dumps({"main.py": "print('hi')"}),
 "github_config": {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": True,
 },
 }

 with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
 mock_post.return_value = mock_exists_response

 response = await client.post("/api/v1/github/save", json=project_data)

 assert response.status_code in [400, 500]


class TestGithubSaveValidation:
 """GitHub 保存请求验证测试"""

 @pytest.mark.asyncio
 async def test_save_missing_project_name(self, client):
 """测试缺少项目名称"""
 project_data = {
 "project_description": "No name",
 "project_data": json.dumps({"main.py": "print('hi')"}),
 "github_config": {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": False,
 },
 }

 response = await client.post("/api/v1/github/save", json=project_data)

 # Pydantic 验证失败返回 422
 assert response.status_code == 422

 @pytest.mark.asyncio
 async def test_save_missing_project_data(self, client):
 """测试缺少项目数据"""
 project_data = {
 "project_name": "test_project",
 "project_description": "No data",
 "github_config": {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": False,
 },
 }

 response = await client.post("/api/v1/github/save", json=project_data)

 assert response.status_code == 422

 @pytest.mark.asyncio
 async def test_save_invalid_project_data_json(self, client):
 """测试无效的项目数据 JSON"""
 project_data = {
 "project_name": "test_project",
 "project_description": "Invalid JSON",
 "project_data": "this is not valid json",
 "github_config": {
 "username": "testuser",
 "token": "ghp_test_token",
 "use_github": False,
 },
 }

 response = await client.post("/api/v1/github/save", json=project_data)

 # JSON 解析失败应返回 500
 assert response.status_code in [400, 500]

 @pytest.mark.asyncio
 async def test_save_missing_github_config(self, client):
 """测试缺少 GitHub 配置"""
 project_data = {
 "project_name": "test_project",
 "project_description": "No config",
 "project_data": json.dumps({"main.py": "print('hi')"}),
 }

 response = await client.post("/api/v1/github/save", json=project_data)

 assert response.status_code == 422


class TestGithubModels:
 """GitHub 数据模型测试"""

 def test_github_config_model(self):
 """测试 GithubConfig 模型"""
 from app.api.v1.github import GithubConfig

 config = GithubConfig(
 username="testuser",
 token="ghp_test",
 use_github=True,
 )
 assert config.username == "testuser"
 assert config.token == "ghp_test"
 assert config.use_github is True

 def test_github_config_default(self):
 """测试 GithubConfig 默认值"""
 from app.api.v1.github import GithubConfig

 config = GithubConfig(username="test", token="test")
 assert config.use_github is False

 def test_github_save_request_model(self):
 """测试 GithubSaveRequest 模型"""
 from app.api.v1.github import GithubSaveRequest, GithubConfig

 request = GithubSaveRequest(
 project_name="test",
 project_description="desc",
 project_data='{"main.py": "code"}',
 github_config=GithubConfig(username="test", token="test"),
 )
 assert request.project_name == "test"
 assert request.project_description == "desc"

 def test_github_save_response_model(self):
 """测试 GithubSaveResponse 模型"""
 from app.api.v1.github import GithubSaveResponse

 response = GithubSaveResponse(
 success=True,
 message="OK",
 repo_url="https://github.com/test/repo",
 commit_id="abc123",
 )
 assert response.success is True
 assert response.repo_url is not None
 assert response.commit_id is not None
