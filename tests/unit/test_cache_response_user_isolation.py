"""响应缓存必须按用户隔离。

身份参数（token/current_user/user_id）被排除在普通参数遍历之外，
若不单独纳入缓存键，不同用户会命中同一条缓存并读到彼此的数据。
"""

import pytest

from app.utils import cache_decorator


class _Body:
    def __init__(self, **payload):
        self._payload = payload

    def model_dump(self):
        return self._payload


class _FakeCache:
    def __init__(self, store):
        self.store = store

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl):
        self.store[key] = value

    async def invalidate_pattern(self, pattern):
        return 0


@pytest.fixture
def cached_endpoint(monkeypatch):
    store = {}

    async def fake_cache_manager():
        return _FakeCache(store)

    monkeypatch.setattr(cache_decorator, "get_cache_manager", fake_cache_manager)
    calls = []

    @cache_decorator.cache_response(ttl=60, key_prefix="history")
    async def endpoint(request, db=None, token=None):
        calls.append(token["sub"])
        return {"owner": token["sub"], "limit": request.model_dump()["limit"]}

    return endpoint, calls


def test_cache_key_differs_by_token_subject():
    base = {
        "func_name": "get_history",
        "args": (_Body(limit=10),),
        "request": None,
    }

    alice = cache_decorator._generate_cache_key(
        "history", base["func_name"], base["args"], {"token": {"sub": "alice"}}
    )
    bob = cache_decorator._generate_cache_key(
        "history", base["func_name"], base["args"], {"token": {"sub": "bob"}}
    )
    alice_again = cache_decorator._generate_cache_key(
        "history", base["func_name"], base["args"], {"token": {"sub": "alice"}}
    )

    assert alice != bob
    assert alice == alice_again


@pytest.mark.asyncio
async def test_each_user_reads_own_cached_response(cached_endpoint):
    endpoint, calls = cached_endpoint

    alice = await endpoint(_Body(limit=10), db=object(), token={"sub": "alice"})
    bob = await endpoint(_Body(limit=10), db=object(), token={"sub": "bob"})
    alice_again = await endpoint(_Body(limit=10), db=object(), token={"sub": "alice"})

    assert alice == alice_again == {"owner": "alice", "limit": 10}
    assert bob == {"owner": "bob", "limit": 10}
    # alice 的第二次请求命中缓存，未再执行被装饰函数
    assert calls == ["alice", "bob"]


@pytest.mark.asyncio
async def test_anonymous_endpoint_still_shares_cache(monkeypatch):
    store = {}

    async def fake_cache_manager():
        return _FakeCache(store)

    monkeypatch.setattr(cache_decorator, "get_cache_manager", fake_cache_manager)
    calls = []

    @cache_decorator.cache_response(ttl=60, key_prefix="public")
    async def endpoint(request, db=None):
        calls.append(1)
        return {"ok": True}

    await endpoint(_Body(limit=1), db=object())
    await endpoint(_Body(limit=1), db=object())

    assert calls == [1]
