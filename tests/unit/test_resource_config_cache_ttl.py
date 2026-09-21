"""资源配置缓存必须有界陈旧。

缓存是进程内的，多 worker 部署下 set_config 只更新当前进程；没有 TTL 时
其他 worker 会一直返回旧配置（功能开关不生效）直到重启。
"""

import importlib
import time

import pytest

rc_module = importlib.import_module("app.services.resource_config")


class _FakeSession:
    async def __aenter__(self):
        return object()

    async def __aexit__(self, *exc_info):
        return False


@pytest.fixture()
def service(monkeypatch):
    monkeypatch.setattr(rc_module.ResourceConfigService, "_instance", None)
    return rc_module.ResourceConfigService()


def test_cache_freshness_uses_ttl(service):
    assert service._cache_is_fresh() is False

    service._cache_loaded = True
    service._cache_loaded_at = time.monotonic()
    assert service._cache_is_fresh() is True

    service._cache_loaded_at = time.monotonic() - service._CACHE_TTL_SECONDS - 1
    assert service._cache_is_fresh() is False


def test_invalidate_resets_freshness(service):
    service._cache_loaded = True
    service._cache_loaded_at = time.monotonic()
    service._config_cache["k"] = "v"

    service.invalidate_cache()

    assert service._cache_is_fresh() is False
    assert service._config_cache == {}


async def test_get_config_reloads_after_ttl(service, monkeypatch):
    calls = []

    async def fake_ensure(db):
        calls.append(1)
        service._config_cache["k"] = f"v{len(calls)}"
        service._cache_loaded = True
        service._cache_loaded_at = time.monotonic()

    monkeypatch.setattr(service, "_ensure_cache_loaded", fake_ensure)
    monkeypatch.setattr(rc_module, "async_session", lambda: _FakeSession())

    assert await service.get_config("k") == "v1"
    # TTL 内命中缓存，不重载
    assert await service.get_config("k") == "v1"
    assert len(calls) == 1

    service._cache_loaded_at = time.monotonic() - service._CACHE_TTL_SECONDS - 1
    assert await service.get_config("k") == "v2"
    assert len(calls) == 2
