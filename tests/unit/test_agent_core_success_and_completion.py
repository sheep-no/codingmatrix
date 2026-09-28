"""`agent_core.ProjectGeneratorAgent` 生成结果语义回归。

- AC5：`generate_project` 的 `success` 必须同时满足「LLM 报告完成」与
  「服务端验证 runnable」，避免验证失败仍上报成功。
- AC11：完成检测按整词匹配 ASCII 关键词，避免 "abandoned"/"unsuccessful"
  这类子串误判为完成并提前终止生成。
"""

import pytest

from app.schema.codeRequest import AgentConfig
from app.utils import agent_core
from app.utils.agent_core import ProjectGeneratorAgent, _has_completion_signal


@pytest.mark.parametrize("text", [
    "任务已abandoned",
    "The generation was unsuccessful",
    "The previous change is undone",
])
def test_completion_signal_ignores_ascii_substrings(text):
    assert _has_completion_signal(text) is False


@pytest.mark.parametrize("text", [
    "done",
    "Generation successful.",
    "项目生成完成",
    "所有文件已创建",
])
def test_completion_signal_matches_real_signals(text):
    assert _has_completion_signal(text) is True


def test_completion_signal_empty_text():
    assert _has_completion_signal("") is False


def _make_agent() -> ProjectGeneratorAgent:
    return ProjectGeneratorAgent(config=AgentConfig(enable_validation=True))


async def _run_generate(monkeypatch, tmp_path, runnable: bool) -> dict:
    agent = _make_agent()

    async def fake_call_llm(messages, **kwargs):
        return {"choices": [{"message": {"content": "项目生成完成"}}]}

    async def fake_run_full_validation(self, callback=None):
        return {"runnable": runnable, "errors": [] if runnable else ["boom"], "warnings": []}

    monkeypatch.setattr(agent, "_call_llm", fake_call_llm)
    monkeypatch.setattr(
        agent_core.ProjectValidator, "run_full_validation", fake_run_full_validation
    )

    return await agent.generate_project(
        requirement="生成一个演示项目", output_dir=str(tmp_path / "proj")
    )


@pytest.mark.asyncio
async def test_success_false_when_validation_not_runnable(monkeypatch, tmp_path):
    result = await _run_generate(monkeypatch, tmp_path, runnable=False)

    assert result["validation"]["runnable"] is False
    assert result["success"] is False


@pytest.mark.asyncio
async def test_success_true_when_validation_runnable(monkeypatch, tmp_path):
    result = await _run_generate(monkeypatch, tmp_path, runnable=True)

    assert result["validation"]["runnable"] is True
    assert result["success"] is True
