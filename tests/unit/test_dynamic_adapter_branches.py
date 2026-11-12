"""Branch coverage for app/utils/aicloud/adapters/dynamic.py."""

import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException

from app.utils.aicloud.adapters import dynamic as module
from app.utils.aicloud.adapters.dynamic import DynamicAdapter
from app.utils.aicloud.dynamic_provider import DynamicProvider, Protocol


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="{}"):
        self.status_code = status_code
        self._payload = payload or {"choices": [{"message": {"content": "ok"}}]}
        self.text = text

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, lines):
        self._lines = lines
        self.closed = False

    async def aiter_lines(self):
        for line in self._lines:
            yield line

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
        return self._response

    def stream(self, method, url, **kwargs):
        self.stream_calls.append((method, url, kwargs))
        return _FakeStreamContext(self._stream_response)


def _provider(protocol, api_key="key"):
    return DynamicProvider(
        id="p", name="P", base_url="https://example.test/v1",
        protocol=protocol, api_key=api_key,
    )


def _patch_client(monkeypatch, client):
    async def _get_client():
        return client

    monkeypatch.setattr(module, "get_http_client", _get_client)


def _patch_retry(monkeypatch):
    async def _call(func, **_kwargs):
        return await func()

    monkeypatch.setattr(module, "call_with_retry", _call)


class TestOpenAiPath:
    def _adapter(self):
        return DynamicAdapter(_provider(Protocol.OPENAI))

    async def test_missing_key_raises(self):
        with pytest.raises(RuntimeError):
            await DynamicAdapter(_provider(Protocol.OPENAI, api_key="")).call_llm("m", "p")

    async def test_non_stream_success(self, monkeypatch):
        client = _FakeClient(response=_FakeResponse())
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        result = await self._adapter().call_llm("m", "prompt", system_prompt="sys")

        assert result["choices"][0]["message"]["content"] == "ok"
        assert client.post_calls[0][0] == "https://example.test/v1/chat/completions"

    async def test_non_stream_uses_explicit_messages(self, monkeypatch):
        client = _FakeClient(response=_FakeResponse())
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        messages = [{"role": "user", "content": "x"}]

        await self._adapter().call_llm("m", "ignored", messages=messages)

        assert client.post_calls[0][1]["json"]["messages"] == messages

    async def test_non_stream_error_status(self, monkeypatch):
        client = _FakeClient(response=_FakeResponse(status_code=500, text="boom"))
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        with pytest.raises(HTTPException) as exc_info:
            await self._adapter().call_llm("m", "p")

        assert exc_info.value.status_code == 500
        assert exc_info.value.detail == "boom"

    async def test_non_stream_cancel_event(self, monkeypatch):
        _patch_client(monkeypatch, _FakeClient(response=_FakeResponse()))
        _patch_retry(monkeypatch)
        cancel = asyncio.Event()
        cancel.set()

        with pytest.raises(asyncio.CancelledError):
            await self._adapter().call_llm("m", "p", cancel_event=cancel)

    async def test_stream_yields_data_until_done(self, monkeypatch):
        response = _FakeStreamResponse(['data: {"a": 1}', "event: x", "data: [DONE]"])
        client = _FakeClient(stream_response=response)
        _patch_client(monkeypatch, client)

        stream = await self._adapter().call_llm("m", "p", stream=True)
        chunks = [c async for c in stream]

        assert chunks == ['{"a": 1}\n']

    async def test_stream_cancel_event_aborts(self, monkeypatch):
        cancel = asyncio.Event()

        class CancellingStream(_FakeStreamResponse):
            async def aiter_lines(self):
                cancel.set()
                yield 'data: {"a": 1}'

        response = CancellingStream([])
        _patch_client(monkeypatch, _FakeClient(stream_response=response))

        stream = await self._adapter().call_llm("m", "p", stream=True, cancel_event=cancel)

        with pytest.raises(asyncio.CancelledError):
            async for _ in stream:
                pass
        assert response.closed is True


class TestAnthropicPath:
    def _adapter(self):
        return DynamicAdapter(_provider(Protocol.ANTHROPIC))

    async def test_headers_and_default_messages(self, monkeypatch):
        client = _FakeClient(
            response=_FakeResponse(
                payload={"content": [{"type": "text", "text": "hi"}]}
            )
        )
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        result = await self._adapter().call_llm("m", "prompt", system_prompt="sys")

        assert result["choices"][0]["message"]["content"] == "hi"
        url, kwargs = client.post_calls[0]
        assert url == "https://example.test/v1/messages"
        assert kwargs["headers"]["x-api-key"] == "key"
        assert kwargs["json"]["system"] == "sys"
        assert kwargs["json"]["messages"] == [{"role": "user", "content": "prompt"}]
        assert result["choices"][0]["finish_reason"] == "stop"

    async def test_non_stream_uses_explicit_messages_and_stop_reason(self, monkeypatch):
        payload = {
            "content": [{"type": "tool_use"}, {"type": "text", "text": "x"}],
            "stop_reason": "end_turn",
            "model": "claude-x",
        }
        client = _FakeClient(response=_FakeResponse(payload=payload))
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        messages = [{"role": "user", "content": "m"}]

        result = await self._adapter().call_llm("m", "prompt", messages=messages)

        assert result["choices"][0]["message"]["content"] == "x"
        assert result["choices"][0]["finish_reason"] == "end_turn"
        assert result["model"] == "claude-x"
        assert "system" not in client.post_calls[0][1]["json"]

    async def test_non_stream_error_status(self, monkeypatch):
        client = _FakeClient(response=_FakeResponse(status_code=400, text="bad"))
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        with pytest.raises(HTTPException):
            await self._adapter().call_llm("m", "p")

    async def test_non_stream_cancel_event(self, monkeypatch):
        _patch_client(monkeypatch, _FakeClient(response=_FakeResponse()))
        _patch_retry(monkeypatch)
        cancel = asyncio.Event()
        cancel.set()

        with pytest.raises(asyncio.CancelledError):
            await self._adapter().call_llm("m", "p", cancel_event=cancel)

    async def test_stream_converts_events(self, monkeypatch):
        lines = [
            "data: {not-json",
            "data: " + json.dumps({"type": "message_start"}),
            "data: "
            + json.dumps(
                {
                    "type": "content_block_delta",
                    "delta": {"type": "text_delta", "text": "hi"},
                }
            ),
            "data: [DONE]",
        ]
        _patch_client(monkeypatch, _FakeClient(stream_response=_FakeStreamResponse(lines)))

        stream = await self._adapter().call_llm("m", "p", stream=True)
        chunks = [c async for c in stream]

        assert len(chunks) == 1
        assert json.loads(chunks[0])["choices"][0]["delta"]["content"] == "hi"

    async def test_stream_cancel_event_aborts(self, monkeypatch):
        cancel = asyncio.Event()

        class CancellingStream(_FakeStreamResponse):
            async def aiter_lines(self):
                cancel.set()
                yield 'data: {"type": "message_start"}'

        response = CancellingStream([])
        _patch_client(monkeypatch, _FakeClient(stream_response=response))

        stream = await self._adapter().call_llm("m", "p", stream=True, cancel_event=cancel)

        with pytest.raises(asyncio.CancelledError):
            async for _ in stream:
                pass
        assert response.closed is True


class TestOther:
    async def test_embedding_not_supported(self):
        with pytest.raises(NotImplementedError):
            await DynamicAdapter(_provider(Protocol.OPENAI)).call_embedding("m", "t")

    def test_headers_openai(self):
        headers = DynamicAdapter(_provider(Protocol.OPENAI))._get_headers()
        assert headers["Authorization"] == "Bearer key"

    def test_headers_anthropic(self):
        headers = DynamicAdapter(_provider(Protocol.ANTHROPIC))._get_headers()
        assert headers["x-api-key"] == "key"
        assert "anthropic-version" in headers
