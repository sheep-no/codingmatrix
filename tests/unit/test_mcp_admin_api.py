"""
MCP Server 管理 API 测试

覆盖：
- GET /api/v2/mcp/servers - 获取所有 MCP Server
- POST /api/v2/mcp/servers - 添加 MCP Server
- PUT /api/v2/mcp/servers/{name} - 更新 MCP Server
- DELETE /api/v2/mcp/servers/{name} - 删除 MCP Server
- POST /api/v2/mcp/servers/{name}/toggle - 切换启用/禁用
- POST /api/v2/mcp/servers/{name}/test - 测试连接
"""

import json
import os
import tempfile
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def tmp_config(tmp_path):
    """创建临时 MCP 配置文件"""
    config_path = str(tmp_path / "mcp_servers.json")
    config = {
        "mcp_servers": {
            "test-server": {
                "transport": "stdio",
                "enabled": True,
                "command": "echo",
                "args": ["hello"],
                "description": "测试 Server",
            },
            "disabled-server": {
                "transport": "http",
                "enabled": False,
                "url": "http://localhost:9999/mcp",
                "description": "已禁用",
            },
        }
    }
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f)
    return config_path


class TestListMCPServers:
    def test_list_servers(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.get("/api/v2/mcp/servers")
        assert resp.status_code == 200
        data = resp.json()
        assert "servers" in data
        assert len(data["servers"]) == 2

    def test_list_servers_hides_secret_env(self, client, tmp_path):
        config_path = str(tmp_path / "mcp_servers.json")
        config = {
            "mcp_servers": {
                "srv": {
                    "transport": "stdio",
                    "command": "echo",
                    "env": {"API_KEY": "secret123", "NORMAL": "visible"},
                }
            }
        }
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f)
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", config_path):
            resp = client.get("/api/v2/mcp/servers")
        srv = resp.json()["servers"][0]
        assert srv["env"]["API_KEY"] == "***"
        assert srv["env"]["NORMAL"] == "visible"

    def test_list_servers_empty_config(self, client, tmp_path):
        config_path = str(tmp_path / "empty.json")
        with open(config_path, "w") as f:
            json.dump({"mcp_servers": {}}, f)
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", config_path):
            resp = client.get("/api/v2/mcp/servers")
        assert resp.json()["servers"] == []

    def test_list_servers_no_file(self, client):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", "/nonexistent/path.json"):
            resp = client.get("/api/v2/mcp/servers")
        assert resp.status_code == 200
        assert resp.json()["servers"] == []


class TestAddMCPServer:
    def test_add_stdio_server(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers", json={
                "name": "new-server",
                "transport": "stdio",
                "command": "python",
                "args": ["-m", "server"],
                "description": "新 Server",
            })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_add_http_server(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers", json={
                "name": "http-server",
                "transport": "http",
                "url": "http://localhost:8080/mcp",
            })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_add_duplicate_name(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers", json={
                "name": "test-server",
                "transport": "stdio",
                "command": "echo",
            })
        assert resp.status_code == 409

    def test_add_stdio_without_command(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers", json={
                "name": "bad-stdio",
                "transport": "stdio",
            })
        assert resp.status_code == 400

    def test_add_http_without_url(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers", json={
                "name": "bad-http",
                "transport": "http",
            })
        assert resp.status_code == 400


class TestUpdateMCPServer:
    def test_update_enabled(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.put("/api/v2/mcp/servers/test-server", json={
                "enabled": False,
            })
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_update_transport(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.put("/api/v2/mcp/servers/test-server", json={
                "transport": "http",
                "url": "http://localhost:8080/mcp",
            })
        assert resp.status_code == 200

    def test_update_description(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.put("/api/v2/mcp/servers/test-server", json={
                "description": "更新后的描述",
            })
        assert resp.status_code == 200

    def test_update_nonexistent(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.put("/api/v2/mcp/servers/nonexistent", json={
                "enabled": False,
            })
        assert resp.status_code == 404


class TestDeleteMCPServer:
    def test_delete_existing(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.delete("/api/v2/mcp/servers/test-server")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_delete_nonexistent(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.delete("/api/v2/mcp/servers/nonexistent")
        assert resp.status_code == 404


class TestToggleMCPServer:
    def test_toggle_enabled_to_disabled(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers/test-server/toggle")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["enabled"] is False

    def test_toggle_disabled_to_enabled(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers/disabled-server/toggle")
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    def test_toggle_nonexistent(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers/nonexistent/toggle")
        assert resp.status_code == 404


class TestTestMCPServer:
    def test_test_connection_success(self, client, tmp_config):
        mock_tools = [
            {"name": "search", "description": "Search files"},
            {"name": "read", "description": "Read file"},
        ]
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config), \
             patch("app.agent.mcp_client.MCPServerConnection") as MockConn:
            mock_server = AsyncMock()
            mock_server.connect.return_value = True
            mock_server.list_tools.return_value = mock_tools
            MockConn.return_value = mock_server

            resp = client.post("/api/v2/mcp/servers/test-server/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["tools_count"] == 2
        assert len(data["tools"]) == 2

    def test_test_connection_failure(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config), \
             patch("app.agent.mcp_client.MCPServerConnection") as MockConn:
            mock_server = AsyncMock()
            mock_server.connect.return_value = False
            MockConn.return_value = mock_server

            resp = client.post("/api/v2/mcp/servers/test-server/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "连接失败" in data["error"]

    def test_test_connection_exception(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config), \
             patch("app.agent.mcp_client.MCPServerConnection") as MockConn:
            mock_server = AsyncMock()
            mock_server.connect.side_effect = Exception("超时")
            MockConn.return_value = mock_server

            resp = client.post("/api/v2/mcp/servers/test-server/test")

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is False
        assert "超时" in data["error"]

    def test_test_nonexistent(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            resp = client.post("/api/v2/mcp/servers/nonexistent/test")
        assert resp.status_code == 404


class TestMCPServerConfigPersistence:
    def test_add_then_list(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            client.post("/api/v2/mcp/servers", json={
                "name": "persist-test",
                "transport": "stdio",
                "command": "echo",
            })
            resp = client.get("/api/v2/mcp/servers")
        names = [s["name"] for s in resp.json()["servers"]]
        assert "persist-test" in names

    def test_add_then_delete(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            client.post("/api/v2/mcp/servers", json={
                "name": "to-delete",
                "transport": "stdio",
                "command": "echo",
            })
            client.delete("/api/v2/mcp/servers/to-delete")
            resp = client.get("/api/v2/mcp/servers")
        names = [s["name"] for s in resp.json()["servers"]]
        assert "to-delete" not in names

    def test_toggle_persists(self, client, tmp_config):
        with patch("app.api.v2.mcp_admin.MCP_CONFIG_PATH", tmp_config):
            client.post("/api/v2/mcp/servers/test-server/toggle")
            resp = client.get("/api/v2/mcp/servers")
        for s in resp.json()["servers"]:
            if s["name"] == "test-server":
                assert s["enabled"] is False
