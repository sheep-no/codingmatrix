"""
ReActEngine 单元测试

覆盖：
- ReActStep/ReActResult 数据类
- 工具描述构建
- 系统 prompt 构建（simple/full 模式）
- 工具调用解析
- 工具执行（同步/异步）
- 历史文本构建（滑动窗口）
- simple 模式运行
- full 模式运行
- 无工具/无项目路径的降级
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.agent.react_engine import ReActEngine, ReActStep, ReActResult


class TestReActStep:
    def test_creation(self):
        step = ReActStep(step_type="thought", content="thinking...")
        assert step.step_type == "thought"
        assert step.content == "thinking..."
        assert step.tool_name is None
        assert step.tool_params is None
        assert step.tool_result is None
        assert step.success is None
        assert step.timestamp > 0

    def test_with_tool_info(self):
        step = ReActStep(
            step_type="action",
            content="exec tool",
            tool_name="read_file",
            tool_params={"file_path": "test.py"},
            tool_result={"content": "..."},
            success=True,
        )
        assert step.tool_name == "read_file"
        assert step.success is True


class TestReActResult:
    def test_creation(self):
        result = ReActResult(
            success=True,
            final_answer="done",
            steps=[],
            total_steps=0,
            execution_time=1.5,
        )
        assert result.success is True
        assert result.reflection_summary == ""


class TestReActEngineInit:
    def test_basic_init(self):
        tools = {"test_tool": {"fn": lambda **k: "ok", "description": "test", "params": {}}}
        engine = ReActEngine(tools=tools, call_llm_fn=AsyncMock(), project_path="/tmp")
        assert engine.mode == "simple"
        assert engine.max_rounds == 6
        assert engine.tool_names == ["test_tool"]

    def test_full_mode_init(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock(), mode="full")
        assert engine.mode == "full"


class TestBuildToolsDescription:
    def test_with_tools(self):
        tools = {
            "read_file": {"description": "Read file", "params": {"file_path": "string"}},
            "list_files": {"description": "List files", "params": {"directory": "string"}},
        }
        engine = ReActEngine(tools=tools, call_llm_fn=AsyncMock())
        desc = engine._build_tools_description()
        assert "read_file" in desc
        assert "list_files" in desc
        assert "Read file" in desc

    def test_empty_tools(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        desc = engine._build_tools_description()
        assert desc == ""


class TestBuildSystemPrompt:
    def test_simple_mode(self):
        tools = {"t1": {"fn": lambda **k: None, "description": "tool1", "params": {}}}
        engine = ReActEngine(tools=tools, call_llm_fn=AsyncMock(), mode="simple")
        prompt = engine._build_system_prompt("base prompt")
        assert "base prompt" in prompt
        assert "可用工具" in prompt
        assert "JSON" in prompt

    def test_full_mode(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock(), mode="full")
        prompt = engine._build_system_prompt("base prompt")
        assert "base prompt" in prompt
        assert "可用工具" in prompt


class TestParseToolCall:
    def test_valid_json(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        result = engine._parse_tool_call('{"tool": "read_file", "params": {"file_path": "x.py"}}')
        assert result == {"tool": "read_file", "params": {"file_path": "x.py"}}

    def test_no_tool_key(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        result = engine._parse_tool_call('{"name": "test"}')
        assert result is None

    def test_empty_text(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        assert engine._parse_tool_call("") is None
        assert engine._parse_tool_call(None) is None

    def test_non_json_text(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        result = engine._parse_tool_call("Just some text")
        assert result is None


class TestExecuteTool:
    @pytest.mark.asyncio
    async def test_sync_tool(self):
        def my_tool(project_path="", **kwargs):
            return {"result": "ok"}

        tools = {"my_tool": {"fn": my_tool, "description": "test", "params": {}}}
        engine = ReActEngine(tools=tools, call_llm_fn=AsyncMock(), project_path="/tmp")
        success, result = await engine._execute_tool("my_tool", {})
        assert success is True
        assert result == {"result": "ok"}

    @pytest.mark.asyncio
    async def test_async_tool(self):
        async def my_async_tool(project_path="", **kwargs):
            return {"result": "async_ok"}

        tools = {"my_async_tool": {"fn": my_async_tool, "description": "test", "params": {}}}
        engine = ReActEngine(tools=tools, call_llm_fn=AsyncMock(), project_path="/tmp")
        success, result = await engine._execute_tool("my_async_tool", {})
        assert success is True
        assert result == {"result": "async_ok"}

    @pytest.mark.asyncio
    async def test_nonexistent_tool(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        success, result = await engine._execute_tool("nonexistent", {})
        assert success is False
        assert "不存在" in result["error"]

    @pytest.mark.asyncio
    async def test_tool_exception(self):
        def bad_tool(project_path="", **kwargs):
            raise RuntimeError("tool broken")

        tools = {"bad_tool": {"fn": bad_tool, "description": "test", "params": {}}}
        engine = ReActEngine(tools=tools, call_llm_fn=AsyncMock(), project_path="/tmp")
        success, result = await engine._execute_tool("bad_tool", {})
        assert success is False
        assert "tool broken" in result["error"]


class TestBuildHistoryText:
    def test_empty_history(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        assert engine._build_history_text() == ""

    def test_few_entries(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        engine.tool_history = ["entry1", "entry2"]
        text = engine._build_history_text()
        assert "entry1" in text
        assert "entry2" in text

    def test_many_entries_sliding_window(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        engine.tool_history = [f"entry{i}" for i in range(10)]
        text = engine._build_history_text()
        # recent entries should be fully present
        assert "entry9" in text
        assert "entry8" in text
        assert "entry7" in text
        # early entries should be summarized
        assert "更早的工具调用" in text

    def test_large_single_entry_truncated(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        engine.tool_history = ["x" * 7000]
        text = engine._build_history_text()
        assert len(text) <= engine.MAX_HISTORY_CHARS + 50  # some margin for suffix


class TestRunSimpleMode:
    @pytest.mark.asyncio
    async def test_no_project_path_fallback(self):
        mock_llm = AsyncMock(return_value="direct response")
        engine = ReActEngine(tools={}, call_llm_fn=mock_llm, project_path="")
        result = await engine.run("test prompt", "system")
        assert result == "direct response"

    @pytest.mark.asyncio
    async def test_no_tools_fallback(self):
        mock_llm = AsyncMock(return_value="direct response")
        engine = ReActEngine(tools={}, call_llm_fn=mock_llm, project_path="/tmp")
        result = await engine.run("test prompt", "system")
        assert result == "direct response"

    @pytest.mark.asyncio
    async def test_natural_termination_no_tool_call(self):
        mock_llm = AsyncMock(return_value="final answer text")
        tools = {"t": {"fn": lambda **k: {}, "description": "t", "params": {}}}
        engine = ReActEngine(tools=tools, call_llm_fn=mock_llm, project_path="/tmp", max_rounds=3)
        result = await engine.run("task", "sys")
        assert result == "final answer text"
        assert len(engine.steps) == 1
        assert engine.steps[0].step_type == "final"

    @pytest.mark.asyncio
    async def test_tool_call_then_natural_termination(self):
        call_count = 0

        async def mock_llm(prompt, system_prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return '{"tool": "read_file", "params": {"file_path": "test.py"}}'
            return "final answer"

        def mock_read_file(project_path="", **kwargs):
            return {"content": "file content"}

        tools = {"read_file": {"fn": mock_read_file, "description": "read", "params": {"file_path": "string"}}}
        engine = ReActEngine(tools=tools, call_llm_fn=mock_llm, project_path="/tmp", max_rounds=3)
        result = await engine.run("task", "sys")
        assert result == "final answer"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_max_rounds_safety_valve(self):
        async def mock_llm(prompt, system_prompt):
            # always return tool call
            return '{"tool": "read_file", "params": {"file_path": "test.py"}}'

        def mock_read_file(project_path="", **kwargs):
            return {"content": "content"}

        tools = {"read_file": {"fn": mock_read_file, "description": "read", "params": {"file_path": "string"}}}
        engine = ReActEngine(tools=tools, call_llm_fn=mock_llm, project_path="/tmp", max_rounds=2)
        result = await engine.run("task", "sys")
        # should have stopped at max_rounds
        assert any(s.step_type == "final" for s in engine.steps)


class TestRunFullMode:
    @pytest.mark.asyncio
    async def test_full_mode_no_tool_call(self):
        mock_llm = AsyncMock(return_value="final answer")
        tools = {"t": {"fn": lambda **k: {}, "description": "t", "params": {}}}
        engine = ReActEngine(
            tools=tools, call_llm_fn=mock_llm, project_path="/tmp",
            max_rounds=2, mode="full",
        )
        result = await engine.run("task", "sys")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_full_mode_with_memory(self):
        mock_llm = AsyncMock(return_value="answer")
        mock_memory = MagicMock()
        mock_memory.get_context_for_prompt.return_value = ""
        tools = {"t": {"fn": lambda **k: {}, "description": "t", "params": {}}}
        engine = ReActEngine(
            tools=tools, call_llm_fn=mock_llm, project_path="/tmp",
            max_rounds=1, mode="full", memory=mock_memory,
        )
        result = await engine.run("task", "sys")
        mock_memory.add_user_message.assert_called()


class TestEmitEvent:
    @pytest.mark.asyncio
    async def test_emit_event_with_callback(self):
        mock_callback = MagicMock()
        mock_emit = MagicMock()

        engine = ReActEngine(
            tools={}, call_llm_fn=AsyncMock(),
            callback=mock_callback, emit_event_fn=mock_emit,
        )
        await engine._emit_event("test_event", {"key": "value"})
        mock_emit.assert_called_once_with(mock_callback, "test_event", {"key": "value"})

    @pytest.mark.asyncio
    async def test_emit_event_no_callback(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        # should not raise
        await engine._emit_event("test_event", {})


class TestStream:
    @pytest.mark.asyncio
    async def test_stream_with_callback(self):
        mock_cb = MagicMock()
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock(), stream_callback=mock_cb)
        await engine._stream("hello")
        mock_cb.assert_called_once_with("hello")

    @pytest.mark.asyncio
    async def test_stream_no_callback(self):
        engine = ReActEngine(tools={}, call_llm_fn=AsyncMock())
        # should not raise
        await engine._stream("hello")
