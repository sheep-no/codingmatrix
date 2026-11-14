"""HealthChecker 各检查项分支与整体状态汇总补测。"""

import asyncio
import sys
import types
from types import SimpleNamespace

import pytest

from app.services import health_checker as module
from app.services.health_checker import (
    HealthChecker,
    HealthCheckResult,
    get_health_checker,
)


def _run(coro):
    return asyncio.run(coro)


def test_check_api_healthy():
    checker = HealthChecker()
    result = _run(checker.check_api())
    assert result.status == "healthy"
    assert result.details["version"] == checker._version


def test_check_api_unhealthy_on_clock_error(monkeypatch):
    checker = HealthChecker()

    def boom():
        raise RuntimeError("clock down")

    monkeypatch.setattr(module, "utcnow_naive", boom)

    result = _run(checker.check_api())

    assert result.status == "unhealthy"
    assert result.message == "clock down"


def test_check_database_healthy(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt):
            return None

    fake_db = types.ModuleType("app.db.database")
    fake_db.async_session = lambda: Session()
    monkeypatch.setitem(sys.modules, "app.db.database", fake_db)

    result = _run(HealthChecker().check_database())

    assert result.status == "healthy"
    assert result.message == "数据库连接正常"


def test_check_database_unhealthy(monkeypatch):
    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, stmt):
            raise OSError("db down")

    fake_db = types.ModuleType("app.db.database")
    fake_db.async_session = lambda: Session()
    monkeypatch.setitem(sys.modules, "app.db.database", fake_db)

    result = _run(HealthChecker().check_database())

    assert result.status == "unhealthy"
    assert "db down" in result.message


def test_check_redis_skipped_without_url(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    result = _run(HealthChecker().check_redis())
    assert result.status == "skipped"
    assert result.message == "Redis 未配置"


def test_check_redis_healthy(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    class Cache:
        def __init__(self):
            self.store = {}

        async def set(self, key, value, ttl=None):
            self.store[key] = value

        async def get(self, key):
            return self.store.get(key)

    fake_cache = types.ModuleType("app.utils.cache")

    async def get_cache(url):
        return Cache()

    fake_cache.get_cache = get_cache
    monkeypatch.setitem(sys.modules, "app.utils.cache", fake_cache)

    result = _run(HealthChecker().check_redis())

    assert result.status == "healthy"
    assert result.message == "Redis 连接正常"


def test_check_redis_readback_mismatch(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

    class Cache:
        async def set(self, key, value, ttl=None):
            return None

        async def get(self, key):
            return "wrong"

    fake_cache = types.ModuleType("app.utils.cache")

    async def get_cache(url):
        return Cache()

    fake_cache.get_cache = get_cache
    monkeypatch.setitem(sys.modules, "app.utils.cache", fake_cache)

    result = _run(HealthChecker().check_redis())

    assert result.status == "unhealthy"
    assert "读写验证失败" in result.message


def test_check_redis_connection_error(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    fake_cache = types.ModuleType("app.utils.cache")

    async def get_cache(url):
        raise ConnectionError("refused")

    fake_cache.get_cache = get_cache
    monkeypatch.setitem(sys.modules, "app.utils.cache", fake_cache)

    result = _run(HealthChecker().check_redis())

    assert result.status == "unhealthy"
    assert "refused" in result.message


def test_check_celery_skipped_when_app_missing(monkeypatch):
    fake = types.ModuleType("app.celery_app")
    fake.celery_app = None
    monkeypatch.setitem(sys.modules, "app.celery_app", fake)

    result = _run(HealthChecker().check_celery())

    assert result.status == "skipped"
    assert result.message == "Celery 未配置"


def test_check_celery_healthy_with_stats(monkeypatch):
    class Inspect:
        def stats(self):
            return {
                "w1": {"pool": {"max-concurrency": 4}},
                "w2": {"pool": {"max-concurrency": 2}},
            }

        def active(self):
            return {"w1": [{"id": 1}], "w2": [{"id": 2}, {"id": 3}]}

    class App:
        class control:
            @staticmethod
            def inspect():
                return Inspect()

    fake = types.ModuleType("app.celery_app")
    fake.celery_app = App()
    monkeypatch.setitem(sys.modules, "app.celery_app", fake)

    result = _run(HealthChecker().check_celery())

    assert result.status == "healthy"
    assert result.details == {"workers": 2, "active_tasks": 3, "queue_size": 6}


def test_check_celery_healthy_handles_missing_active(monkeypatch):
    class Inspect:
        def stats(self):
            return {"w1": {"pool": {"max-concurrency": 1}}}

        def active(self):
            return None

    class App:
        class control:
            @staticmethod
            def inspect():
                return Inspect()

    fake = types.ModuleType("app.celery_app")
    fake.celery_app = App()
    monkeypatch.setitem(sys.modules, "app.celery_app", fake)

    result = _run(HealthChecker().check_celery())

    assert result.details["active_tasks"] == 0


def test_check_celery_exception_degrades(monkeypatch):
    class App:
        class control:
            @staticmethod
            def inspect():
                raise RuntimeError("broker unreachable")

    fake = types.ModuleType("app.celery_app")
    fake.celery_app = App()
    monkeypatch.setitem(sys.modules, "app.celery_app", fake)

    result = _run(HealthChecker().check_celery())

    assert result.status == "degraded"
    assert "broker unreachable" in result.message


def test_check_websocket_error(monkeypatch):
    fake = types.ModuleType("app.services.websocket_manager")

    def get_ws_manager():
        raise RuntimeError("ws down")

    fake.get_ws_manager = get_ws_manager
    monkeypatch.setitem(sys.modules, "app.services.websocket_manager", fake)

    result = _run(HealthChecker().check_websocket())

    assert result.status == "unhealthy"
    assert "ws down" in result.message


@pytest.mark.parametrize("memory_percent,disk_free,expected", [
    (50, 100 * 1024 ** 3, "healthy"),
    (80, 100 * 1024 ** 3, "degraded"),
    (50, 3 * 1024 ** 3, "degraded"),
    (95, 100 * 1024 ** 3, "unhealthy"),
    (50, 512 * 1024 ** 2, "unhealthy"),
])
def test_check_system_status_matrix(monkeypatch, memory_percent, disk_free, expected):
    monkeypatch.setattr(
        module.psutil, "disk_usage",
        lambda path: SimpleNamespace(free=disk_free, percent=10.0),
    )
    monkeypatch.setattr(
        module.psutil, "virtual_memory",
        lambda: SimpleNamespace(percent=memory_percent, available=2 * 1024 ** 3),
    )

    result = _run(HealthChecker().check_system())

    assert result.status == expected
    assert result.details["disk_free_gb"] == round(disk_free / 1024 ** 3, 2)


def test_check_system_error(monkeypatch):
    def boom(path):
        raise OSError("disk gone")

    monkeypatch.setattr(module.psutil, "disk_usage", boom)

    result = _run(HealthChecker().check_system())

    assert result.status == "unhealthy"
    assert "disk gone" in result.message


def _stub(name, status, details=None, message=None):
    async def check():
        return HealthCheckResult(status=status, details=details or {}, message=message)
    return check


@pytest.mark.parametrize("statuses,overall", [
    (["healthy"] * 6, "healthy"),
    (["healthy", "skipped", "degraded", "healthy", "healthy", "healthy"], "degraded"),
    (["healthy", "unhealthy", "degraded", "healthy", "healthy", "healthy"], "unhealthy"),
])
def test_check_all_overall_status(monkeypatch, statuses, overall):
    checker = HealthChecker()
    names = ["check_api", "check_database", "check_redis",
             "check_celery", "check_websocket", "check_system"]
    for name, status in zip(names, statuses):
        monkeypatch.setattr(checker, name, _stub(name, status))

    result = _run(checker.check_all())

    assert result["status"] == overall
    assert set(result["checks"]) == {"api", "database", "redis", "celery", "websocket", "system"}
    assert result["version"] == checker._version


@pytest.mark.parametrize("db_status,redis_status,sys_status,expected", [
    ("healthy", "healthy", "healthy", "ready"),
    ("healthy", "skipped", "degraded", "ready"),
    ("unhealthy", "healthy", "healthy", "not_ready"),
    ("healthy", "unhealthy", "healthy", "not_ready"),
    ("healthy", "healthy", "unhealthy", "not_ready"),
])
def test_check_ready_matrix(monkeypatch, db_status, redis_status, sys_status, expected):
    checker = HealthChecker()
    monkeypatch.setattr(checker, "check_database", _stub("check_database", db_status))
    monkeypatch.setattr(checker, "check_redis", _stub("check_redis", redis_status))
    monkeypatch.setattr(
        checker, "check_system",
        _stub("check_system", sys_status, details={"disk_free_gb": 1}),
    )

    result = _run(checker.check_ready())

    assert result["status"] == expected
    assert result["checks"]["system"]["details"] == {"disk_free_gb": 1}


def test_check_live():
    result = _run(HealthChecker().check_live())
    assert result["status"] == "alive"
    assert "timestamp" in result


def test_get_health_checker_inner_recheck(monkeypatch):
    created = []

    class FakeChecker:
        def __init__(self):
            created.append(True)

    class RacingLock:
        def __enter__(self):
            module._health_checker_instance = FakeChecker()
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(module, "HealthChecker", FakeChecker)
    monkeypatch.setattr(module, "_health_checker_instance", None)
    monkeypatch.setattr(module, "_health_checker_lock", RacingLock())

    result = get_health_checker()

    assert isinstance(result, FakeChecker)
    assert created == [True]


def test_check_celery_no_workers_degraded(monkeypatch):
    class Inspect:
        def stats(self):
            return None

        def active(self):
            return None

    class App:
        class control:
            @staticmethod
            def inspect():
                return Inspect()

    fake = types.ModuleType("app.celery_app")
    fake.celery_app = App()
    monkeypatch.setitem(sys.modules, "app.celery_app", fake)

    result = _run(HealthChecker().check_celery())

    assert result.status == "degraded"
    assert result.details == {"workers": 0, "active_tasks": 0, "queue_size": 0}


def test_check_websocket_healthy_with_stub_manager(monkeypatch):
    class Manager:
        def get_connection_count(self):
            return 3

        @property
        def max_connections(self):
            return 10

    fake = types.ModuleType("app.services.websocket_manager")
    fake.get_ws_manager = lambda: Manager()
    monkeypatch.setitem(sys.modules, "app.services.websocket_manager", fake)

    result = _run(HealthChecker().check_websocket())

    assert result.status == "healthy"
    assert result.details == {"current": 3, "max": 10, "available": 7}


def test_get_health_checker_creates_inside_lock(monkeypatch):
    created = []

    class FakeChecker:
        def __init__(self):
            created.append(True)

    class Lock:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(module, "HealthChecker", FakeChecker)
    monkeypatch.setattr(module, "_health_checker_instance", None)
    monkeypatch.setattr(module, "_health_checker_lock", Lock())

    result = get_health_checker()

    assert isinstance(result, FakeChecker)
    assert created == [True]


def test_get_health_checker_returns_existing_instance(monkeypatch):
    sentinel = HealthChecker()
    monkeypatch.setattr(module, "_health_checker_instance", sentinel)
    assert get_health_checker() is sentinel
