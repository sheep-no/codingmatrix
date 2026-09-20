"""hot_reload 变更回调与动态包过滤的回归（HR1/HR4/HR8、DPM5）。"""
import pytest

from app.utils.hot_reload import ConfigWatcher, HotReloadConfig
from app.utils.dynamic_package_manager import DynamicPackageManager


class _FakeSettings:
    """模拟 settings 对象，让 _get_settings 返回可控旧值。"""


async def _reload_with(monkeypatch, watcher, new_config):
    monkeypatch.setattr(watcher, "_get_settings", lambda: _FakeSettings())
    monkeypatch.setattr(
        "dotenv.dotenv_values", lambda *args, **kwargs: new_config, raising=False
    )
    await watcher._reload_config()


@pytest.mark.asyncio
async def test_async_callback_is_awaited(monkeypatch):
    watcher = ConfigWatcher()
    executed = []

    async def async_callback(key, old_value, new_value):
        executed.append((key, old_value, new_value))

    watcher.watch("FEATURE_FLAG", async_callback)

    await _reload_with(monkeypatch, watcher, {"FEATURE_FLAG": "on"})

    assert executed == [("FEATURE_FLAG", None, "on")]


@pytest.mark.asyncio
async def test_callback_exception_does_not_stop_other_callbacks(monkeypatch):
    watcher = ConfigWatcher()
    executed = []

    def failing_callback(key, old_value, new_value):
        raise RuntimeError("boom")

    def healthy_callback(key, old_value, new_value):
        executed.append((key, new_value))

    watcher.watch("BROKEN", failing_callback)
    watcher.watch("HEALTHY", healthy_callback)

    await _reload_with(monkeypatch, watcher, {"BROKEN": "1", "HEALTHY": "2"})

    assert executed == [("HEALTHY", "2")]


@pytest.mark.asyncio
async def test_change_history_records_reloaded_keys(monkeypatch):
    config = HotReloadConfig()
    watcher = config.register_watcher("default")
    watcher.watch("FEATURE_FLAG", lambda *args: None)

    await _reload_with(monkeypatch, watcher, {"FEATURE_FLAG": "on"})

    history = config.get_change_history()
    assert len(history) == 1
    assert history[0].key == "FEATURE_FLAG"
    assert history[0].new_value == "on"


def test_filter_packages_rejects_unevaluated_package():
    manager = DynamicPackageManager()

    allowed, rejected = manager.filter_packages(
        ["redis", "requests2", "totally-unknown-package-xyz"]
    )

    assert "redis" in allowed
    assert "requests2" in rejected
    assert "totally-unknown-package-xyz" in rejected
