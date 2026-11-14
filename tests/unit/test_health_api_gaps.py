"""健康检查 API 剩余分支补测。"""

from unittest.mock import AsyncMock

import pytest

from app.api.v1 import health as health_api


@pytest.mark.asyncio
async def test_health_check_reports_unhealthy_when_dependency_fails(monkeypatch):
    monkeypatch.setattr(health_api, "_check_db_quick", AsyncMock(return_value=False))
    monkeypatch.setattr(health_api, "_check_redis_quick", AsyncMock(return_value=True))

    payload = await health_api.health_check()

    assert payload["status"] == "unhealthy"
    assert payload["version"] == health_api.APP_VERSION


@pytest.mark.asyncio
async def test_health_check_swallows_probe_exceptions(monkeypatch):
    monkeypatch.setattr(
        health_api, "_check_db_quick", AsyncMock(side_effect=RuntimeError("db down"))
    )

    payload = await health_api.health_check()

    assert payload["status"] == "unhealthy"


@pytest.mark.asyncio
async def test_readiness_check_marks_not_ready_when_database_down(monkeypatch):
    monkeypatch.setattr(health_api, "_check_db_quick", AsyncMock(return_value=False))
    monkeypatch.setattr(health_api, "_check_redis_quick", AsyncMock(return_value=True))

    payload = await health_api.readiness_check()

    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"]["status"] == "disconnected"
    assert payload["checks"]["redis"]["status"] == "connected"


@pytest.mark.asyncio
async def test_readiness_check_marks_not_ready_when_redis_down(monkeypatch):
    monkeypatch.setattr(health_api, "_check_db_quick", AsyncMock(return_value=True))
    monkeypatch.setattr(health_api, "_check_redis_quick", AsyncMock(return_value=False))

    payload = await health_api.readiness_check()

    assert payload["status"] == "not_ready"
    assert payload["checks"]["database"]["status"] == "connected"
    assert payload["checks"]["redis"]["status"] == "disconnected"


@pytest.mark.asyncio
async def test_liveness_check_returns_alive():
    payload = await health_api.liveness_check()
    assert payload["status"] == "alive"


@pytest.mark.asyncio
async def test_check_db_quick_returns_false_on_failure(monkeypatch):
    import app.db.database as db_module

    class _BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("cannot connect")

        async def __aexit__(self, *exc_info):
            return False

    monkeypatch.setattr(db_module, "async_session", lambda: _BrokenSession())

    assert await health_api._check_db_quick() is False


@pytest.mark.asyncio
async def test_check_db_quick_returns_true_on_success(monkeypatch):
    import app.db.database as db_module

    executed = []

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def execute(self, statement):
            executed.append(statement)

    monkeypatch.setattr(db_module, "async_session", lambda: _Session())

    assert await health_api._check_db_quick() is True
    assert executed


@pytest.mark.asyncio
async def test_check_redis_quick_returns_true_without_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    assert await health_api._check_redis_quick() is True


@pytest.mark.asyncio
async def test_check_redis_quick_roundtrips_value(monkeypatch):
    import app.utils.cache as cache_module

    class _Cache:
        def __init__(self):
            self.storage = {}

        async def set(self, key, value, ttl=None):
            self.storage[key] = value

        async def get(self, key):
            return self.storage.get(key)

    cache = _Cache()

    async def fake_get_cache(url):
        return cache

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(cache_module, "get_cache", fake_get_cache)

    assert await health_api._check_redis_quick() is True


@pytest.mark.asyncio
async def test_check_redis_quick_returns_false_on_failure(monkeypatch):
    import app.utils.cache as cache_module

    async def broken_get_cache(url):
        raise RuntimeError("redis down")

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    monkeypatch.setattr(cache_module, "get_cache", broken_get_cache)

    assert await health_api._check_redis_quick() is False


@pytest.mark.asyncio
async def test_detailed_health_check_delegates_to_health_checker(monkeypatch):
    monkeypatch.setattr(
        health_api.health_checker,
        "check_all",
        AsyncMock(return_value={"status": "healthy"}),
    )

    payload = await health_api.detailed_health_check(token={})

    assert payload == {"status": "healthy"}


@pytest.mark.asyncio
async def test_prometheus_metrics_renders_text(monkeypatch):
    import app.services.prometheus_metrics as metrics_module
    import app.services.websocket_manager as ws_module

    calls = {}

    class _Registry:
        def gauge(self, name, value, labels=None):
            pass

        def histogram(self, name, value, labels=None):
            pass

        def counter(self, name, labels):
            calls["gc_counter"] = (name, labels)

    class _Manager:
        def get_connection_count(self):
            return 3

    monkeypatch.setattr(metrics_module.prometheus_metrics, "_registry", _Registry())
    monkeypatch.setattr(health_api, "generate_metrics_text", lambda: "python_info 1\n")
    monkeypatch.setattr(ws_module, "get_ws_manager", lambda: _Manager())

    response = await health_api.prometheus_metrics(token={})

    assert response.body == b"python_info 1\n"
    assert response.media_type == "text/plain; charset=utf-8"
    assert calls["gc_counter"][0] == "python_gc_objects_collected"


@pytest.mark.asyncio
async def test_prometheus_metrics_reports_websocket_failure(monkeypatch):
    import app.services.prometheus_metrics as metrics_module
    import app.services.websocket_manager as ws_module

    statuses = {}

    class _Registry:
        def gauge(self, name, value, labels=None):
            pass

        def histogram(self, name, value, labels=None):
            pass

        def counter(self, name, labels):
            pass

    monkeypatch.setattr(metrics_module.prometheus_metrics, "_registry", _Registry())
    monkeypatch.setattr(health_api, "generate_metrics_text", lambda: "")
    monkeypatch.setattr(
        metrics_module.prometheus_metrics,
        "set_health_status",
        lambda name, ok: statuses.__setitem__(name, ok),
    )

    def broken_manager():
        raise RuntimeError("no websocket manager")

    monkeypatch.setattr(ws_module, "get_ws_manager", broken_manager)

    await health_api.prometheus_metrics(token={})

    assert statuses["websocket"] is False


@pytest.mark.asyncio
async def test_prometheus_metrics_without_gc_stats_skips_counter(monkeypatch):
    import gc

    import app.services.prometheus_metrics as metrics_module
    import app.services.websocket_manager as ws_module

    counters = []

    class _Registry:
        def gauge(self, name, value, labels=None):
            pass

        def histogram(self, name, value, labels=None):
            pass

        def counter(self, name, labels):
            counters.append(name)

    class _Manager:
        def get_connection_count(self):
            return 0

    monkeypatch.setattr(metrics_module.prometheus_metrics, "_registry", _Registry())
    monkeypatch.setattr(health_api, "generate_metrics_text", lambda: "")
    monkeypatch.setattr(ws_module, "get_ws_manager", lambda: _Manager())
    monkeypatch.setattr(gc, "get_stats", lambda: [])

    await health_api.prometheus_metrics(token={})

    assert counters == []


@pytest.mark.asyncio
async def test_model_health_check_returns_router_report(monkeypatch):
    import app.agent.dynamic_model_router as router_module

    class _Router:
        async def get_model_health_report(self):
            return [{"model": "gpt", "status": "healthy"}]

    async def fake_get_router():
        return _Router()

    monkeypatch.setattr(router_module, "get_dynamic_router", fake_get_router)

    payload = await health_api.model_health_check()

    assert payload["status"] == "success"
    assert payload["models"][0]["model"] == "gpt"
