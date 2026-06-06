"""
MCP Client 单元测试

覆盖：
- MCPServerConnection 初始化、连接、断开
- JSON-RPC 消息处理
- 工具格式转换
- MCPClientManager 单例、配置加载、工具合并
"""

import asyncio
import json
import os
import tempfile
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

from app.agent.mcp_client import (
    MCPServerConnection,
    MCPClientManager,
    MCPError,
    MCP_CONNECT_TIMEOUT,
    MCP_CALL_TIMEOUT,
)


class TestMCPError:
    def test_is_exception(self):
        err = MCPError("test error")
        assert isinstance(err, Exception)
        assert str(err) == "test error"


class TestMCPServerConnection:
    def test_init_defaults(self):
        conn = MCPServerConnection("test", {"transport": "stdio", "command": "echo"})
        assert conn.name == "test"
        assert conn.transport == "stdio"
        assert conn._initialized is False
        assert conn._tools == []
        assert conn._request_id == 0

    def test_init_http(self):
        conn = MCPServerConnection("http-srv", {"transport": "http", "url": "http://localhost:8080"})
        assert conn.transport == "http"
        assert conn._url is None  # set during connect

    def test_next_id_increments(self):
        conn = MCPServerConnection("test", {})
        assert conn._next_id() == 1
        assert conn._next_id() == 2
        assert conn._next_id() == 3

    @pytest.mark.asyncio
    async def test_connect_unsupported_transport(self):
        conn = MCPServerConnection("test", {"transport": "grpc"})
        result = await conn.connect()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_stdio_no_command(self):
        conn = MCPServerConnection("test", {"transport": "stdio"})
        result = await conn._connect_stdio()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_http_no_url(self):
        conn = MCPServerConnection("test", {"transport": "http"})
        result = await conn._connect_http()
        assert result is False

    @pytest.mark.asyncio
    async def test_connect_http_success(self):
        conn = MCPServerConnection("test", {"transport": "http", "url": "http://localhost:8080/mcp"})
        result = await conn._connect_http()
        assert result is True
        assert conn._initialized is True
        assert conn._http_client is not None
        await conn.disconnect()

    @pytest.mark.asyncio
    async def test_handle_message_resolves_future(self):
        conn = MCPServerConnection("test", {})
        future = asyncio.get_event_loop().create_future()
        conn._pending[42] = future
        conn._handle_message({"id": 42, "result": {"tools": []}})
        assert future.done()
        assert future.result() == {"tools": []}

    @pytest.mark.asyncio
    async def test_handle_message_error_raises(self):
        conn = MCPServerConnection("test", {})
        future = asyncio.get_event_loop().create_future()
        conn._pending[42] = future
        conn._handle_message({"id": 42, "error": {"code": -1, "msg": "bad"}})
        assert future.done()
        with pytest.raises(MCPError):
            future.result()

    @pytest.mark.asyncio
    async def test_handle_message_unknown_id_ignored(self):
        conn = MCPServerConnection("test", {})
        # should not raise
        conn._handle_message({"id": 999, "result": {}})

    @pytest.mark.asyncio
    async def test_list_tools_not_initialized(self):
        conn = MCPServerConnection("test", {})
        result = await conn.list_tools()
        assert result == []

    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self):
        conn = MCPServerConnection("test", {})
        with pytest.raises(MCPError, match="未连接"):
            await conn.call_tool("some_tool", {})

    def test_get_tools_as_specialist_format_empty(self):
        conn = MCPServerConnection("test", {})
        result = conn.get_tools_as_specialist_format()
        assert result == {}

    def test_get_tools_as_specialist_format(self):
        conn = MCPServerConnection("myserver", {})
        conn._tools = [
            {
                "name": "search",
                "description": "Search files",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "search query"},
                        "limit": {"type": "integer"},
                    }
                }
            }
        ]
        result = conn.get_tools_as_specialist_format()
        assert "mcp_myserver_search" in result
        tool = result["mcp_myserver_search"]
        assert "[MCP:myserver]" in tool["description"]
        assert "string" in tool["params"]["query"]
        assert "integer" in tool["params"]["limit"]
        assert tool["_mcp_source"] == "myserver"
        assert tool["_mcp_tool_name"] == "search"
        assert callable(tool["fn"])

    def test_get_tools_as_specialist_format_skips_empty_name(self):
        conn = MCPServerConnection("test", {})
        conn._tools = [{"name": "", "description": "empty"}]
        result = conn.get_tools_as_specialist_format()
        assert result == {}

    @pytest.mark.asyncio
    async def test_send_stdio_request_no_process(self):
        conn = MCPServerConnection("test", {"transport": "stdio"})
        result = await conn._send_stdio_request(1, {"method": "test"}, 5.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_http_request_no_client(self):
        conn = MCPServerConnection("test", {"transport": "http"})
        result = await conn._send_http_request({"method": "test"}, 5.0)
        assert result is None

    @pytest.mark.asyncio
    async def test_send_notification_stdio_no_process(self):
        conn = MCPServerConnection("test", {"transport": "stdio"})
        # should not raise
        await conn._send_notification("test/method", {})

    @pytest.mark.asyncio
    async def test_disconnect_no_resources(self):
        conn = MCPServerConnection("test", {})
        conn._initialized = True
        await conn.disconnect()
        assert conn._initialized is False

    @pytest.mark.asyncio
    async def test_send_http_request_success(self):
        conn = MCPServerConnection("test", {"transport": "http", "url": "http://x/mcp"})
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"result": {"tools": []}}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        conn._http_client = mock_client
        conn._url = "http://x/mcp"
        result = await conn._send_http_request({"jsonrpc": "2.0", "method": "tools/list"}, 10.0)
        assert result == {"tools": []}

    @pytest.mark.asyncio
    async def test_send_http_request_rpc_error(self):
        conn = MCPServerConnection("test", {"transport": "http", "url": "http://x/mcp"})
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"error": {"code": -1}}
        mock_resp.raise_for_status = MagicMock()
        mock_client.post.return_value = mock_resp
        conn._http_client = mock_client
        conn._url = "http://x/mcp"
        result = await conn._send_http_request({"jsonrpc": "2.0", "method": "test"}, 10.0)
        assert result is None


class TestMCPClientManager:
    def setup_method(self):
        MCPClientManager._instance = None

    def test_singleton(self):
        mgr = MCPClientManager()
        assert MCPClientManager.get_instance() is mgr

    def test_get_all_tools_empty(self):
        mgr = MCPClientManager()
        assert mgr.get_all_tools() == {}

    def test_get_tool_names_empty(self):
        mgr = MCPClientManager()
        assert mgr.get_tool_names() == []

    def test_get_server_none(self):
        mgr = MCPClientManager()
        assert mgr.get_server("nonexistent") is None

    @pytest.mark.asyncio
    async def test_load_servers_no_file(self):
        mgr = MCPClientManager()
        result = await mgr.load_servers("/nonexistent/path/config.json")
        assert result == 0

    @pytest.mark.asyncio
    async def test_load_servers_empty_config(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({}, f)
            f.flush()
            mgr = MCPClientManager()
            result = await mgr.load_servers(f.name)
            assert result == 0
        os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_load_servers_disabled(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"mcp_servers": {"test": {"enabled": False, "transport": "stdio"}}}, f)
            f.flush()
            mgr = MCPClientManager()
            result = await mgr.load_servers(f.name)
            assert result == 0
        os.unlink(f.name)

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        mgr = MCPClientManager()
        mock_server = AsyncMock()
        mgr._servers = {"test": mock_server}
        mgr._all_tools = {"tool1": {}}
        await mgr.disconnect_all()
        mock_server.disconnect.assert_called_once()
        assert mgr._servers == {}
        assert mgr._all_tools == {}

    def test_create_default_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "mcp_servers.json")
            result = MCPClientManager.create_default_config(path)
            assert result == path
            assert os.path.exists(path)
            with open(path) as f:
                config = json.load(f)
            assert "mcp_servers" in config
            assert "filesystem" in config["mcp_servers"]


class TestMCPToolFunction:
    @pytest.mark.asyncio
    async def test_mcp_tool_fn_no_manager(self):
        MCPClientManager._instance = None
        conn = MCPServerConnection("test", {})
        conn._tools = [{"name": "search", "description": "Search", "inputSchema": {"properties": {}}}]
        tools = conn.get_tools_as_specialist_format()
        fn = tools["mcp_test_search"]["fn"]
        result = await fn(project_path="")
        assert result["success"] is False
        assert "未初始化" in result["error"]

    @pytest.mark.asyncio
    async def test_mcp_tool_fn_no_server(self):
        mgr = MCPClientManager()
        MCPClientManager._instance = mgr
        conn = MCPServerConnection("test", {})
        conn._tools = [{"name": "search", "description": "Search", "inputSchema": {"properties": {}}}]
        tools = conn.get_tools_as_specialist_format()
        fn = tools["mcp_test_search"]["fn"]
        result = await fn(project_path="")
        assert result["success"] is False
        assert "不存在" in result["error"]
