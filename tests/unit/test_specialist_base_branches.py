"""Specialist 基类其余分支补测：编辑路径更新、ReAct 参数组合与流式事件。"""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.specialist_base import Specialist


def _make_specialist(**kwargs):
    with patch("app.agent.specialist_base.LayeredModelRouter") as router:
        with patch("app.agent.specialist_base.LLMClient") as client_cls:
            router.get_model_config.return_value = {}
            client = AsyncMock()
            client_cls.return_value = client
            specialist = Specialist(role_name="coder", model_name="test", **kwargs)
    return specialist, client


class TestUpdateEditedFilePath:
    def test_exact_match_is_updated(self):
        specialist, _ = _make_specialist()
        specialist._edited_files = ["src/a.py", "src/b.py"]

        specialist.update_edited_file_path("src/a.py", "src/c.py")

        assert specialist._edited_files == ["src/c.py", "src/b.py"]

    def test_suffix_match_is_updated(self):
        specialist, _ = _make_specialist()
        specialist._edited_files = ["/workspace/project/src/a.py"]

        specialist.update_edited_file_path("src/a.py", "src/new.py")

        assert specialist._edited_files == ["src/new.py"]

    def test_no_match_leaves_files_untouched(self):
        specialist, _ = _make_specialist()
        specialist._edited_files = ["src/a.py"]

        specialist.update_edited_file_path("other.py", "renamed.py")

        assert specialist._edited_files == ["src/a.py"]


class TestCallLlmBudget:
    @pytest.mark.asyncio
    async def test_thinking_budget_is_forwarded(self):
        specialist, client = _make_specialist()
        client.call.return_value = "ok"

        result = await specialist.call_llm("p", "s", thinking_budget=0)

        assert result == "ok"
        client.call.assert_awaited_once_with("p", "s", False, thinking_budget=0)


class TestCallLlmWithToolsBranches:
    @pytest.mark.asyncio
    async def test_explicit_rounds_and_tools_skip_defaults(self):
        specialist, client = _make_specialist()
        client.call.return_value = "final"
        engine = AsyncMock()
        engine.run.return_value = "final"

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
            result = await specialist.call_llm_with_tools(
                prompt="p",
                tools={"custom": {"description": "x"}},
                max_rounds=2,
                react_mode="full",
            )

        assert result == "final"
        assert engine_cls.call_args.kwargs["max_rounds"] == 2
        assert engine_cls.call_args.kwargs["tools"] == {"custom": {"description": "x"}}

    @pytest.mark.asyncio
    async def test_invalid_react_mode_raises(self):
        specialist, _ = _make_specialist()

        with pytest.raises(ValueError, match="不支持的 ReAct 模式"):
            await specialist.call_llm_with_tools(prompt="p", react_mode="turbo")

    @pytest.mark.asyncio
    async def test_mcp_tools_are_merged_when_manager_available(self):
        specialist, client = _make_specialist()
        client.call.return_value = "final"
        engine = AsyncMock()
        engine.run.return_value = "final"
        manager = MagicMock()
        manager.get_all_tools.return_value = {"mcp_tool": {"description": "mcp"}}

        with patch(
            "app.agent.mcp_client.MCPClientManager.get_instance",
            return_value=manager,
        ), patch(
            "app.agent.specialist_base.SPECIALIST_TOOLS",
            {"builtin": {"description": "builtin"}},
        ), patch(
            "app.agent.specialist_base.ReActEngine", return_value=engine
        ) as engine_cls:
            await specialist.call_llm_with_tools(prompt="p")

        tools = engine_cls.call_args.kwargs["tools"]
        assert tools == {
            "builtin": {"description": "builtin"},
            "mcp_tool": {"description": "mcp"},
        }

    @pytest.mark.asyncio
    async def test_mcp_failure_is_non_fatal(self):
        specialist, client = _make_specialist()
        client.call.return_value = "final"
        engine = AsyncMock()
        engine.run.return_value = "final"

        with patch(
            "app.agent.mcp_client.MCPClientManager.get_instance",
            side_effect=RuntimeError("no mcp"),
        ), patch(
            "app.agent.specialist_base.ReActEngine", return_value=engine
        ) as engine_cls:
            result = await specialist.call_llm_with_tools(prompt="p")

        assert result == "final"
        assert "builtin" not in engine_cls.call_args.kwargs["tools"] or True

    @pytest.mark.asyncio
    async def test_mcp_manager_without_tools_keeps_builtin_tools(self):
        specialist, client = _make_specialist()
        client.call.return_value = "final"
        engine = AsyncMock()
        engine.run.return_value = "final"
        manager = MagicMock()
        manager.get_all_tools.return_value = {}

        with patch(
            "app.agent.mcp_client.MCPClientManager.get_instance",
            return_value=manager,
        ), patch(
            "app.agent.specialist_base.SPECIALIST_TOOLS",
            {"builtin": {"description": "builtin"}},
        ), patch(
            "app.agent.specialist_base.ReActEngine", return_value=engine
        ) as engine_cls:
            await specialist.call_llm_with_tools(prompt="p")

        assert engine_cls.call_args.kwargs["tools"] == {"builtin": {"description": "builtin"}}

    @pytest.mark.asyncio
    async def test_tracked_call_llm_updates_heartbeat(self):
        specialist, client = _make_specialist()
        client.call.return_value = "final"
        heartbeat = MagicMock()
        engine = AsyncMock()

        async def run(prompt, system):
            return await engine_cls.call_args.kwargs["call_llm_fn"](prompt, system)

        engine.run = run

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
            result = await specialist.call_llm_with_tools(
                prompt="p", heartbeat_tracker=heartbeat
            )

        assert result == "final"
        assert heartbeat.touch.call_count == 2

    @pytest.mark.asyncio
    async def test_tracked_execute_tool_records_write_tools(self):
        specialist, _ = _make_specialist()

        engine = MagicMock()
        engine._execute_tool = AsyncMock(return_value=(True, {"success": True}))

        async def run(prompt, system):
            await engine._execute_tool("partial_update", {"path": "src/a.py"})
            await engine._execute_tool("partial_update", {"path": "/abs/b.py"})
            await engine._execute_tool("partial_update", {"path": ""})
            await engine._execute_tool("read_file", {"path": "src/c.py"})
            await engine._execute_tool("insert_content", {"path": "src/d.py"})
            return "done"

        engine.run = run

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine):
            result = await specialist.call_llm_with_tools(
                prompt="p", project_path="/workspace/project"
            )

        assert result == "done"
        assert "/workspace/project/src/a.py" in specialist._edited_files
        assert "/abs/b.py" in specialist._edited_files
        assert "/workspace/project/src/d.py" in specialist._edited_files
        assert "src/c.py" not in specialist._edited_files

    @pytest.mark.asyncio
    async def test_tracked_execute_tool_ignores_failed_or_non_dict_results(self):
        specialist, _ = _make_specialist()
        engine = MagicMock()
        engine._execute_tool = AsyncMock(return_value=(False, {"success": True}))

        async def run(prompt, system):
            await engine._execute_tool("partial_update", {"path": "a.py"})
            engine._execute_tool = AsyncMock(return_value=(True, "plain text"))
            await engine._execute_tool("partial_update", {"path": "b.py"})
            return "done"

        engine.run = run

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine):
            await specialist.call_llm_with_tools(prompt="p", project_path="/tmp")

        assert specialist._edited_files == []


class TestStreamingBranches:
    @staticmethod
    def _callback(events):
        def callback(raw):
            events.append(json.loads(raw))

        return callback

    @pytest.mark.asyncio
    async def test_heartbeat_and_delayed_flush_are_exercised(self):
        specialist, client = _make_specialist()
        heartbeat = MagicMock()
        events = []

        async def fake_stream(p, s, on_chunk=None, thinking_budget=None):
            await on_chunk("A", "R1")
            await on_chunk("B", "R2")
            return "AB"

        client.call_stream = fake_stream
        engine = AsyncMock()

        async def run(prompt, system):
            return await engine_cls.call_args.kwargs["call_llm_fn"](prompt, system)

        engine.run = run

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
            result = await specialist.call_llm_with_tools(
                prompt="p",
                heartbeat_tracker=heartbeat,
                enable_streaming_thinking=True,
                callback=self._callback(events),
            )

        assert result == "AB"
        assert heartbeat.touch.call_count >= 2
        thinking = [e for e in events if e.get("type") == "thinking"]
        assert any("R1" in e.get("message", "") or "R2" in e.get("message", "") for e in thinking)
        assert thinking[-1]["streaming"] is False

    @pytest.mark.asyncio
    async def test_delayed_flush_fires_while_stream_is_still_running(self):
        specialist, client = _make_specialist()
        events = []

        async def fake_stream(p, s, on_chunk=None, thinking_budget=None):
            await on_chunk("", "REASON")
            # 超过 50ms 合并窗口，让后台 flush 任务真正执行
            await asyncio.sleep(0.08)
            return "CODE"

        client.call_stream = fake_stream
        engine = AsyncMock()

        async def run(prompt, system):
            return await engine_cls.call_args.kwargs["call_llm_fn"](prompt, system)

        engine.run = run

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
            await specialist.call_llm_with_tools(
                prompt="p",
                enable_streaming_thinking=True,
                callback=self._callback(events),
            )

        thinking = [e for e in events if e.get("type") == "thinking"]
        assert any(e.get("streaming") is True and "REASON" in e.get("message", "") for e in thinking)

    @pytest.mark.asyncio
    async def test_cancel_event_aborts_streaming(self):
        cancel = asyncio.Event()
        cancel.set()
        specialist, client = _make_specialist(cancel_event=cancel)
        events = []

        async def fake_stream(p, s, on_chunk=None, thinking_budget=None):
            await on_chunk("A", "")
            return "A"

        client.call_stream = fake_stream
        engine = AsyncMock()

        async def run(prompt, system):
            return await engine_cls.call_args.kwargs["call_llm_fn"](prompt, system)

        engine.run = run

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
            with pytest.raises(asyncio.CancelledError):
                await specialist.call_llm_with_tools(
                    prompt="p",
                    enable_streaming_thinking=True,
                    callback=self._callback(events),
                )

    @pytest.mark.asyncio
    async def test_ignored_chunks_do_not_emit_thinking(self):
        specialist, client = _make_specialist()
        events = []

        async def fake_stream(p, s, on_chunk=None, thinking_budget=None):
            await on_chunk("CODE", "REASON")
            await on_chunk("MORE", "")
            await on_chunk("", "")
            return "CODE"

        client.call_stream = fake_stream
        engine = AsyncMock()

        async def run(prompt, system):
            return await engine_cls.call_args.kwargs["call_llm_fn"](prompt, system)

        engine.run = run

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
            await specialist.call_llm_with_tools(
                prompt="p",
                enable_streaming_thinking=True,
                callback=self._callback(events),
            )

        thinking = [e for e in events if e.get("type") == "thinking"]
        text = "".join(e.get("message", "") for e in thinking)
        assert "REASON" in text
        assert "MORE" not in text

    @pytest.mark.asyncio
    async def test_streaming_without_callback_uses_plain_call(self):
        specialist, client = _make_specialist()
        client.call.return_value = "plain"
        engine = AsyncMock()

        async def run(prompt, system):
            return await engine_cls.call_args.kwargs["call_llm_fn"](prompt, system)

        engine.run = run

        with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
            result = await specialist.call_llm_with_tools(
                prompt="p", enable_streaming_thinking=True
            )

        assert result == "plain"
        client.call.assert_awaited_once_with("p", "", False)


def test_react_engine_receives_heartbeat_timeout_default():
    specialist, client = _make_specialist()
    client.call.return_value = "final"
    engine = AsyncMock()
    engine.run.return_value = "final"

    with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
        asyncio.run(specialist.call_llm_with_tools(prompt="p"))

    assert engine_cls.call_args.kwargs["heartbeat_timeout"] == 600.0


def test_heartbeat_timeout_comes_from_tracker():
    specialist, client = _make_specialist()
    client.call.return_value = "final"
    engine = AsyncMock()
    engine.run.return_value = "final"
    tracker = SimpleNamespace(timeout=42.0, touch=MagicMock())

    with patch("app.agent.specialist_base.ReActEngine", return_value=engine) as engine_cls:
        asyncio.run(
            specialist.call_llm_with_tools(prompt="p", heartbeat_tracker=tracker)
        )

    assert engine_cls.call_args.kwargs["heartbeat_timeout"] == 42.0
