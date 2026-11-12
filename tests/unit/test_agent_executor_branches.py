"""EnhancedExecutor / StreamingExecutor 全分支回归。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import executor as ex


@pytest.fixture(autouse=True)
def reset_registry():
    ex.ToolRegistry.reset_instance()
    yield
    ex.ToolRegistry.reset_instance()


def _result(success=True, result=None, error=None):
    return ex.ToolResult(success, result, error)


class TestInterpretResult:
    def test_non_dict_is_success(self):
        out = ex._interpret_tool_result("ok", 0)
        assert out.success is True
        assert out.result == "ok"

    def test_dict_without_error_is_success(self):
        assert ex._interpret_tool_result({"a": 1}, 0).success is True

    def test_dict_with_error_is_failure(self):
        out = ex._interpret_tool_result({"error": "missing"}, 0)
        assert out.success is False
        assert out.error == "missing"

    def test_dict_explicit_success_overrides_error(self):
        out = ex._interpret_tool_result({"success": True, "error": "x"}, 0)
        assert out.success is True
        assert out.error is None

    def test_dict_explicit_failure(self):
        out = ex._interpret_tool_result({"success": False, "error": "bad"}, 0)
        assert out.success is False
        assert out.error == "bad"


class TestWrap:
    def test_wrap_sync_success(self):
        out = ex._wrap_sync(lambda p, **kw: {"value": kw["v"]}, "proj", {"v": 1})
        assert out.success is True
        assert out.result == {"value": 1}

    def test_wrap_sync_exception(self):
        def _boom(p, **kw):
            raise RuntimeError("sync failed")

        out = ex._wrap_sync(_boom, "proj", {})
        assert out.success is False
        assert "sync failed" in out.error

    @pytest.mark.asyncio
    async def test_wrap_async_success(self):
        async def _fn(p, **kw):
            return {"value": kw["v"]}

        out = await ex._wrap_async(_fn, "proj", {"v": 2})
        assert out.result == {"value": 2}

    @pytest.mark.asyncio
    async def test_wrap_async_exception(self):
        async def _boom(p, **kw):
            raise RuntimeError("async failed")

        out = await ex._wrap_async(_boom, "proj", {})
        assert out.success is False
        assert "async failed" in out.error


class TestRegistry:
    def test_singleton_and_reset(self):
        first = ex.ToolRegistry.get_instance()
        assert ex.ToolRegistry.get_instance() is first
        ex.ToolRegistry.reset_instance()
        assert ex.ToolRegistry.get_instance() is not first

    def test_register_get_schema_list(self):
        registry = ex.ToolRegistry.get_instance()
        registry.register("t", lambda: 1, "desc", {"type": "object"})
        assert registry.get("t")() == 1
        assert registry.get_schema("t") == {"type": "object"}
        assert registry.get("missing") is None
        assert registry.get_schema("missing") is None
        assert registry.list_tools() == [{"name": "t", "description": "desc"}]

    def test_register_without_schema(self):
        registry = ex.ToolRegistry.get_instance()
        registry.register("t", lambda: 1, "desc")
        assert registry.get_schema("t") == {}

    def test_get_all_schemas(self):
        registry = ex.ToolRegistry.get_instance()
        registry.register("t", lambda: 1, "desc", {"type": "object", "properties": {}})
        assert registry.get_all_schemas() == [
            {
                "type": "function",
                "function": {
                    "name": "t",
                    "description": "desc",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]


class TestParamsToSchema:
    def test_empty(self):
        assert ex.EnhancedExecutor._params_to_schema({}) == {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def test_types_and_required(self):
        schema = ex.EnhancedExecutor._params_to_schema(
            {
                "a": "string 描述",
                "b": "int 描述 (可选)",
                "c": "bool optional desc",
                "d": "float",
                "e": "object",
                "f": "list",
                "g": "unknown",
            }
        )
        props = schema["properties"]
        assert props["a"]["type"] == "string"
        assert props["b"]["type"] == "integer"
        assert props["d"]["type"] == "number"
        assert props["e"]["type"] == "object"
        assert props["f"]["type"] == "array"
        assert props["g"]["type"] == "string"
        assert schema["required"] == ["a", "d", "e", "f", "g"]


class TestEnhancedExecutorInit:
    def test_registers_default_tools(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        names = {t["name"] for t in executor.tool_registry.list_tools()}
        assert {"read_file", "write_file", "web_search", "http_request"} <= names
        assert executor.tool_registry._registered_project_path == str(tmp_path)

    def test_skips_registration_for_same_path(self, tmp_path):
        first = ex.EnhancedExecutor(project_path=str(tmp_path))
        registry = first.tool_registry
        registry.register("sentinel", lambda: 1, "s")
        ex.EnhancedExecutor(project_path=str(tmp_path))
        assert registry.get("sentinel") is not None

    def test_re_registers_for_different_path(self, tmp_path):
        first = ex.EnhancedExecutor(project_path=str(tmp_path))
        first.tool_registry.register("read_file", lambda: "stale", "s")
        ex.EnhancedExecutor(project_path=str(tmp_path / "other"))
        assert first.tool_registry._registered_project_path == str(tmp_path / "other")
        assert first.tool_registry.get("read_file")() is not "stale"

    @pytest.mark.asyncio
    async def test_sync_default_wrapper_uses_params_and_path(self, tmp_path, monkeypatch):
        seen = {}

        def _fake_read(project_path, **params):
            seen.update(path=project_path, params=params)
            return {"content": "x"}

        monkeypatch.setattr(ex, "_impl_read_file", _fake_read)
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        wrapper = executor.tool_registry.get("read_file")
        out = await wrapper({"file_path": "a.txt"}, limit=1)
        assert out.success is True
        assert seen == {"path": str(tmp_path), "params": {"file_path": "a.txt", "limit": 1}}
        await wrapper(file_path="b.txt", project_path="/other")
        assert seen["path"] == "/other"

    @pytest.mark.asyncio
    async def test_async_default_wrapper_uses_params_and_path(self, tmp_path, monkeypatch):
        seen = {}

        async def _fake_search(project_path, **params):
            seen.update(path=project_path, params=params)
            return {"results": []}

        monkeypatch.setattr(ex, "_impl_web_search", _fake_search)
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        wrapper = executor.tool_registry.get("web_search")
        out = await wrapper({"query": "q"}, limit=2)
        assert out.success is True
        assert seen == {"path": str(tmp_path), "params": {"query": "q", "limit": 2}}
        await wrapper(query="q2", project_path="/other")
        assert seen["path"] == "/other"


class TestMcp:
    @pytest.mark.asyncio
    async def test_returns_zero_when_loaded(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        executor._mcp_loaded = True
        assert await executor.load_mcp_tools() == 0

    @pytest.mark.asyncio
    async def test_loads_and_registers_tools(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        executor.tool_registry.reset_instance()
        executor._mcp_loaded = False

        class _Manager:
            @classmethod
            def get_or_create_instance(cls):
                return cls()

            async def load_servers(self):
                return 1

            def get_all_tools(self):
                return {
                    "mcp_tool": {
                        "fn": lambda: 1,
                        "description": "d",
                        "params": {"q": "string"},
                    }
                }

        import app.agent.mcp_client as mcp_client

        monkeypatch.setattr(mcp_client, "MCPClientManager", _Manager)
        count = await executor.load_mcp_tools()
        assert count == 1
        assert executor.tool_registry.get("mcp_tool") is not None

    @pytest.mark.asyncio
    async def test_no_tools_connected(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        executor.tool_registry.reset_instance()
        executor._mcp_loaded = False

        class _Manager:
            @classmethod
            def get_or_create_instance(cls):
                return cls()

            async def load_servers(self):
                return 0

            def get_all_tools(self):
                return {}

        import app.agent.mcp_client as mcp_client

        monkeypatch.setattr(mcp_client, "MCPClientManager", _Manager)
        assert await executor.load_mcp_tools() == 0
        assert executor._mcp_loaded is True

    @pytest.mark.asyncio
    async def test_manager_error_is_swallowed(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        executor._mcp_loaded = False

        class _Manager:
            @classmethod
            def get_or_create_instance(cls):
                raise RuntimeError("mcp down")

        import app.agent.mcp_client as mcp_client

        monkeypatch.setattr(mcp_client, "MCPClientManager", _Manager)
        assert await executor.load_mcp_tools() == 0
        assert executor._mcp_loaded is True


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_unknown_tool(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        out = await executor.execute_tool("nope", {})
        assert out.success is False
        assert "未知工具" in out.error

    @pytest.mark.asyncio
    async def test_async_tool_with_project_path(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        seen = {}

        async def _tool(params, project_path=None):
            seen["params"] = params
            seen["path"] = project_path
            return _result(True, "ok")

        executor.tool_registry.register("t", _tool, "d")
        out = await executor.execute_tool("t", {"a": 1})
        assert out.result == "ok"
        assert seen == {"params": {"a": 1}, "path": str(tmp_path)}

    @pytest.mark.asyncio
    async def test_async_tool_without_project_path(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        seen = {}

        async def _tool(params):
            seen["params"] = params
            return _result(True, params)

        executor.tool_registry.register("t", _tool, "d")
        out = await executor.execute_tool("t", {"a": 1})
        assert out.result == {"a": 1}
        assert seen == {"params": {"a": 1}}

    @pytest.mark.asyncio
    async def test_sync_tool_runs_in_thread(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))

        def _tool(params):
            return _result(True, params["x"])

        executor.tool_registry.register("t", _tool, "d")
        assert (await executor.execute_tool("t", {"x": 3})).result == 3

    @pytest.mark.asyncio
    async def test_tool_exception_is_captured(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))

        async def _tool(params):
            raise RuntimeError("tool blew up")

        executor.tool_registry.register("t", _tool, "d")
        out = await executor.execute_tool("t", {})
        assert out.success is False
        assert "tool blew up" in out.error


class TestExecute:
    @pytest.mark.asyncio
    async def test_tool_call(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        captured = {}

        async def _execute_tool(name, params):
            captured.update(name=name, params=params)
            return _result(True, "ok")

        monkeypatch.setattr(executor, "execute_tool", _execute_tool)
        out = await executor.execute(
            {"type": "tool_call", "params": {"tool": "x", "arguments": {"a": 1}}}
        )
        assert out.result == "ok"
        assert captured == {"name": "x", "params": {"a": 1}}

    @pytest.mark.asyncio
    async def test_function_call_name_and_params(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        captured = {}

        async def _execute_tool(name, params):
            captured.update(name=name, params=params)
            return _result(True)

        monkeypatch.setattr(executor, "execute_tool", _execute_tool)
        await executor.execute(
            {"type": "function_call", "params": {"name": "y", "params": {"b": 2}}}
        )
        assert captured == {"name": "y", "params": {"b": 2}}

    @pytest.mark.asyncio
    async def test_file_operation(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        called = []

        async def _execute_file_operation(params):
            called.append(params)
            return _result(True)

        monkeypatch.setattr(executor, "execute_file_operation", _execute_file_operation)
        await executor.execute({"type": "file_operation", "params": {"path": "x"}})
        assert called == [{"path": "x"}]

    @pytest.mark.asyncio
    async def test_api_call(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        called = []

        async def _adapt_http(params):
            called.append(params)
            return _result(True)

        monkeypatch.setattr(executor, "_adapt_http", _adapt_http)
        await executor.execute({"type": "api_call", "params": {"url": "u"}})
        assert called == [{"url": "u"}]

    @pytest.mark.asyncio
    async def test_code_execution_defaults(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        captured = {}

        async def _execute_tool(name, params):
            captured.update(name=name, params=params)
            return _result(True)

        monkeypatch.setattr(executor, "execute_tool", _execute_tool)
        await executor.execute({"type": "code_execution", "params": {}})
        assert captured == {"name": "execute_code", "params": {"code": "", "timeout": 30}}

    @pytest.mark.asyncio
    async def test_unknown_step_type(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        out = await executor.execute({"type": "mystery"})
        assert out.success is False
        assert "未知步骤类型" in out.error
        assert out.tool_name == "mystery"


class TestExecuteFileOperation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "operation,expected",
        [
            ("read", ("read_file", {"file_path": "p"})),
            ("write", ("write_file", {"path": "p", "content": "c"})),
            ("list", ("list_files", {"directory": "p"})),
        ],
    )
    async def test_supported(self, tmp_path, monkeypatch, operation, expected):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        captured = {}

        async def _execute_tool(name, params):
            captured.update(name=name, params=params)
            return _result(True)

        monkeypatch.setattr(executor, "execute_tool", _execute_tool)
        await executor.execute_file_operation(
            {"operation": operation, "path": "p", "content": "c"}
        )
        assert captured == {"name": expected[0], "params": expected[1]}

    @pytest.mark.asyncio
    async def test_default_operation_is_read(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        captured = {}

        async def _execute_tool(name, params):
            captured.update(name=name, params=params)
            return _result(True)

        monkeypatch.setattr(executor, "execute_tool", _execute_tool)
        await executor.execute_file_operation({"path": "p"})
        assert captured["name"] == "read_file"

    @pytest.mark.asyncio
    async def test_unknown_operation(self, tmp_path):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        out = await executor.execute_file_operation({"operation": "move"})
        assert out.success is False
        assert "未知文件操作" in out.error

    @pytest.mark.asyncio
    async def test_adapt_http(self, tmp_path, monkeypatch):
        executor = ex.EnhancedExecutor(project_path=str(tmp_path))
        captured = {}

        async def _execute_tool(name, params):
            captured.update(name=name, params=params)
            return _result(True)

        monkeypatch.setattr(executor, "execute_tool", _execute_tool)
        await executor._adapt_http({"url": "u"})
        assert captured == {"name": "http_request", "params": {"url": "u"}}


class TestStreamingExecutor:
    @pytest.mark.asyncio
    async def test_set_callback_and_stream_output(self, tmp_path):
        executor = ex.StreamingExecutor(project_path=str(tmp_path))
        chunks = []
        executor.set_stream_callback(chunks.append)
        await executor._stream_output("hello")
        assert chunks == ["hello"]

    @pytest.mark.asyncio
    async def test_stream_without_callback(self, tmp_path):
        executor = ex.StreamingExecutor(project_path=str(tmp_path))
        await executor._stream_output("hello")

    @pytest.mark.asyncio
    async def test_callback_error_is_logged(self, tmp_path, monkeypatch):
        executor = ex.StreamingExecutor(project_path=str(tmp_path))
        messages = []

        def _boom(text):
            raise RuntimeError("cb failed")

        monkeypatch.setattr(
            ex.logger, "error", lambda message: messages.append(message)
        )
        executor.set_stream_callback(_boom)
        await executor._stream_output("hello")
        assert "cb failed" in messages[0]

    @pytest.mark.asyncio
    async def test_execute_with_stream_success(self, tmp_path, monkeypatch):
        executor = ex.StreamingExecutor(project_path=str(tmp_path))
        chunks = []
        executor.set_stream_callback(chunks.append)

        async def _execute(step):
            return _result(True, "done")

        monkeypatch.setattr(executor, "execute", _execute)
        out = await executor.execute_with_stream({"type": "tool_call"})
        assert out.success is True
        assert chunks == ["[开始执行: tool_call]\n", "[成功] done\n"]

    @pytest.mark.asyncio
    async def test_execute_with_stream_failure(self, tmp_path, monkeypatch):
        executor = ex.StreamingExecutor(project_path=str(tmp_path))
        chunks = []
        executor.set_stream_callback(chunks.append)

        async def _execute(step):
            return _result(False, None, "bad")

        monkeypatch.setattr(executor, "execute", _execute)
        out = await executor.execute_with_stream({"type": "tool_call"})
        assert out.success is False
        assert chunks[-1] == "[失败] bad\n"
