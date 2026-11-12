"""Branch coverage for the aicloud provider adapters."""

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from app.utils.aicloud.adapters import (
    anthropic as anthropic_module,
    dashscope as dashscope_module,
    deepseek as deepseek_module,
    openai as openai_module,
    zhipu as zhipu_module,
)
from app.utils.aicloud.adapters.anthropic import AnthropicAdapter
from app.utils.aicloud.adapters.dashscope import DashScopeAdapter
from app.utils.aicloud.adapters.deepseek import DeepSeekAdapter
from app.utils.aicloud.adapters.openai import OpenAIAdapter
from app.utils.aicloud.adapters.zhipu import ZhipuAdapter
from app.utils.aicloud.providers import ModelProvider, ProviderConfig


def _config(provider):
    return ProviderConfig(
        provider=provider,
        api_key="test-key",
        base_url="https://example.test/v1",
        timeout=12.0,
    )


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="{}"):
        self.status_code = status_code
        self._payload = payload or {"choices": [{"message": {"content": "ok"}}]}
        self.text = text
        self.request = httpx.Request("POST", "https://example.test/v1")

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, lines, status_code=200, body=b""):
        self._lines = lines
        self.status_code = status_code
        self._body = body
        self.request = httpx.Request("POST", "https://example.test/v1")
        self.closed = False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def aiter_bytes(self):
        yield self._body

    async def aclose(self):
        self.closed = True


class _FakeStreamContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    def __init__(self, response=None, stream_response=None):
        self.post_calls = []
        self.stream_calls = []
        self._response = response
        self._stream_response = stream_response

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        if isinstance(self._response, Exception):
            raise self._response
        return self._response

    def stream(self, method, url, **kwargs):
        self.stream_calls.append((method, url, kwargs))
        return _FakeStreamContext(self._stream_response)


def _patch_client(monkeypatch, module, client):
    async def _get_client():
        return client

    monkeypatch.setattr(module, "get_http_client", _get_client)


ADAPTER_CASES = [
    (openai_module, OpenAIAdapter, ModelProvider.OPENAI),
    (deepseek_module, DeepSeekAdapter, ModelProvider.DEEPSEEK),
    (zhipu_module, ZhipuAdapter, ModelProvider.ZHIPU),
    (dashscope_module, DashScopeAdapter, ModelProvider.DASHSCOPE),
]


@pytest.fixture(params=ADAPTER_CASES, ids=["openai", "deepseek", "zhipu", "dashscope"])
def adapter_case(request):
    return request.param


class TestCommonAdapters:
    async def test_missing_key_raises_for_llm_and_embedding(self, adapter_case):
        _module, cls, provider = adapter_case
        adapter = cls(ProviderConfig(provider=provider, api_key="", base_url="x"))

        with pytest.raises(RuntimeError):
            await adapter.call_llm("m", "p")
        with pytest.raises(RuntimeError):
            await adapter.call_embedding("m", "text")

    async def test_non_stream_returns_payload(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        client = _FakeClient(response=_FakeResponse())
        _patch_client(monkeypatch, module, client)
        adapter = cls(_config(provider))

        result = await adapter.call_llm("model", "prompt", system_prompt="sys")

        assert result["choices"][0]["message"]["content"] == "ok"
        url, kwargs = client.post_calls[0]
        assert url == "https://example.test/v1/chat/completions"
        assert kwargs["timeout"].read == 12.0

    async def test_non_stream_uses_explicit_messages(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        client = _FakeClient(response=_FakeResponse())
        _patch_client(monkeypatch, module, client)
        adapter = cls(_config(provider))
        messages = [{"role": "user", "content": "explicit"}]

        await adapter.call_llm("model", "ignored", messages=messages)

        assert client.post_calls[0][1]["json"]["messages"] == messages

    async def test_non_stream_error_status_raises_http_exception(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        client = _FakeClient(
            response=_FakeResponse(status_code=400, text="bad request")
        )
        _patch_client(monkeypatch, module, client)
        adapter = cls(_config(provider))

        with pytest.raises(HTTPException) as exc_info:
            await adapter.call_llm("model", "prompt")

        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "bad request"

    async def test_non_stream_cancel_event_raises(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        _patch_client(monkeypatch, module, _FakeClient(response=_FakeResponse()))
        adapter = cls(_config(provider))
        cancel = asyncio.Event()
        cancel.set()

        with pytest.raises(asyncio.CancelledError):
            await adapter.call_llm("model", "prompt", cancel_event=cancel)

    async def test_stream_yields_data_lines_until_done(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        response = _FakeStreamResponse(
            ['data: {"a": 1}', "event: ping", "data: [DONE]", 'data: {"b": 2}']
        )
        client = _FakeClient(stream_response=response)
        _patch_client(monkeypatch, module, client)
        adapter = cls(_config(provider))

        stream = await adapter.call_llm("model", "prompt", stream=True)
        chunks = [chunk async for chunk in stream]

        assert chunks == ['{"a": 1}\n']
        assert client.stream_calls[0][0] == "POST"

    async def test_stream_cancel_event_aborts_mid_stream(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case

        class CancellingStream(_FakeStreamResponse):
            def __init__(self, cancel):
                super().__init__(['data: {"a": 1}', 'data: {"b": 2}'])
                self._cancel = cancel

            async def aiter_lines(self):
                for line in self._lines:
                    self._cancel.set()
                    yield line

        cancel = asyncio.Event()
        response = CancellingStream(cancel)
        _patch_client(monkeypatch, module, _FakeClient(stream_response=response))
        adapter = cls(_config(provider))

        stream = await adapter.call_llm("model", "prompt", stream=True, cancel_event=cancel)

        with pytest.raises(asyncio.CancelledError):
            async for _ in stream:
                pass
        assert response.closed is True

    async def test_stream_error_status_raises_before_lines(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        response = _FakeStreamResponse([], status_code=502, body=b'{"error": "overload"}')
        _patch_client(monkeypatch, module, _FakeClient(stream_response=response))
        adapter = cls(_config(provider))

        stream = await adapter.call_llm("model", "prompt", stream=True)

        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            async for _ in stream:
                pass
        assert exc_info.value.response.status_code == 502

    async def test_embedding_returns_payload(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        client = _FakeClient(
            response=_FakeResponse(payload={"data": [{"embedding": [0.1]}]})
        )
        _patch_client(monkeypatch, module, client)
        adapter = cls(_config(provider))

        result = await adapter.call_embedding("embed-model", "hello")

        assert result == {"data": [{"embedding": [0.1]}]}
        assert client.post_calls[0][0] == "https://example.test/v1/embeddings"

    async def test_embedding_error_status_raises_http_exception(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        client = _FakeClient(response=_FakeResponse(status_code=401, text="unauthorized"))
        _patch_client(monkeypatch, module, client)
        adapter = cls(_config(provider))

        with pytest.raises(HTTPException) as exc_info:
            await adapter.call_embedding("embed-model", "hello")

        assert exc_info.value.status_code == 401

    async def test_default_base_url_used_when_unset(self, adapter_case, monkeypatch):
        module, cls, provider = adapter_case
        client = _FakeClient(response=_FakeResponse())
        _patch_client(monkeypatch, module, client)
        adapter = cls(ProviderConfig(provider=provider, api_key="test-key", base_url=""))

        await adapter.call_llm("model", "prompt")

        assert client.post_calls[0][0].startswith(cls.BASE_URL)

    def test_headers_include_authorization(self, adapter_case):
        _module, cls, provider = adapter_case
        adapter = cls(_config(provider))
        assert adapter._get_headers()["Authorization"] == "Bearer test-key"


class TestAnthropicAdapter:
    def _adapter(self):
        return AnthropicAdapter(_config(ModelProvider.ANTHROPIC))

    async def test_missing_key_raises(self):
        adapter = AnthropicAdapter(
            ProviderConfig(provider=ModelProvider.ANTHROPIC, api_key="", base_url="x")
        )
        with pytest.raises(RuntimeError):
            await adapter.call_llm("m", "p")

    async def test_embedding_not_supported(self):
        with pytest.raises(NotImplementedError):
            await self._adapter().call_embedding("m", "text")

    def test_headers_use_anthropic_scheme(self):
        headers = self._adapter()._get_headers()
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == AnthropicAdapter.API_VERSION

    async def test_non_stream_converts_content_blocks(self, monkeypatch):
        payload = {
            "content": [
                {"type": "text", "text": "hello "},
                {"type": "tool_use", "name": "x"},
                {"type": "text", "text": "world"},
            ],
            "usage": {"input_tokens": 3},
        }
        client = _FakeClient(response=_FakeResponse(payload=payload))
        _patch_client(monkeypatch, anthropic_module, client)

        result = await self._adapter().call_llm(
            "claude", "prompt", system_prompt="be nice"
        )

        assert result["choices"][0]["message"]["content"] == "hello world"
        assert result["usage"] == {"input_tokens": 3}
        body = client.post_calls[0][1]["json"]
        assert body["system"] == "be nice"
        assert body["messages"] == [{"role": "user", "content": "prompt"}]

    async def test_non_stream_explicit_messages_skip_default(self, monkeypatch):
        client = _FakeClient(response=_FakeResponse(payload={"content": []}))
        _patch_client(monkeypatch, anthropic_module, client)
        messages = [{"role": "user", "content": "explicit"}]

        await self._adapter().call_llm("claude", "ignored", messages=messages)

        assert client.post_calls[0][1]["json"]["messages"] == messages

    async def test_non_stream_without_system_prompt_omits_field(self, monkeypatch):
        client = _FakeClient(response=_FakeResponse(payload={"content": []}))
        _patch_client(monkeypatch, anthropic_module, client)

        await self._adapter().call_llm("claude", "prompt")

        assert "system" not in client.post_calls[0][1]["json"]

    async def test_non_stream_error_status(self, monkeypatch):
        client = _FakeClient(response=_FakeResponse(status_code=529, text="overloaded"))
        _patch_client(monkeypatch, anthropic_module, client)

        with pytest.raises(HTTPException) as exc_info:
            await self._adapter().call_llm("claude", "prompt")

        assert exc_info.value.status_code == 529

    async def test_non_stream_cancel_event(self, monkeypatch):
        _patch_client(monkeypatch, anthropic_module, _FakeClient(response=_FakeResponse()))
        cancel = asyncio.Event()
        cancel.set()

        with pytest.raises(asyncio.CancelledError):
            await self._adapter().call_llm("claude", "prompt", cancel_event=cancel)

    async def test_stream_converts_and_skips_invalid_chunks(self, monkeypatch):
        text_event = {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "hi"},
        }
        stop_event = {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}
        ignored_event = {"type": "message_start"}
        lines = [
            "event: content_block_delta",
            "data: {not json",
            "data: " + json.dumps(ignored_event),
            "data: " + json.dumps(text_event),
            "data: " + json.dumps(stop_event),
            "data: [DONE]",
        ]
        client = _FakeClient(stream_response=_FakeStreamResponse(lines))
        _patch_client(monkeypatch, anthropic_module, client)

        stream = await self._adapter().call_llm("claude", "prompt", stream=True)
        chunks = [chunk async for chunk in stream]

        first = json.loads(chunks[0])
        second = json.loads(chunks[1])
        assert first["choices"][0]["delta"]["content"] == "hi"
        assert second["choices"][0]["finish_reason"] == "end_turn"
        assert len(chunks) == 2

    async def test_stream_cancel_event_aborts(self, monkeypatch):
        cancel = asyncio.Event()

        class CancellingStream(_FakeStreamResponse):
            async def aiter_lines(self):
                cancel.set()
                yield "data: " + json.dumps(
                    {
                        "type": "content_block_delta",
                        "delta": {"type": "text_delta", "text": "hi"},
                    }
                )

        response = CancellingStream([])
        _patch_client(monkeypatch, anthropic_module, _FakeClient(stream_response=response))

        stream = await self._adapter().call_llm(
            "claude", "prompt", stream=True, cancel_event=cancel
        )

        with pytest.raises(asyncio.CancelledError):
            async for _ in stream:
                pass
        assert response.closed is True

    async def test_stream_uses_default_base_url(self, monkeypatch):
        adapter = AnthropicAdapter(
            ProviderConfig(provider=ModelProvider.ANTHROPIC, api_key="k", base_url="")
        )
        client = _FakeClient(stream_response=_FakeStreamResponse([]))
        _patch_client(monkeypatch, anthropic_module, client)

        stream = await adapter.call_llm("claude", "prompt", stream=True)
        [chunk async for chunk in stream]

        assert client.stream_calls[0][1] == AnthropicAdapter.BASE_URL + "/messages"
