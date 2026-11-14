"""partial_response_store 回退字典裁剪、过期与删除异常分支补测。"""

import time

import pytest

from app.utils import partial_response_store as store


@pytest.fixture(autouse=True)
def _reset():
    store._fallback.clear()
    store.set_store_client(None)
    yield
    store._fallback.clear()
    store.set_store_client(None)


class _Redis:
    def __init__(self, delete_error=None, get_error=None):
        self.store = {}
        self.delete_error = delete_error
        self.get_error = get_error

    def setex(self, key, ttl, value):
        self.store[key] = value

    def get(self, key):
        if self.get_error:
            raise self.get_error
        return self.store.get(key)

    def delete(self, key):
        if self.delete_error:
            raise self.delete_error
        self.store.pop(key, None)


def test_get_client_without_redis_module(monkeypatch):
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "redis":
            raise ImportError("no redis")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setattr(store, "_client", None)
    assert store._get_client() is None


def test_get_client_uses_default_url_when_setting_empty(monkeypatch):
    seen = {}

    class FakeRedisModule:
        class Redis:
            @staticmethod
            def from_url(url, **kwargs):
                seen["url"] = url
                seen["kwargs"] = kwargs
                return "client"

    import sys

    monkeypatch.setitem(sys.modules, "redis", FakeRedisModule)
    monkeypatch.setattr(store, "_client", None)
    monkeypatch.setattr(store.settings, "REDIS_URL", "", raising=False)

    assert store._get_client() == "client"
    assert seen["url"] == store._DEFAULT_REDIS_URL


def test_get_client_caches(monkeypatch):
    import sys

    calls = []

    class FakeRedisModule:
        class Redis:
            @staticmethod
            def from_url(url, **kwargs):
                calls.append(url)
                return object()

    monkeypatch.setitem(sys.modules, "redis", FakeRedisModule)
    monkeypatch.setattr(store, "_client", None)
    monkeypatch.setattr(store.settings, "REDIS_URL", "redis://x/1", raising=False)

    first = store._get_client()
    second = store._get_client()
    assert first is second
    assert len(calls) == 1


def test_prune_removes_expired_and_oldest():
    now = time.time()
    store._fallback.clear()
    store._fallback["expired"] = ({"a": 1}, now - 1)
    for index in range(store._FALLBACK_MAX_ENTRIES + 2):
        store._fallback[f"k{index}"] = ({"i": index}, now + index)

    store._prune_fallback(now)

    assert "expired" not in store._fallback
    assert len(store._fallback) == store._FALLBACK_MAX_ENTRIES
    assert "k0" not in store._fallback


def test_fallback_get_expired_entry():
    resume_id = "gone"
    store._fallback[resume_id] = ({"x": 1}, time.time() - 1)
    assert store._fallback_get(resume_id) is None
    assert resume_id not in store._fallback


def test_fallback_pop_missing_and_expired():
    assert store._fallback_pop("missing") is None
    store._fallback["old"] = ({"x": 1}, time.time() - 1)
    assert store._fallback_pop("old") is None
    assert "old" not in store._fallback


def test_get_falls_back_when_redis_get_raises():
    store.set_store_client(_Redis(get_error=RuntimeError("down")))
    store._fallback["r"] = ({"v": 1}, time.time() + 60)
    assert store.get_partial_response("r") == {"v": 1}


def test_pop_logs_delete_failure_but_returns_payload():
    client = _Redis(delete_error=RuntimeError("delete failed"))
    client.store["partial_response:r"] = '{"v": 2}'
    store.set_store_client(client)

    assert store.pop_partial_response("r") == {"v": 2}


def test_pop_falls_back_when_redis_get_raises():
    store.set_store_client(_Redis(get_error=RuntimeError("down")))
    store._fallback["r"] = ({"v": 3}, time.time() + 60)
    assert store.pop_partial_response("r") == {"v": 3}
    assert "r" not in store._fallback


def test_fallback_paths_when_no_redis_client(monkeypatch):
    monkeypatch.setattr(store, "_get_client", lambda: None)

    assert store.save_partial_response("r", {"v": 4}, 60) is True
    assert store.get_partial_response("r") == {"v": 4}
    assert store.pop_partial_response("r") == {"v": 4}
    assert store.get_partial_response("r") is None


def test_pop_falls_back_when_redis_missing_key():
    store.set_store_client(_Redis())
    store._fallback["r"] = ({"v": 5}, time.time() + 60)

    assert store.pop_partial_response("r") == {"v": 5}
