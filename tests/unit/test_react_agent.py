"""ReActAgent 薄封装的单元测试。"""

import pytest


class TestCallLlmParameters:
    @pytest.mark.asyncio
    async def test_temperature_follows_default_model(self, monkeypatch):
        """temperature 不能硬编码 0.7，必须跟随所选模型的配置。"""
        from app.agent import react_agent as react_agent_module

        captured = {}

        async def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return {"choices": [{"message": {"content": "ok"}}]}

        monkeypatch.setattr(react_agent_module, "call_llm", fake_call_llm)

        agent = react_agent_module.ReActAgent(model_name="custom-test")
        agent.default_model.temperature = 0.2

        content = await agent._call_llm("prompt", "system")

        assert content == "ok"
        assert captured["temperature"] == 0.2
        assert captured["model"] == agent.default_model.name
