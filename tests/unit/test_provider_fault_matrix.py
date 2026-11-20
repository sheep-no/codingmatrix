"""Provider 故障矩阵回归：认证、限流、流式中断与错误体边界。"""

import httpx
import pytest

from app.utils.aicloud import llm_caller
from app.utils.aicloud.adapters.base import BaseProviderAdapter
from app.utils.aicloud.errors import LLMCallError, normalize_llm_error
from app.utils.aicloud.providers import ModelProvider, ProviderConfig


def _response(status_code: int) -> httpx.Response:
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    return httpx.Response(status_code, request=request)


@pytest.mark.asyncio
async def test_non_stream_403_is_fatal_auth_error(monkeypatch):
    class AuthError(Exception):
        status_code = 403

    class Adapter:
        provider = ModelProvider.SILICONFLOW
        api_key = "sk-invalid"
        timeout = 0

        async def call_llm(self, **_kwargs):
            raise AuthError("HTTP 403: forbidden")

    async def fake_get_adapter(_provider, _config=None):
        return Adapter()

    monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)

    with pytest.raises(llm_caller.LLMCallError) as exc_info:
        await llm_caller.call_llm("m", "p", disable_fallback=True)

    assert exc_info.value.status_code == 403
    assert exc_info.value.code == "LLM_AUTH_FAILED"


class _RateLimitedStream:
    """SiliconFlow 风格：首 chunk 前抛出带 status_code 的通用异常。"""

    def __aiter__(self):
        return self

    async def __anext__(self):
        error = Exception("HTTP 429: rate limited")
        error.status_code = 429
        raise error

    async def aclose(self):
        return None


class _OkStream:
    def __init__(self):
        self._sent = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._sent:
            raise StopAsyncIteration
        self._sent = True
        return "ok\n"

    async def aclose(self):
        return None


@pytest.mark.asyncio
async def test_siliconflow_style_429_stream_is_retried(monkeypatch):
    attempts = []

    async def factory():
        attempts.append(1)
        return _RateLimitedStream() if len(attempts) == 1 else _OkStream()

    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(llm_caller.time, "monotonic", lambda: 1000.0)

    result = await llm_caller._invoke_adapter_with_retry(
        factory, model="m", stream=True, skip_semaphore=True
    )

    assert [chunk async for chunk in result] == ["ok\n"]
    assert attempts == [1, 1]
    assert slept == [15.0]


class _PartialThenDisconnectResponse:
    status_code = 200

    async def aiter_lines(self):
        yield 'data: {"choices":[{"delta":{"content":"first"}}]}'
        raise httpx.ReadError("connection lost")

    async def aclose(self):
        return None


class _StreamContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *_exc_info):
        return False


class _StreamClient:
    def __init__(self, response):
        self._response = response

    def stream(self, *_args, **_kwargs):
        return _StreamContext(self._response)


@pytest.mark.asyncio
async def test_stream_disconnect_after_first_chunk_keeps_partial_output(monkeypatch):
    from app.utils.aicloud.adapters import siliconflow
    from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter

    async def fake_get_client():
        return _StreamClient(_PartialThenDisconnectResponse())

    monkeypatch.setattr(siliconflow, "get_http_client", fake_get_client)

    adapter = SiliconFlowAdapter(
        ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key="test-key",
            base_url="https://provider.test/v1",
        )
    )
    adapter._reasoning_models = set()
    adapter._stream_usage_supported = False

    stream = await adapter.call_llm("plain-model", "prompt", stream=True)
    chunks = []
    with pytest.raises(Exception, match="读取响应失败"):
        async for chunk in stream:
            chunks.append(chunk)

    assert chunks == ['{"choices":[{"delta":{"content":"first"}}]}\n']


@pytest.mark.asyncio
async def test_stream_5xx_is_not_retried(monkeypatch):
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    response = httpx.Response(502, request=request)
    attempts = []

    async def factory():
        attempts.append(1)

        async def failing():
            raise httpx.HTTPStatusError("bad gateway", request=request, response=response)
            yield "never"

        return failing()

    with pytest.raises(httpx.HTTPStatusError):
        await llm_caller._invoke_adapter_with_retry(
            factory, model="m", stream=True, skip_semaphore=True
        )

    assert attempts == [1]


@pytest.mark.asyncio
async def test_stream_transport_error_before_first_chunk_retries(monkeypatch):
    attempts = []
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)

    async def factory():
        attempts.append(1)

        async def failing():
            raise httpx.ConnectError("connection refused")
            yield "never"

        async def ok():
            yield "recovered\n"

        return failing() if len(attempts) == 1 else ok()

    result = await llm_caller._invoke_adapter_with_retry(
        factory, model="m", stream=True, skip_semaphore=True
    )

    assert [chunk async for chunk in result] == ["recovered\n"]
    assert len(attempts) == 2
    assert slept == [1.0]


@pytest.mark.asyncio
async def test_stream_wrapped_transport_error_retries_via_cause(monkeypatch):
    attempts = []

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)

    async def factory():
        attempts.append(1)

        async def failing():
            try:
                raise httpx.ConnectError("dns failure")
            except httpx.ConnectError as cause:
                raise Exception("连接失败: dns failure") from cause
            yield "never"

        async def ok():
            yield "ok\n"

        return failing() if len(attempts) == 1 else ok()

    result = await llm_caller._invoke_adapter_with_retry(
        factory, model="m", stream=True, skip_semaphore=True
    )

    assert [chunk async for chunk in result] == ["ok\n"]
    assert len(attempts) == 2


@pytest.mark.asyncio
async def test_stream_transport_error_exhausts_attempts(monkeypatch):
    attempts = []

    async def fake_sleep(_seconds):
        return None

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)

    async def factory():
        attempts.append(1)

        async def failing():
            raise httpx.ReadTimeout("read timed out")
            yield "never"

        return failing()

    with pytest.raises(httpx.ReadTimeout):
        await llm_caller._invoke_adapter_with_retry(
            factory, model="m", stream=True, skip_semaphore=True
        )

    assert len(attempts) == 3


@pytest.mark.asyncio
async def test_stream_error_body_is_truncated():
    class LargeErrorResponse:
        status_code = 502

        async def aiter_bytes(self):
            yield b"x" * 3000

    with pytest.raises(LLMCallError) as exc_info:
        await BaseProviderAdapter._raise_for_stream_status(LargeErrorResponse())

    assert exc_info.value.status_code == 502
    assert str(exc_info.value).count("x") == 500


@pytest.mark.asyncio
async def test_stream_error_body_read_failure_still_raises():
    class BrokenErrorResponse:
        status_code = 500

        async def aiter_bytes(self):
            raise httpx.ReadError("cannot read body")
            yield b"never"

    with pytest.raises(LLMCallError) as exc_info:
        await BaseProviderAdapter._raise_for_stream_status(BrokenErrorResponse())

    assert exc_info.value.status_code == 500
    assert "HTTP 500" in str(exc_info.value)


def test_normalize_http_error_preserves_rate_limit_metadata():
    request = httpx.Request("POST", "https://provider.test/v1/chat/completions")
    response = httpx.Response(429, headers={"Retry-After": "30"}, request=request)
    error = httpx.HTTPStatusError("busy", request=request, response=response)

    normalized = normalize_llm_error(error)

    assert normalized is not None
    assert normalized.status_code == 429
    assert normalized.code == "LLM_RATE_LIMITED"
    assert normalized.retry_after == 30.0


@pytest.mark.asyncio
async def test_empty_stream_is_counted_and_logged(monkeypatch):
    llm_caller.reset_empty_stream_stats()
    warnings = []

    def capture(message, *args, **_kwargs):
        warnings.append(message % args if args else message)

    monkeypatch.setattr(llm_caller.logger, "warning", capture)

    async def factory():
        async def empty():
            if False:
                yield ""

        return empty()

    result = await llm_caller._invoke_adapter_with_retry(
        factory,
        model="empty-model",
        stream=True,
        skip_semaphore=True,
        provider=ModelProvider.SILICONFLOW,
    )
    assert [chunk async for chunk in result] == []

    assert llm_caller.get_empty_stream_stats() == {
        "empty_stream_total": 1,
        "provider=siliconflow": 1,
        "provider=siliconflow,model=empty-model": 1,
    }
    assert any(
        "empty_stream provider=siliconflow model=empty-model" in message
        for message in warnings
    )


@pytest.mark.asyncio
async def test_empty_stream_stats_group_by_provider_and_model(monkeypatch):
    llm_caller.reset_empty_stream_stats()

    async def factory():
        async def empty():
            if False:
                yield ""

        return empty()

    async def fake_warning(*_args, **_kwargs):
        return None

    monkeypatch.setattr(llm_caller.logger, "warning", fake_warning)

    for provider, model in (
        (ModelProvider.SILICONFLOW, "a"),
        (ModelProvider.SILICONFLOW, "b"),
        (ModelProvider.DEEPSEEK, "a"),
    ):
        await llm_caller._invoke_adapter_with_retry(
            factory,
            model=model,
            stream=True,
            skip_semaphore=True,
            provider=provider,
        )

    assert llm_caller.get_empty_stream_stats() == {
        "empty_stream_total": 3,
        "provider=siliconflow": 2,
        "provider=siliconflow,model=a": 1,
        "provider=siliconflow,model=b": 1,
        "provider=deepseek": 1,
        "provider=deepseek,model=a": 1,
    }
