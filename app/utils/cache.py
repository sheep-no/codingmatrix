"""
Redis 缓存管理层
支持 Redis 缓存、内存缓存降级、键前缀管理、TTL 配置、模式失效
"""
import json
import hashlib
import logging
from typing import Any, Optional, List, Union
from datetime import datetime, timedelta
from collections import OrderedDict
import asyncio

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


class SerializationError(Exception):
    """序列化/反序列化错误"""
    pass


class MemoryCache:
    """
    内存缓存（LRU 实现，Redis 不可用时降级使用）
    """

    def __init__(self, max_size: int = 1000, default_ttl: int = 3600):
        self._cache: OrderedDict = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        async with self._lock:
            if key in self._cache:
                data, expire_at = self._cache[key]
                if expire_at is None or datetime.now() < expire_at:
                    self._cache.move_to_end(key)
                    return data
                else:
                    del self._cache[key]
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        async with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            elif len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)

            ttl = ttl if ttl is not None else self._default_ttl
            expire_at = datetime.now() + timedelta(seconds=ttl)
            self._cache[key] = (value, expire_at)

    async def delete(self, key: str) -> bool:
        async with self._lock:
            return self._cache.pop(key, None) is not None

    async def invalidate_pattern(self, pattern: str) -> int:
        async with self._lock:
            keys_to_delete = [k for k in self._cache if self._match_pattern(k, pattern)]
            for k in keys_to_delete:
                del self._cache[k]
            return len(keys_to_delete)

    async def clear(self) -> None:
        async with self._lock:
            self._cache.clear()

    @staticmethod
    def _match_pattern(key: str, pattern: str) -> bool:
        import fnmatch
        return fnmatch.fnmatch(key, pattern)


class RedisCache:
    """
    Redis 缓存实现
    支持序列化/反序列化、TTL、模式失效
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379/0",
        key_prefix: str = "app",
        default_ttl: int = 3600,
        max_connections: int = 20,
        socket_timeout: float = 2.0,
        socket_connect_timeout: float = 2.0,
        retry_on_timeout: bool = True,
    ):
        self._redis: Optional[aioredis.Redis] = None
        self._redis_url = redis_url
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl
        self._max_connections = max_connections
        self._socket_timeout = socket_timeout
        self._socket_connect_timeout = socket_connect_timeout
        self._retry_on_timeout = retry_on_timeout
        self._is_connected = False
        self._lock = asyncio.Lock()

    async def _ensure_connection(self) -> bool:
        if self._redis is None:
            async with self._lock:
                if self._redis is None:
                    try:
                        self._redis = aioredis.from_url(
                            self._redis_url,
                            decode_responses=True,
                            max_connections=self._max_connections,
                            socket_timeout=self._socket_timeout,
                            socket_connect_timeout=self._socket_connect_timeout,
                            retry_on_timeout=self._retry_on_timeout,
                        )
                        await self._redis.ping()
                        self._is_connected = True
                        logger.info("Redis 连接成功")
                    except Exception as e:
                        logger.error(f"Redis 连接失败: {e}")
                        self._is_connected = False
                        self._redis = None
                        return False
        return self._is_connected

    def _make_key(self, key: str) -> str:
        return f"{self._key_prefix}:{key}"

    async def get(self, key: str) -> Optional[Any]:
        if not await self._ensure_connection():
            return None
        try:
            value = await self._redis.get(self._make_key(key))
            if value is None:
                return None
            return json.loads(value)
        except json.JSONDecodeError as e:
            logger.error(f"缓存反序列化失败 key={key}: {e}")
            return None
        except Exception as e:
            logger.error(f"Redis GET 失败 key={key}: {e}")
            self._is_connected = False
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        if not await self._ensure_connection():
            return False
        try:
            ttl = ttl if ttl is not None else self._default_ttl
            serialized = json.dumps(value, ensure_ascii=False, default=str)
            await self._redis.setex(self._make_key(key), ttl, serialized)
            return True
        except (TypeError, ValueError) as e:
            logger.error(f"缓存序列化失败 key={key}: {e}")
            return False
        except Exception as e:
            logger.error(f"Redis SET 失败 key={key}: {e}")
            self._is_connected = False
            return False

    async def delete(self, key: str) -> bool:
        if not await self._ensure_connection():
            return False
        try:
            result = await self._redis.delete(self._make_key(key))
            return result > 0
        except Exception as e:
            logger.error(f"Redis DELETE 失败 key={key}: {e}")
            self._is_connected = False
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        if not await self._ensure_connection():
            return 0
        try:
            full_pattern = self._make_key(pattern)
            keys = []
            async for key in self._redis.scan_iter(match=full_pattern, count=100):
                keys.append(key)
            if keys:
                return await self._redis.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Redis 模式失效失败 pattern={pattern}: {e}")
            self._is_connected = False
            return 0

    async def clear(self) -> bool:
        if not await self._ensure_connection():
            return False
        try:
            await self._redis.flushdb()
            return True
        except Exception as e:
            logger.error(f"Redis 清空失败: {e}")
            self._is_connected = False
            return False

    async def close(self) -> None:
        if self._redis:
            try:
                await self._redis.close()
            except Exception as e:
                logger.error(f"Redis 关闭失败: {e}")
            finally:
                self._redis = None
                self._is_connected = False


class RedisCacheManager:
    """
    缓存管理器 - 统一接口
    优先使用 Redis，不可用时自动降级到内存缓存
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        key_prefix: str = "app",
        default_ttl: int = 3600,
        memory_max_size: int = 1000,
    ):
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl
        self._use_redis = redis_url is not None and REDIS_AVAILABLE
        self._redis_cache: Optional[RedisCache] = None
        self._memory_cache = MemoryCache(max_size=memory_max_size, default_ttl=default_ttl)

        if self._use_redis:
            self._redis_cache = RedisCache(
                redis_url=redis_url,
                key_prefix=key_prefix,
                default_ttl=default_ttl,
            )

    @property
    def backend(self) -> str:
        return "redis" if (self._use_redis and self._redis_cache and self._redis_cache._is_connected) else "memory"

    async def get(self, key: str) -> Optional[Any]:
        if self._use_redis and self._redis_cache:
            value = await self._redis_cache.get(key)
            if value is not None:
                return value
            if self._redis_cache._is_connected:
                return None
        return await self._memory_cache.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        success = False
        if self._use_redis and self._redis_cache:
            success = await self._redis_cache.set(key, value, ttl)
        if not success:
            await self._memory_cache.set(key, value, ttl)
        return True

    async def delete(self, key: str) -> bool:
        deleted = False
        if self._use_redis and self._redis_cache:
            deleted = await self._redis_cache.delete(key)
        mem_deleted = await self._memory_cache.delete(key)
        return deleted or mem_deleted

    async def invalidate_pattern(self, pattern: str) -> int:
        count = 0
        if self._use_redis and self._redis_cache:
            count = await self._redis_cache.invalidate_pattern(pattern)
        mem_count = await self._memory_cache.invalidate_pattern(pattern)
        return count + mem_count

    async def clear(self) -> None:
        if self._use_redis and self._redis_cache:
            await self._redis_cache.clear()
        await self._memory_cache.clear()

    async def close(self) -> None:
        if self._redis_cache:
            await self._redis_cache.close()


_cache_manager: Optional[RedisCacheManager] = None
_init_lock = asyncio.Lock()


async def get_cache_manager(
    redis_url: Optional[str] = None,
    key_prefix: str = "app",
    default_ttl: int = 3600,
) -> RedisCacheManager:
    global _cache_manager
    if _cache_manager is None:
        async with _init_lock:
            if _cache_manager is None:
                _cache_manager = RedisCacheManager(
                    redis_url=redis_url,
                    key_prefix=key_prefix,
                    default_ttl=default_ttl,
                )
    return _cache_manager


async def get_cache(redis_url: Optional[str] = None):
    return await get_cache_manager(redis_url=redis_url)


async def invalidate_user_cache(user_id: Union[int, str]) -> None:
    cache = await get_cache_manager()
    await cache.invalidate_pattern(f"user:{user_id}:*")
    await cache.invalidate_pattern(f"profile:{user_id}:*")


def cached(ttl: int = 3600, prefix: str = ""):
    """
    缓存装饰器（向后兼容）
    用法:
        @cached(ttl=300, prefix="file")
        async def get_file_content(file_path: str):
            ...
    """
    import hashlib
    from functools import wraps

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key_parts = [prefix, func.__name__]
            for arg in args:
                cache_key_parts.append(str(arg))
            for k, v in sorted(kwargs.items()):
                cache_key_parts.append(f"{k}={v}")
            cache_key = hashlib.md5(":".join(cache_key_parts).encode()).hexdigest()

            cache = await get_cache_manager()
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                return cached_value

            result = await func(*args, **kwargs)

            await cache.set(cache_key, result, ttl)
            return result
        return wrapper
    return decorator
