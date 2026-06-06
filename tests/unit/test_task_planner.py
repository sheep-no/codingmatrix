"""
任务规划器单元测试

覆盖：
- TaskPlanner 初始化
- decompose 正常拆解
- decompose 解析失败降级
- decompose 异常降级
- _explore_project
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.task_planner import TaskPlanner
from app.agent.file_contract import _degrade_step


class TestTaskPlannerInit:
    @patch("app.agent.task_planner.ModelRegistry")
    def test_init_default(self, mock_registry):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_registry.get.return_value = mock_model
        planner = TaskPlanner()
        mock_registry.get.assert_called_once_with("deepseek-r1-qwen3-8b")

    @patch("app.agent.task_planner.ModelRegistry")
    def test_init_custom_key(self, mock_registry):
        mock_model = MagicMock()
        mock_model.name = "custom-model"
        mock_registry.get.return_value = mock_model
        planner = TaskPlanner(model_key="custom-key")
        mock_registry.get.assert_called_once_with("custom-key")


class TestDecompose:
    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_decompose_success(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_model.max_tokens = 4096
        mock_registry.get.return_value = mock_model

        steps = [
            {"type": "file_operation", "description": "Read config", "params": {"operation": "read", "path": "config.py"}},
            {"type": "code_generation", "description": "Generate code", "params": {"language": "python"}},
        ]
        mock_call_llm.return_value = {
            "choices": [{"message": {"content": json.dumps(steps)}}],
        }

        planner = TaskPlanner()
        result = await planner.decompose("build a web app")
        assert len(result) == 2
        assert result[0]["type"] == "file_operation"
        assert result[1]["type"] == "code_generation"

    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_decompose_single_dict_wrapped(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_model.max_tokens = 4096
        mock_registry.get.return_value = mock_model

        step = {"type": "ai_call", "description": "Analyze", "params": {"task": "analyze"}}
        mock_call_llm.return_value = {
            "choices": [{"message": {"content": json.dumps(step)}}],
        }

        planner = TaskPlanner()
        result = await planner.decompose("analyze code")
        assert len(result) == 1
        assert result[0]["type"] == "ai_call"

    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_decompose_parse_failure_degrades(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_model.max_tokens = 4096
        mock_registry.get.return_value = mock_model

        mock_call_llm.return_value = {
            "choices": [{"message": {"content": "not json at all"}}],
        }

        planner = TaskPlanner()
        result = await planner.decompose("some task")
        assert len(result) == 1
        assert result[0]["type"] == "ai_call"
        assert result[0]["degraded"] is True

    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_decompose_llm_exception_degrades(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_model.max_tokens = 4096
        mock_registry.get.return_value = mock_model

        mock_call_llm.side_effect = RuntimeError("LLM down")

        planner = TaskPlanner()
        result = await planner.decompose("some task")
        assert len(result) == 1
        assert result[0]["degraded"] is True
        assert "LLM down" in result[0]["description"] or "异常" in result[0]["description"]

    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_decompose_with_context(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_model.max_tokens = 4096
        mock_registry.get.return_value = mock_model

        mock_call_llm.return_value = {
            "choices": [{"message": {"content": '[]'}}],
        }

        planner = TaskPlanner()
        result = await planner.decompose("task", context={"key": "value"})
        assert isinstance(result, list)

    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_decompose_with_dependency_hints(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_model.max_tokens = 4096
        mock_registry.get.return_value = mock_model

        mock_call_llm.return_value = {
            "choices": [{"message": {"content": '[]'}}],
        }

        planner = TaskPlanner()
        result = await planner.decompose("task", dependency_hints="models.py must be generated first")
        assert isinstance(result, list)

    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_decompose_invalid_schema_degrades(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_model.max_tokens = 4096
        mock_registry.get.return_value = mock_model

        # valid JSON but invalid TaskStep schema (missing required 'type' and 'description')
        mock_call_llm.return_value = {
            "choices": [{"message": {"content": '{"bad": "schema"}'}}],
        }

        planner = TaskPlanner()
        result = await planner.decompose("task")
        assert len(result) == 1
        assert result[0]["degraded"] is True


class TestExploreProject:
    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_explore_with_no_readonly_tools(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_registry.get.return_value = mock_model

        planner = TaskPlanner()
        result = await planner._explore_project("task", "/tmp", {"write_file": {"fn": lambda **k: {}, "description": "w", "params": {}}})
        assert result == ""

    @pytest.mark.asyncio
    @patch("app.agent.task_planner.call_llm")
    @patch("app.agent.task_planner.ModelRegistry")
    async def test_explore_with_readonly_tools(self, mock_registry, mock_call_llm):
        mock_model = MagicMock()
        mock_model.name = "test-model"
        mock_registry.get.return_value = mock_model

        mock_call_llm.return_value = {
            "choices": [{"message": {"content": "project structure: main.py, utils.py"}}],
        }

        mock_tools = {
            "list_files": {"fn": AsyncMock(return_value={"entries": []}), "description": "list", "params": {}},
            "read_file": {"fn": AsyncMock(return_value={"content": "x"}), "description": "read", "params": {}},
        }

        planner = TaskPlanner()
        result = await planner._explore_project("task", "/tmp", mock_tools)
        assert isinstance(result, str)


class TestDegradeStep:
    def test_degrade_step_format(self):
        step = _degrade_step("my task", "reason")
        assert step["type"] == "ai_call"
        assert step["params"]["task"] == "my task"
        assert step["degraded"] is True
        assert "reason" in step["description"]
