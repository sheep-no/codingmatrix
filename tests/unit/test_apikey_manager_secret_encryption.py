"""AKM3：API Key 在 Redis 中不得以明文存储。"""
from unittest.mock import Mock

from app.services.apikey_manager import APIKeyManager


class _FakeRedis:
    """最小内存 Redis：够 store_key/get_key 往返。"""

    def __init__(self):
        self.values = {}
        self.eval = Mock(return_value=1)
        self.get = Mock(side_effect=self._get)
        self.setex = Mock(side_effect=self._setex)

    def _setex(self, key, _ttl, value):
        self.values[key] = value

    def _get(self, key):
        return self.values.get(key)


def test_store_key_writes_encrypted_envelope():
    redis = _FakeRedis()
    manager = APIKeyManager(redis_client=redis)

    token = manager.store_key(
        user_id="user1", provider="siliconflow", api_key="sk-plain-secret", ttl="24h"
    )

    stored = redis.values[manager._key_token("user1", token)]
    assert stored.startswith("v1:")
    assert "sk-plain-secret" not in stored
    assert manager.get_key("user1", token) == "sk-plain-secret"


def test_get_key_passes_through_legacy_plaintext():
    """兼容历史明文条目：读取时直接返回，不做解密。"""
    redis = _FakeRedis()
    manager = APIKeyManager(redis_client=redis)
    redis.values[manager._key_token("user1", "legacy-token")] = b"sk-legacy-plain"

    assert manager.get_key("user1", "legacy-token") == "sk-legacy-plain"


def test_get_key_returns_none_when_envelope_undecryptable(monkeypatch):
    """信封损坏/密钥不匹配时不泄露异常，记 error 并返回 None。"""
    logged = []
    monkeypatch.setattr(
        "app.services.apikey_manager.logger.error", lambda msg, *a, **k: logged.append(msg)
    )
    redis = _FakeRedis()
    manager = APIKeyManager(redis_client=redis)
    redis.values[manager._key_token("user1", "bad-token")] = "v1:not-a-valid-envelope"

    assert manager.get_key("user1", "bad-token") is None
    assert any("解密失败" in msg for msg in logged)
