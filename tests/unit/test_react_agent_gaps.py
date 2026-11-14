"""ReActAgent thin wrapper 全分支补测。"""

import pytest

from app.agent import react_agent as module
from app.agent.react_agent import ReActAgent, ReActResult, ReActStep


class _Reflection:
    def __init__(self, insights):
        self._insights = insights

    def get_insights(self):
        return list(self._insights)


class _Memory:
    def __init__(self, insights=()):
        self.reflection = _Reflection(insights)


def test_custom_model_name_builds_model_info():
    agent = ReActAgent(model_name="my-model", api_key_token="token")

    assert agent.default_model.name == "my-model"
    assert agent.default_model.display_name == "my-model"
    assert agent.model is agent.default_model
    assert agent.api_key_token == "token"


def test_model_key_path_uses_registry(monkeypatch):
    sentinel = object()

    class _Registry:
        @staticmethod
        def get(key):
            assert key == "glm-z1-9b"
            return sentinel

    monkeypatch.setattr(module, "ModelRegistry", _Registry)

    assert ReActAgent().default_model is sentinel


def test_stage_models_default_and_override():
    assert ReActAgent().stage_models == ReActAgent.DEFAULT_STAGE_MODELS
    custom = {"thought": "m"}
    assert ReActAgent(stage_models=custom).stage_models is custom


def test_set_stream_callback_updates_executor():
    agent = ReActAgent()
    seen = []
    agent.executor.set_stream_callback = seen.append

    agent.set_stream_callback(lambda text: None)

    assert len(seen) == 1
    assert agent._stream_callback is seen[0]


async def test_process_builds_tools_from_registry_and_passes_results(monkeypatch):
    captured = {}

    class _Engine:
        def __init__(self, **kwargs):
            captured["engine_kwargs"] = kwargs
            self.steps = [
                module.ReActStep(step_type="action", content="do", success=None),
            ]

        async def run(self, task, prompt):
            captured["run"] = (task, prompt)
            return "final answer"

    monkeypatch.setattr(module, "ReActEngine", _Engine)
    agent = ReActAgent(max_iterations=3, enable_streaming=True)
    agent.memory = _Memory([{"summary": "insight"}])
    agent._stream_callback = lambda text: None
    agent.executor.tool_registry._tools = {
        "read": {
            "func": lambda: None,
            "description": "read files",
            "parameters": {"properties": {"path": {"type": "string"}}},
        },
        "broken": {},
    }

    result = await agent.process("do it", {"project_path": "/tmp/p"})

    assert captured["run"] == ("do it", "")
    kwargs = captured["engine_kwargs"]
    assert kwargs["tools"] == {
        "read": {
            "fn": agent.executor.tool_registry._tools["read"]["func"],
            "description": "read files",
            "params": {"path": "string"},
        }
    }
    assert kwargs["project_path"] == "/tmp/p"
    assert kwargs["max_rounds"] == 3
    assert kwargs["mode"] == "full"
    assert kwargs["stream_callback"] is agent._stream_callback
    assert result.final_answer == "final answer"
    assert result.success is True
    assert result.total_steps == 1
    assert result.steps[0].success is True
    assert result.reflection_summary == {"summary": "insight"}


async def test_process_falls_back_to_specialist_tools(monkeypatch):
    captured = {}

    class _Engine:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.steps = []

        async def run(self, task, prompt):
            return ""

    monkeypatch.setattr(module, "ReActEngine", _Engine)
    agent = ReActAgent()
    agent.executor.tool_registry._tools = {}

    result = await agent.process("task")

    assert captured["tools"] is module.SPECIALIST_TOOLS
    assert captured["project_path"] == ""
    assert captured["stream_callback"] is None
    assert result.success is False
    assert result.reflection_summary == ""


async def test_process_success_when_action_step_succeeded(monkeypatch):
    class _Engine:
        def __init__(self, **kwargs):
            self.steps = [
                module.ReActStep(step_type="thought", content="t", success=False),
                module.ReActStep(step_type="action", content="a", success=True),
            ]

        async def run(self, task, prompt):
            return "   "

    monkeypatch.setattr(module, "ReActEngine", _Engine)
    agent = ReActAgent()

    result = await agent.process("task")

    assert result.success is True
    assert result.final_answer == "   "


async def test_call_llm_returns_empty_on_error(monkeypatch):
    async def boom(**_kwargs):
        raise RuntimeError("provider down")

    monkeypatch.setattr(module, "call_llm", boom)
    agent = ReActAgent(model_name="custom")

    assert await agent._call_llm("prompt", "system") == ""


async def test_call_llm_tolerates_empty_payload(monkeypatch):
    async def empty(**_kwargs):
        return {"choices": []}

    monkeypatch.setattr(module, "call_llm", empty)
    agent = ReActAgent(model_name="custom")

    assert await agent._call_llm("prompt", "system") == ""


async def test_call_llm_includes_api_key_token(monkeypatch):
    captured = {}

    async def fake(**_kwargs):
        captured.update(_kwargs)
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setattr(module, "call_llm", fake)
    agent = ReActAgent(model_name="custom", api_key_token="tok")

    assert await agent._call_llm("prompt", "system") == "ok"
    assert captured["api_key_token"] == "tok"
    assert captured["stream"] is False
