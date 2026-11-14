"""token_denylist Redis 降级与异常路径补测。"""

import sys
import types

import pytest

from app.utils import token_denylist


class _BrokenRedis:
    async def setex(self, *args, **kwargs):
        raise RuntimeError("write failed")

    async def exists(self, *args, **kwargs):
        raise RuntimeError("read failed")


@pytest.fixture(autouse=True)
def _reset_client():
    token_denylist.set_denylist_client(None)
    yield
    token_denylist.set_denylist_client(None)


def test_get_client_returns_none_without_redis(monkeypatch):
    token_denylist.set_denylist_client(None)
    monkeypatch.setitem(sys.modules, "redis.asyncio", None)

    assert token_denylist._get_client() is None


def test_get_client_uses_default_url_when_setting_blank(monkeypatch):
    captured = {}

    class _Module:
        @staticmethod
        def from_url(url, **kwargs):
            captured["url"] = url
            captured["kwargs"] = kwargs
            return "client"

    fake_redis = types.ModuleType("redis")
    fake_redis.asyncio = _Module
    token_denylist.set_denylist_client(None)
    monkeypatch.setitem(sys.modules, "redis", fake_redis)
    monkeypatch.setitem(sys.modules, "redis.asyncio", _Module)
    monkeypatch.setattr(token_denylist.settings, "REDIS_URL", "   ")

    assert token_denylist._get_client() == "client"
    assert captured["url"] == token_denylist._DEFAULT_REDIS_URL
    assert captured["kwargs"]["decode_responses"] is True


def test_get_client_reuses_cached_client():
    token_denylist.set_denylist_client("cached")
    assert token_denylist._get_client() == "cached"


async def test_revoke_returns_false_without_client(monkeypatch):
    monkeypatch.setattr(token_denylist, "_get_client", lambda: None)
    assert await token_denylist.revoke_token("token", 60) is False


async def test_revoke_swallows_redis_errors():
    token_denylist.set_denylist_client(_BrokenRedis())
    assert await token_denylist.revoke_token("token", 60) is False


async def test_revoke_ignores_missing_token():
    token_denylist.set_denylist_client(_BrokenRedis())
    assert await token_denylist.revoke_token(None, 60) is False


async def test_revoke_success():
    class _Client:
        async def setex(self, key, ttl, value):
            return True

    token_denylist.set_denylist_client(_Client())
    assert await token_denylist.revoke_token("token", 60) is True


async def test_is_revoked_false_without_client(monkeypatch):
    monkeypatch.setattr(token_denylist, "_get_client", lambda: None)
    assert await token_denylist.is_token_revoked("token") is False


async def test_is_revoked_false_for_blank_token():
    assert await token_denylist.is_token_revoked("") is False


async def test_is_revoked_fail_open_on_redis_error():
    token_denylist.set_denylist_client(_BrokenRedis())
    assert await token_denylist.is_token_revoked("token") is False


async def test_is_revoked_true_when_present():
    class _Client:
        async def exists(self, key):
            return 1

    token_denylist.set_denylist_client(_Client())
    assert await token_denylist.is_token_revoked("token") is True


def test_token_key_is_sha256_prefixed():
    token_denylist.set_denylist_client(None)
    assert token_denylist._token_key("abc").startswith(token_denylist._KEY_PREFIX)
