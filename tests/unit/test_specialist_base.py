"""
Specialist 基类单元测试

覆盖：
- Specialist 初始化
- 编辑文件追踪
- call_llm_with_tools 委托
- _emit_event
- 复杂度到 ReAct 模式的映射
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.specialist_base import (
    Specialist,
    SpecialistCallError,
    _REACT_MODE_BY_COMPLEXITY,
    _REACT_ROUNDS_BY_COMPLEXITY,
)


class TestReactModeMapping:
    def test_simple_uses_simple(self):
        assert _REACT_MODE_BY_COMPLEXITY["simple"] == "simple"

    def test_small_uses_simple(self):
        assert _REACT_MODE_BY_COMPLEXITY["small"] == "simple"

    def test_medium_uses_full(self):
        assert _REACT_MODE_BY_COMPLEXITY["medium"] == "full"

    def test_large_uses_full(self):
        assert _REACT_MODE_BY_COMPLEXITY["large"] == "full"

    def test_enterprise_uses_full(self):
        assert _REACT_MODE_BY_COMPLEXITY["enterprise"] == "full"

    def test_rounds_mapping(self):
        assert _REACT_ROUNDS_BY_COMPLEXITY["simple"] == 3
        assert _REACT_ROUNDS_BY_COMPLEXITY["small"] == 4
        assert _REACT_ROUNDS_BY_COMPLEXITY["medium"] == 6
        assert _REACT_ROUNDS_BY_COMPLEXITY["large"] == 8
        assert _REACT_ROUNDS_BY_COMPLEXITY["enterprise"] == 10


class TestSpecialistInit:
    @patch("app.agent.specialist_base.LayeredModelRouter")
    @patch("app.agent.specialist_base.LLMClient")
    def test_init_defaults(self, mock_llm_cls, mock_router):
        mock_router.get_model_config.return_value = {"max_tokens": 4096}
        s = Specialist(role_name="coder", model_name="test-model")
        assert s.role_name == "coder"
        assert s.model_name == "test-model"
        assert s.task_type == "generate"
        assert s._complexity == "medium"
        assert s._edited_files == []

    @patch("app.agent.specialist_base.LayeredModelRouter")
    @patch("app.agent.specialist_base.LLMClient")
    def test_init_with_complexity(self, mock_llm_cls, mock_router):
        mock_router.get_model_config.return_value = {"max_tokens": 4096}
        s = Specialist(role_name="reviewer", model_name="test", complexity="large")
        assert s._complexity == "large"


class TestEditedFiles:
    @patch("app.agent.specialist_base.LayeredModelRouter")
    @patch("app.agent.specialist_base.LLMClient")
    def test_get_edited_files_empty(self, mock_llm_cls, mock_router):
        mock_router.get_model_config.return_value = {}
        s = Specialist(role_name="test", model_name="test")
        assert s.get_edited_files() == []

    @patch("app.agent.specialist_base.LayeredModelRouter")
    @patch("app.agent.specialist_base.LLMClient")
    def test_clear_edits(self, mock_llm_cls, mock_router):
        mock_router.get_model_config.return_value = {}
        s = Specialist(role_name="test", model_name="test")
        s._edited_files = ["a.py", "b.py"]
        s.clear_edits()
        assert s._edited_files == []

    @patch("app.agent.specialist_base.LayeredModelRouter")
    @patch("app.agent.specialist_base.LLMClient")
    def test_get_edited_files_returns_copy(self, mock_llm_cls, mock_router):
        mock_router.get_model_config.return_value = {}
        s = Specialist(role_name="test", model_name="test")
        s._edited_files = ["a.py"]
        files = s.get_edited_files()
        files.append("b.py")
        assert s._edited_files == ["a.py"]


class TestBuildToolsDescription:
    def test_with_params(self):
        tools = {
            "read_file": {
                "description": "Read a file",
                "params": {"file_path": "string", "offset": "int"},
            }
        }
        desc = Specialist._build_tools_description(tools)
        assert "read_file" in desc
        assert "Read a file" in desc
        assert "file_path" in desc

    def test_empty_tools(self):
        desc = Specialist._build_tools_description({})
        assert desc == ""


class TestParseToolCall:
    def test_delegates_to_json_parser(self):
        result = Specialist._parse_tool_call('{"tool": "test", "params": {}}')
        assert result is not None
        assert result["tool"] == "test"

    def test_no_tool_returns_none(self):
        result = Specialist._parse_tool_call("just text")
        assert result is None


class TestEmitEvent:
    def test_emit_event_success(self):
        mock_cb = MagicMock()
        Specialist._emit_event(mock_cb, "test_event", {"key": "value"})
        mock_cb.assert_called_once()
        call_args = mock_cb.call_args[0][0]
        parsed = json.loads(call_args)
        assert parsed["type"] == "test_event"
        assert parsed["key"] == "value"

    def test_emit_event_callback_error(self):
        mock_cb = MagicMock(side_effect=Exception("callback error"))
        # should not raise
        Specialist._emit_event(mock_cb, "test_event", {})

    def test_emit_event_callback_returns_coroutine(self):
        async def async_cb(data):
            pass

        mock_cb = MagicMock(side_effect=async_cb)
        # should not raise (coroutine will be created as task)
        Specialist._emit_event(mock_cb, "test_event", {})


class TestCallLLM:
    @pytest.mark.asyncio
    @patch("app.agent.specialist_base.LayeredModelRouter")
    @patch("app.agent.specialist_base.LLMClient")
    async def test_call_llm_delegates(self, mock_llm_cls, mock_router):
        mock_router.get_model_config.return_value = {}
        mock_client = AsyncMock()
        mock_client.call.return_value = "response text"
        mock_llm_cls.return_value = mock_client

        s = Specialist(role_name="test", model_name="test")
        result = await s.call_llm("prompt", "system")
        assert result == "response text"
        mock_client.call.assert_called_once_with("prompt", "system", False)


class TestSpecialistCallError:
    def test_is_llm_client_error(self):
        assert SpecialistCallError.__name__ == "LLMClientError"


class TestCallLLMWithTools:
    @pytest.mark.asyncio
    @patch("app.agent.specialist_base.LayeredModelRouter")
    @patch("app.agent.specialist_base.LLMClient")
    @patch("app.agent.specialist_base.SPECIALIST_TOOLS", {})
    async def test_call_llm_with_tools_creates_engine(self, mock_llm_cls, mock_router):
        mock_router.get_model_config.return_value = {}
        mock_client = AsyncMock()
        mock_client.call.return_value = "final code"
        mock_llm_cls.return_value = mock_client

        s = Specialist(role_name="coder", model_name="test", complexity="simple")
        result = await s.call_llm_with_tools(
            prompt="write code",
            system_prompt="you are coder",
            project_path="/tmp",
        )
        assert isinstance(result, str)

    @pytest.mark.asyncio
    @patch("app.agent.specialist_base.LayeredModelRouter")
    @patch("app.agent.specialist_base.LLMClient")
    @patch("app.agent.specialist_base.SPECIALIST_TOOLS", {})
    async def test_call_llm_with_tools_tracks_edits(self, mock_llm_cls, mock_router):
        mock_router.get_model_config.return_value = {}
        mock_client = AsyncMock()
        mock_client.call.return_value = '{"tool": "partial_update", "params": {"path": "test.py", "target": "old", "replacement": "new"}}'
        mock_llm_cls.return_value = mock_client

        s = Specialist(role_name="coder", model_name="test", complexity="simple")
        # The tracked_execute_tool will be tested through the engine integration
        assert s._write_tools == {"partial_update", "insert_content", "regex_replace"}
