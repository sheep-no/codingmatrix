"""用户 Key 与缓存 Redis 隔离后的迁移回退必须无感。"""

import json
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from app.services import apikey_manager as module
from app.services.apikey_manager import APIKeyManager, KeyMetadata


class FakeRedis:
    def __init__(self):
        self.data = {}
        self.expires = {}

    def get(self, key):
        return self.data.get(key)

    def set(self, key, value):
        self.data[key] = value
        self.expires.pop(key, None)

    def setex(self, key, ttl, value):
        self.set(key, value)
        self.expires[key] = ttl

    def ttl(self, key):
        if key not in self.data:
            return -2
        return self.expires.get(key, -1)

    def delete(self, *keys):
        for key in keys:
            self.data.pop(key, None)
            self.expires.pop(key, None)

    def smembers(self, key):
        return set(self.data.get(key, set()))

    def sadd(self, key, *values):
        members = self.data.setdefault(key, set())
        members.update(values)
        return len(values)

    def srem(self, key, *values):
        members = self.data.get(key, set())
        for value in values:
            members.discard(value)

    def scan(self, cursor, match=None, count=None):
        prefix = (match or "").rstrip("*")
        return 0, [key for key in self.data if key.startswith(prefix)]

    def expire(self, key, ttl):
        self.expires[key] = ttl


def _metadata(token: str, provider: str = "openai") -> KeyMetadata:
    now = datetime.now(timezone.utc)
    return KeyMetadata(
        token=token,
        provider=provider,
        remark="",
        status="verified",
        created_at=now.isoformat(),
        expires_at=(now + timedelta(days=7)).isoformat(),
        ttl_seconds=604800,
        enabled=True,
    )


def _seed_legacy(user_id: str, token: str):
    legacy = FakeRedis()
    legacy.sadd(f"apikey_index:{user_id}", token)
    legacy.expire(f"apikey_index:{user_id}", 604800 + 86400)
    legacy.setex(f"apikey:{user_id}:{token}", 604800, "sk-plain")
    legacy.setex(
        f"apikey_meta:{user_id}:{token}", 604800, json.dumps(asdict(_metadata(token)))
    )
    legacy.setex(f"apikey:token:{token}", 604800 + 86400, user_id)
    return legacy


def test_list_keys_migrates_legacy_index_and_metadata():
    user_id, token = "u1", "t" * 32
    legacy = _seed_legacy(user_id, token)
    primary = FakeRedis()
    manager = APIKeyManager(primary, legacy_redis_client=legacy)

    keys = manager.list_keys(user_id)

    assert [meta.token for meta in keys] == [token]
    assert token in primary.smembers(f"apikey_index:{user_id}")
    assert primary.get(f"apikey_meta:{user_id}:{token}") is not None


def test_get_key_reads_legacy_then_backfills_with_remaining_ttl():
    user_id, token = "u2", "u" * 32
    legacy = _seed_legacy(user_id, token)
    primary = FakeRedis()
    manager = APIKeyManager(primary, legacy_redis_client=legacy)

    assert manager.get_key(user_id, token) == "sk-plain"
    assert primary.get(f"apikey:{user_id}:{token}") == "sk-plain"
    assert primary.ttl(f"apikey:{user_id}:{token}") == 604800


def test_permanent_legacy_key_backfills_without_expiry():
    user_id, token = "u5", "x" * 32
    legacy = _seed_legacy(user_id, token)
    legacy.expires.pop(f"apikey:{user_id}:{token}")
    primary = FakeRedis()
    manager = APIKeyManager(primary, legacy_redis_client=legacy)

    assert manager.get_key(user_id, token) == "sk-plain"
    assert primary.ttl(f"apikey:{user_id}:{token}") == -1


def test_backfill_failure_still_returns_legacy_value(monkeypatch):
    user_id, token = "u6", "y" * 32
    legacy = _seed_legacy(user_id, token)
    primary = FakeRedis()
    manager = APIKeyManager(primary, legacy_redis_client=legacy)

    def explode(key):
        raise RuntimeError("ttl unavailable")

    monkeypatch.setattr(legacy, "ttl", explode)

    assert manager.get_key(user_id, token) == "sk-plain"
    assert primary.get(f"apikey:{user_id}:{token}") is None


def test_zero_ttl_legacy_value_is_returned_without_backfill():
    user_id, token = "u8", "q" * 32
    legacy = _seed_legacy(user_id, token)
    legacy.expire(f"apikey:{user_id}:{token}", 0)
    primary = FakeRedis()
    manager = APIKeyManager(primary, legacy_redis_client=legacy)

    assert manager.get_key(user_id, token) == "sk-plain"
    assert primary.get(f"apikey:{user_id}:{token}") is None


def test_delete_removes_legacy_copy_to_prevent_resurrection():
    user_id, token = "u3", "v" * 32
    legacy = _seed_legacy(user_id, token)
    primary = FakeRedis()
    manager = APIKeyManager(primary, legacy_redis_client=legacy)

    manager.delete_key(user_id, token)

    assert manager.get_key(user_id, token) is None
    assert manager.get_metadata(user_id, token) is None


def test_get_all_enabled_keys_scans_legacy_instance():
    user_id, token = "u4", "w" * 32
    legacy = _seed_legacy(user_id, token)
    manager = APIKeyManager(FakeRedis(), legacy_redis_client=legacy)

    assert manager.get_all_enabled_keys() == [(user_id, token, "openai", "sk-plain")]


def test_list_keys_keeps_permanent_legacy_index_and_dedupes_scan():
    user_id, token = "u7", "z" * 32
    legacy = _seed_legacy(user_id, token)
    legacy.expires.pop(f"apikey_index:{user_id}")
    primary = FakeRedis()
    primary.sadd(f"apikey_index:{user_id}", token)
    primary.expire(f"apikey_index:{user_id}", 604800)
    manager = APIKeyManager(primary, legacy_redis_client=legacy)

    assert [meta.token for meta in manager.list_keys(user_id)] == [token]
    assert [item[1] for item in manager.get_all_enabled_keys()] == [token]
    assert primary.ttl(f"apikey_index:{user_id}") == 604800


def test_default_client_prefers_dedicated_url_and_builds_legacy_fallback(monkeypatch):
    created = []
    monkeypatch.setattr(module.redis, "from_url", lambda url, **kwargs: created.append(url) or Mock())
    monkeypatch.setattr(module.settings, "APIKEY_REDIS_URL", "redis://keys:6379/0", raising=False)
    monkeypatch.setattr(module.settings, "REDIS_URL", "redis://cache:6379/0", raising=False)

    module._build_default_redis_client()
    module._build_legacy_redis_client()

    assert created == ["redis://keys:6379/0", "redis://cache:6379/0"]
