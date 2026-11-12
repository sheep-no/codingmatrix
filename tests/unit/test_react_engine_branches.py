import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.mcp_client import MCPError
from app.agent.react_engine import ReActEngine, ReActStep
from app.agent.topology_scheduler import HeartbeatTracker


def _engine(**overrides):
    values = {
        "tools": {"t": {"fn": lambda **kwargs: {"ok": True}, "description": "t", "params": {}}},
        "call_llm_fn": AsyncMock(return_value="answer"),
        "project_path": "/tmp",
    }
    values.update(overrides)
    return ReActEngine(**values)


@pytest.mark.asyncio
async def test_parse_tool_call_uses_safe_parser_after_json_decode_failure():
    engine = _engine(tools={})
    engine.json_parser = MagicMock()
    engine.json_parser.safe_parse_json.return_value = {"tool": "t", "params": {"x": 1}}

    assert engine._parse_tool_call("not json at all") == {"tool": "t", "params": {"x": 1}}


@pytest.mark.asyncio
async def test_execute_tool_propagates_cancellation_and_mcp_errors():
    def cancelled_tool(project_path="", **kwargs):
        raise asyncio.CancelledError()

    def mcp_tool(project_path="", **kwargs):
        raise MCPError("connection lost")

    cancel_engine = _engine(tools={"x": {"fn": cancelled_tool}})
    with pytest.raises(asyncio.CancelledError):
        await cancel_engine._execute_tool("x", {})

    mcp_engine = _engine(tools={"x": {"fn": mcp_tool}})
    with pytest.raises(MCPError):
        await mcp_engine._execute_tool("x", {})


@pytest.mark.asyncio
async def test_emit_event_and_stream_swallow_callback_failures():
    def broken_emit(callback, event_type, data):
        raise RuntimeError("emit failed")

    def broken_stream(text):
        raise RuntimeError("stream failed")

    engine = _engine(
        tools={},
        callback=object(),
        emit_event_fn=broken_emit,
        stream_callback=broken_stream,
    )

    await engine._emit_event("x", {})
    await engine._stream("text")


@pytest.mark.asyncio
async def test_reflect_returns_dict_and_falls_back_for_non_dict():
    engine = _engine()
    engine._heartbeat_tracker = None
    engine.json_parser = MagicMock()
    engine.json_parser.safe_parse_json.return_value = {
        "continue": True,
        "task_complete": False,
        "reflection": "keep going",
    }
    result = await engine._reflect("task", [ReActStep("thought", "x")])
    assert result["reflection"] == "keep going"

    engine.json_parser.safe_parse_json.return_value = ["not", "a", "dict"]
    engine.call_llm_fn = AsyncMock(return_value="raw reflection")
    result = await engine._reflect("task", [])
    assert result == {"continue": True, "task_complete": False, "reflection": "raw reflection"}


@pytest.mark.asyncio
async def test_reflect_wraps_llm_failure():
    engine = _engine()
    engine._heartbeat_tracker = None
    engine.call_llm_fn = AsyncMock(side_effect=ValueError("boom"))

    with pytest.raises(RuntimeError, match="reflection LLM call failed"):
        await engine._reflect("task", [])


@pytest.mark.asyncio
async def test_generate_final_answer_rejects_empty_and_wraps_failure():
    engine = _engine()
    engine._heartbeat_tracker = None
    engine.call_llm_fn = AsyncMock(return_value="   ")
    with pytest.raises(RuntimeError, match="final answer was empty"):
        await engine._generate_final_answer("task", [])

    engine.call_llm_fn = AsyncMock(side_effect=ValueError("boom"))
    with pytest.raises(RuntimeError, match="final answer failed"):
        await engine._generate_final_answer("task", [])


@pytest.mark.asyncio
async def test_run_without_project_raises_when_heartbeat_times_out():
    async def hanging_llm(_prompt, _system):
        await asyncio.Event().wait()

    tracker = HeartbeatTracker(timeout=0.03)
    engine = ReActEngine(
        tools={},
        call_llm_fn=hanging_llm,
        project_path="",
        heartbeat_timeout=tracker.timeout,
        heartbeat_tracker=tracker,
    )

    with pytest.raises(asyncio.TimeoutError, match="心跳超时"):
        await asyncio.wait_for(engine.run("task", "sys"), timeout=0.3)


def test_build_history_text_hard_truncates_when_summary_cannot_shrink(monkeypatch):
    engine = _engine(tools={})
    engine.tool_history = ["early-1", "early-2"] + ["x" * 20000] * engine.MAX_RECENT_ENTRIES

    # Early summary has no blank line; recent entries are joined with "\n\n".
    def no_summary_tokens(text):
        if "\n\n" not in text:
            return 0
        return 999999

    monkeypatch.setattr(engine, "_estimate_tokens", no_summary_tokens)
    monkeypatch.setattr(engine, "_truncate_to_tokens", MagicMock(return_value="TRUNCATED"))
    assert engine._build_history_text() == "TRUNCATED"


def test_build_history_text_shrinks_summary_then_skips_hard_truncate(monkeypatch):
    engine = _engine(tools={})
    engine.tool_history = ["early-1", "early-2"] + ["x" * 20000] * engine.MAX_RECENT_ENTRIES
    # summary cut brings the text back under the limit -> skip hard truncate.
    # Estimate order: full text (452), full text (453), summary (455), full text again (461).
    estimates = iter([5000, 5000, 2000, 1000])
    monkeypatch.setattr(engine, "_estimate_tokens", lambda text: next(estimates))
    assert "结果已截断" not in engine._build_history_text()


def test_truncate_to_tokens_returns_text_when_within_budget():
    assert ReActEngine._truncate_to_tokens("short text", 100) == "short text"


@pytest.mark.asyncio
async def test_run_simple_returns_empty_on_cancel():
    cancel = asyncio.Event()
    cancel.set()
    engine = _engine(cancel_event=cancel)

    assert await engine.run("task", "sys") == ""


@pytest.mark.asyncio
async def test_run_simple_forced_generation_rejects_empty_response():
    engine = _engine(call_llm_fn=AsyncMock(return_value=""), max_rounds=1)

    with pytest.raises(RuntimeError, match="forced generate returned empty"):
        await engine.run("task", "sys")


@pytest.mark.asyncio
async def test_run_simple_recovers_from_empty_response(monkeypatch):
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())
    llm = AsyncMock(side_effect=["", "recovered answer"])
    engine = _engine(call_llm_fn=llm, max_rounds=3)

    assert await engine.run("task", "sys") == "recovered answer"


@pytest.mark.asyncio
async def test_run_simple_wraps_mcp_disconnect():
    def mcp_tool(project_path="", **kwargs):
        raise MCPError("gone")

    llm = AsyncMock(side_effect=[
        '{"tool": "x", "params": {}}',
        "unreachable",
    ])
    engine = _engine(
        tools={"x": {"fn": mcp_tool, "description": "x", "params": {}}},
        call_llm_fn=llm,
        max_rounds=3,
    )

    with pytest.raises(RuntimeError, match="MCP connection lost"):
        await engine.run("task", "sys")


@pytest.mark.asyncio
async def test_run_simple_reraises_non_mcp_tool_execution_error():
    llm = AsyncMock(return_value='{"tool": "t", "params": {}}')
    engine = _engine(call_llm_fn=llm, max_rounds=3)
    engine._execute_tool = AsyncMock(side_effect=ValueError("unexpected"))

    with pytest.raises(ValueError, match="unexpected"):
        await engine.run("task", "sys")


@pytest.mark.asyncio
async def test_run_simple_with_zero_rounds_raises_ending_error():
    engine = _engine(max_rounds=0)

    with pytest.raises(RuntimeError, match="ended without a final response"):
        await engine.run("task", "sys")


@pytest.mark.asyncio
async def test_run_full_returns_empty_on_cancel():
    cancel = asyncio.Event()
    cancel.set()
    engine = _engine(mode="full", cancel_event=cancel)

    assert await engine.run("task", "sys") == ""


@pytest.mark.asyncio
async def test_run_full_rejects_empty_action():
    engine = _engine(
        mode="full",
        call_llm_fn=AsyncMock(side_effect=["thinking", "  "]),
        max_rounds=2,
    )

    with pytest.raises(RuntimeError, match="action was empty"):
        await engine.run("task", "sys")


@pytest.mark.asyncio
async def test_run_full_tool_observation_reflection_then_final_answer():
    memory = MagicMock()
    memory.get_context_for_prompt.return_value = "remembered"
    llm = AsyncMock(side_effect=[
        "thinking",
        '{"tool": "t", "params": {}}',
        "observed",
        '{"continue": false, "task_complete": true, "reflection": "done"}',
        "final answer",
    ])
    engine = _engine(mode="full", call_llm_fn=llm, memory=memory, max_rounds=1)

    result = await engine.run("task", "sys")

    assert result == "final answer"
    memory.add_user_message.assert_called_once()
    memory.add_tool_result.assert_called_once()
    memory.add_reflection.assert_called_once()
    memory.add_assistant_message.assert_called_once()
    assert any(step.step_type == "reflection" for step in engine.steps)


@pytest.mark.asyncio
async def test_run_full_continues_to_next_iteration_after_reflection():
    llm = AsyncMock(side_effect=[
        "thinking-1",
        '{"tool": "t", "params": {}}',
        "observed-1",
        '{"continue": true, "task_complete": false, "reflection": "more"}',
        "thinking-2",
        "final text",
    ])
    engine = _engine(mode="full", call_llm_fn=llm, max_rounds=2)

    assert await engine.run("task", "sys") == "final text"


@pytest.mark.asyncio
async def test_run_full_exhausted_rounds_builds_final_result():
    llm = AsyncMock(side_effect=[
        "thinking",
        '{"tool": "t", "params": {}}',
        "observed",
        '{"continue": true, "task_complete": false, "reflection": "again"}',
        "generated final",
    ])
    engine = _engine(mode="full", call_llm_fn=llm, max_rounds=1)

    assert await engine.run("task", "sys") == "generated final"


@pytest.mark.asyncio
async def test_run_full_wraps_mcp_disconnect():
    def mcp_tool(project_path="", **kwargs):
        raise MCPError("lost")

    llm = AsyncMock(side_effect=["thinking", '{"tool": "x", "params": {}}'])
    engine = _engine(
        tools={"x": {"fn": mcp_tool, "description": "x", "params": {}}},
        call_llm_fn=llm,
        mode="full",
        max_rounds=2,
    )

    with pytest.raises(RuntimeError, match="MCP connection lost"):
        await engine.run("task", "sys")


@pytest.mark.asyncio
async def test_run_full_reraises_non_mcp_tool_execution_error():
    llm = AsyncMock(side_effect=["thinking", '{"tool": "t", "params": {}}'])
    engine = _engine(mode="full", call_llm_fn=llm, max_rounds=2)
    engine._execute_tool = AsyncMock(side_effect=ValueError("unexpected"))

    with pytest.raises(ValueError, match="unexpected"):
        await engine.run("task", "sys")


@pytest.mark.asyncio
async def test_run_full_wraps_observation_llm_failure():
    llm = AsyncMock(side_effect=[
        "thinking",
        '{"tool": "t", "params": {}}',
        RuntimeError("observation boom"),
    ])
    engine = _engine(mode="full", call_llm_fn=llm, max_rounds=2)

    with pytest.raises(RuntimeError, match="observation LLM call failed"):
        await engine.run("task", "sys")


@pytest.mark.asyncio
async def test_call_llm_with_heartbeat_without_tracker():
    engine = _engine()
    engine._heartbeat_tracker = None

    assert await engine._call_llm_with_heartbeat("prompt", "system") == "answer"


def test_build_context_uses_history_and_memory():
    engine = _engine(tools={})
    memory = MagicMock()
    memory.get_context_for_prompt.return_value = "memo"
    engine.memory = memory
    engine.tool_history = ["entry-a", "entry-b", "entry-c", "entry-d"]

    context = engine._build_context()

    assert "工具调用记录：" in context
    assert "entry-d" in context
    assert "记忆：memo" in context


def test_build_context_without_data():
    engine = _engine(tools={})
    memory = MagicMock()
    memory.get_context_for_prompt.return_value = ""
    engine.memory = memory

    assert engine._build_context() == "无"
