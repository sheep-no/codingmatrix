"""RL6 附：限流存储必须带 socket 超时，Redis 不可达时快速回退内存。

`_create_limiter` 以 Redis 为限流存储并开启 `in_memory_fallback_enabled`，但
该回退只在存储抛异常时触发；未设 socket 超时时 Redis 卡住会让 `incr` 永久
阻塞，回退逻辑形同虚设。
"""

from app.utils import rate_limiter
from limits.storage import MemoryStorage


def _connection_kwargs(limiter):
    return limiter._storage.storage.connection_pool.connection_kwargs


def test_redis_storage_sets_socket_timeouts(monkeypatch):
    monkeypatch.setattr(
        rate_limiter.settings, "REDIS_URL", "redis://127.0.0.1:6379/0"
    )

    limiter = rate_limiter._create_limiter()

    kwargs = _connection_kwargs(limiter)
    assert kwargs["socket_timeout"] == rate_limiter.REDIS_SOCKET_TIMEOUT_SECONDS
    assert kwargs["socket_connect_timeout"] == rate_limiter.REDIS_SOCKET_TIMEOUT_SECONDS


def test_without_redis_url_uses_memory_storage(monkeypatch):
    monkeypatch.setattr(rate_limiter.settings, "REDIS_URL", "")

    limiter = rate_limiter._create_limiter()

    assert isinstance(limiter._storage, MemoryStorage)
