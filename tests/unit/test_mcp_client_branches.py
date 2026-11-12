"""mcp_client 全分支回归。"""

import asyncio
import json
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent import mcp_client as mc
from app.agent.mcp_client import MCPClientManager, MCPError, MCPServerConnection


@pytest.fixture(autouse=True)
def reset_manager():
    MCPClientManager._instance = None
    yield
    MCPClientManager._instance = None


def _conn(transport="stdio", **config):
    return MCPServerConnection("srv", {"transport": transport, **config})


class FakeProcess:
    def __init__(self, stdout_lines=None, stderr_lines=None):
        self.stdin = MagicMock()
        self.stdin.write = MagicMock()
        self.stdin.drain = AsyncMock()
        self.stdin.close = MagicMock()
        self.stdout = self._stream(stdout_lines or [])
        self.stderr = self._stream(stderr_lines or [])
        self.terminate = MagicMock()
        self.kill = MagicMock()
        self.wait = AsyncMock(return_value=0)

    @staticmethod
    def _stream(lines):
        return _FakeStream(lines)


class _FakeStream:
    def __init__(self, lines):
        self._lines = lines
        self.readline = AsyncMock(side_effect=lines + [b""])

    def __aiter__(self):
        async def gen():
            for line in self._lines:
                yield line
        return gen()


class TestConnect:
    @pytest.mark.asyncio
    async def test_unsupported_transport(self):
        c = _conn(transport="udp")
        assert await c.connect() is False

    @pytest.mark.asyncio
    async def test_connect_exception(self, monkeypatch):
        c = _conn()
        monkeypatch.setattr(c, "_connect_stdio", AsyncMock(side_effect=RuntimeError("x")))
        monkeypatch.setattr(mc.logger, "error", lambda *a, **k: None)
        assert await c.connect() is False

    @pytest.mark.asyncio
    async def test_stdio_missing_command(self):
        c = _conn()
        assert await c._connect_stdio() is False

    @pytest.mark.asyncio
    async def test_stdio_command_not_found(self, monkeypatch):
        monkeypatch.setattr(mc.shutil, "which", lambda cmd: None)
        c = _conn(command="nope")
        assert await c._connect_stdio() is False

    @pytest.mark.asyncio
    async def test_stdio_subprocess_file_not_found(self, monkeypatch):
        monkeypatch.setattr(mc.shutil, "which", lambda cmd: "/usr/bin/x")
        async def boom(*a, **kw):
            raise FileNotFoundError()
        monkeypatch.setattr(mc.asyncio, "create_subprocess_exec", boom)
        c = _conn(command="x")
        assert await c._connect_stdio() is False

    @pytest.mark.asyncio
    async def test_stdio_absolute_command(self, monkeypatch):
        proc = FakeProcess()
        monkeypatch.setattr(
            mc.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)
        )
        c = _conn(command="/usr/bin/x")
        monkeypatch.setattr(c, "_send_request", AsyncMock(return_value={"ok": 1}))
        monkeypatch.setattr(c, "_send_notification", AsyncMock())
        monkeypatch.setattr(c, "_read_loop", AsyncMock())
        monkeypatch.setattr(c, "_consume_stderr", AsyncMock())
        assert await c._connect_stdio() is True

    @pytest.mark.asyncio
    async def test_stdio_initialize_failure(self, monkeypatch):
        monkeypatch.setattr(mc.shutil, "which", lambda cmd: "/usr/bin/x")
        proc = FakeProcess()
        monkeypatch.setattr(
            mc.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)
        )
        c = _conn(command="x", args=["a"], env={"K": "V"})
        monkeypatch.setattr(c, "_send_request", AsyncMock(return_value=None))
        monkeypatch.setattr(c, "disconnect", AsyncMock())
        monkeypatch.setattr(c, "_read_loop", AsyncMock())
        monkeypatch.setattr(c, "_consume_stderr", AsyncMock())
        assert await c._connect_stdio() is False
        c.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_stdio_success(self, monkeypatch):
        monkeypatch.setattr(mc.shutil, "which", lambda cmd: "/usr/bin/x")
        proc = FakeProcess()
        monkeypatch.setattr(
            mc.asyncio, "create_subprocess_exec", AsyncMock(return_value=proc)
        )
        c = _conn(command="x")
        monkeypatch.setattr(c, "_send_request", AsyncMock(return_value={"ok": 1}))
        monkeypatch.setattr(c, "_send_notification", AsyncMock())
        monkeypatch.setattr(c, "_read_loop", AsyncMock())
        monkeypatch.setattr(c, "_consume_stderr", AsyncMock())
        assert await c._connect_stdio() is True
        assert c._initialized is True
        c._send_notification.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_http_missing_url(self):
        c = _conn(transport="http")
        assert await c._connect_http() is False

    @pytest.mark.asyncio
    async def test_connect_http_dispatch(self):
        c = _conn(transport="http", url="http://x")
        assert await c.connect() is True
        await c._http_client.aclose()

    @pytest.mark.asyncio
    async def test_http_success(self):
        c = _conn(transport="http", url="http://x")
        assert await c._connect_http() is True
        assert c._initialized is True
        await c._http_client.aclose()


class TestReadLoop:
    @pytest.mark.asyncio
    async def test_no_process(self):
        await _conn()._read_loop()

    @pytest.mark.asyncio
    async def test_process_without_stdout(self):
        c = _conn()
        c._process = SimpleNamespace(stdout=None)
        await c._read_loop()

    @pytest.mark.asyncio
    async def test_reads_messages_and_flushes_pending(self, monkeypatch):
        c = _conn()
        lines = [b'{"id": 1, "result": 1}\n', b"not json\n", b"\n", b""]
        c._process = SimpleNamespace(
            stdout=SimpleNamespace(readline=AsyncMock(side_effect=lines))
        )
        fut = asyncio.get_event_loop().create_future()
        done = asyncio.get_event_loop().create_future()
        done.set_result(1)
        c._pending = {1: fut, 2: done}
        await c._read_loop()
        assert fut.result() == 1
        assert c._pending == {}

    @pytest.mark.asyncio
    async def test_read_unresolved_pending_gets_exception(self):
        c = _conn()
        c._process = SimpleNamespace(
            stdout=SimpleNamespace(readline=AsyncMock(side_effect=[b""]))
        )
        pending = asyncio.get_event_loop().create_future()
        c._pending = {7: pending}
        await c._read_loop()
        with pytest.raises(MCPError):
            pending.result()

    @pytest.mark.asyncio
    async def test_read_exception_is_logged(self, monkeypatch):
        c = _conn()
        c._process = SimpleNamespace(
            stdout=SimpleNamespace(readline=AsyncMock(side_effect=RuntimeError("x")))
        )
        messages = []
        monkeypatch.setattr(mc.logger, "debug", messages.append)
        await c._read_loop()
        assert any("读取循环异常" in m for m in messages)

    @pytest.mark.asyncio
    async def test_read_cancelled(self):
        c = _conn()
        c._process = SimpleNamespace(
            stdout=SimpleNamespace(readline=AsyncMock(side_effect=asyncio.CancelledError()))
        )
        await c._read_loop()


class TestHandleMessage:
    def test_error_result(self):
        c = _conn()
        fut = asyncio.get_event_loop().create_future()
        c._pending = {1: fut}
        c._handle_message({"id": 1, "error": {"code": 1}})
        with pytest.raises(MCPError):
            fut.result()

    def test_ignored_when_unknown(self):
        c = _conn()
        c._handle_message({"id": 99, "result": 1})
        assert c._pending == {}

    def test_next_id(self):
        c = _conn()
        assert c._next_id() == 1
        assert c._next_id() == 2


class TestSend:
    @pytest.mark.asyncio
    async def test_request_dispatches_stdio(self, monkeypatch):
        c = _conn()
        c._send_stdio_request = AsyncMock(return_value="ok")
        assert await c._send_request("m", {}) == "ok"

    @pytest.mark.asyncio
    async def test_request_dispatches_http(self):
        c = _conn(transport="http")
        c._send_http_request = AsyncMock(return_value="ok")
        assert await c._send_request("m", {}) == "ok"

    @pytest.mark.asyncio
    async def test_stdio_without_process(self):
        assert await _conn()._send_stdio_request(1, {"method": "m"}, 1) is None

    @pytest.mark.asyncio
    async def test_stdio_broken_pipe(self):
        c = _conn()
        proc = FakeProcess()
        proc.stdin.drain = AsyncMock(side_effect=BrokenPipeError())
        c._process = proc
        with pytest.raises(MCPError):
            await c._send_stdio_request(1, {"method": "m"}, 1)
        assert c._pending == {}

    @pytest.mark.asyncio
    async def test_stdio_timeout(self, monkeypatch):
        c = _conn()
        c._process = FakeProcess()
        messages = []
        monkeypatch.setattr(mc.logger, "error", messages.append)
        assert await c._send_stdio_request(1, {"method": "m"}, 0.001) is None
        assert c._pending == {}
        assert any("请求超时" in m for m in messages)

    @pytest.mark.asyncio
    async def test_http_without_client(self):
        assert await _conn(transport="http")._send_http_request({}, 1) is None

    @pytest.mark.asyncio
    async def test_http_success(self):
        c = _conn(transport="http")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"result": 42}
        c._http_client = MagicMock()
        c._http_client.post = AsyncMock(return_value=resp)
        c._url = "http://x"
        assert await c._send_http_request({"id": 1}, 1) == 42

    @pytest.mark.asyncio
    async def test_http_rpc_error(self, monkeypatch):
        c = _conn(transport="http")
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"error": {"code": 1}}
        c._http_client = MagicMock()
        c._http_client.post = AsyncMock(return_value=resp)
        c._url = "http://x"
        monkeypatch.setattr(mc.logger, "error", lambda *a, **k: None)
        assert await c._send_http_request({"id": 1}, 1) is None

    @pytest.mark.asyncio
    async def test_http_exception(self, monkeypatch):
        c = _conn(transport="http")
        c._http_client = MagicMock()
        c._http_client.post = AsyncMock(side_effect=RuntimeError("x"))
        c._url = "http://x"
        monkeypatch.setattr(mc.logger, "error", lambda *a, **k: None)
        assert await c._send_http_request({"id": 1}, 1) is None

    @pytest.mark.asyncio
    async def test_notification_stdio(self):
        c = _conn()
        c._process = FakeProcess()
        await c._send_notification("m", {})
        c._process.stdin.write.assert_called_once()

    @pytest.mark.asyncio
    async def test_notification_http_noop(self):
        c = _conn(transport="http")
        await c._send_notification("m", {})


class TestTools:
    @pytest.mark.asyncio
    async def test_list_tools_not_initialized(self):
        assert await _conn().list_tools() == []

    @pytest.mark.asyncio
    async def test_list_tools_no_result(self, monkeypatch):
        c = _conn()
        c._initialized = True
        c._send_request = AsyncMock(return_value=None)
        assert await c.list_tools() == []

    @pytest.mark.asyncio
    async def test_list_tools_success(self, monkeypatch):
        c = _conn()
        c._initialized = True
        c._send_request = AsyncMock(return_value={"tools": [{"name": "t"}]})
        assert await c.list_tools() == [{"name": "t"}]

    @pytest.mark.asyncio
    async def test_call_tool_not_initialized(self):
        with pytest.raises(MCPError):
            await _conn().call_tool("t", {})

    @pytest.mark.asyncio
    async def test_call_tool_none_result(self):
        c = _conn()
        c._initialized = True
        c._send_request = AsyncMock(return_value=None)
        with pytest.raises(MCPError):
            await c.call_tool("t", {})

    @pytest.mark.asyncio
    async def test_call_tool_error_result(self):
        c = _conn()
        c._initialized = True
        c._send_request = AsyncMock(
            return_value={"isError": True, "content": [{"type": "text", "text": "bad"}]}
        )
        with pytest.raises(MCPError, match="bad"):
            await c.call_tool("t", {})

    @pytest.mark.asyncio
    async def test_call_tool_non_list_content(self):
        c = _conn()
        c._initialized = True
        c._send_request = AsyncMock(return_value={"content": "raw"})
        assert await c.call_tool("t", {}) == "raw"

    @pytest.mark.asyncio
    async def test_call_tool_multiple_texts(self):
        c = _conn()
        c._initialized = True
        c._send_request = AsyncMock(
            return_value={"content": [
                {"type": "text", "text": "a"},
                {"type": "image", "text": "x"},
                {"type": "text", "text": "b"},
            ]}
        )
        assert await c.call_tool("t", {}) == "a\nb"

    @pytest.mark.asyncio
    async def test_call_tool_empty_content(self):
        c = _conn()
        c._initialized = True
        c._send_request = AsyncMock(return_value={"content": []})
        assert await c.call_tool("t", {}) == "[]"


class TestStderrAndDisconnect:
    @pytest.mark.asyncio
    async def test_consume_stderr_logs(self, monkeypatch):
        c = _conn()
        c._process = FakeProcess(stderr_lines=[b"warn\n", b"\n"])
        messages = []
        monkeypatch.setattr(mc.logger, "debug", messages.append)
        await c._consume_stderr()
        assert any("stderr" in m for m in messages)

    @pytest.mark.asyncio
    async def test_consume_stderr_without_stream(self):
        c = _conn()
        await c._consume_stderr()
        c._process = SimpleNamespace(stderr=None)
        await c._consume_stderr()

    @pytest.mark.asyncio
    async def test_consume_stderr_cancelled(self, monkeypatch):
        c = _conn()
        c._process = SimpleNamespace(stderr=_CancelStream())
        await c._consume_stderr()

    @pytest.mark.asyncio
    async def test_consume_stderr_exception(self, monkeypatch):
        c = _conn()
        c._process = SimpleNamespace(stderr=_BadStream())
        messages = []
        monkeypatch.setattr(mc.logger, "debug", messages.append)
        await c._consume_stderr()
        assert any("stderr 消费异常" in m for m in messages)

    @pytest.mark.asyncio
    async def test_disconnect_full(self, monkeypatch):
        c = _conn()
        proc = FakeProcess()
        proc.stdin.close.side_effect = RuntimeError("bad")
        c._process = proc
        c._read_task = asyncio.create_task(asyncio.sleep(30))
        c._stderr_task = asyncio.create_task(asyncio.sleep(30))
        c._http_client = MagicMock()
        c._http_client.aclose = AsyncMock()
        await c.disconnect()
        proc.kill.assert_called_once()
        assert c._process is None
        assert c._http_client is None

    @pytest.mark.asyncio
    async def test_disconnect_process_graceful(self):
        c = _conn()
        proc = FakeProcess()
        c._process = proc
        await c.disconnect()
        proc.terminate.assert_called_once()
        proc.wait.assert_awaited_once()
        assert c._process is None

    @pytest.mark.asyncio
    async def test_disconnect_http_only(self):
        c = _conn(transport="http")
        c._http_client = MagicMock()
        c._http_client.aclose = AsyncMock()
        await c.disconnect()
        assert c._initialized is False

    @pytest.mark.asyncio
    async def test_disconnect_kill_failure(self, monkeypatch):
        c = _conn()
        proc = FakeProcess()
        proc.stdin.close.side_effect = RuntimeError("bad")
        proc.kill.side_effect = RuntimeError("nope")
        c._process = proc
        messages = []
        monkeypatch.setattr(mc.logger, "debug", messages.append)
        await c.disconnect()
        assert any("kill 失败" in m for m in messages)


class _CancelStream:
    def __aiter__(self):
        async def gen():
            raise asyncio.CancelledError()
            yield b""
        return gen()


class _BadStream:
    def __aiter__(self):
        async def gen():
            raise RuntimeError("boom")
            yield b""
        return gen()


class TestSpecialistFormat:
    def test_converts_tools(self):
        c = _conn()
        c._tools = [
            {"name": "", "inputSchema": {}},
            {
                "name": "read",
                "description": "Read file",
                "inputSchema": {
                    "properties": {
                        "path": {"type": "string", "description": "file path"},
                        "n": {"type": "integer"},
                    }
                },
            },
            {"name": "bare"},
        ]
        tools = c.get_tools_as_specialist_format()
        assert set(tools) == {"mcp_srv_read", "mcp_srv_bare"}
        info = tools["mcp_srv_read"]
        assert info["params"]["path"] == "string (file path)"
        assert info["params"]["n"] == "integer"
        assert info["description"] == "[MCP:srv] Read file"
        assert info["_mcp_source"] == "srv"
        assert info["_mcp_tool_name"] == "read"
        assert tools["mcp_srv_bare"]["description"] == "[MCP:srv] MCP 工具: bare"

    @pytest.mark.asyncio
    async def test_tool_fn_success(self):
        c = _conn()
        c.call_tool = AsyncMock(return_value="result")
        c._tools = [{"name": "t"}]
        fn = c.get_tools_as_specialist_format()["mcp_srv_t"]["fn"]
        assert await fn(path="p") == {"success": True, "result": "result"}
        c.call_tool.assert_awaited_once_with("t", {"path": "p"})

    @pytest.mark.asyncio
    async def test_tool_fn_mcp_error(self):
        c = _conn()
        c.call_tool = AsyncMock(side_effect=MCPError("bad"))
        c._tools = [{"name": "t"}]
        fn = c.get_tools_as_specialist_format()["mcp_srv_t"]["fn"]
        assert await fn() == {"success": False, "error": "bad"}


class TestManager:
    def test_singleton(self):
        MCPClientManager._instance = None
        created = MCPClientManager.get_or_create_instance()
        assert MCPClientManager.get_instance() is created
        assert MCPClientManager() is created
        assert MCPClientManager.get_or_create_instance() is created

    @pytest.mark.asyncio
    async def test_load_no_file(self, monkeypatch):
        manager = MCPClientManager()
        monkeypatch.setattr(manager, "_read_servers_config", lambda p: None)
        assert await manager.load_servers("x") == 0

    @pytest.mark.asyncio
    async def test_load_empty_servers(self, monkeypatch):
        manager = MCPClientManager()
        monkeypatch.setattr(manager, "_read_servers_config", lambda p: {"mcp_servers": {}})
        assert await manager.load_servers("x") == 0

    @pytest.mark.asyncio
    async def test_load_connects_and_rebuilds(self, monkeypatch):
        manager = MCPClientManager()
        monkeypatch.setattr(
            manager,
            "_read_servers_config",
            lambda p: {
                "mcp_servers": {
                    "a": {"enabled": True},
                    "b": {"enabled": False},
                }
            },
        )

        class FakeConn:
            def __init__(self, name, cfg):
                self.name = name

            async def connect(self):
                return True

            async def list_tools(self):
                return [{"name": "t"}]

            def get_tools_as_specialist_format(self):
                return {"mcp_a_t": {"fn": None}}

            async def disconnect(self):
                pass

        monkeypatch.setattr(mc, "MCPServerConnection", FakeConn)
        assert await manager.load_servers("x") == 1
        assert set(manager._all_tools) == {"mcp_a_t"}
        assert "a" in manager._servers

    @pytest.mark.asyncio
    async def test_load_removes_disabled_old_and_skips_reconnect(self, monkeypatch):
        manager = MCPClientManager()
        old = MagicMock()
        old.disconnect = AsyncMock()
        manager._servers = {"old": old, "keep": MagicMock()}
        monkeypatch.setattr(
            manager,
            "_read_servers_config",
            lambda p: {"mcp_servers": {"keep": {"enabled": True}}},
        )
        assert await manager.load_servers("x") == 1
        old.disconnect.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_load_connect_failure_and_empty_tools(self, monkeypatch):
        manager = MCPClientManager()
        monkeypatch.setattr(
            manager,
            "_read_servers_config",
            lambda p: {"mcp_servers": {"a": {}, "b": {}}},
        )

        class FakeConn:
            def __init__(self, name, cfg):
                self.name = name

            async def connect(self):
                return self.name == "a"

            async def list_tools(self):
                return []

            async def disconnect(self):
                pass

        monkeypatch.setattr(mc, "MCPServerConnection", FakeConn)
        assert await manager.load_servers("x") == 0

    def test_read_servers_config(self, tmp_path):
        assert MCPClientManager._read_servers_config(str(tmp_path / "no.json")) is None
        good = tmp_path / "good.json"
        good.write_text('{"mcp_servers": {}}')
        assert MCPClientManager._read_servers_config(str(good)) == {"mcp_servers": {}}
        bad = tmp_path / "bad.json"
        bad.write_text("not json")
        assert MCPClientManager._read_servers_config(str(bad)) is None

    def test_getters(self):
        manager = MCPClientManager()
        manager._servers = {"a": "conn"}
        manager._all_tools = {"t": {}}
        assert manager.get_server("a") == "conn"
        assert manager.get_all_tools() == {"t": {}}
        assert manager.get_tool_names() == ["t"]

    @pytest.mark.asyncio
    async def test_disconnect_all(self):
        manager = MCPClientManager()
        conn = MagicMock()
        conn.disconnect = AsyncMock()
        manager._servers = {"a": conn}
        manager._all_tools = {"t": {}}
        await manager.disconnect_all()
        conn.disconnect.assert_awaited_once()
        assert manager._servers == {}
        assert manager._all_tools == {}

    def test_create_default_config(self, tmp_path):
        path = tmp_path / "sub" / "mcp.json"
        assert MCPClientManager.create_default_config(str(path)) == str(path)
        data = json.loads(path.read_text())
        assert "filesystem" in data["mcp_servers"]

    def test_init_skips_when_servers_exist(self):
        manager = MCPClientManager()
        manager._servers = {"x": None}
        manager._all_tools = {}
        before = manager._servers
        MCPClientManager()
        assert manager._servers is before
