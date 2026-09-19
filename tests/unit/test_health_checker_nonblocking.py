"""健康检查不得阻塞事件循环，且各检查项应并行执行。

Celery 的 control.inspect 是同步网络 RPC，直接在 async 函数里调用会阻塞
事件循环，被 /health /ready 探针高频放大。
"""

import asyncio
import sys
import time
import types

import pytest

from app.services.health_checker import (
    HealthChecker,
    HealthCheckResult,
    get_health_checker,
)


class _BlockingInspect:
    """模拟会同步阻塞的 Celery inspect"""

    def __init__(self, delay: float):
        self._delay = delay

    def stats(self):
        time.sleep(self._delay)
        return {"worker-1": {"pool": {"max-concurrency": 4}}}

    def active(self):
        time.sleep(self._delay)
        return {"worker-1": [{"id": "task-1"}]}


class _FakeControl:
    def __init__(self, delay: float):
        self._delay = delay

    def inspect(self):
        return _BlockingInspect(self._delay)


class _FakeCeleryApp:
    def __init__(self, delay: float):
        self.control = _FakeControl(delay)


@pytest.fixture
def fake_celery_module():
    """注入假的 app.celery_app，避免真实导入与 Redis 依赖"""
    fake = _FakeCeleryApp(delay=0.3)
    module = types.ModuleType("app.celery_app")
    module.celery_app = fake
    original = sys.modules.get("app.celery_app")
    sys.modules["app.celery_app"] = module
    yield fake
    if original is None:
        sys.modules.pop("app.celery_app", None)
    else:
        sys.modules["app.celery_app"] = original


@pytest.mark.asyncio
async def test_check_celery_does_not_block_event_loop(fake_celery_module):
    checker = HealthChecker()
    ticks = 0

    async def heartbeat():
        nonlocal ticks
        while True:
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(heartbeat())
    try:
        result = await checker.check_celery()
    finally:
        task.cancel()

    assert result.status == "healthy"
    assert result.details["workers"] == 1
    assert result.details["active_tasks"] == 1
    # 同步实现会让心跳在检查期间完全停摆；线程化后检查耗时内应持续心跳
    assert ticks >= 5


@pytest.mark.asyncio
async def test_check_all_runs_checks_in_parallel(monkeypatch):
    checker = HealthChecker()
    delay = 0.2

    async def slow_result(*args, **kwargs):
        await asyncio.sleep(delay)
        return HealthCheckResult(status="healthy", details={})

    for name in (
        "check_api",
        "check_database",
        "check_redis",
        "check_celery",
        "check_websocket",
        "check_system",
    ):
        monkeypatch.setattr(checker, name, slow_result)

    start = time.perf_counter()
    result = await checker.check_all()
    elapsed = time.perf_counter() - start

    assert set(result["checks"]) == {
        "api", "database", "redis", "celery", "websocket", "system"
    }
    # 串行执行需 6*delay=1.2s，并行应接近单次 delay
    assert elapsed < delay * 3


@pytest.mark.asyncio
async def test_check_ready_runs_checks_in_parallel(monkeypatch):
    checker = HealthChecker()
    delay = 0.2

    async def slow_result(*args, **kwargs):
        await asyncio.sleep(delay)
        return HealthCheckResult(status="healthy", details={})

    for name in ("check_database", "check_redis", "check_system"):
        monkeypatch.setattr(checker, name, slow_result)

    start = time.perf_counter()
    result = await checker.check_ready()
    elapsed = time.perf_counter() - start

    assert result["status"] == "ready"
    assert set(result["checks"]) == {"database", "redis", "system"}
    # 串行执行需 3*delay=0.6s，并行应接近单次 delay
    assert elapsed < delay * 2.5


@pytest.mark.asyncio
async def test_check_websocket_uses_public_max_connections(monkeypatch):
    """check_websocket 不应触碰 ws_manager 私有属性。"""
    from app.services import websocket_manager

    class _StubManager:
        def get_connection_count(self):
            return 2

        @property
        def max_connections(self):
            return 11

    monkeypatch.setattr(websocket_manager, "get_ws_manager", lambda: _StubManager())

    result = await HealthChecker().check_websocket()

    assert result.status == "healthy"
    assert result.details == {"current": 2, "max": 11, "available": 9}


def test_get_health_checker_returns_singleton():
    assert get_health_checker() is get_health_checker()
