"""
Redis 缓存层测试
"""
import pytest
import asyncio
from app.utils.cache import RedisCacheManager, MemoryCache, get_cache_manager, invalidate_user_cache, _cache_manager
from app.utils.cache_decorator import cache_response, invalidate_cache_by_prefix, _generate_cache_key


@pytest.fixture
def memory_cache():
 return MemoryCache(max_size=100, default_ttl=60)


@pytest.fixture
async def cache_manager():
 return RedisCacheManager(key_prefix="test", default_ttl=60)


@pytest.mark.asyncio
async def test_memory_cache_set_get(cache_manager):
 await cache_manager.set("test_key", {"data": "value"}, ttl=60)
 result = await cache_manager.get("test_key")
 assert result == {"data": "value"}


@pytest.mark.asyncio
async def test_memory_cache_delete(cache_manager):
 await cache_manager.set("to_delete", "value")
 deleted = await cache_manager.delete("to_delete")
 assert deleted is True
 result = await cache_manager.get("to_delete")
 assert result is None


@pytest.mark.asyncio
async def test_memory_cache_ttl_expiry():
 cache = MemoryCache(max_size=100, default_ttl=1)
 await cache.set("expire_key", "value", ttl=1)
 result = await cache.get("expire_key")
 assert result == "value"

 await asyncio.sleep(1.1)
 result = await cache.get("expire_key")
 assert result is None


@pytest.mark.asyncio
async def test_memory_cache_lru_eviction():
 cache = MemoryCache(max_size=3, default_ttl=60)
 await cache.set("key1", "value1")
 await cache.set("key2", "value2")
 await cache.set("key3", "value3")

 await cache.set("key4", "value4")

 result = await cache.get("key1")
 assert result is None

 result = await cache.get("key4")
 assert result == "value4"


@pytest.mark.asyncio
async def test_memory_cache_invalidate_pattern():
 cache = RedisCacheManager(key_prefix="pattern_test", default_ttl=60)
 await cache.set("user:1:profile", {"name": "Alice"})
 await cache.set("user:1:history", [1, 2, 3])
 await cache.set("user:2:profile", {"name": "Bob"})

 count = await cache.invalidate_pattern("user:1:*")
 assert count == 2

 assert await cache.get("user:1:profile") is None
 assert await cache.get("user:1:history") is None
 assert await cache.get("user:2:profile") is not None


@pytest.mark.asyncio
async def test_cache_fallback_to_memory():
 manager = RedisCacheManager(redis_url=None, key_prefix="test")
 assert manager.backend == "memory"

 await manager.set("fallback_key", "fallback_value")
 result = await manager.get("fallback_key")
 assert result == "fallback_value"


@pytest.mark.asyncio
async def test_invalid_cache_by_prefix():
 cache = RedisCacheManager(key_prefix="inv_test", default_ttl=60)
 await cache.set("history:abc123", {"items": []})
 await cache.set("history:def456", {"items": []})
 await cache.set("other:key", "value")

 count = await cache.invalidate_pattern("history:*")
 assert count >= 2

 assert await cache.get("history:abc123") is None
 assert await cache.get("history:def456") is None
 assert await cache.get("other:key") == "value"


@pytest.mark.asyncio
async def test_invalidate_user_cache_direct():
 cache = RedisCacheManager(key_prefix="user_test", default_ttl=60)
 await cache.set("user:42:profile", {"id": 42})
 await cache.set("profile:42:data", {"name": "Test"})
 await cache.set("user:99:profile", {"id": 99})

 count1 = await cache.invalidate_pattern("user:42:*")
 count2 = await cache.invalidate_pattern("profile:42:*")
 assert count1 + count2 >= 2

 assert await cache.get("user:42:profile") is None
 assert await cache.get("profile:42:data") is None
 assert await cache.get("user:99:profile") is not None


@pytest.mark.asyncio
async def test_serialization_complex_data():
 cache = RedisCacheManager(key_prefix="serial_test", default_ttl=60)
 complex_data = {
 "items": [
 {"id": 1, "title": "Test", "nested": {"a": 1, "b": [1, 2, 3]}},
 {"id": 2, "title": "Test2"}
 ],
 "total": 2,
 "meta": {"page": 1, "has_more": False}
 }
 await cache.set("complex", complex_data)
 result = await cache.get("complex")
 assert result == complex_data


@pytest.mark.asyncio
async def test_generate_cache_key():
 from unittest.mock import MagicMock
 mock_request = MagicMock()
 mock_request.url.path = "/api/v1/history"
 mock_request.query_params = {"limit": "20", "offset": "0"}

 key1 = _generate_cache_key("history", "get_history", (), {"limit": 20, "offset": 0}, mock_request)
 key2 = _generate_cache_key("history", "get_history", (), {"limit": 20, "offset": 0}, mock_request)

 assert key1 == key2

 mock_request2 = MagicMock()
 mock_request2.url.path = "/api/v1/history"
 mock_request2.query_params = {"limit": "50"}

 key3 = _generate_cache_key("history", "get_history", (), {"limit": 50}, mock_request2)
 assert key1 != key3


@pytest.mark.asyncio
async def test_cache_clear():
 cache = RedisCacheManager(key_prefix="clear_test", default_ttl=60)
 await cache.set("key1", "value1")
 await cache.set("key2", "value2")
 await cache.clear()

 assert await cache.get("key1") is None
 assert await cache.get("key2") is None


@pytest.mark.asyncio
async def test_get_cache_manager_singleton():
 manager1 = await get_cache_manager(key_prefix="singleton_test")
 manager2 = await get_cache_manager(key_prefix="different_prefix")

 assert manager1 is manager2
