"""LangChain 适配器的加载、归一化与流式输出补测。"""

import json
import sys
import types

import pytest

from app.utils.aicloud import langchain_adapter as adapter
from app.utils.aicloud.providers import ModelProvider


def _message(**overrides):
    base = dict(
        text=None,
        content="",
        content_blocks=[],
        tool_calls=[],
        usage_metadata={},
        response_metadata={},
    )
    base.update(overrides)
    return types.SimpleNamespace(**base)


def test_load_model_uses_openai_by_default(monkeypatch):
    captured = {}

    class _ChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "langchain_openai", types.SimpleNamespace(ChatOpenAI=_ChatOpenAI))

    adapter._load_model(ModelProvider.OPENAI, "gpt-x", "key", "https://example.test/v1")

    assert captured == {
        "model": "gpt-x",
        "api_key": "key",
        "base_url": "https://example.test/v1",
    }


def test_load_model_uses_anthropic_and_none_base_url(monkeypatch):
    captured = {}

    class _ChatAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "langchain_anthropic", types.SimpleNamespace(ChatAnthropic=_ChatAnthropic))

    adapter._load_model(ModelProvider.ANTHROPIC, "claude", "key", "")

    assert captured["model"] == "claude"
    assert captured["base_url"] is None


def test_load_model_wraps_import_error(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "langchain_openai":
            raise ImportError("missing package")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(adapter.LangChainUnavailable, match="not installed"):
        adapter._load_model(ModelProvider.OPENAI, "gpt-x", "key")


def test_message_to_dict_defaults_empty_fields():
    result = adapter._message_to_dict(types.SimpleNamespace())

    assert result == {
        "content": "",
        "content_blocks": [],
        "tool_calls": [],
        "usage": {},
        "response_metadata": {},
    }


def test_message_to_dict_handles_non_string_content_without_text_blocks():
    message = _message(content=[{"type": "reasoning"}, "ignored"])

    assert adapter._message_to_dict(message)["content"] == ""


async def test_invoke_returns_normalized_message(monkeypatch):
    class _Model:
        async def ainvoke(self, messages):
            assert messages == ["hi"]
            return _message(text="answer", usage_metadata={"total_tokens": 3})

    monkeypatch.setattr(adapter, "_load_model", lambda *_a, **_k: _Model())

    result = await adapter.invoke(ModelProvider.OPENAI, "m", ["hi"], "key")

    assert result["content"] == "answer"
    assert result["usage"] == {"total_tokens": 3}


async def test_stream_yields_text_tool_calls_and_usage(monkeypatch):
    chunks = [
        _message(text="", tool_calls=[{"name": "search"}]),
        _message(text="hi"),
        _message(text="", usage_metadata={"total_tokens": 5}),
        _message(text="", content_blocks=[{"type": "text", "text": "x"}]),
    ]

    class _Model:
        async def astream(self, messages):
            assert messages == ["hi"]
            for chunk in chunks:
                yield chunk

    monkeypatch.setattr(adapter, "_load_model", lambda *_a, **_k: _Model())

    payloads = [json.loads(item) async for item in adapter.stream(ModelProvider.OPENAI, "m", ["hi"], "key")]

    assert payloads[0]["choices"][0]["delta"]["tool_calls"] == [{"name": "search"}]
    assert payloads[1]["choices"][0]["delta"]["content"] == "hi"
    assert payloads[2] == {"usage": {"total_tokens": 5}}
    assert len(payloads) == 3
