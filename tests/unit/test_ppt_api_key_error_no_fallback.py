"""PPT 大纲生成对配置类错误的处理契约。

401（Key 缺失/失效）必须直接失败，不得重试或降级为模板大纲；
其它错误保留重试与降级，避免网络抖动造成生成中断。
"""

import pytest

from app.agent.ppt_agent import PPTAgent, _is_api_key_error
from app.utils.aicloud.llm_caller import LLMCallError, UserAPIKeyNotFoundError


def test_is_api_key_error_only_matches_401():
    assert _is_api_key_error(UserAPIKeyNotFoundError()) is True
    assert _is_api_key_error(LLMCallError("服务异常", status_code=500)) is False
    assert _is_api_key_error(TimeoutError("timeout")) is False
    assert _is_api_key_error(RuntimeError("boom")) is False


@pytest.mark.asyncio
async def test_stream_outline_raises_on_api_key_error(monkeypatch):
    async def failing_call_llm(**kwargs):
        raise UserAPIKeyNotFoundError()

    monkeypatch.setattr("app.agent.ppt_agent.call_llm", failing_call_llm)

    events = []
    with pytest.raises(UserAPIKeyNotFoundError):
        async for event in PPTAgent().stream_outline("测试主题"):
            events.append(event)

    assert [e for e in events if e["type"] == "retry"] == []
    assert [e for e in events if e["type"] == "complete"] == []


@pytest.mark.asyncio
async def test_stream_outline_retries_then_falls_back_on_transient_error(monkeypatch):
    calls = {"count": 0}

    async def failing_call_llm(**kwargs):
        calls["count"] += 1
        raise LLMCallError("上游 500", status_code=500)

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr("app.agent.ppt_agent.call_llm", failing_call_llm)
    monkeypatch.setattr("app.agent.ppt_agent.asyncio.sleep", no_sleep)

    events = [event async for event in PPTAgent().stream_outline("测试主题", num_slides=4)]

    assert calls["count"] == PPTAgent.MAX_RETRIES
    assert [e["attempt"] for e in events if e["type"] == "retry"] == [2, 3]
    complete = [e for e in events if e["type"] == "complete"]
    assert len(complete) == 1
    assert len(complete[0]["outline"].slides) == 4


@pytest.mark.asyncio
async def test_generate_outline_raises_on_api_key_error(monkeypatch):
    async def failing_call_llm(**kwargs):
        raise UserAPIKeyNotFoundError()

    monkeypatch.setattr("app.agent.ppt_agent.call_llm", failing_call_llm)

    with pytest.raises(UserAPIKeyNotFoundError):
        await PPTAgent().generate_outline("测试主题")
