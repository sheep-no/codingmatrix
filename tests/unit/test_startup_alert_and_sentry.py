"""startup_alert / sentry 回归测试。

覆盖已建档缺陷：
- STA2 _max_alerts 从未执行裁剪，告警列表无限增长
- STA5 get_startup_alert 单例无锁
- SNT2 capture_* 未初始化时静默 return，调用方误以为已上报
"""

import asyncio

from app.utils import sentry as sentry_mod
from app.utils.startup_alert import (
    AlertLevel,
    StartupAlert,
    StartupFailureAlert,
    get_startup_alert,
)


def test_alerts_are_trimmed_to_max():
    manager = StartupFailureAlert()

    async def record_many():
        for index in range(manager._max_alerts + 10):
            await manager.record_startup_failure(
                Exception(str(index)), phase="test"
            )

    asyncio.run(record_many())

    assert len(manager._alerts) == manager._max_alerts
    assert manager.get_last_alert().details["phase"] == "test"


def test_remember_helper_trims_and_keeps_newest():
    manager = StartupFailureAlert()

    for index in range(manager._max_alerts + 5):
        manager._remember(
            StartupAlert(level=AlertLevel.INFO, message=str(index), timestamp=0.0)
        )

    assert manager._alerts[0].message == "5"
    assert manager._alerts[-1].message == str(manager._max_alerts + 4)


def test_get_startup_alert_returns_singleton():
    assert get_startup_alert() is get_startup_alert()


def test_capture_functions_log_debug_when_not_initialized(monkeypatch):
    """未初始化时应留下可观测的 debug 记录，而不是完全静默。"""
    logged = []
    monkeypatch.setattr(sentry_mod.logger, "debug", lambda *a, **k: logged.append(a))
    monkeypatch.setattr(sentry_mod, "_sentry_initialized", False)

    sentry_mod.capture_error(Exception("boom"))
    sentry_mod.capture_message_sync("hello")
    asyncio.run(sentry_mod.capture_message_async("hello"))

    assert len(logged) >= 3


def test_init_sentry_skips_without_dsn(monkeypatch):
    monkeypatch.setattr(sentry_mod, "_sentry_initialized", False)

    asyncio.run(sentry_mod.init_sentry(dsn=None))

    assert sentry_mod.is_sentry_initialized() is False
