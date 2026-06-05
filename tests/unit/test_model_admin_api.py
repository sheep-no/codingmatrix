"""
模型管理 API (v2) 测试

覆盖：
- POST /api/v2/models/default - 切换默认模型
- PUT /api/v2/models/agent-config - 更新 Agent 模型配置
- POST /api/v2/models/agent-config/reload - 重新加载配置
- PUT /api/v2/models/agent-config/fallback-chain - 更新降级链
- PUT /api/v2/models/agent-config/error-type-model - 更新错误类型映射
- GET /api/v2/models/context-lengths - 获取上下文长度
- PUT /api/v2/models/context-length - 更新上下文长度
- DELETE /api/v2/models/context-length/{model_key} - 删除上下文长度配置
"""

import json
import os
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient

from app.main import app
from app.utils.security import require_superadmin


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_superadmin():
    async def _mock():
        return {"sub": "1", "permission_level": "superadmin", "role": "admin"}
    app.dependency_overrides[require_superadmin] = _mock
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def tmp_agent_config(tmp_path):
    config_path = str(tmp_path / "agent_model_config.json")
    config = {
        "version": "1.0",
        "description": "test config",
        "last_updated": "",
        "assignments": {
            "SIMPLE": {"architect_model": "qwen3-8b"},
        },
        "fallback_chains": {
            "default": ["qwen3-8b", "deepseek-r1"],
        },
        "error_type_models": {
            "NameError": "qwen3-8b",
        },
        "model_context_lengths": {
            "Qwen/Qwen3-8B": 32768,
        },
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    return config_path


class TestSwitchDefaultModel:
    def test_switch_to_valid_model(self, client, mock_superadmin):
        resp = client.post("/api/v2/models/default", json={"model_id": "qwen3-8b"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["new_default"] == "qwen3-8b"

    def test_switch_to_nonexistent_model(self, client, mock_superadmin):
        resp = client.post("/api/v2/models/default", json={"model_id": "nonexistent"})
        assert resp.status_code == 404


class TestUpdateAgentModelConfig:
    def test_update_valid_config(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin.load_agent_model_config") as mock_load, \
             patch("app.api.v2.model_admin.save_agent_model_config") as mock_save, \
             patch("app.api.v2.model_admin._LayeredModelRouterCompat") as mock_router:
            mock_load.return_value = json.loads(open(tmp_agent_config).read())
            mock_save.return_value = True

            resp = client.put("/api/v2/models/agent-config", json={
                "complexity": "MEDIUM",
                "role": "frontend",
                "model_id": "qwen3-8b",
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_invalid_complexity(self, client, mock_superadmin):
        resp = client.put("/api/v2/models/agent-config", json={
            "complexity": "INVALID",
            "role": "frontend",
            "model_id": "qwen3-8b",
        })
        assert resp.status_code == 400

    def test_update_invalid_role(self, client, mock_superadmin):
        resp = client.put("/api/v2/models/agent-config", json={
            "complexity": "SIMPLE",
            "role": "invalid_role",
            "model_id": "qwen3-8b",
        })
        assert resp.status_code == 400

    def test_update_invalid_model_id(self, client, mock_superadmin):
        resp = client.put("/api/v2/models/agent-config", json={
            "complexity": "SIMPLE",
            "role": "architect",
            "model_id": "nonexistent-model",
        })
        assert resp.status_code == 400

    def test_update_with_auto_suffix(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin.load_agent_model_config") as mock_load, \
             patch("app.api.v2.model_admin.save_agent_model_config") as mock_save, \
             patch("app.api.v2.model_admin._LayeredModelRouterCompat") as mock_router:
            mock_load.return_value = json.loads(open(tmp_agent_config).read())
            mock_save.return_value = True

            resp = client.put("/api/v2/models/agent-config", json={
                "complexity": "SIMPLE",
                "role": "architect",
                "model_id": "qwen3-8b",
            })

        assert resp.status_code == 200


class TestReloadAgentModelConfig:
    def test_reload(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin._LayeredModelRouterCompat") as mock_router, \
             patch("app.api.v2.model_admin.load_agent_model_config") as mock_load:
            mock_load.return_value = {"version": "1.0"}

            resp = client.post("/api/v2/models/agent-config/reload")

        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_router.reload_config.assert_called_once()


class TestUpdateFallbackChain:
    def test_update_valid_chain(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin.load_agent_model_config") as mock_load, \
             patch("app.api.v2.model_admin.save_agent_model_config") as mock_save, \
             patch("app.api.v2.model_admin._LayeredModelRouterCompat") as mock_router:
            mock_load.return_value = json.loads(open(tmp_agent_config).read())
            mock_save.return_value = True

            resp = client.put("/api/v2/models/agent-config/fallback-chain", json={
                "chain_name": "default",
                "models": ["deepseek-r1", "qwen3-8b"],
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_invalid_chain_name(self, client, mock_superadmin):
        resp = client.put("/api/v2/models/agent-config/fallback-chain", json={
            "chain_name": "nonexistent",
            "models": ["qwen3-8b"],
        })
        assert resp.status_code == 400

    def test_update_chain_with_invalid_model(self, client, mock_superadmin):
        resp = client.put("/api/v2/models/agent-config/fallback-chain", json={
            "chain_name": "default",
            "models": ["nonexistent-model"],
        })
        assert resp.status_code == 400


class TestUpdateErrorTypeModel:
    def test_update_valid_mapping(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin.load_agent_model_config") as mock_load, \
             patch("app.api.v2.model_admin.save_agent_model_config") as mock_save:
            mock_load.return_value = json.loads(open(tmp_agent_config).read())
            mock_save.return_value = True

            resp = client.put("/api/v2/models/agent-config/error-type-model", json={
                "error_type": "ImportError",
                "model_id": "deepseek-r1",
            })

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_with_invalid_model(self, client, mock_superadmin):
        resp = client.put("/api/v2/models/agent-config/error-type-model", json={
            "error_type": "NameError",
            "model_id": "nonexistent",
        })
        assert resp.status_code == 400


class TestContextLengths:
    def test_get_context_lengths(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin.load_agent_model_config") as mock_load:
            mock_load.return_value = json.loads(open(tmp_agent_config).read())

            resp = client.get("/api/v2/models/context-lengths")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "models" in data

    def test_update_context_length(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin.load_agent_model_config") as mock_load, \
             patch("app.api.v2.model_admin.save_agent_model_config") as mock_save:
            mock_load.return_value = json.loads(open(tmp_agent_config).read())
            mock_save.return_value = True

            resp = client.put("/api/v2/models/context-length", json={
                "model_key": "Qwen/Qwen3-8B",
                "context_length": 65536,
            })

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["context_length"] == 65536

    def test_delete_context_length(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin.load_agent_model_config") as mock_load, \
             patch("app.api.v2.model_admin.save_agent_model_config") as mock_save:
            mock_load.return_value = json.loads(open(tmp_agent_config).read())
            mock_save.return_value = True

            resp = client.delete("/api/v2/models/context-length/Qwen/Qwen3-8B")

        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_delete_nonexistent_context_length(self, client, mock_superadmin, tmp_agent_config):
        with patch("app.api.v2.model_admin.load_agent_model_config") as mock_load:
            mock_load.return_value = json.loads(open(tmp_agent_config).read())

            resp = client.delete("/api/v2/models/context-length/Nonexistent/Model")

        assert resp.status_code == 404
