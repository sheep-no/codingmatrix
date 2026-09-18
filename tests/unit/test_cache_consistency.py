"""缓存层 P2 缺陷回归。
"""
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.utils.cache import RedisCacheManager


class _RecoveredRedis:
    """模拟 Redis 恢复连接但目标 key 不存在（降级期写的是 memory）。"""

    _is_connected = True

    async def get(self, key):
        return None

    async def set(self, key, value, ttl=None):
        return True

    async def delete(self, key):
        return False

    async def invalidate_pattern(self, pattern):
        return 0

    async def clear(self):
        return None

    async def close(self):
        return None


class _MemoryManager:
    """记录写入的极简缓存管理器，用于断言 cache_response 是否落缓存。"""

    def __init__(self):
        self.store = {}

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl=None):
        self.store[key] = value
        return True

    async def invalidate_pattern(self, pattern):
        return 0


class TestRedisFailoverConsistency:
    @pytest.mark.asyncio
    async def test_memory_value_survives_redis_recovery(self):
        manager = RedisCacheManager(redis_url=None)
        # 降级期：Redis 不可用，写入落 memory
        manager._use_redis = True
        await manager.set("session:1", {"role": "admin"}, 60)
        assert manager.backend == "memory"

        # Redis 恢复连接，但该 key 不在 Redis 中
        manager._redis_cache = _RecoveredRedis()

        assert await manager.get("session:1") == {"role": "admin"}


class TestCacheKeyParameterCoverage:
    def test_dict_argument_is_part_of_key(self):
        from app.utils.cache_decorator import _generate_cache_key

        key_a = _generate_cache_key("p", "f", (), {"payload": {"a": 1}})
        key_b = _generate_cache_key("p", "f", (), {"payload": {"a": 2}})
        assert key_a != key_b

    def test_pydantic_body_named_request_is_part_of_key(self):
        from app.utils.cache_decorator import _generate_cache_key

        class HistoryRequest(BaseModel):
            prompt_keyword: str = ""
            limit: int = 20

        token = {"sub": "7"}
        key_a = _generate_cache_key(
            "history", "get_history", (), {"request": HistoryRequest(prompt_keyword="a"), "token": token}
        )
        key_b = _generate_cache_key(
            "history", "get_history", (), {"request": HistoryRequest(prompt_keyword="b"), "token": token}
        )
        assert key_a != key_b
        # 同参数同用户必须稳定同键
        assert key_a == _generate_cache_key(
            "history", "get_history", (), {"request": HistoryRequest(prompt_keyword="a"), "token": token}
        )
        # 仍按用户隔离
        assert key_a != _generate_cache_key(
            "history", "get_history", (), {"request": HistoryRequest(prompt_keyword="a"), "token": {"sub": "8"}}
        )

    def test_fastapi_request_object_does_not_destabilize_key(self):
        from starlette.requests import Request

        from app.utils.cache_decorator import _generate_cache_key

        scope = {"type": "http", "method": "GET", "path": "/x", "query_string": b"", "headers": []}
        key_a = _generate_cache_key("p", "f", (), {"request": Request(scope), "token": {"sub": "1"}})
        key_b = _generate_cache_key("p", "f", (), {"request": Request(scope), "token": {"sub": "1"}})
        assert key_a == key_b


class TestResponseObjectCaching:
    @pytest.mark.asyncio
    async def test_raw_response_is_not_written_to_cache(self):
        from app.utils.cache_decorator import cache_response

        manager = _MemoryManager()
        calls = {"count": 0}

        @cache_response(ttl=60, key_prefix="profile")
        async def handler():
            calls["count"] += 1
            return JSONResponse({"count": calls["count"]})

        with patch(
            "app.utils.cache_decorator.get_cache_manager",
            AsyncMock(return_value=manager),
        ):
            await handler()
            await handler()

        # Response 对象无法被 Redis 后端可靠序列化，跳过缓存以避免命中后返回字符串
        assert manager.store == {}
        assert calls["count"] == 2


class TestCacheInvalidation:
    @pytest.mark.asyncio
    async def test_prefix_invalidation_matches_cached_keys(self):
        from app.utils.cache_decorator import _generate_cache_key

        manager = RedisCacheManager(redis_url=None)
        key = _generate_cache_key("history", "get_history", (), {"token": {"sub": "7"}})
        await manager.set(key, {"items": []}, 60)
        assert await manager.get(key) == {"items": []}

        removed = await manager.invalidate_pattern("history:*")

        assert removed == 1
        assert await manager.get(key) is None

    @pytest.mark.asyncio
    async def test_invalidate_cache_runs_on_exception(self, monkeypatch):
        from app.utils import cache_decorator

        patterns = []

        class _Cache:
            async def invalidate_pattern(self, pattern):
                patterns.append(pattern)
                return 0

        async def fake_manager():
            return _Cache()

        monkeypatch.setattr(cache_decorator, "get_cache_manager", fake_manager)

        @cache_decorator.invalidate_cache(key_prefix="profile")
        async def mutate():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError):
            await mutate()

        assert patterns == ["profile:*"]


class TestCachedDecoratorNone:
    @pytest.mark.asyncio
    async def test_none_result_is_cached_not_recomputed(self, monkeypatch):
        from app.utils import cache as cache_mod

        manager = cache_mod.RedisCacheManager(redis_url=None)

        async def fake_manager():
            return manager

        monkeypatch.setattr(cache_mod, "get_cache_manager", fake_manager)
        calls = {"count": 0}

        @cache_mod.cached(ttl=60, prefix="none")
        async def compute():
            calls["count"] += 1
            return None

        assert await compute() is None
        assert await compute() is None
        assert calls["count"] == 1


class TestRedisResilience:
    @pytest.mark.asyncio
    async def test_connection_failure_enters_cooldown(self, monkeypatch):
        from app.utils import cache as cache_mod

        attempts = {"count": 0}

        def boom(*args, **kwargs):
            attempts["count"] += 1
            raise ConnectionError("redis down")

        monkeypatch.setattr(cache_mod.aioredis, "from_url", boom)
        cache = cache_mod.RedisCache(redis_url="redis://127.0.0.1:1/0")

        results = [await cache._ensure_connection() for _ in range(3)]

        assert results == [False, False, False]
        assert attempts["count"] == 1

    @pytest.mark.asyncio
    async def test_clear_scopes_to_key_prefix(self):
        from app.utils import cache as cache_mod

        class _FakeRedis:
            def __init__(self):
                self.keys = {"app:a", "app:b", "other:c"}
                self.flushed = False

            async def scan_iter(self, match, count=100):
                import fnmatch

                for key in list(self.keys):
                    if fnmatch.fnmatch(key, match):
                        yield key

            async def delete(self, *keys):
                for key in keys:
                    self.keys.discard(key)
                return len(keys)

            async def flushdb(self):
                self.flushed = True

        cache = cache_mod.RedisCache(redis_url="redis://localhost:6379/0")
        cache._redis = _FakeRedis()
        cache._is_connected = True

        await cache.clear()

        assert cache._redis.keys == {"other:c"}
        assert cache._redis.flushed is False
