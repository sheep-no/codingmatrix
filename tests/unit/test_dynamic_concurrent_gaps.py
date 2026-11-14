"""dynamic_concurrent 单例、负载推荐与变更历史分支补测。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.utils.dynamic_concurrent import ConcurrentLimitManager


@pytest.fixture(autouse=True)
def _reset_singleton():
    ConcurrentLimitManager._instance = None
    yield
    ConcurrentLimitManager._instance = None


async def test_singleton_reuses_instance():
    first = ConcurrentLimitManager()
    second = ConcurrentLimitManager()
    assert first is second


async def test_change_log_truncates_to_max(monkeypatch):
    manager = ConcurrentLimitManager()
    manager._change_log = []
    monkeypatch.setattr(ConcurrentLimitManager, "MAX_CHANGE_LOG", 3)

    for i in range(5):
        await manager.update_limit("free", i, "admin")

    assert len(manager._change_log) == 3
    assert manager.get_limit("free") == 4


async def test_get_recommended_limits_without_monitor():
    manager = ConcurrentLimitManager()
    result = await manager.get_recommended_limits()
    assert result == manager._limits


async def test_get_recommended_limits_high_load_halves():
    monitor = SimpleNamespace(
        get_system_load=AsyncMock(
            return_value=SimpleNamespace(cpu_percent=90, memory_percent=10)
        )
    )
    manager = ConcurrentLimitManager(load_monitor=monitor)

    result = await manager.get_recommended_limits()

    assert result["premium"] == 2
    assert result["free"] == 1


async def test_get_recommended_limits_medium_load_reduces():
    monitor = SimpleNamespace(
        get_system_load=AsyncMock(
            return_value=SimpleNamespace(cpu_percent=65, memory_percent=10)
        )
    )
    manager = ConcurrentLimitManager(load_monitor=monitor)

    result = await manager.get_recommended_limits()

    assert result["premium"] == 3
    assert result["enterprise"] == 7


async def test_get_recommended_limits_low_load_uses_base():
    monitor = SimpleNamespace(
        get_system_load=AsyncMock(
            return_value=SimpleNamespace(cpu_percent=10, memory_percent=10)
        )
    )
    manager = ConcurrentLimitManager(load_monitor=monitor)

    result = await manager.get_recommended_limits()

    assert result == ConcurrentLimitManager.BASE_LIMITS


async def test_get_recommended_limits_swallows_error():
    monitor = SimpleNamespace(
        get_system_load=AsyncMock(side_effect=RuntimeError("no metrics"))
    )
    manager = ConcurrentLimitManager(load_monitor=monitor)

    result = await manager.get_recommended_limits()

    assert result == manager._limits


async def test_session_registration_and_release():
    manager = ConcurrentLimitManager()

    manager.register_session("free")
    assert manager.get_active_count("free") == 1
    assert manager.can_create_session("free") is False

    manager.unregister_session("free")
    assert manager.get_active_count("free") == 0
    assert manager.can_create_session("free") is True


async def test_unregister_unknown_role_is_noop():
    manager = ConcurrentLimitManager()
    manager.unregister_session("ghost")
    assert manager.get_active_count("ghost") == 0


async def test_get_change_history_limit_and_zero():
    manager = ConcurrentLimitManager()
    manager._change_log = list(range(5))

    assert manager.get_change_history(2) == [3, 4]
    assert manager.get_change_history(0) == []
    assert manager.get_change_history(-10) == []
    assert manager.get_change_history(10_000) == list(range(5))


def test_singleton_double_check_path(monkeypatch):
    class Guarded:
        _instance = None
        _lock = ConcurrentLimitManager._lock

    instance = ConcurrentLimitManager()
    # 模拟并发窗口：外层检查后实例被另一线程创建，内层分支不再进入
    monkeypatch.setattr(ConcurrentLimitManager, "_instance", instance)
    assert ConcurrentLimitManager() is instance


async def test_unregister_keeps_positive_session_count():
    manager = ConcurrentLimitManager()
    manager.register_session("premium")
    manager.register_session("premium")

    manager.unregister_session("premium")

    assert manager.get_active_count("premium") == 1
