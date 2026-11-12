"""Branch coverage for app/utils/cache.py."""

from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils import cache as cache_module
from app.utils.cache import (
    MemoryCache,
    RedisCache,
    RedisCacheManager,
    cached,
    get_cache_manager,
    invalidate_user_cache,
)


@pytest.fixture(autouse=True)
def _reset_global_cache(monkeypatch):
    monkeypatch.setattr(cache_module, "_cache_manager", None)
    yield
    cache_module._cache_manager = None


class TestMemoryCache:
    @pytest.mark.asyncio
    async def test_get_missing(self):
        assert await MemoryCache().get("k") is None

    @pytest.mark.asyncio
    async def test_get_expired_entry_deleted(self):
        cache = MemoryCache()
        cache._cache["k"] = ("v", datetime.now() - timedelta(seconds=1))
        assert await cache.get("k") is None
        assert "k" not in cache._cache

    @pytest.mark.asyncio
    async def test_get_no_expiry(self):
        cache = MemoryCache()
        cache._cache["k"] = ("v", None)
        assert await cache.get("k") == "v"

    @pytest.mark.asyncio
    async def test_set_existing_moves_to_end(self):
        cache = MemoryCache(max_size=2)
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.set("a", 3)
        assert list(cache._cache) == ["b", "a"]

    @pytest.mark.asyncio
    async def test_set_evicts_oldest_when_full(self):
        cache = MemoryCache(max_size=2)
        await cache.set("a", 1)
        await cache.set("b", 2)
        await cache.set("c", 3)
        assert "a" not in cache._cache
        assert list(cache._cache) == ["b", "c"]

    @pytest.mark.asyncio
    async def test_delete_and_clear(self):
        cache = MemoryCache()
        await cache.set("a", 1)
        assert await cache.delete("a") is True
        assert await cache.delete("a") is False
        await cache.set("b", 2)
        await cache.clear()
        assert cache._cache == {}

    @pytest.mark.asyncio
    async def test_invalidate_pattern(self):
        cache = MemoryCache()
        await cache.set("user:1", 1)
        await cache.set("user:2", 2)
        await cache.set("other", 3)
        assert await cache.invalidate_pattern("user:*") == 2
        assert "other" in cache._cache


def _fake_redis(**overrides):
    values = {
        "get": AsyncMock(return_value='{"a": 1}'),
        "setex": AsyncMock(),
        "delete": AsyncMock(return_value=2),
        "close": AsyncMock(),
        "ping": AsyncMock(),
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class _ScanIter:
    def __init__(self, keys):
        self._keys = list(keys)

    def __aiter__(self):
        self._it = iter(self._keys)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class TestRedisCache:
    @pytest.mark.asyncio
    async def test_connect_success(self, monkeypatch):
        fake = _fake_redis()
        monkeypatch.setattr(cache_module.aioredis, "from_url", MagicMock(return_value=fake))
        cache = RedisCache()
        assert await cache._ensure_connection() is True
        assert cache._is_connected is True

    @pytest.mark.asyncio
    async def test_connect_failure_sets_cooldown(self, monkeypatch):
        monkeypatch.setattr(
            cache_module.aioredis, "from_url", MagicMock(side_effect=RuntimeError("down"))
        )
        cache = RedisCache()
        assert await cache._ensure_connection() is False
        assert cache._next_connect_attempt > 0

    @pytest.mark.asyncio
    async def test_connect_skipped_during_cooldown(self, monkeypatch):
        monkeypatch.setattr(
            cache_module.aioredis, "from_url", MagicMock(side_effect=AssertionError("no"))
        )
        cache = RedisCache()
        cache._next_connect_attempt = float("inf")
        assert await cache._ensure_connection() is False

    @pytest.mark.asyncio
    async def test_connect_returns_false_when_already_disconnected(self):
        cache = RedisCache()
        cache._redis = object()
        assert await cache._ensure_connection() is False

    @pytest.mark.asyncio
    async def test_get_success_and_miss(self, monkeypatch):
        fake = _fake_redis()
        cache = RedisCache()
        cache._redis = fake
        cache._is_connected = True
        assert await cache.get("k") == {"a": 1}

        fake.get = AsyncMock(return_value=None)
        assert await cache.get("k") is None

    @pytest.mark.asyncio
    async def test_get_disconnected_returns_none(self):
        cache = RedisCache()
        cache._ensure_connection = AsyncMock(return_value=False)
        assert await cache.get("k") is None

    @pytest.mark.asyncio
    async def test_get_json_error(self):
        cache = RedisCache()
        cache._redis = _fake_redis(get=AsyncMock(return_value="not json"))
        cache._is_connected = True
        assert await cache.get("k") is None

    @pytest.mark.asyncio
    async def test_get_generic_error_disconnects(self):
        cache = RedisCache()
        cache._redis = _fake_redis(get=AsyncMock(side_effect=RuntimeError("boom")))
        cache._is_connected = True
        assert await cache.get("k") is None
        assert cache._is_connected is False

    @pytest.mark.asyncio
    async def test_set_success_and_disconnected(self, monkeypatch):
        cache = RedisCache(default_ttl=10)
        cache._redis = _fake_redis()
        cache._is_connected = True
        assert await cache.set("k", {"a": 1}) is True
        cache._redis.setex.assert_awaited_once()

        disconnected = RedisCache()
        disconnected._ensure_connection = AsyncMock(return_value=False)
        assert await disconnected.set("k", {"a": 1}) is False

    @pytest.mark.asyncio
    async def test_set_serialization_error(self):
        cache = RedisCache()
        cache._redis = _fake_redis()
        cache._is_connected = True
        assert await cache.set("k", object()) is True  # default=str handles it
        assert await cache.set("k", {"a": 1}, ttl=5) is True

    @pytest.mark.asyncio
    async def test_set_type_error(self, monkeypatch):
        cache = RedisCache()
        cache._redis = _fake_redis()
        cache._is_connected = True
        monkeypatch.setattr(cache_module.json, "dumps", MagicMock(side_effect=TypeError("bad")))
        assert await cache.set("k", 1) is False

    @pytest.mark.asyncio
    async def test_set_value_error(self, monkeypatch):
        cache = RedisCache()
        cache._redis = _fake_redis()
        cache._is_connected = True
        monkeypatch.setattr(cache_module.json, "dumps", MagicMock(side_effect=ValueError("bad")))
        assert await cache.set("k", 1) is False

    @pytest.mark.asyncio
    async def test_set_generic_error_disconnects(self):
        cache = RedisCache()
        cache._redis = _fake_redis(setex=AsyncMock(side_effect=RuntimeError("boom")))
        cache._is_connected = True
        assert await cache.set("k", 1) is False
        assert cache._is_connected is False

    @pytest.mark.asyncio
    async def test_delete_success_miss_and_error(self):
        cache = RedisCache()
        cache._redis = _fake_redis()
        cache._is_connected = True
        assert await cache.delete("k") is True

        cache._redis.delete = AsyncMock(return_value=0)
        assert await cache.delete("k") is False

        disconnected = RedisCache()
        disconnected._ensure_connection = AsyncMock(return_value=False)
        assert await disconnected.delete("k") is False

        cache._redis.delete = AsyncMock(side_effect=RuntimeError("boom"))
        assert await cache.delete("k") is False
        assert cache._is_connected is False

    @pytest.mark.asyncio
    async def test_invalidate_pattern_with_keys(self):
        cache = RedisCache()
        cache._redis = _fake_redis()
        cache._redis.scan_iter = MagicMock(return_value=_ScanIter(["a:k1", "a:k2"]))
        cache._is_connected = True
        assert await cache.invalidate_pattern("k*") == 2

    @pytest.mark.asyncio
    async def test_invalidate_pattern_without_keys(self):
        cache = RedisCache()
        cache._redis = _fake_redis()
        cache._redis.scan_iter = MagicMock(return_value=_ScanIter([]))
        cache._is_connected = True
        assert await cache.invalidate_pattern("k*") == 0

    @pytest.mark.asyncio
    async def test_invalidate_pattern_disconnected_and_error(self):
        disconnected = RedisCache()
        disconnected._ensure_connection = AsyncMock(return_value=False)
        assert await disconnected.invalidate_pattern("*") == 0

        cache = RedisCache()
        cache._redis = _fake_redis()
        cache._redis.scan_iter = MagicMock(side_effect=RuntimeError("boom"))
        cache._is_connected = True
        assert await cache.invalidate_pattern("*") == 0
        assert cache._is_connected is False

    @pytest.mark.asyncio
    async def test_clear_and_close(self):
        cache = RedisCache()
        cache.invalidate_pattern = AsyncMock(return_value=3)
        assert await cache.clear() is True
        cache.invalidate_pattern.assert_awaited_once_with("*")

        cache._redis = _fake_redis()
        cache._is_connected = True
        await cache.close()
        assert cache._redis is None
        assert cache._is_connected is False

        broken = RedisCache()
        broken._redis = _fake_redis(close=AsyncMock(side_effect=RuntimeError("x")))
        await broken.close()
        assert broken._redis is None

    @pytest.mark.asyncio
    async def test_close_when_no_redis(self):
        cache = RedisCache()
        await cache.close()
        assert cache._redis is None


class TestRedisCacheManager:
    def test_backend_memory_by_default(self):
        assert RedisCacheManager().backend == "memory"

    @pytest.mark.asyncio
    async def test_backend_redis_when_connected(self, monkeypatch):
        manager = RedisCacheManager(redis_url="redis://localhost")
        manager._redis_cache._is_connected = True
        assert manager.backend == "redis"

    @pytest.mark.asyncio
    async def test_memory_only_operations(self):
        manager = RedisCacheManager()
        assert await manager.set("k", 1) is True
        assert await manager.get("k") == 1
        assert await manager.get("missing") is None
        assert await manager.delete("k") is True
        assert await manager.delete("k") is False
        await manager.set("user:1", 1)
        assert await manager.invalidate_pattern("user:*") == 1
        await manager.clear()
        await manager.close()

    @pytest.mark.asyncio
    async def test_redis_hit(self, monkeypatch):
        manager = RedisCacheManager(redis_url="redis://localhost")
        redis_cache = manager._redis_cache
        redis_cache.get = AsyncMock(return_value={"a": 1})
        assert await manager.get("k") == {"a": 1}

    @pytest.mark.asyncio
    async def test_redis_miss_memory_hit_backfills(self):
        manager = RedisCacheManager(redis_url="redis://localhost")
        redis_cache = manager._redis_cache
        redis_cache.get = AsyncMock(return_value=None)
        redis_cache.set = AsyncMock(return_value=True)
        await manager._memory_cache.set("k", "mem")

        assert await manager.get("k") == "mem"
        redis_cache.set.assert_awaited_once_with("k", "mem")

    @pytest.mark.asyncio
    async def test_redis_miss_everything(self):
        manager = RedisCacheManager(redis_url="redis://localhost")
        manager._redis_cache.get = AsyncMock(return_value=None)
        assert await manager.get("k") is None

    @pytest.mark.asyncio
    async def test_set_redis_success_clears_memory(self):
        manager = RedisCacheManager(redis_url="redis://localhost")
        manager._redis_cache.set = AsyncMock(return_value=True)
        await manager._memory_cache.set("k", "old")
        assert await manager.set("k", "new") is True
        assert await manager._memory_cache.get("k") is None

    @pytest.mark.asyncio
    async def test_set_redis_failure_writes_memory(self):
        manager = RedisCacheManager(redis_url="redis://localhost")
        manager._redis_cache.set = AsyncMock(return_value=False)
        assert await manager.set("k", "new") is True
        assert await manager._memory_cache.get("k") == "new"

    @pytest.mark.asyncio
    async def test_delete_redis_paths(self):
        manager = RedisCacheManager(redis_url="redis://localhost")
        manager._redis_cache.delete = AsyncMock(return_value=False)
        await manager._memory_cache.set("k", 1)
        assert await manager.delete("k") is True

        manager._redis_cache.delete = AsyncMock(return_value=True)
        assert await manager.delete("other") is True

        manager._redis_cache.delete = AsyncMock(return_value=False)
        assert await manager.delete("gone") is False

    @pytest.mark.asyncio
    async def test_invalidate_and_clear_redis_paths(self):
        manager = RedisCacheManager(redis_url="redis://localhost")
        manager._redis_cache.invalidate_pattern = AsyncMock(return_value=2)
        await manager._memory_cache.set("user:1", 1)
        assert await manager.invalidate_pattern("user:*") == 3

        manager._redis_cache.clear = AsyncMock()
        manager._redis_cache.close = AsyncMock()
        await manager.clear()
        await manager.close()
        manager._redis_cache.clear.assert_awaited_once()
        manager._redis_cache.close.assert_awaited_once()


class TestGetCacheManager:
    @pytest.mark.asyncio
    async def test_singleton_created_once(self):
        first = await get_cache_manager()
        second = await get_cache_manager()
        assert first is second

    @pytest.mark.asyncio
    async def test_get_cache_delegates(self):
        cache = await cache_module.get_cache()
        assert isinstance(cache, RedisCacheManager)

    @pytest.mark.asyncio
    async def test_invalidate_user_cache(self, monkeypatch):
        manager = RedisCacheManager()
        manager.invalidate_pattern = AsyncMock(return_value=2)
        monkeypatch.setattr(cache_module, "_cache_manager", manager)

        assert await invalidate_user_cache(7) == 4
        assert manager.invalidate_pattern.await_count == 2


class TestCachedDecorator:
    @pytest.mark.asyncio
    async def test_caches_result(self, monkeypatch):
        manager = RedisCacheManager()
        monkeypatch.setattr(cache_module, "_cache_manager", manager)
        calls = []

        @cached(ttl=10, prefix="p")
        async def fn(x, flag=False):
            calls.append(x)
            return None

        assert await fn(1, flag=True) is None
        assert await fn(1, flag=True) is None
        assert calls == [1]

    @pytest.mark.asyncio
    async def test_cache_hit_returns_value(self, monkeypatch):
        manager = RedisCacheManager()
        monkeypatch.setattr(cache_module, "_cache_manager", manager)
        await manager.set("p:x", {"_cached_value": "hit"})

        @cached(prefix="p")
        async def fn():
            raise AssertionError("should not run")

        import hashlib

        digest = hashlib.md5("p:fn".encode()).hexdigest()
        await manager.set(f"p:{digest}", {"_cached_value": "hit"})
        assert await fn() == "hit"


class _RaceLock:
    """Lock stub that simulates another coroutine initializing state first."""

    def __init__(self, on_enter):
        self._on_enter = on_enter

    async def __aenter__(self):
        self._on_enter()
        return self

    async def __aexit__(self, *_exc):
        return False


@pytest.mark.asyncio
async def test_ensure_connection_double_check_race(monkeypatch):
    cache = RedisCache()
    monkeypatch.setattr(
        cache,
        "_lock",
        _RaceLock(lambda: setattr(cache, "_redis", object())),
    )
    cache._is_connected = True
    assert await cache._ensure_connection() is True


@pytest.mark.asyncio
async def test_get_cache_manager_double_check_race(monkeypatch):
    existing = RedisCacheManager()
    lock = _RaceLock(lambda: setattr(cache_module, "_cache_manager", existing))
    monkeypatch.setattr(cache_module, "_init_lock", lock)
    monkeypatch.setattr(cache_module, "_cache_manager", None)

    assert await get_cache_manager() is existing
