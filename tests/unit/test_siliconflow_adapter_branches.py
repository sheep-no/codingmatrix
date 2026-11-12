"""Branch coverage for app/utils/aicloud/adapters/siliconflow.py."""

import asyncio

import httpx
import pytest
from fastapi import HTTPException

from app.utils.aicloud.adapters import siliconflow as module
from app.utils.aicloud.adapters.siliconflow import (
    SiliconFlowAdapter,
    _StreamRequestError,
)
from app.utils.aicloud.providers import ModelProvider, ProviderConfig


def _adapter():
    return SiliconFlowAdapter(
        ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key="key",
            base_url="https://example.test/v1",
            timeout=9.0,
        )
    )


class _FakeResponse:
    def __init__(self, status_code=200, payload=None, text="{}"):
        self.status_code = status_code
        self._payload = payload or {"choices": [{"message": {"content": "ok"}}]}
        self.text = text

    def json(self):
        return self._payload


class _FakeStreamResponse:
    def __init__(self, lines, status_code=200, body=b""):
        self._lines = lines
        self.status_code = status_code
        self._body = body
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
    def __init__(self, responses=(), stream_responses=()):
        self.post_calls = []
        self.stream_calls = []
        self._responses = list(responses)
        self._stream_responses = list(stream_responses)

    async def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        return self._responses.pop(0)

    def stream(self, method, url, **kwargs):
        self.stream_calls.append((method, url, kwargs))
        return _FakeStreamContext(self._stream_responses.pop(0))


def _patch_client(monkeypatch, client):
    async def _get_client():
        return client

    monkeypatch.setattr(module, "get_http_client", _get_client)


def _patch_retry(monkeypatch):
    async def _call(func, **_kwargs):
        return await func()

    monkeypatch.setattr(module, "call_with_retry", _call)


def test_default_config_from_settings():
    adapter = SiliconFlowAdapter()
    assert adapter.provider == ModelProvider.SILICONFLOW
    assert adapter.base_url


class TestReasoningDetection:
    def test_loads_from_model_config(self, monkeypatch):
        config = {"models": {"m1": {"name": "my-reasoner", "is_reasoning": True}}}
        monkeypatch.setattr(
            "app.utils.model_config_io.load_model_config", lambda _path: config
        )
        adapter = _adapter()

        assert adapter._is_reasoning_model("my-reasoner") is True
        assert adapter._is_reasoning_model("other") is False

    def test_falls_back_when_config_load_fails(self, monkeypatch):
        def boom(_path):
            raise RuntimeError("missing")

        monkeypatch.setattr("app.utils.model_config_io.load_model_config", boom)
        adapter = _adapter()

        assert adapter._is_reasoning_model("deepseek-ai/DeepSeek-R1") is True
        assert adapter._is_reasoning_model("deepseek-ai/DeepSeek-R1-0528-Qwen3-8B") is True
        assert adapter._is_reasoning_model("qwen") is False

    def test_config_without_reasoning_models_uses_fallback(self, monkeypatch):
        monkeypatch.setattr(
            "app.utils.model_config_io.load_model_config",
            lambda _path: {"models": {"m": {"name": "x", "is_reasoning": False}}},
        )
        adapter = _adapter()

        assert adapter._is_reasoning_model("deepseek-ai/DeepSeek-R1") is True


class TestMessageBuilding:
    async def test_extracts_system_and_user_markers(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse()])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        await _adapter().call_llm("m", "【SYSTEM】be brief【USER】hello")

        messages = client.post_calls[0][1]["json"]["messages"]
        assert messages == [
            {"role": "system", "content": "be brief"},
            {"role": "user", "content": "hello"},
        ]

    async def test_explicit_system_prompt_wins_over_marker(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse()])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        await _adapter().call_llm(
            "m", "【SYSTEM】inner【USER】hello", system_prompt="outer"
        )

        messages = client.post_calls[0][1]["json"]["messages"]
        # The outer system prompt is kept; the marker's user part still replaces prompt.
        assert messages[0] == {"role": "system", "content": "outer"}
        assert messages[1] == {"role": "user", "content": "hello"}

    async def test_marker_without_user_section_is_kept(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse()])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        await _adapter().call_llm("m", "【SYSTEM】only")

        assert client.post_calls[0][1]["json"]["messages"][0]["content"] == "【SYSTEM】only"

    async def test_explicit_messages_skip_building(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse()])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        messages = [{"role": "user", "content": "explicit"}]

        await _adapter().call_llm("m", "ignored", messages=messages)

        assert client.post_calls[0][1]["json"]["messages"] == messages


class TestRequestBody:
    async def test_reasoning_model_gets_thinking_budget(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse()])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        adapter = _adapter()
        adapter._reasoning_models = {"r1"}

        await adapter.call_llm("r1", "prompt", thinking_budget=1024)

        body = client.post_calls[0][1]["json"]
        assert body["thinking_budget"] == 1024
        assert "enable_thinking" not in body

    async def test_non_reasoning_model_disables_thinking(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse()])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        adapter = _adapter()
        adapter._reasoning_models = set()

        await adapter.call_llm("plain", "prompt")

        assert client.post_calls[0][1]["json"]["enable_thinking"] is False

    async def test_known_unsupported_model_omits_toggle(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse()])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        adapter = _adapter()
        adapter._reasoning_models = set()
        adapter._unsupported_thinking.add("plain")

        await adapter.call_llm("plain", "prompt")

        assert "enable_thinking" not in client.post_calls[0][1]["json"]


class TestNonStreamRetries:
    async def test_error_without_thinking_reraises(self, monkeypatch):
        _patch_client(monkeypatch, _FakeClient())
        adapter = _adapter()

        async def failing(_func, **_kwargs):
            raise RuntimeError("network")

        monkeypatch.setattr(module, "call_with_retry", failing)

        with pytest.raises(RuntimeError):
            await adapter.call_llm("plain", "prompt")

    async def test_exception_mentions_enable_thinking_then_retries(self, monkeypatch):
        ok = _FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]})
        client = _FakeClient(responses=[ok])
        _patch_client(monkeypatch, client)
        adapter = _adapter()
        adapter._reasoning_models = set()
        calls = {"n": 0}

        async def retry(func, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("bad enable_thinking parameter")
            return await func()

        monkeypatch.setattr(module, "call_with_retry", retry)

        result = await adapter.call_llm("plain", "prompt")

        assert result["choices"][0]["message"]["content"] == "ok"
        assert "plain" in adapter._unsupported_thinking
        assert "enable_thinking" not in client.post_calls[0][1]["json"]

    async def test_status_400_mentions_enable_thinking_then_retries(self, monkeypatch):
        bad = _FakeResponse(status_code=400, text="Invalid enable_thinking")
        ok = _FakeResponse(payload={"choices": [{"message": {"content": "ok"}}]})
        client = _FakeClient(responses=[bad, ok])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        adapter = _adapter()
        adapter._reasoning_models = set()

        result = await adapter.call_llm("plain", "prompt")

        assert result["choices"][0]["message"]["content"] == "ok"
        assert "plain" in adapter._unsupported_thinking
        assert "enable_thinking" not in client.post_calls[1][1]["json"]

    async def test_400_retry_still_failing_raises(self, monkeypatch):
        bad = _FakeResponse(status_code=400, text="enable_thinking rejected")
        still_bad = _FakeResponse(status_code=500, text="still bad")
        client = _FakeClient(responses=[bad, still_bad])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        adapter = _adapter()
        adapter._reasoning_models = set()

        with pytest.raises(HTTPException) as exc_info:
            await adapter.call_llm("plain", "prompt")

        assert exc_info.value.status_code == 500

    async def test_other_error_status_raises(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse(status_code=429, text="slow")])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)
        adapter = _adapter()
        adapter._reasoning_models = set()

        with pytest.raises(HTTPException) as exc_info:
            await adapter.call_llm("plain", "prompt")

        assert exc_info.value.status_code == 429

    async def test_non_stream_cancel_event(self, monkeypatch):
        _patch_client(monkeypatch, _FakeClient(responses=[_FakeResponse()]))
        _patch_retry(monkeypatch)
        cancel = asyncio.Event()
        cancel.set()

        with pytest.raises(asyncio.CancelledError):
            await _adapter().call_llm("plain", "prompt", cancel_event=cancel)


class TestStreaming:
    async def test_stream_success_includes_usage_options(self, monkeypatch):
        response = _FakeStreamResponse(
            ["", ": keep-alive", "other-line", "data: {\"a\":1}", "data: [DONE]"]
        )
        client = _FakeClient(stream_responses=[response])
        _patch_client(monkeypatch, client)
        adapter = _adapter()
        adapter._reasoning_models = set()

        stream = await adapter.call_llm("plain", "prompt", stream=True)
        chunks = [c async for c in stream]

        assert chunks == ['{"a":1}\n']
        assert client.stream_calls[0][2]["json"]["stream_options"] == {"include_usage": True}

    async def test_large_error_body_is_truncated(self, monkeypatch):
        response = _FakeStreamResponse([], status_code=500, body=b"x" * 4000)
        _patch_client(monkeypatch, _FakeClient(stream_responses=[response]))
        adapter = _adapter()
        adapter._reasoning_models = set()

        stream = await adapter.call_llm("plain", "prompt", stream=True)

        with pytest.raises(Exception):
            async for _ in stream:
                pass

    async def test_stream_error_status_raises_stream_error(self, monkeypatch):
        response = _FakeStreamResponse([], status_code=500, body=b"server error")
        client = _FakeClient(stream_responses=[response])
        _patch_client(monkeypatch, client)
        adapter = _adapter()
        adapter._reasoning_models = set()

        stream = await adapter.call_llm("plain", "prompt", stream=True)

        with pytest.raises(Exception) as exc_info:
            async for _ in stream:
                pass
        assert "HTTP 500" in str(exc_info.value)

    async def test_stream_options_rejected_then_retried_without(self, monkeypatch):
        rejected = _FakeStreamResponse(
            [], status_code=400, body=b"stream_options is not supported"
        )
        ok = _FakeStreamResponse(['data: {"ok":true}', "data: [DONE]"])
        client = _FakeClient(stream_responses=[rejected, ok])
        _patch_client(monkeypatch, client)
        adapter = _adapter()
        adapter._reasoning_models = set()

        stream = await adapter.call_llm("plain", "prompt", stream=True)
        chunks = [c async for c in stream]

        assert chunks == ['{"ok":true}\n']
        assert adapter._stream_usage_supported is False
        assert "stream_options" in client.stream_calls[0][2]["json"]
        assert "stream_options" not in client.stream_calls[1][2]["json"]

    async def test_stream_error_without_stream_options_reraises(self, monkeypatch):
        response = _FakeStreamResponse([], status_code=400, body=b"bad request")
        client = _FakeClient(stream_responses=[response])
        _patch_client(monkeypatch, client)
        adapter = _adapter()
        adapter._reasoning_models = set()
        adapter._stream_usage_supported = False

        stream = await adapter.call_llm("plain", "prompt", stream=True)

        with pytest.raises(Exception) as exc_info:
            async for _ in stream:
                pass
        assert "HTTP 400" in str(exc_info.value)

    async def test_stream_cancel_event_aborts(self, monkeypatch):
        cancel = asyncio.Event()

        class CancellingStream(_FakeStreamResponse):
            async def aiter_lines(self):
                cancel.set()
                yield 'data: {"a":1}'

        response = CancellingStream([])
        _patch_client(monkeypatch, _FakeClient(stream_responses=[response]))
        adapter = _adapter()
        adapter._reasoning_models = set()

        stream = await adapter.call_llm("plain", "prompt", stream=True, cancel_event=cancel)

        with pytest.raises(asyncio.CancelledError):
            async for _ in stream:
                pass
        assert response.closed is True

    @pytest.mark.parametrize(
        ("error", "expected"),
        [
            (httpx.RemoteProtocolError(""), "服务器断开连接（无响应）"),
            (httpx.ReadError(""), "读取响应失败（连接中断）"),
            (httpx.ConnectError(""), "连接服务器失败"),
            (httpx.ReadTimeout(""), "请求超时"),
        ],
    )
    async def test_stream_network_errors_are_wrapped(self, monkeypatch, error, expected):
        client = _FakeClient()

        def failing_stream(*_args, **_kwargs):
            raise error

        client.stream = failing_stream
        _patch_client(monkeypatch, client)
        adapter = _adapter()
        adapter._reasoning_models = set()

        stream = await adapter.call_llm("plain", "prompt", stream=True)

        with pytest.raises(Exception) as exc_info:
            async for _ in stream:
                pass
        assert str(exc_info.value) == expected

    async def test_stream_network_error_with_message_keeps_it(self, monkeypatch):
        client = _FakeClient()

        def failing_stream(*_args, **_kwargs):
            raise httpx.ConnectError("dns failure")

        client.stream = failing_stream
        _patch_client(monkeypatch, client)
        adapter = _adapter()
        adapter._reasoning_models = set()

        stream = await adapter.call_llm("plain", "prompt", stream=True)

        with pytest.raises(Exception) as exc_info:
            async for _ in stream:
                pass
        assert "连接失败: dns failure" in str(exc_info.value)

    async def test_stream_generic_empty_exception_is_wrapped(self, monkeypatch):
        client = _FakeClient()

        def failing_stream(*_args, **_kwargs):
            raise ValueError("")

        client.stream = failing_stream
        _patch_client(monkeypatch, client)
        adapter = _adapter()
        adapter._reasoning_models = set()

        stream = await adapter.call_llm("plain", "prompt", stream=True)

        with pytest.raises(Exception) as exc_info:
            async for _ in stream:
                pass
        assert "ValueError" in str(exc_info.value)


class TestEmbedding:
    async def test_success(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse(payload={"data": []})])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        assert await _adapter().call_embedding("embed", "text") == {"data": []}
        assert client.post_calls[0][0] == "https://example.test/v1/embeddings"

    async def test_error_raises(self, monkeypatch):
        client = _FakeClient(responses=[_FakeResponse(status_code=400, text="bad")])
        _patch_client(monkeypatch, client)
        _patch_retry(monkeypatch)

        with pytest.raises(HTTPException):
            await _adapter().call_embedding("embed", "text")


def test_headers():
    headers = _adapter()._get_headers()
    assert headers == {
        "Authorization": "Bearer key",
        "Content-Type": "application/json",
    }


def test_stream_request_error_carries_fields():
    error = _StreamRequestError(400, "x" * 800)
    assert error.status_code == 400
    assert len(error.body) == 800
    assert len(str(error)) < 600
