"""Branch coverage for the unified LLM caller."""

from __future__ import annotations

import asyncio
import gc
from types import SimpleNamespace

import pytest

from app.utils.aicloud import llm_caller
from app.utils.aicloud.providers import ModelProvider, ProviderConfig


async def _agen(*chunks):
    for chunk in chunks:
        yield chunk


async def _failing_agen(error):
    if False:  # pragma: no cover
        yield ""
    raise error


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    class _NullLock:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(llm_caller, "_adapter_cache", {})
    monkeypatch.setattr(llm_caller, "_user_adapter_cache", type(llm_caller._user_adapter_cache)())
    monkeypatch.setattr(llm_caller, "_adapter_cache_lock", _NullLock())
    monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: None)
    monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: None)
    llm_caller.reset_model_cooldowns()
    yield
    llm_caller.reset_model_cooldowns()


class TestMetrics:
    def test_finish_without_scope_returns_zeroes(self):
        token = llm_caller.begin_llm_call_metrics()
        metrics = llm_caller.finish_llm_call_metrics(token)

        assert metrics == {"model_call_count": 0, "token_count": 0}

    def test_response_metrics_ignore_non_dict_and_null_usage(self):
        token = llm_caller.begin_llm_call_metrics()

        llm_caller._record_llm_response_metrics("nope")
        llm_caller._record_llm_response_metrics({"usage": None})
        llm_caller._record_llm_response_metrics({"usage": {"total_tokens": "7"}})
        metrics = llm_caller.finish_llm_call_metrics(token)

        assert metrics["token_count"] == 7

    def test_response_metrics_without_scope_are_noops(self):
        llm_caller._record_llm_call()
        llm_caller._record_llm_response_metrics({"usage": {"total_tokens": 3}})
        llm_caller._record_llm_stream_metrics("data: {}")

    @pytest.mark.parametrize(
        ("chunk", "expected"),
        [
            (None, 0),
            ("not json", 0),
            ("data: 42", 0),
            ('{"usage": {"total_tokens": 5}}', 5),
            ('data: {"usage": {"total_tokens": 9}}', 9),
        ],
    )
    def test_stream_usage_tokens(self, chunk, expected):
        assert llm_caller._stream_usage_tokens(chunk) == expected

    def test_stream_metrics_accumulate(self):
        token = llm_caller.begin_llm_call_metrics()

        llm_caller._record_llm_stream_metrics('{"usage": {"total_tokens": 4}}')
        llm_caller._record_llm_stream_metrics("invalid")
        metrics = llm_caller.finish_llm_call_metrics(token)

        assert metrics["token_count"] == 4


class TestCooldown:
    def test_rate_limit_detection_variants(self):
        assert llm_caller._is_rate_limit_error(SimpleNamespace(status_code=429))
        response = SimpleNamespace(status_code=429)
        assert llm_caller._is_rate_limit_error(SimpleNamespace(response=response))
        assert llm_caller._is_rate_limit_error(RuntimeError("Too Many Requests"))
        assert llm_caller._is_rate_limit_error(RuntimeError("rate limit"))
        assert llm_caller._is_rate_limit_error(RuntimeError("429"))
        assert not llm_caller._is_rate_limit_error(RuntimeError("boom"))

    @pytest.mark.parametrize(
        ("header", "expected"),
        [
            (None, llm_caller._MODEL_COOLDOWN_MIN),
            ("bad", llm_caller._MODEL_COOLDOWN_MIN),
            ("1", llm_caller._MODEL_COOLDOWN_MIN),
            ("9999", llm_caller._MODEL_COOLDOWN_MAX),
            ("30", 30.0),
        ],
    )
    def test_retry_after_seconds(self, header, expected):
        if header is None:
            exc = RuntimeError("boom")
        else:
            exc = SimpleNamespace(response=SimpleNamespace(headers={"Retry-After": header}))

        assert llm_caller._retry_after_seconds(exc) == expected

    def test_retry_after_uses_lowercase_header(self):
        exc = SimpleNamespace(response=SimpleNamespace(headers={"retry-after": "40"}))

        assert llm_caller._retry_after_seconds(exc) == 40.0

    def test_set_cooldown_ignores_empty_model(self):
        llm_caller._set_model_cooldown("", 100)

        assert llm_caller._model_cooldown_until == {}

    @pytest.mark.asyncio
    async def test_await_cooldown_ignores_empty_model(self):
        await llm_caller._await_model_cooldown("")

    @pytest.mark.asyncio
    async def test_await_cooldown_sleeps(self, monkeypatch):
        sleeps = []

        async def fake_sleep(seconds):
            sleeps.append(seconds)

        monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)
        llm_caller._set_model_cooldown("m", 20)

        await llm_caller._await_model_cooldown("m")

        assert len(sleeps) == 1 and sleeps[0] > 0

    @pytest.mark.asyncio
    async def test_retry_helper_retries_then_succeeds(self, monkeypatch):
        attempts = []

        async def fake_sleep(_seconds):
            return None

        monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)

        async def factory():
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("429 rate limit")
            return "ok"

        assert await llm_caller._retry_on_rate_limit_for_model(factory, model="m") == "ok"
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_retry_helper_propagates_other_errors(self):
        async def factory():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            await llm_caller._retry_on_rate_limit_for_model(factory)

    @pytest.mark.asyncio
    async def test_retry_helper_exhausts_last_error(self):
        async def factory():
            raise RuntimeError("429")

        with pytest.raises(RuntimeError, match="429"):
            await llm_caller._retry_on_rate_limit_for_model(factory, max_attempts=1)

    @pytest.mark.asyncio
    async def test_invoke_retry_rate_limit_then_success(self, monkeypatch):
        attempts = []

        async def fake_sleep(_seconds):
            return None

        monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)

        async def factory():
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("429 rate limit")
            return "ok"

        assert await llm_caller._invoke_adapter_with_retry(factory, "m") == "ok"
        assert len(attempts) == 2

    @pytest.mark.asyncio
    async def test_retry_helper_zero_attempts_raises_none(self):
        async def factory():
            return "unused"

        with pytest.raises(TypeError):
            await llm_caller._retry_on_rate_limit_for_model(factory, max_attempts=0)

    @pytest.mark.asyncio
    async def test_invoke_retry_releases_lease_between_attempts(self, monkeypatch):
        released = []
        monkeypatch.setattr(
            llm_caller._LLMSemaphoreLease, "release", lambda self: released.append(True)
        )
        attempts = []

        async def fake_sleep(_seconds):
            return None

        monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)

        async def factory():
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("429")
            return "ok"

        await llm_caller._invoke_adapter_with_retry(factory, "m", max_attempts=2)

        assert released == [True, True]


class TestSemaphoreLease:
    @pytest.mark.asyncio
    async def test_skip_makes_no_calls(self, monkeypatch):
        def boom():
            raise AssertionError("should not import semaphores")

        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", boom)
        lease = llm_caller._LLMSemaphoreLease()

        await lease.acquire("m", skip=True)

        assert lease.global_acquired is False

    @pytest.mark.asyncio
    async def test_import_failure_is_swallowed(self, monkeypatch):
        def boom():
            raise RuntimeError("no semaphores")

        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", boom)
        lease = llm_caller._LLMSemaphoreLease()

        await lease.acquire("m", skip=False)

        assert lease.global_acquired is False
        assert lease.model_acquired is False

    @pytest.mark.asyncio
    async def test_acquire_failure_releases_and_raises(self, monkeypatch):
        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()
        model_sem = Sem()
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

        async def boom(*args, **kwargs):
            raise RuntimeError("full")

        monkeypatch.setattr(llm_caller, "_acquire_llm_semaphores", boom)
        lease = llm_caller._LLMSemaphoreLease()

        with pytest.raises(RuntimeError, match="full"):
            await lease.acquire("m", skip=False)
        assert lease.global_acquired is False

    @pytest.mark.asyncio
    async def test_partial_acquire_and_transfer(self, monkeypatch):
        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()
        model_sem = Sem()
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)
        lease = llm_caller._LLMSemaphoreLease()

        await lease.acquire("m", skip=False)
        transferred = lease.transfer()
        assert transferred == (global_sem, model_sem)
        assert lease.global_acquired is False

        lease.release()
        assert global_sem.released == 0

    @pytest.mark.asyncio
    async def test_reacquire_with_existing_semaphores_is_noop(self, monkeypatch):
        class Sem:
            async def acquire(self):
                return None

            def release(self):
                return None

        global_sem = Sem()
        model_sem = Sem()
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)
        lease = llm_caller._LLMSemaphoreLease()

        await lease.acquire("m", skip=False)
        await lease.acquire("m", skip=False)

        assert lease.global_acquired is True
        assert lease.model_acquired is True

    @pytest.mark.asyncio
    async def test_only_model_semaphore_available(self, monkeypatch):
        class Sem:
            async def acquire(self):
                return None

            def release(self):
                return None

        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: None)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: Sem())
        lease = llm_caller._LLMSemaphoreLease()

        await lease.acquire("m", skip=False)

        assert lease.global_acquired is False
        assert lease.model_acquired is True
        lease.release()
        assert lease.model_acquired is False


class TestInvokeRetry:
    @pytest.mark.asyncio
    async def test_non_stream_releases_lease(self, monkeypatch):
        released = []
        monkeypatch.setattr(llm_caller._LLMSemaphoreLease, "release", lambda self: released.append(True))

        async def factory():
            return {"ok": True}

        assert await llm_caller._invoke_adapter_with_retry(factory, "m") == {"ok": True}
        assert released == [True]

    @pytest.mark.asyncio
    async def test_stream_returns_wrapped_iterator(self):
        async def factory():
            return _agen("a", "b")

        result = await llm_caller._invoke_adapter_with_retry(factory, "m", stream=True)

        assert [chunk async for chunk in result] == ["a", "b"]
        assert result._released is True

    @pytest.mark.asyncio
    async def test_empty_stream_is_wrapped(self):
        async def factory():
            return _agen()

        result = await llm_caller._invoke_adapter_with_retry(factory, "m", stream=True)

        assert [chunk async for chunk in result] == []

    @pytest.mark.asyncio
    async def test_stream_error_closes_iterator(self):
        closed = []

        class Stream:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise RuntimeError("boom")

            async def aclose(self):
                closed.append(True)

        async def factory():
            return Stream()

        with pytest.raises(RuntimeError, match="boom"):
            await llm_caller._invoke_adapter_with_retry(factory, "m", stream=True)
        assert closed == [True]

    @pytest.mark.asyncio
    async def test_cancellation_releases_lease(self, monkeypatch):
        released = []
        monkeypatch.setattr(llm_caller._LLMSemaphoreLease, "release", lambda self: released.append(True))

        async def factory():
            raise asyncio.CancelledError()

        with pytest.raises(asyncio.CancelledError):
            await llm_caller._invoke_adapter_with_retry(factory, "m")
        assert released == [True]

    @pytest.mark.asyncio
    async def test_empty_attempt_range_raises_none(self):
        async def factory():
            return "unused"

        with pytest.raises(TypeError):
            await llm_caller._invoke_adapter_with_retry(factory, "m", max_attempts=0)


class TestAdapterFactory:
    @pytest.mark.asyncio
    async def test_unknown_provider(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            await llm_caller.get_adapter("unknown")

    @pytest.mark.asyncio
    async def test_default_config_missing_raises(self):
        class Registry:
            def get(self, provider):
                return None

        settings = SimpleNamespace(get_provider_registry=lambda: Registry())

        with pytest.raises(RuntimeError, match="not configured"):
            await llm_caller.get_adapter(ModelProvider.SILICONFLOW)

    @pytest.mark.asyncio
    async def test_default_adapter_is_cached(self, monkeypatch):
        created = []

        class Adapter:
            pass

        def factory(cfg):
            created.append(cfg)
            return Adapter()

        class Registry:
            def get(self, provider):
                return ProviderConfig(provider=provider, api_key="k", base_url="u")

        settings = SimpleNamespace(get_provider_registry=lambda: Registry())
        monkeypatch.setattr(llm_caller, "settings", settings)
        monkeypatch.setattr(
            llm_caller, "ADAPTER_FACTORIES", {ModelProvider.SILICONFLOW: factory}
        )

        first = await llm_caller.get_adapter(ModelProvider.SILICONFLOW)
        second = await llm_caller.get_adapter(ModelProvider.SILICONFLOW)

        assert first is second
        assert len(created) == 1

    @pytest.mark.asyncio
    async def test_user_adapter_is_cached_and_evicted(self, monkeypatch):
        created = []

        class Adapter:
            pass

        def factory(cfg):
            created.append(cfg)
            return Adapter()

        config = ProviderConfig(
            provider=ModelProvider.SILICONFLOW, api_key="key-a", base_url="u"
        )
        monkeypatch.setattr(
            llm_caller, "ADAPTER_FACTORIES", {ModelProvider.SILICONFLOW: factory}
        )
        monkeypatch.setattr(llm_caller, "_USER_ADAPTER_CACHE_MAX", 1)

        first = await llm_caller.get_adapter(ModelProvider.SILICONFLOW, config)
        second = await llm_caller.get_adapter(ModelProvider.SILICONFLOW, config)
        assert first is second
        assert len(created) == 1

        other = ProviderConfig(
            provider=ModelProvider.SILICONFLOW, api_key="key-b", base_url="u"
        )
        await llm_caller.get_adapter(ModelProvider.SILICONFLOW, other)

        assert len(llm_caller._user_adapter_cache) == 1
        assert (
            llm_caller._make_user_cache_key(ModelProvider.SILICONFLOW, "key-a")
            not in llm_caller._user_adapter_cache
        )


class TestCallLLMDynamic:
    @pytest.mark.asyncio
    async def test_provider_id_uses_langchain_invoke(self, monkeypatch):
        provider = SimpleNamespace(enabled=True, protocol=SimpleNamespace(value="openai"), api_key="k", base_url="u")
        manager = SimpleNamespace(get=lambda pid, user: provider)
        calls = []

        async def invoke(*args, **kwargs):
            calls.append(args)
            return {"content": "ok"}

        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr("app.utils.aicloud.langchain_adapter.invoke", invoke)

        result = await llm_caller.call_llm("m", "p", provider_id="p1")

        assert result == {"content": "ok"}
        assert calls

    @pytest.mark.asyncio
    async def test_provider_id_uses_langchain_stream(self, monkeypatch):
        provider = SimpleNamespace(enabled=True, protocol=SimpleNamespace(value="anthropic"), api_key="k", base_url="u")
        manager = SimpleNamespace(get=lambda pid, user: provider)

        def stream(*args, **kwargs):
            return _agen("x")

        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr("app.utils.aicloud.langchain_adapter.stream", stream)

        result = await llm_caller.call_llm("m", "p", provider_id="p1", stream=True)

        assert [chunk async for chunk in result] == ["x"]

    @pytest.mark.asyncio
    async def test_langchain_unavailable_falls_back_to_native_adapter(self, monkeypatch):
        from app.utils.aicloud.langchain_adapter import LangChainUnavailable

        provider = SimpleNamespace(enabled=True, protocol=SimpleNamespace(value="openai"), api_key="k", base_url="u")
        manager = SimpleNamespace(get=lambda pid, user: provider)
        captured = []

        async def invoke(*args, **kwargs):
            raise LangChainUnavailable()

        class Adapter:
            def __init__(self, provider_obj):
                captured.append(provider_obj)
                self.api_key = "k"
                self.provider = ModelProvider.OPENAI
                self.timeout = 0

            async def call_llm(self, **kwargs):
                return {"native": True}

        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr("app.utils.aicloud.langchain_adapter.invoke", invoke)
        monkeypatch.setattr(llm_caller, "DynamicAdapter", Adapter)

        result = await llm_caller.call_llm("m", "p", provider_id="p1")

        assert result == {"native": True}
        assert captured == [provider]

    @pytest.mark.asyncio
    async def test_langchain_import_error_falls_back_to_native_adapter(self, monkeypatch):
        provider = SimpleNamespace(enabled=True, protocol=SimpleNamespace(value="openai"), api_key="k", base_url="u")
        manager = SimpleNamespace(get=lambda pid, user: provider)

        async def invoke(*args, **kwargs):
            raise ImportError("missing")

        class Adapter:
            def __init__(self, provider_obj):
                self.api_key = "k"
                self.provider = ModelProvider.OPENAI
                self.timeout = 0

            async def call_llm(self, **kwargs):
                return {"native": True}

        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr("app.utils.aicloud.langchain_adapter.invoke", invoke)
        monkeypatch.setattr(llm_caller, "DynamicAdapter", Adapter)

        assert await llm_caller.call_llm("m", "p", provider_id="p1") == {"native": True}

    @pytest.mark.asyncio
    async def test_disabled_provider_id_falls_through(self, monkeypatch):
        provider = SimpleNamespace(enabled=False)
        manager = SimpleNamespace(get=lambda pid, user: provider, get_by_model=lambda model, user: None)
        primary = ModelProvider.SILICONFLOW

        class Router:
            def route(self, model):
                return primary

            def get_fallback_providers(self, provider, model):
                return []

            def get_fallback_providers(self, provider, model):
                return []

        class Adapter:
            provider = primary
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"ok": True}

        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(llm_caller, "get_adapter", self._adapter_factory(Adapter))

        assert await llm_caller.call_llm("m", "p", provider_id="missing") == {"ok": True}

    @pytest.mark.asyncio
    async def test_dynamic_model_lookup_uses_dynamic_adapter(self, monkeypatch):
        dp = SimpleNamespace(name="dp")
        manager = SimpleNamespace(
            get=lambda pid, user: None,
            get_by_model=lambda model, user: dp,
        )
        captured = []

        class Adapter:
            provider = ModelProvider.SILICONFLOW
            api_key = "k"
            timeout = 0

            def __init__(self, provider_obj):
                captured.append(provider_obj)

            async def call_llm(self, **kwargs):
                return {"dynamic": True}

        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr(llm_caller, "DynamicAdapter", Adapter)

        assert await llm_caller.call_llm("m", "p") == {"dynamic": True}
        assert captured == [dp]

    @pytest.mark.asyncio
    async def test_user_key_missing_raises(self, monkeypatch):
        monkeypatch.setattr(llm_caller, "_get_user_api_key_from_token", lambda token: None)

        with pytest.raises(llm_caller.UserAPIKeyNotFoundError):
            await llm_caller.call_llm("m", "p", api_key_token="t" * 40)

    @pytest.mark.asyncio
    async def test_user_adapter_creation_failure_falls_back(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        manager = SimpleNamespace(get_by_model=lambda model, user: None)

        class Router:
            def route(self, model):
                return primary

            def get_fallback_providers(self, provider, model):
                return []

        calls = []

        class Adapter:
            provider = primary
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"ok": True}

        async def fake_get_adapter(provider, config=None):
            calls.append(config)
            if config is not None:
                raise RuntimeError("bad key")
            return Adapter()

        monkeypatch.setattr(llm_caller, "_get_user_api_key_from_token", lambda token: "sk-user")
        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)

        assert await llm_caller.call_llm("m", "p", api_key_token="t" * 40) == {"ok": True}
        assert calls[0] is not None

    @pytest.mark.asyncio
    async def test_user_key_adapter_is_used(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        manager = SimpleNamespace(get_by_model=lambda model, user: None)

        class Router:
            def route(self, model):
                return primary

            def get_fallback_providers(self, provider, model):
                return []

        class Adapter:
            provider = primary
            api_key = "sk-user"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"user": True}

        calls = []

        async def fake_get_adapter(provider, config=None):
            calls.append((provider, config))
            return Adapter()

        monkeypatch.setattr(llm_caller, "_get_user_api_key_from_token", lambda token: "sk-user")
        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)

        result = await llm_caller.call_llm("m", "p", api_key_token="t" * 40)

        assert result == {"user": True}
        assert calls[0][1] is not None
        assert calls[0][1].api_key == "sk-user"

    @pytest.mark.asyncio
    async def test_user_key_with_unrouted_model_falls_through(self, monkeypatch):
        manager = SimpleNamespace(get_by_model=lambda model, user: None)

        class Router:
            def route(self, model):
                return None

        class Adapter:
            provider = ModelProvider.SILICONFLOW
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"ok": True}

        monkeypatch.setattr(llm_caller, "_get_user_api_key_from_token", lambda token: "sk-user")
        monkeypatch.setattr(
            "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager", lambda: manager
        )
        monkeypatch.setattr("app.utils.logging.get_user_id", lambda: "u")
        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(
            llm_caller, "get_adapter", TestCallLLMDynamic._adapter_factory(Adapter)
        )

        assert await llm_caller.call_llm("m", "p", api_key_token="t" * 40) == {"ok": True}

    @staticmethod
    def _adapter_factory(adapter_cls, error=None):
        async def fake(provider, config=None):
            if error is not None and config is None:
                raise error
            return adapter_cls()

        return fake


class TestCallLLMRouting:
    @pytest.mark.asyncio
    async def test_disable_fallback_raises(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW

        class Router:
            def route(self, model):
                return primary

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )

        async def fake_get_adapter(provider, config=None):
            raise RuntimeError("down")

        monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)

        with pytest.raises(RuntimeError, match="fallback is disabled"):
            await llm_caller.call_llm("m", "p", disable_fallback=True)

    @pytest.mark.asyncio
    async def test_fallback_provider_succeeds(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Router:
            def route(self, model):
                return primary

            def get_fallback_providers(self, provider, model):
                return [fallback]

        class Adapter:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"fallback": True}

        async def fake_get_adapter(provider, config=None):
            if provider is primary:
                raise RuntimeError("primary down")
            return Adapter()

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)

        assert await llm_caller.call_llm("m", "p") == {"fallback": True}

    @pytest.mark.asyncio
    async def test_all_fallback_providers_fail(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Router:
            def route(self, model):
                return primary

            def get_fallback_providers(self, provider, model):
                return [fallback]

        async def fake_get_adapter(provider, config=None):
            raise RuntimeError(f"{provider.value} down")

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)

        with pytest.raises(RuntimeError, match="All providers failed"):
            await llm_caller.call_llm("m", "p")

    @pytest.mark.asyncio
    async def test_missing_adapter_key_raises(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW

        class Router:
            def route(self, model):
                return primary

        class Adapter:
            provider = primary
            api_key = ""
            timeout = 0

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(
            llm_caller,
            "get_adapter",
            TestCallLLMDynamic._adapter_factory(Adapter),
        )

        with pytest.raises(llm_caller.ProviderAPIKeyNotConfiguredError):
            await llm_caller.call_llm("m", "p")

    @pytest.mark.asyncio
    async def test_non_stream_records_usage_metrics(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW

        class Router:
            def route(self, model):
                return primary

        class Adapter:
            provider = primary
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"usage": {"total_tokens": 11}}

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(
            llm_caller, "get_adapter", TestCallLLMDynamic._adapter_factory(Adapter)
        )
        token = llm_caller.begin_llm_call_metrics()

        await llm_caller.call_llm("m", "p")
        metrics = llm_caller.finish_llm_call_metrics(token)

        assert metrics == {"model_call_count": 1, "token_count": 11}

    @pytest.mark.asyncio
    async def test_stream_records_call_metrics_only(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW

        class Router:
            def route(self, model):
                return primary

        class Adapter:
            provider = primary
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return _agen("x")

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(
            llm_caller, "get_adapter", TestCallLLMDynamic._adapter_factory(Adapter)
        )
        token = llm_caller.begin_llm_call_metrics()

        result = await llm_caller.call_llm("m", "p", stream=True)
        metrics = llm_caller.finish_llm_call_metrics(token)

        assert [chunk async for chunk in result] == ["x"]
        assert metrics["model_call_count"] == 1

    @pytest.mark.asyncio
    async def test_cancellation_propagates(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW

        class Router:
            def route(self, model):
                return primary

        class Adapter:
            provider = primary
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise asyncio.CancelledError()

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(
            llm_caller, "get_adapter", TestCallLLMDynamic._adapter_factory(Adapter)
        )

        with pytest.raises(asyncio.CancelledError):
            await llm_caller.call_llm("m", "p")

    @pytest.mark.asyncio
    async def test_non_stream_failure_reraises(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW

        class Router:
            def route(self, model):
                return primary

        class Adapter:
            provider = primary
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise RuntimeError("boom")

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(
            llm_caller, "get_adapter", TestCallLLMDynamic._adapter_factory(Adapter)
        )

        with pytest.raises(RuntimeError, match="boom"):
            await llm_caller.call_llm("m", "p", stream=True, disable_fallback=True)


class TestCallLLMStreamFallback:
    @staticmethod
    def _install(monkeypatch, primary, fallback, fallback_adapter):
        class Router:
            def route(self, model):
                return primary

            def get_fallback_providers(self, provider, model):
                return [fallback]

        class PrimaryAdapter:
            provider = primary
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return _failing_agen(RuntimeError("stream down"))

        async def fake_get_adapter(provider, config=None):
            return PrimaryAdapter() if provider is primary else fallback_adapter

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)

    @pytest.mark.asyncio
    async def test_fallback_returns_wrapped_stream(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return _agen("a", "b")

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: None)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: None)

        result = await llm_caller.call_llm("m", "p", stream=True)

        assert [chunk async for chunk in result] == ["a", "b"]

    @pytest.mark.asyncio
    async def test_fallback_non_stream_result_releases_semaphores(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()
        model_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"content": "plain"}

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

        result = await llm_caller.call_llm("m", "p", stream=True)

        assert result == {"content": "plain"}
        # Primary lease is released after the stream error; fallback releases again.
        assert model_sem.released == 2
        assert global_sem.released == 2

    @pytest.mark.asyncio
    async def test_fallback_cancellation_releases_semaphores(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()
        model_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise asyncio.CancelledError()

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

        with pytest.raises(asyncio.CancelledError):
            await llm_caller.call_llm("m", "p", stream=True)
        assert model_sem.released == 2
        assert global_sem.released == 2

    @pytest.mark.asyncio
    async def test_fallback_failure_releases_semaphores_and_reraises(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()
        model_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise RuntimeError("fallback down")

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

        with pytest.raises(RuntimeError, match="stream down"):
            await llm_caller.call_llm("m", "p", stream=True)
        assert model_sem.released == 2
        assert global_sem.released == 2

    @pytest.mark.asyncio
    async def test_semaphore_import_failure_is_swallowed(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return _agen("ok")

        def boom():
            raise RuntimeError("no semaphores")

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", boom)

        result = await llm_caller.call_llm("m", "p", stream=True)

        assert [chunk async for chunk in result] == ["ok"]

    @pytest.mark.asyncio
    async def test_fallback_non_stream_with_only_model_semaphore(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        model_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"content": "plain"}

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: None)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

        assert await llm_caller.call_llm("m", "p", stream=True) == {"content": "plain"}
        assert model_sem.released == 2

    @pytest.mark.asyncio
    async def test_fallback_cancellation_with_only_global_semaphore(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise asyncio.CancelledError()

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: None)

        with pytest.raises(asyncio.CancelledError):
            await llm_caller.call_llm("m", "p", stream=True)
        assert global_sem.released == 2

    @pytest.mark.asyncio
    async def test_fallback_error_with_only_global_semaphore(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise RuntimeError("fallback down")

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: None)

        with pytest.raises(RuntimeError, match="stream down"):
            await llm_caller.call_llm("m", "p", stream=True)
        assert global_sem.released == 2

    @pytest.mark.asyncio
    async def test_fallback_non_stream_with_only_global_semaphore(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return {"content": "plain"}

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: None)

        assert await llm_caller.call_llm("m", "p", stream=True) == {"content": "plain"}
        assert global_sem.released == 2

    @pytest.mark.asyncio
    async def test_fallback_cancellation_with_only_model_semaphore(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        model_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise asyncio.CancelledError()

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: None)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

        with pytest.raises(asyncio.CancelledError):
            await llm_caller.call_llm("m", "p", stream=True)
        assert model_sem.released == 2

    @pytest.mark.asyncio
    async def test_fallback_error_with_only_model_semaphore(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        fallback = ModelProvider.DEEPSEEK

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        model_sem = Sem()

        class Fallback:
            provider = fallback
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise RuntimeError("fallback down")

        self._install(monkeypatch, primary, fallback, Fallback())
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: None)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

        with pytest.raises(RuntimeError, match="stream down"):
            await llm_caller.call_llm("m", "p", stream=True)
        assert model_sem.released == 2

    @pytest.mark.asyncio
    async def test_second_fallback_reuses_semaphores_from_first_attempt(self, monkeypatch):
        primary = ModelProvider.SILICONFLOW
        first = ModelProvider.DEEPSEEK
        second = ModelProvider.ZHIPU

        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()
        model_sem = Sem()

        class Router:
            def route(self, model):
                return primary

            def get_fallback_providers(self, provider, model):
                return [first, second]

        class Primary:
            provider = primary
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return _failing_agen(RuntimeError("primary down"))

        class FailingFallback:
            provider = first
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                raise RuntimeError("first fallback down")

        class WorkingFallback:
            provider = second
            api_key = "k"
            timeout = 0

            async def call_llm(self, **kwargs):
                return _agen("ok")

        async def fake_get_adapter(provider, config=None):
            return {
                primary: Primary(),
                first: FailingFallback(),
                second: WorkingFallback(),
            }[provider]

        monkeypatch.setattr(
            llm_caller.ProviderRouter,
            "get_instance",
            classmethod(lambda cls, registry=None: Router()),
        )
        monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)
        monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
        monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

        result = await llm_caller.call_llm("m", "p", stream=True)

        assert [chunk async for chunk in result] == ["ok"]


class TestStreamWrapper:
    @pytest.mark.asyncio
    async def test_aclose_is_idempotent_and_releases(self):
        class Sem:
            def __init__(self):
                self.released = 0

            def release(self):
                self.released += 1

        inner = _agen('{"usage": {"total_tokens": 6}}')
        global_sem = Sem()
        model_sem = Sem()
        stream = llm_caller.SemaphoreHeldStream(inner, global_sem, model_sem)
        token = llm_caller.begin_llm_call_metrics()

        await stream.__anext__()
        await stream.aclose()
        await stream.aclose()
        metrics = llm_caller.finish_llm_call_metrics(token)

        assert global_sem.released == 1
        assert model_sem.released == 1
        assert metrics["token_count"] == 6

    @pytest.mark.asyncio
    async def test_close_failure_is_logged(self, monkeypatch):
        warnings = []

        class Inner:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise RuntimeError("iter boom")

            async def aclose(self):
                raise RuntimeError("close boom")

        monkeypatch.setattr(
            llm_caller.logger, "warning", lambda *args, **kwargs: warnings.append(args)
        )
        stream = llm_caller.SemaphoreHeldStream(Inner(), None, None)

        with pytest.raises(RuntimeError, match="iter boom"):
            await stream.__anext__()
        assert warnings

    @pytest.mark.asyncio
    async def test_close_with_inner_lacking_aclose(self):
        class Inner:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        stream = llm_caller.SemaphoreHeldStream(Inner(), None, None)

        await stream.aclose()

        assert stream._closed is True
        assert stream._released is True

    @pytest.mark.asyncio
    async def test_release_now_is_idempotent(self):
        stream = llm_caller.SemaphoreHeldStream(_agen(), None, None)

        stream.release_now()
        stream.release_now()

        assert stream._released is True

    def test_del_releases_once(self):
        class Sem:
            def __init__(self):
                self.released = 0

            def release(self):
                self.released += 1

        sem = Sem()
        stream = llm_caller.SemaphoreHeldStream(_agen(), sem, None)

        stream.__del__()
        stream.__del__()

        assert sem.released == 1

    def test_del_swallows_release_errors(self):
        class Sem:
            def release(self):
                raise RuntimeError("boom")

        stream = llm_caller.SemaphoreHeldStream(_agen(), Sem(), None)

        stream.__del__()

    def test_iterated_stream_is_released_after_gc(self):
        class Sem:
            def __init__(self):
                self.released = 0

            def release(self):
                self.released += 1

        sem = Sem()
        stream = llm_caller.SemaphoreHeldStream(_agen(), sem, None)
        del stream
        gc.collect()

        assert sem.released == 1


class TestSemaphoreAcquisition:
    @pytest.mark.asyncio
    async def test_release_llm_semaphores_handles_none(self):
        class Sem:
            def __init__(self):
                self.released = 0

            def release(self):
                self.released += 1

        sem = Sem()
        llm_caller._release_llm_semaphores(None, None)
        llm_caller._release_llm_semaphores(sem, sem)

        assert sem.released == 2

    @pytest.mark.asyncio
    async def test_timeout_becomes_busy_error(self):
        class Sem:
            async def acquire(self):
                await asyncio.sleep(10)

            def release(self):
                return None

        with pytest.raises(llm_caller.LLMCallError) as exc:
            await llm_caller._acquire_llm_semaphores(Sem(), None, timeout=0.001)
        assert exc.value.status_code == 503

    @pytest.mark.asyncio
    async def test_cancellation_releases_partial_acquisition(self):
        class Sem:
            def __init__(self):
                self.released = 0

            async def acquire(self):
                return None

            def release(self):
                self.released += 1

        global_sem = Sem()

        class Blocking:
            async def acquire(self):
                raise asyncio.CancelledError()

            def release(self):
                return None

        with pytest.raises(asyncio.CancelledError):
            await llm_caller._acquire_llm_semaphores(global_sem, Blocking())
        assert global_sem.released == 1

    def test_iter_stream_helper_returns_wrapper(self):
        result = llm_caller._iter_stream_holding_semaphore(_agen(), None, None)

        assert isinstance(result, llm_caller.SemaphoreHeldStream)

    def test_prefixed_iterator_passthrough(self):
        async def collect():
            inner = _agen("b")
            prefixed = llm_caller._PrefixedAsyncIterator("a", inner)
            return [chunk async for chunk in prefixed]

        assert asyncio.run(collect()) == ["a", "b"]

    @pytest.mark.asyncio
    async def test_prefixed_iterator_without_aclose(self):
        class Rest:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration

        prefixed = llm_caller._PrefixedAsyncIterator("a", Rest())

        await prefixed.aclose()


class TestGetUserKey:
    def test_short_token_is_rejected(self):
        assert llm_caller._get_user_api_key_from_token("short") is None

    def test_manager_exception_is_logged(self, monkeypatch):
        warnings = []

        def boom():
            raise RuntimeError("redis down")

        monkeypatch.setattr("app.services.apikey_manager.get_apikey_manager", boom)
        monkeypatch.setattr(
            llm_caller.logger, "warning", lambda *args, **kwargs: warnings.append(args)
        )

        assert llm_caller._get_user_api_key_from_token("x" * 40) is None
        assert warnings

    def test_manager_returns_key(self, monkeypatch):
        manager = SimpleNamespace(get_key_by_token=lambda token: "sk-user")
        monkeypatch.setattr(
            "app.services.apikey_manager.get_apikey_manager", lambda: manager
        )

        assert llm_caller._get_user_api_key_from_token("x" * 40) == "sk-user"

    def test_provider_base_urls(self):
        assert "anthropic" in llm_caller._get_provider_base_url(ModelProvider.ANTHROPIC)
        assert llm_caller._get_provider_base_url("unknown") == "https://api.siliconflow.cn/v1"
