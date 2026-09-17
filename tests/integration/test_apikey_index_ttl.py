"""用户 API Key 索引的 TTL 不应被后续短效 Key 缩短。

索引集合记录用户已有哪些 token，list_keys/管理面依赖它。若每次存 Key
都用新 Key 的 TTL 覆盖索引 TTL，先存的长效 Key 会随索引过期而从管理面
消失，但 Key 本体仍在 Redis。
"""

import pytest
import redis

from app.services.apikey_manager import APIKeyManager, TTL_OPTIONS

REDIS_HOST = "127.0.0.1"
REDIS_PORT = 6379
REDIS_DB = 15


def _redis_available() -> bool:
    try:
        redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, socket_connect_timeout=2
        ).ping()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _redis_available(), reason="需要本地 Redis 服务"
)


@pytest.fixture
def redis_client():
    client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    client.flushdb()
    yield client
    client.flushdb()


@pytest.fixture
def manager(redis_client):
    return APIKeyManager(redis_client=redis_client, max_keys_per_user=10)


def _index_ttl(redis_client, user_id):
    return redis_client.ttl(f"apikey_index:{user_id}")


def test_short_lived_key_does_not_shrink_index_ttl(manager, redis_client):
    long_ttl = TTL_OPTIONS["never"]
    manager.store_key("user-a", "openai", "sk-long-lived-key", "never")
    ttl_after_long = _index_ttl(redis_client, "user-a")

    manager.store_key("user-a", "deepseek", "sk-short-lived-key", "1h")
    ttl_after_short = _index_ttl(redis_client, "user-a")

    # 索引寿命仍覆盖长效 Key（+1 天），不会掉到 1h + 1 天
    assert ttl_after_short >= long_ttl
    assert ttl_after_short >= ttl_after_long - 5


def test_long_lived_key_extends_index_ttl(manager, redis_client):
    manager.store_key("user-b", "openai", "sk-short-lived-key", "1h")
    ttl_after_short = _index_ttl(redis_client, "user-b")

    manager.store_key("user-b", "deepseek", "sk-long-lived-key", "never")
    ttl_after_long = _index_ttl(redis_client, "user-b")

    assert ttl_after_long > ttl_after_short
    assert ttl_after_long >= TTL_OPTIONS["never"]


def test_index_survives_shorter_key_and_still_lists_all(manager, redis_client):
    manager.store_key("user-c", "openai", "sk-long-lived-key", "never")
    manager.store_key("user-c", "deepseek", "sk-short-lived-key", "1h")

    keys = manager.list_keys("user-c")

    assert len(keys) == 2
    assert _index_ttl(redis_client, "user-c") >= TTL_OPTIONS["never"]


def test_index_uses_largest_ttl_across_many_keys(manager, redis_client):
    for ttl in ("1h", "24h", "7d", "never"):
        manager.store_key("user-d", "openai", f"sk-key-{ttl}", ttl)

    assert _index_ttl(redis_client, "user-d") >= TTL_OPTIONS["never"]
    assert len(manager.list_keys("user-d")) == 4
