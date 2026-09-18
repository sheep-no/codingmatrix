"""llm_caller 回归测试

覆盖已建档缺陷：
- LCL2/LCL3 流式 fallback 复用 primary 的用户 Key/URL，跨供应商必然失败
- LCL4 信号量日志访问 asyncio.Semaphore 私有属性 `_value`
- LCL5 用户适配器缓存按插入序 FIFO 淘汰，命中不刷新
"""

import asyncio

import pytest

from app.utils.aicloud import llm_caller


async def test_semaphore_acquire_does_not_access_private_value(monkeypatch):
    """LCL4：信号量对象无需暴露 `_value` 即可获取/释放。"""

    class _Sem:
        def __init__(self):
            self.count = 1

        async def acquire(self):
            self.count -= 1

        def release(self):
            self.count += 1

    global_sem = _Sem()
    model_sem = _Sem()
    monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: global_sem)
    monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: model_sem)

    lease = llm_caller._LLMSemaphoreLease()
    await lease.acquire("glm-4.7-flash", skip=False)

    assert lease.global_acquired is True
    assert lease.model_acquired is True
    assert global_sem.count == 0
    assert model_sem.count == 0

    lease.release()
    assert global_sem.count == 1
    assert model_sem.count == 1


async def test_user_adapter_cache_evicts_least_recently_used(monkeypatch):
    """LCL5：命中刷新顺序，超限淘汰最久未使用而非最早插入。"""
    from app.utils.aicloud.providers import ModelProvider, ProviderConfig

    monkeypatch.setattr(llm_caller, "_adapter_cache_lock", asyncio.Lock())
    monkeypatch.setattr(llm_caller, "_USER_ADAPTER_CACHE_MAX", 2)
    llm_caller._user_adapter_cache.clear()
    provider = ModelProvider.SILICONFLOW

    def cfg(key: str) -> ProviderConfig:
        return ProviderConfig(provider=provider, api_key=key)

    adapter_a = await llm_caller.get_adapter(provider, cfg("key-a"))
    await llm_caller.get_adapter(provider, cfg("key-b"))
    assert await llm_caller.get_adapter(provider, cfg("key-a")) is adapter_a
    adapter_c = await llm_caller.get_adapter(provider, cfg("key-c"))

    cache = llm_caller._user_adapter_cache
    key_a = llm_caller._make_user_cache_key(provider, "key-a")
    key_b = llm_caller._make_user_cache_key(provider, "key-b")
    key_c = llm_caller._make_user_cache_key(provider, "key-c")

    assert len(cache) == 2
    assert cache.get(key_a) is adapter_a
    assert cache.get(key_c) is adapter_c
    assert key_b not in cache
    cache.clear()


async def test_stream_fallback_does_not_reuse_primary_user_config(monkeypatch):
    """LCL2/LCL3：跨供应商流式 fallback 使用平台默认配置。"""
    from app.utils.aicloud.providers import ModelProvider

    primary = ModelProvider.SILICONFLOW
    fallback = ModelProvider.DEEPSEEK

    monkeypatch.setattr(
        llm_caller, "_get_user_api_key_from_token", lambda token: "sk-user"
    )

    class _Router:
        def route(self, model):
            return primary

        def get_fallback_providers(self, provider, model):
            return [fallback]

    monkeypatch.setattr(
        llm_caller.ProviderRouter,
        "get_instance",
        classmethod(lambda cls, registry=None: _Router()),
    )
    monkeypatch.setattr("app.agent.llm_client.get_global_semaphore", lambda: None)
    monkeypatch.setattr("app.agent.llm_client.get_model_semaphore", lambda model: None)

    class _PrimaryAdapter:
        provider = primary
        api_key = "sk-user"
        timeout = 0

        async def call_llm(self, **kwargs):
            async def _gen():
                raise RuntimeError("primary stream failed")
                yield ""  # pragma: no cover

            return _gen()

    class _FallbackAdapter:
        provider = fallback
        api_key = "sk-platform"
        timeout = 0

        async def call_llm(self, **kwargs):
            async def _gen():
                yield "data: ok\n"

            return _gen()

    calls = []

    async def fake_get_adapter(provider, config=None):
        calls.append((provider, config))
        return _PrimaryAdapter() if provider == primary else _FallbackAdapter()

    monkeypatch.setattr(llm_caller, "get_adapter", fake_get_adapter)

    result = await llm_caller.call_llm(
        model="demo-model",
        prompt="hi",
        stream=True,
        api_key_token="x" * 40,
    )
    chunks = [chunk async for chunk in result]

    assert chunks == ["data: ok\n"]
    assert calls[0][0] == primary
    assert calls[0][1] is not None, "primary 应使用用户 Key 配置"
    assert calls[1] == (fallback, None), "fallback 不得复用 primary 的用户配置"
