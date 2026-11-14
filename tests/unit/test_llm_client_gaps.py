"""补齐 llm_client 的降级偏好、流式异常与信号量回收分支。"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

import app.agent.llm_client as llm_client
from app.agent.llm_client import LLMClient, LLMClientError


MODEL_CONFIG = {
    "max_tokens": 4096,
    "thinking_budget": 0,
    "temperature": 0.7,
    "timeout": 300,
}


@pytest.fixture(autouse=True)
def reset_semaphores():
    llm_client._global_semaphore = None
    llm_client._model_semaphores.clear()
    llm_client._model_semaphore_limits.clear()
    yield
    llm_client._global_semaphore = None
    llm_client._model_semaphores.clear()
    llm_client._model_semaphore_limits.clear()


def _client(**kwargs):
    with patch.object(
        llm_client.LayeredModelRouter, "get_model_config", return_value=dict(MODEL_CONFIG)
    ):
        return LLMClient(model_name=kwargs.pop("model_name", "test-model"), **kwargs)


class TestSemaphoreEviction:
    def test_keep_key_is_skipped(self, monkeypatch):
        monkeypatch.setattr(llm_client, "MAX_CACHED_MODEL_SEMAPHORES", 1)
        llm_client._model_semaphores.clear()
        llm_client._model_semaphore_limits.clear()
        llm_client._model_semaphores["keep"] = asyncio.Semaphore(2)
        llm_client._model_semaphore_limits["keep"] = 2
        llm_client._model_semaphores["other"] = asyncio.Semaphore(2)
        llm_client._model_semaphore_limits["other"] = 2

        llm_client._evict_idle_model_semaphores(keep="keep")

        # 上限为 1，只保留 keep
        assert set(llm_client._model_semaphores) == {"keep"}

    def test_in_use_semaphore_retained(self, monkeypatch):
        monkeypatch.setattr(llm_client, "MAX_CACHED_MODEL_SEMAPHORES", 1)
        llm_client._model_semaphores.clear()
        llm_client._model_semaphore_limits.clear()
        in_use = asyncio.Semaphore(2)
        in_use._value = 0
        llm_client._model_semaphores["busy"] = in_use
        llm_client._model_semaphore_limits["busy"] = 2
        llm_client._model_semaphores["new"] = asyncio.Semaphore(2)
        llm_client._model_semaphore_limits["new"] = 2

        llm_client._evict_idle_model_semaphores(keep="new")

        assert "busy" in llm_client._model_semaphores


class TestDisableFallback:
    def test_disabled_preference_returns_true(self):
        manager = MagicMock()
        manager.get_fallback_preference_by_token.return_value = {
            "fallback_preference": "disabled"
        }

        with patch(
            "app.services.apikey_manager.get_apikey_manager", return_value=manager
        ):
            client = _client(api_key_token="sk-test")

        assert client._disable_fallback is True

    def test_manager_exception_is_non_fatal(self):
        with patch(
            "app.services.apikey_manager.get_apikey_manager",
            side_effect=RuntimeError("db down"),
        ):
            client = _client(api_key_token="sk-test")

        assert client._disable_fallback is False

    def test_no_token_short_circuits(self):
        client = _client()

        assert client._disable_fallback is False


class TestCallStreamValidation:
    async def test_missing_callback_rejected(self):
        client = _client()

        with pytest.raises(ValueError, match="on_chunk"):
            await client.call_stream("Hi", on_chunk=None)

    async def test_pre_cancelled_event(self):
        event = asyncio.Event()
        event.set()
        client = _client(cancel_event=event)
        router = AsyncMock()

        with patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)):
            with pytest.raises(asyncio.CancelledError):
                await client.call_stream("Hi", on_chunk=AsyncMock())

        assert router.record_call.await_args.kwargs["error"] == "cancelled"

    async def test_without_semaphore_skips_model_slot(self):
        client = _client()
        client._semaphore = None
        router = AsyncMock()

        async def stream():
            yield json.dumps({"choices": [{"delta": {"content": "Hi"}}]})

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(llm_client, "call_llm", AsyncMock(return_value=stream())),
        ):
            assert await client.call_stream("Hi", on_chunk=AsyncMock()) == "Hi"

    async def test_coroutine_stream_is_awaited(self):
        client = _client()
        router = AsyncMock()

        async def stream():
            yield json.dumps({"choices": [{"delta": {"content": "Hi"}}]})

        async def returns_coroutine(*args, **kwargs):
            async def inner():
                return stream()

            return inner()

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(llm_client, "call_llm", AsyncMock(return_value=stream())),
        ):
            # 直接构造 coroutine 返回值，触发 iscoroutine 分支
            coro_client = client
            original = llm_client.call_llm
            llm_client.call_llm = returns_coroutine
            try:
                assert await coro_client.call_stream("Hi", on_chunk=AsyncMock()) == "Hi"
            finally:
                llm_client.call_llm = original

    async def test_generic_failure_wrapped(self):
        client = _client()
        router = AsyncMock()

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(
                llm_client, "call_llm", AsyncMock(side_effect=RuntimeError("upstream"))
            ),
        ):
            with pytest.raises(LLMClientError, match="流式调用失败"):
                await client.call_stream("Hi", on_chunk=AsyncMock())

        assert router.record_call.await_args.kwargs["success"] is False

    async def test_auth_failure_wrapped(self):
        client = _client()
        router = AsyncMock()
        request = httpx.Request("POST", "https://api.example.com")
        response = httpx.Response(401, request=request)
        error = httpx.HTTPStatusError("unauthorized", request=request, response=response)

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(llm_client, "call_llm", AsyncMock(side_effect=error)),
        ):
            with pytest.raises(LLMClientError, match="认证失败"):
                await client.call_stream("Hi", on_chunk=AsyncMock())

    async def test_timeout_wrapped(self):
        client = _client()
        router = AsyncMock()

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(
                llm_client, "call_llm", AsyncMock(side_effect=asyncio.TimeoutError())
            ),
        ):
            with pytest.raises(LLMClientError, match="超时"):
                await client.call_stream("Hi", on_chunk=AsyncMock())


class TestStreamChunkParsing:
    async def _run(self, chunks, on_chunk=None):
        client = _client()
        router = AsyncMock()

        async def stream():
            for chunk in chunks:
                yield chunk

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(llm_client, "call_llm", AsyncMock(return_value=stream())),
        ):
            return await client.call_stream("Hi", on_chunk=on_chunk or AsyncMock())

    async def test_blank_and_done_chunks_skipped(self):
        content = await self._run(
            [
                "",
                "   ",
                "[DONE]",
                json.dumps({"choices": [{"delta": {"content": "A"}}]}),
            ]
        )

        assert content == "A"

    async def test_malformed_json_chunk_skipped(self):
        content = await self._run(
            ["{not json", json.dumps({"choices": [{"delta": {"content": "B"}}]})]
        )

        assert content == "B"

    async def test_data_prefix_stripped(self):
        payload = json.dumps({"choices": [{"delta": {"content": "C"}}]})
        content = await self._run([f"data: {payload}"])

        assert content == "C"

    async def test_reasoning_delta_passed_to_callback(self):
        calls = []

        async def on_chunk(content, reasoning):
            calls.append((content, reasoning))

        payload = json.dumps(
            {"choices": [{"delta": {"reasoning_content": "thinking"}}]}
        )
        content = await self._run([payload], on_chunk=on_chunk)

        assert content == ""
        assert calls == [("", "thinking")]

    async def test_callback_failure_is_non_fatal(self):
        async def on_chunk(content, reasoning):
            raise RuntimeError("callback boom")

        payload = json.dumps({"choices": [{"delta": {"content": "D"}}]})
        content = await self._run([payload], on_chunk=on_chunk)

        assert content == "D"

    async def test_usage_chunk_with_choices_captured(self):
        tracker = MagicMock()
        client = _client(cost_tracker=tracker)
        router = AsyncMock()

        async def stream():
            yield json.dumps(
                {
                    "choices": [{"delta": {"content": "E"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 5},
                }
            )

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(llm_client, "call_llm", AsyncMock(return_value=stream())),
        ):
            assert await client.call_stream("Hi", on_chunk=AsyncMock()) == "E"

        tracker.add_usage.assert_called_once()

    async def test_empty_choices_without_usage_skipped(self):
        content = await self._run(
            [
                json.dumps({"choices": []}),
                json.dumps({"choices": [{"delta": {"content": "F"}}]}),
            ]
        )

        assert content == "F"

    async def test_repeated_reasoning_chunks_skip_first_log(self):
        payloads = [
            json.dumps({"choices": [{"delta": {"reasoning_content": "a"}}]}),
            json.dumps({"choices": [{"delta": {"reasoning_content": "b"}}]}),
        ]
        calls = []

        async def on_chunk(content, reasoning):
            calls.append(reasoning)

        assert await self._run(payloads, on_chunk=on_chunk) == ""
        assert calls == ["a", "b"]

    async def test_empty_delta_chunk_skips_callback(self):
        calls = []

        async def on_chunk(content, reasoning):
            calls.append((content, reasoning))

        content = await self._run(
            [
                json.dumps({"choices": [{"delta": {}}]}),
                json.dumps({"choices": [{"delta": {"content": "G"}}]}),
            ],
            on_chunk=on_chunk,
        )

        assert content == "G"
        assert calls == [("G", "")]


class TestCallInternalBranches:
    async def test_without_semaphore(self):
        client = _client()
        client._semaphore = None
        router = AsyncMock()
        response = {"choices": [{"message": {"content": "ok"}}]}

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(llm_client, "call_llm", AsyncMock(return_value=response)),
        ):
            assert await client.call("Hi") == "ok"

    async def test_pre_cancelled_event(self):
        event = asyncio.Event()
        event.set()
        client = _client(cancel_event=event)
        router = AsyncMock()

        with patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)):
            with pytest.raises(asyncio.CancelledError):
                await client.call("Hi")

    async def test_auth_failure_wrapped(self):
        client = _client()
        router = AsyncMock()
        request = httpx.Request("POST", "https://api.example.com")
        response = httpx.Response(403, request=request)
        error = httpx.HTTPStatusError("forbidden", request=request, response=response)

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(llm_client, "call_llm", AsyncMock(side_effect=error)),
        ):
            with pytest.raises(LLMClientError, match="认证失败"):
                await client.call("Hi")

    async def test_timeout_wrapped(self):
        client = _client()
        router = AsyncMock()

        with (
            patch.object(llm_client, "get_dynamic_router", AsyncMock(return_value=router)),
            patch.object(
                llm_client, "call_llm", AsyncMock(side_effect=asyncio.TimeoutError())
            ),
        ):
            with pytest.raises(LLMClientError, match="超时"):
                await client.call("Hi")
