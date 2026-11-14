"""补齐 AsyncSmartGuardian 的扫描、可信判定与关闭流程。"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.utils import async_enhanced_guard as module


class _ConfigManager:
    def __init__(self, configs=None):
        self.configs = configs or {}
        self.saved = 0
        self.created = []

    def get_or_create_config(self, port, process_info):
        self.created.append((port, process_info))
        return self.configs.setdefault(
            port,
            {
                "display_name": process_info["name"],
                "auto_start": False,
            },
        )

    def save_configs(self):
        self.saved += 1

    def get_enabled_services(self):
        return [cfg for cfg in self.configs.values() if cfg.get("auto_start")]


@pytest.fixture
def guardian(monkeypatch):
    manager = _ConfigManager()
    monkeypatch.setattr(module, "ServiceConfigManager", lambda: manager)
    breaker = SimpleNamespace(call=AsyncMock(return_value="ok"), get_status=lambda: {"state": "CLOSED"})
    monkeypatch.setattr(module, "get_circuit_breaker", lambda *a, **k: breaker)
    instance = module.AsyncSmartGuardian(check_interval=1)
    return instance, manager, breaker


@pytest.mark.asyncio
async def test_scan_and_learn_skips_closed_and_pidless_ports(guardian, monkeypatch):
    instance, manager, _ = guardian
    instance.is_port_open = AsyncMock(side_effect=lambda port: port == 6379)
    instance.find_pid_by_port = AsyncMock(return_value=None)

    await instance.scan_and_learn()

    instance.is_port_open.assert_awaited()
    instance.find_pid_by_port.assert_awaited_once_with(6379)
    assert manager.created == []


@pytest.mark.asyncio
async def test_scan_and_learn_handles_process_lookup_errors(guardian, monkeypatch):
    instance, manager, _ = guardian
    instance.is_port_open = AsyncMock(return_value=True)
    instance.find_pid_by_port = AsyncMock(return_value=4321)

    def boom(pid):
        raise ValueError("gone")

    monkeypatch.setattr(module.psutil, "Process", boom)

    await instance.scan_and_learn()

    port, info = manager.created[0]
    assert info == {"pid": 4321, "name": "unknown", "cmdline": ""}


@pytest.mark.asyncio
async def test_scan_and_learn_auto_enables_trusted(guardian, monkeypatch):
    instance, manager, _ = guardian
    manager.configs[6379] = {"display_name": "redis", "auto_start": False}
    instance.is_port_open = AsyncMock(side_effect=lambda port: port == 6379)
    instance.find_pid_by_port = AsyncMock(return_value=99)
    monkeypatch.setattr(
        module.psutil,
        "Process",
        lambda pid: SimpleNamespace(name=lambda: "redis-server", cmdline=lambda: ["redis"]),
    )

    await instance.scan_and_learn(auto_enable_trusted=True)

    assert manager.configs[6379]["auto_start"] is True
    assert manager.saved == 1


@pytest.mark.asyncio
async def test_scan_and_learn_keeps_untrusted_disabled(guardian, monkeypatch):
    instance, manager, _ = guardian
    manager.configs[8080] = {"display_name": "my-app", "auto_start": False}
    instance.is_port_open = AsyncMock(side_effect=lambda port: port == 8080)
    instance.find_pid_by_port = AsyncMock(return_value=99)
    monkeypatch.setattr(
        module.psutil,
        "Process",
        lambda pid: SimpleNamespace(name=lambda: "app", cmdline=lambda: ["app"]),
    )

    await instance.scan_and_learn(auto_enable_trusted=True)

    assert manager.configs[8080]["auto_start"] is False
    assert manager.saved == 0


@pytest.mark.asyncio
async def test_scan_and_learn_does_not_resave_enabled_service(guardian, monkeypatch):
    instance, manager, _ = guardian
    manager.configs[6379] = {"display_name": "redis", "auto_start": True}
    instance.is_port_open = AsyncMock(side_effect=lambda port: port == 6379)
    instance.find_pid_by_port = AsyncMock(return_value=99)
    monkeypatch.setattr(
        module.psutil,
        "Process",
        lambda pid: SimpleNamespace(name=lambda: "redis", cmdline=lambda: ["redis"]),
    )

    await instance.scan_and_learn(auto_enable_trusted=True)

    assert manager.saved == 0


@pytest.mark.asyncio
async def test_start_monitoring_without_services(guardian):
    instance, _, _ = guardian

    await instance.start_monitoring_enabled_services()

    assert instance.monitor_task is None


@pytest.mark.asyncio
async def test_start_monitoring_creates_task(guardian, monkeypatch):
    instance, manager, _ = guardian
    manager.configs[1] = {"display_name": "job", "auto_start": True}
    instance.monitor_all = AsyncMock()

    await instance.start_monitoring_enabled_services()
    await instance.monitor_task

    instance.monitor_all.assert_awaited_once()


def test_is_trusted_infrastructure_name(guardian):
    instance, _, _ = guardian

    assert instance.is_trusted({"display_name": "MySQL Server", "auto_start": False}) is True


def test_is_trusted_user_enabled(guardian):
    instance, _, _ = guardian

    assert instance.is_trusted({"display_name": "custom", "auto_start": True}) is True


def test_is_trusted_unknown(guardian):
    instance, _, _ = guardian

    assert instance.is_trusted({"display_name": "custom"}) is False


@pytest.mark.asyncio
async def test_shutdown_cancels_task(guardian):
    instance, _, _ = guardian

    async def forever():
        await asyncio.sleep(60)

    instance.monitor_task = asyncio.create_task(forever())

    await instance.shutdown()

    assert instance.monitor_task.cancelled()


@pytest.mark.asyncio
async def test_shutdown_without_task(guardian):
    instance, _, _ = guardian

    await instance.shutdown()

    assert instance.monitor_task is None


@pytest.mark.asyncio
async def test_guarded_api_call_delegates(guardian):
    instance, _, breaker = guardian
    func = AsyncMock(return_value=42)

    assert await instance.guarded_api_call(func, 1, key=2) == "ok"
    breaker.call.assert_awaited_once_with(func, 1, key=2)


def test_circuit_breaker_status(guardian):
    instance, _, _ = guardian

    assert instance.get_circuit_breaker_status() == {"state": "CLOSED"}
