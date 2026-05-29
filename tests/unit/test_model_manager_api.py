"""
模型管理 API 测试

测试模型管理接口的功能：
1. 获取所有模型列表
2. 获取当前默认模型
3. 切换默认模型（仅超级管理员）
4. 按能力筛选模型
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock

from app.main import app
from app.utils.aicloud.model_registry import MODEL_REGISTRY, get_default_model
from app.utils.security import require_superadmin, verify_token


@pytest.fixture
def client():
    """创建测试客户端"""
    return TestClient(app)


@pytest.fixture
def mock_superadmin_auth():
    """模拟超级管理员认证"""
    async def mock_require_superadmin():
        return {
            "sub": "1",
            "permission_level": "superadmin",
            "role": "admin"
        }
    
    app.dependency_overrides[require_superadmin] = mock_require_superadmin
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def mock_normal_user_auth():
    """模拟普通用户认证"""
    async def mock_verify_token():
        return {
            "sub": "2",
            "permission_level": "normal",
            "role": "user"
        }
    
    app.dependency_overrides[verify_token] = mock_verify_token
    yield
    app.dependency_overrides.clear()


class TestModelManagerAPI:
    """模型管理 API 测试类"""

    def test_list_models(self, client, mock_superadmin_auth):
        """测试获取所有模型列表"""
        response = client.get("/api/v1/models/")
        assert response.status_code == 200
        
        data = response.json()
        assert "models" in data
        assert "total" in data
        assert "default_model" in data
        
        # 验证模型数量
        assert data["total"] == len(MODEL_REGISTRY)
        assert len(data["models"]) == len(MODEL_REGISTRY)

    def test_list_models_with_capability_filter(self, client, mock_superadmin_auth):
        """测试按能力筛选模型"""
        response = client.get("/api/v1/models/?capability=text")
        assert response.status_code == 200
        
        data = response.json()
        assert "models" in data
        
        # 验证所有返回的模型都有 text 能力
        for model in data["models"]:
            assert "text" in model["capabilities"]

    def test_get_default_model(self, client, mock_superadmin_auth):
        """测试获取当前默认模型"""
        response = client.get("/api/v1/models/default")
        assert response.status_code == 200
        
        data = response.json()
        assert "id" in data
        assert "name" in data
        assert "is_default" in data
        assert data["is_default"] is True

    def test_switch_default_model_as_superadmin(self, client, mock_superadmin_auth):
        """测试超级管理员切换默认模型"""
        # 获取一个非默认模型
        default_model = get_default_model()
        other_model_id = None
        for model_id in MODEL_REGISTRY:
            if model_id != default_model.id:
                other_model_id = model_id
                break
        
        if other_model_id:
            response = client.post(
                "/api/v2/models/default",
                json={"model_id": other_model_id}
            )
            assert response.status_code == 200
            
            data = response.json()
            assert data["success"] is True
            assert data["new_default"] == other_model_id

    def test_switch_default_model_as_normal_user(self, client, mock_normal_user_auth):
        """测试普通用户无法切换默认模型"""
        response = client.post(
            "/api/v2/models/default",
            json={"model_id": "qwen2.5-7b"}
        )
        # 普通用户应该被拒绝访问
        assert response.status_code == 403

    def test_switch_to_nonexistent_model(self, client, mock_superadmin_auth):
        """测试切换到不存在的模型"""
        response = client.post(
            "/api/v2/models/default",
            json={"model_id": "nonexistent-model"}
        )
        assert response.status_code == 404

    def test_get_model_info(self, client, mock_superadmin_auth):
        """测试获取指定模型信息"""
        # 获取第一个模型
        model_id = list(MODEL_REGISTRY.keys())[0]
        
        response = client.get(f"/api/v1/models/{model_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == model_id
        assert "name" in data
        assert "capabilities" in data

    def test_get_nonexistent_model_info(self, client, mock_superadmin_auth):
        """测试获取不存在模型的信息"""
        response = client.get("/api/v1/models/nonexistent-model")
        assert response.status_code == 404

    def test_list_capabilities(self, client, mock_superadmin_auth):
        """测试获取能力类型列表"""
        response = client.get("/api/v1/models/capabilities/list")
        assert response.status_code == 200
        
        data = response.json()
        assert "capabilities" in data
        assert len(data["capabilities"]) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
