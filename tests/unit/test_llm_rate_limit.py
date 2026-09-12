import types

import pytest

from app.utils.aicloud import llm_caller


@pytest.fixture(autouse=True)
def _clear_cooldowns():
    llm_caller.reset_model_cooldowns()
    yield
    llm_caller.reset_model_cooldowns()


@pytest.mark.asyncio
async def test_retry_on_rate_limit_uses_retry_after_and_sets_cooldown(monkeypatch):
    attempts = {"n": 0}

    class Fake429(Exception):
        def __init__(self):
            super().__init__("429 Too Many Requests")
            self.status_code = 429
            self.response = types.SimpleNamespace(headers={"Retry-After": "20"})

    async def factory():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise Fake429()
        return "ok"

    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(llm_caller.time, "monotonic", lambda: 1000.0)

    result = await llm_caller._retry_on_rate_limit_for_model(factory, model="glm-4.7-flash")
    assert result == "ok"
    assert slept == [20.0]
    assert llm_caller._model_cooldown_until["glm-4.7-flash"] == 1020.0


@pytest.mark.asyncio
async def test_retry_after_is_clamped_between_15_and_60(monkeypatch):
    class Fake429(Exception):
        def __init__(self, retry_after):
            super().__init__("429")
            self.status_code = 429
            self.response = types.SimpleNamespace(headers={"Retry-After": retry_after})

    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)

    attempts = {"n": 0}

    async def factory_low():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise Fake429("5")
        return "ok"

    await llm_caller._retry_on_rate_limit_for_model(factory_low, model="glm-4.7-flash")
    assert slept == [15.0]

    slept.clear()
    attempts["n"] = 0

    async def factory_high():
        attempts["n"] += 1
        if attempts["n"] == 1:
            raise Fake429("120")
        return "ok"

    await llm_caller._retry_on_rate_limit_for_model(factory_high, model="glm-4.7-flash")
    assert slept == [60.0]


@pytest.mark.asyncio
async def test_await_model_cooldown_waits_remaining(monkeypatch):
    llm_caller._model_cooldown_until["glm-4.7-flash"] = 1010.0
    monkeypatch.setattr(llm_caller.time, "monotonic", lambda: 1000.0)
    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)
    await llm_caller._await_model_cooldown("glm-4.7-flash")
    assert slept == [10.0]


@pytest.mark.asyncio
async def test_rate_limit_retry_releases_semaphore_during_sleep(monkeypatch):
    import asyncio

    model_sem = asyncio.Semaphore(1)
    global_sem = asyncio.Semaphore(6)
    monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)
    monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)

    attempts = {"n": 0}

    class Fake429(Exception):
        status_code = 429

    async def factory():
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise Fake429()
        return "ok"

    observed = []

    async def fake_sleep(seconds):
        observed.append(("model", model_sem._value))
        observed.append(("global", global_sem._value))

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(llm_caller.time, "monotonic", lambda: 1000.0)

    result = await llm_caller._invoke_adapter_with_retry(factory, model="glm-4.7-flash")
    assert result == "ok"
    assert observed == [("model", 1), ("global", 6)]


@pytest.mark.asyncio
async def test_stream_429_waits_retry_after_seconds(monkeypatch):
    import httpx

    request = httpx.Request("POST", "https://example.test/v1/chat")
    response = httpx.Response(429, headers={"Retry-After": "20"}, request=request)
    attempts = {"n": 0}

    async def factory():
        attempts["n"] += 1
        if attempts["n"] == 1:
            async def gen():
                raise httpx.HTTPStatusError("429", request=request, response=response)
                yield "x"
            return gen()
        async def ok():
            yield "ok\n"
        return ok()

    slept = []

    async def fake_sleep(seconds):
        slept.append(seconds)

    monkeypatch.setattr(llm_caller.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(llm_caller.time, "monotonic", lambda: 1000.0)

    result = await llm_caller._invoke_adapter_with_retry(
        factory, model="glm-4.7-flash", stream=True, skip_semaphore=True
    )
    chunks = [chunk async for chunk in result]
    assert chunks == ["ok\n"]
    assert slept == [20.0]


@pytest.mark.asyncio
async def test_zhipu_stream_raises_http_status_error_with_retry_after(monkeypatch):
    import httpx
    from app.utils.aicloud.adapters.zhipu import ZhipuAdapter
    from app.utils.aicloud.providers import ModelProvider, ProviderConfig

    request = httpx.Request("POST", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
    response = httpx.Response(429, headers={"Retry-After": "20"}, request=request)

    class FakeStream:
        async def __aenter__(self):
            return response

        async def __aexit__(self, *args):
            return False

    class FakeClient:
        def stream(self, *args, **kwargs):
            return FakeStream()

    async def fake_get_http_client():
        return FakeClient()

    monkeypatch.setattr("app.utils.aicloud.adapters.zhipu.get_http_client", fake_get_http_client)

    adapter = ZhipuAdapter(ProviderConfig(provider=ModelProvider.ZHIPU, api_key="test-key"))
    agen = await adapter.call_llm(model="glm-4.7-flash", prompt="hi", stream=True)
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        async for _ in agen:
            pass
    assert exc_info.value.response.status_code == 429
    assert llm_caller._retry_after_seconds(exc_info.value) == 20.0
