"""performance_monitor 非 HTTP scope、异常、统计裁剪与装饰器补测。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.utils import performance_monitor as module
from app.utils.performance_monitor import (
    PerformanceMonitorMiddleware,
    setup_performance_monitoring,
    track_performance,
)


async def _call(middleware, scope, app_error=None, messages=None):
    messages = messages or []

    async def app(scope, receive, send):
        if app_error:
            raise app_error
        for message in messages:
            await send(message)

    middleware.app = app
    await middleware(scope, AsyncMock(), AsyncMock())


async def test_non_http_scope_passes_through():
    seen = []
    middleware = PerformanceMonitorMiddleware(None)

    async def app(scope, receive, send):
        seen.append(scope["type"])

    middleware.app = app
    await middleware({"type": "lifespan"}, AsyncMock(), AsyncMock())
    assert seen == ["lifespan"]


async def test_exception_logged_and_reraised(monkeypatch):
    errors = []
    monkeypatch.setattr(module.logger, "error", lambda msg: errors.append(msg))
    middleware = PerformanceMonitorMiddleware(None)

    with pytest.raises(RuntimeError):
        await _call(middleware, {"type": "http", "method": "GET", "path": "/x"},
                    app_error=RuntimeError("boom"))
    assert any("请求异常" in msg for msg in errors)


async def test_records_metric_and_warns_slow_request(monkeypatch):
    warnings = []
    monkeypatch.setattr(module.logger, "warning", lambda msg: warnings.append(msg))
    middleware = PerformanceMonitorMiddleware(None, slow_threshold=0)

    sent = []

    async def send(message):
        sent.append(message)

    middleware.app = _ok_app()
    scope = {"type": "http", "method": "GET", "path": "/p"}

    async def app(scope, receive, send):
        await send({
            "type": "http.response.start",
            "status": 503,
            "headers": [(b"x-request-id", b"old"), (b"x-process-time", b"old")],
        })

    middleware.app = app
    await middleware(scope, AsyncMock(), send)

    headers = dict(sent[0]["headers"])
    assert b"x-request-id" in headers
    assert b"x-process-time" in headers
    assert middleware.stats["GET:<unmatched>"]["count"] == 1
    assert middleware.stats["GET:<unmatched>"]["error_count"] == 1
    assert any("慢请求" in msg for msg in warnings)


async def _ok_app():
    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    return app


async def test_prometheus_import_failure_is_ignored(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "app.services.prometheus_metrics", None)
    middleware = PerformanceMonitorMiddleware(None)

    async def app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})

    middleware.app = app
    await middleware({"type": "http", "method": "GET", "path": "/x"}, AsyncMock(), AsyncMock())
    assert middleware.stats["GET:<unmatched>"]["count"] == 1


async def test_record_metric_prunes_oldest_when_over_limit():
    middleware = PerformanceMonitorMiddleware(None)
    middleware.stats = {
        f"GET:/{i}": {"count": i, "total_time": 0.0, "min_time": 0.0,
                      "max_time": 0.0, "error_count": 0}
        for i in range(1001)
    }

    await middleware._record_metric("/new", "GET", 0.1, 200)

    assert "GET:/new" in middleware.stats
    assert "GET:/0" not in middleware.stats


async def test_get_stats_skips_zero_count_and_handles_infinite_min():
    middleware = PerformanceMonitorMiddleware(None)
    middleware.stats = {
        "zero": {"count": 0, "total_time": 0.0, "min_time": float("inf"),
                 "max_time": 0.0, "error_count": 0},
        "ok": {"count": 2, "total_time": 1.0, "min_time": float("inf"),
               "max_time": 0.8, "error_count": 1},
    }

    stats = await middleware.get_stats()

    assert "zero" not in stats
    assert stats["ok"] == {
        "count": 2, "avg_time": 0.5, "min_time": 0,
        "max_time": 0.8, "error_rate": 50.0,
    }


def test_setup_performance_monitoring_registers_middleware():
    app = SimpleNamespace(add_middleware=lambda *a, **k: None)
    setup_performance_monitoring(app, slow_threshold=2)


async def test_track_performance_logs_slow(monkeypatch):
    times = iter([100.0, 102.0])
    monkeypatch.setattr(module.time, "time", lambda: next(times))
    warnings = []
    monkeypatch.setattr(module.logger, "warning", lambda msg: warnings.append(msg))

    @track_performance
    async def slow():
        return "done"

    assert await slow() == "done"
    assert any("慢函数" in msg for msg in warnings)


async def test_track_performance_fast_no_warning(monkeypatch):
    times = iter([100.0, 100.5])
    monkeypatch.setattr(module.time, "time", lambda: next(times))
    warnings = []
    monkeypatch.setattr(module.logger, "warning", lambda msg: warnings.append(msg))

    @track_performance
    async def fast():
        return 1

    assert await fast() == 1
    assert warnings == []


async def test_record_metric_small_stats_no_prune():
    middleware = PerformanceMonitorMiddleware(None)
    await middleware._record_metric("/a", "GET", 0.1, 200)
    await middleware._record_metric("/b", "GET", 0.2, 200)
    assert set(middleware.stats) == {"GET:/a", "GET:/b"}
