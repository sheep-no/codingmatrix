"""SystemLoadMonitor 快照采集与负载判定测试。"""

import asyncio

import pytest

import app.utils.system_load as sl
from app.utils.system_load import SystemLoadMonitor, SystemLoadSnapshot


def _snapshot(**overrides):
    defaults = dict(
        timestamp=1.0,
        active_requests=0,
        is_drain_mode=False,
        model_queue_depths={},
        rate_limit_stats={},
        system_resources={"cpu": 0.1, "memory": 0.1, "disk": 0.1},
    )
    defaults.update(overrides)
    return SystemLoadSnapshot(**defaults)


class TestSnapshot:
    @pytest.mark.asyncio
    async def test_collects_all_sections(self, monkeypatch):
        monitor = SystemLoadMonitor()
        monitor.shutdown_manager = type("M", (), {"is_draining": True})()

        async def active():
            return 4

        async def queues():
            return {"gpt-4": 2}

        async def rates():
            return {"enabled": True}

        async def resources():
            return {"cpu": 0.2}

        monkeypatch.setattr(monitor, "_get_active_requests", active)
        monkeypatch.setattr(monitor, "_get_model_queue_depths", queues)
        monkeypatch.setattr(monitor, "_get_rate_limit_stats", rates)
        monkeypatch.setattr(monitor, "_get_system_resources", resources)

        snapshot = await monitor.get_load_snapshot()

        assert snapshot.active_requests == 4
        assert snapshot.is_drain_mode is True
        assert snapshot.model_queue_depths == {"gpt-4": 2}
        assert snapshot.rate_limit_stats == {"enabled": True}
        assert snapshot.system_resources == {"cpu": 0.2}

    @pytest.mark.asyncio
    async def test_is_draining_property_is_not_called(self, monkeypatch):
        monitor = SystemLoadMonitor()
        monitor.shutdown_manager = type("M", (), {"is_draining": False})()

        async def noop_int():
            return 0

        async def noop_dict():
            return {}

        monkeypatch.setattr(monitor, "_get_active_requests", noop_int)
        monkeypatch.setattr(monitor, "_get_model_queue_depths", noop_dict)
        monkeypatch.setattr(monitor, "_get_rate_limit_stats", noop_dict)
        monkeypatch.setattr(monitor, "_get_system_resources", noop_dict)

        snapshot = await monitor.get_load_snapshot()

        assert snapshot.is_drain_mode is False

    @pytest.mark.asyncio
    async def test_cache_returns_previous_snapshot(self, monkeypatch):
        monitor = SystemLoadMonitor()
        cached = _snapshot()
        monitor.last_snapshot = cached
        monitor._last_snapshot_time = 1000.0
        monkeypatch.setattr(sl.time, "time", lambda: 1000.5)

        assert await monitor.get_load_snapshot() is cached

    @pytest.mark.asyncio
    async def test_force_refresh_bypasses_cache(self, monkeypatch):
        monitor = SystemLoadMonitor()
        cached = _snapshot()
        monitor.last_snapshot = cached
        monitor._last_snapshot_time = 1000.0
        monkeypatch.setattr(sl.time, "time", lambda: 1000.5)

        async def zero():
            return 0

        async def empty():
            return {}

        monkeypatch.setattr(monitor, "_get_active_requests", zero)
        monkeypatch.setattr(monitor, "_get_model_queue_depths", empty)
        monkeypatch.setattr(monitor, "_get_rate_limit_stats", empty)
        monkeypatch.setattr(monitor, "_get_system_resources", empty)

        snapshot = await monitor.get_load_snapshot(force_refresh=True)

        assert snapshot is not cached
        assert monitor.last_snapshot is snapshot

    @pytest.mark.asyncio
    async def test_expired_cache_refreshes(self, monkeypatch):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot()
        monitor._last_snapshot_time = 0.0
        monkeypatch.setattr(sl.time, "time", lambda: 100.0)

        async def zero():
            return 0

        async def empty():
            return {}

        monkeypatch.setattr(monitor, "_get_active_requests", zero)
        monkeypatch.setattr(monitor, "_get_model_queue_depths", empty)
        monkeypatch.setattr(monitor, "_get_rate_limit_stats", empty)
        monkeypatch.setattr(monitor, "_get_system_resources", empty)

        snapshot = await monitor.get_load_snapshot()

        assert monitor.last_snapshot is snapshot


class TestRateLimitHelpers:
    @pytest.mark.asyncio
    async def test_active_requests_counts_current_window(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import app.middleware.rate_limiter as rl

        class FakeConfig:
            global_limit = (10, 60)

        calls = []
        limiter = rl.rate_limiter
        monkeypatch.setattr(limiter, "_config", FakeConfig())
        monkeypatch.setattr(sl.time, "time", lambda: 10.0)
        monkeypatch.setattr(
            limiter, "_cleanup_old_records",
            lambda key, cutoff: calls.append((key, cutoff)),
        )
        monkeypatch.setattr(limiter, "_history", {"global:0": [1.0, 2.0]})

        count = await monitor._get_active_requests()

        assert count == 2
        assert calls[0][0] == "global:0"

    @pytest.mark.asyncio
    async def test_active_requests_failure_returns_zero(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import app.middleware.rate_limiter as rl

        class FakeConfig:
            @property
            def global_limit(self):
                raise RuntimeError("broken")

        monkeypatch.setattr(rl.rate_limiter, "_config", FakeConfig())

        assert await monitor._get_active_requests() == 0

    @pytest.mark.asyncio
    async def test_rate_limit_stats_delegates(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import app.middleware.rate_limiter as rl

        monkeypatch.setattr(rl.rate_limiter, "get_stats", lambda: {"total_keys": 1})

        assert await monitor._get_rate_limit_stats() == {"total_keys": 1}

    @pytest.mark.asyncio
    async def test_rate_limit_stats_failure_returns_empty(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import app.middleware.rate_limiter as rl

        def boom():
            raise RuntimeError("stats")

        monkeypatch.setattr(rl.rate_limiter, "get_stats", boom)

        assert await monitor._get_rate_limit_stats() == {}


class TestResourceCollection:
    @pytest.mark.asyncio
    async def test_psutil_values_are_normalized(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import psutil

        monkeypatch.setattr(psutil, "cpu_percent", lambda: 50.0)
        monkeypatch.setattr(
            psutil, "virtual_memory",
            lambda: type("V", (), {"percent": 40.0})(),
        )
        monkeypatch.setattr(
            psutil, "disk_usage",
            lambda path: type("D", (), {"percent": 30.0})(),
        )

        resources = await monitor._get_system_resources()

        assert resources == {"cpu": 0.5, "memory": 0.4, "disk": 0.3}

    @pytest.mark.asyncio
    async def test_missing_psutil_returns_zeros(self, monkeypatch):
        monitor = SystemLoadMonitor()
        monkeypatch.setitem(__import__("sys").modules, "psutil", None)

        assert await monitor._get_system_resources() == {
            "cpu": 0.0,
            "memory": 0.0,
            "disk": 0.0,
        }


class TestOverloadDetection:
    def test_no_snapshot_is_not_overloaded(self):
        assert SystemLoadMonitor().is_system_overloaded() is False

    def test_resource_over_threshold(self):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot(
            system_resources={"cpu": 0.9, "memory": 0.1, "disk": 0.1}
        )

        assert monitor.is_system_overloaded(0.8) is True

    def test_active_requests_above_default_limit(self, monkeypatch):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot(active_requests=101)
        monkeypatch.setattr(sl.settings, "MAX_ACTIVE_REQUESTS", 100)

        assert monitor.is_system_overloaded(0.9) is True

    def test_resource_guard_raises_default_limit(self, monkeypatch):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot(active_requests=300)
        monkeypatch.setattr(sl.settings, "MAX_ACTIVE_REQUESTS", 100)
        import app.utils.resource_guard as rg

        class FakeGuard:
            def get_safe_concurrency(self):
                return 10

        monkeypatch.setattr(rg, "get_resource_guard", lambda: FakeGuard())

        assert monitor.is_system_overloaded(0.9) is True

    def test_resource_guard_failure_falls_back(self, monkeypatch):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot(active_requests=50)
        monkeypatch.setattr(sl.settings, "MAX_ACTIVE_REQUESTS", 100)

        import app.utils.resource_guard as rg

        def boom():
            raise RuntimeError("guard")

        monkeypatch.setattr(rg, "get_resource_guard", boom)

        assert monitor.is_system_overloaded(0.9) is False

    def test_normal_load_is_not_overloaded(self, monkeypatch):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot(active_requests=1)
        monkeypatch.setattr(sl.settings, "MAX_ACTIVE_REQUESTS", 100)

        assert monitor.is_system_overloaded(0.8) is False


class TestModelLoadScore:
    def test_no_snapshot_returns_neutral(self):
        assert SystemLoadMonitor().get_model_load_score("gpt-4") == 0.5

    def test_queue_depth_and_resources_combine(self):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot(
            model_queue_depths={"gpt-4": 5},
            system_resources={"cpu": 0.4, "memory": 0.2},
        )

        score = monitor.get_model_load_score("gpt-4")

        assert score == pytest.approx(5 / 10 * 0.7 + 0.4 * 0.3)

    def test_queue_depth_is_capped(self):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot(
            model_queue_depths={"gpt-4": 100},
            system_resources={"cpu": 0.1},
        )

        assert monitor.get_model_load_score("gpt-4") == pytest.approx(0.7 + 0.03)

    def test_unknown_model_uses_zero_depth(self):
        monitor = SystemLoadMonitor()
        monitor.last_snapshot = _snapshot(system_resources={"cpu": 0.2})

        assert monitor.get_model_load_score("other") == pytest.approx(0.06)


class TestQueueDepthBranches:
    @pytest.mark.asyncio
    async def test_task_without_id_and_args_counts_default(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import app.celery_app as celery_module

        class FakeInspect:
            def active(self):
                return {"worker": [{"args": []}]}

            def reserved(self):
                return None

        class FakeControl:
            def inspect(self, timeout=None):
                return FakeInspect()

        monkeypatch.setattr(
            celery_module, "celery_app", type("C", (), {"control": FakeControl()})()
        )

        depths = await monitor._get_model_queue_depths()

        assert depths == {"default": 1}

    @pytest.mark.asyncio
    async def test_task_with_non_dict_first_arg_uses_default(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import app.celery_app as celery_module

        class FakeInspect:
            def active(self):
                return {"worker": [{"id": "t1", "args": ["plain"]}]}

            def reserved(self):
                return {}

        class FakeControl:
            def inspect(self, timeout=None):
                return FakeInspect()

        monkeypatch.setattr(
            celery_module, "celery_app", type("C", (), {"control": FakeControl()})()
        )

        assert await monitor._get_model_queue_depths() == {"default": 1}

    @pytest.mark.asyncio
    async def test_inspect_none_returns_empty(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import app.celery_app as celery_module

        class FakeControl:
            def inspect(self, timeout=None):
                return None

        monkeypatch.setattr(
            celery_module, "celery_app", type("C", (), {"control": FakeControl()})()
        )

        assert await monitor._get_model_queue_depths() == {}

    @pytest.mark.asyncio
    async def test_language_fallback_used(self, monkeypatch):
        monitor = SystemLoadMonitor()
        import app.celery_app as celery_module

        class FakeInspect:
            def active(self):
                return {"worker": [{"id": "t1", "args": [{"language": "go"}]}]}

            def reserved(self):
                return {}

        class FakeControl:
            def inspect(self, timeout=None):
                return FakeInspect()

        monkeypatch.setattr(
            celery_module, "celery_app", type("C", (), {"control": FakeControl()})()
        )

        assert await monitor._get_model_queue_depths() == {"go": 1}


def test_constructor_falls_back_without_singleton(monkeypatch):
    monitor = SystemLoadMonitor()

    assert monitor.shutdown_manager is not None
