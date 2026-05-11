"""
测试启动告警
"""
import pytest
import asyncio
import time
from app.utils.startup_alert import (
    StartupFailureAlert,
    StartupAlert,
    AlertLevel,
    WebhookAlertHandler,
    ConsoleAlertHandler,
    get_startup_alert
)


class TestStartupAlert:
    """测试启动告警"""

    def test_singleton(self):
        """测试单例"""
        alert1 = get_startup_alert()
        alert2 = get_startup_alert()
        assert alert1 is alert2

    def test_record_startup_begin(self):
        """测试记录启动开始"""
        alert = StartupFailureAlert()
        alert.record_startup_begin()
        assert alert._start_time is not None
        assert alert._startup_successful is False

    @pytest.mark.asyncio
    async def test_record_startup_success(self):
        """测试记录启动成功"""
        alert = StartupFailureAlert()
        alert.record_startup_begin()
        await asyncio.sleep(0.01)
        await alert.record_startup_success(0.5)

        assert alert.is_startup_successful() is True

    @pytest.mark.asyncio
    async def test_record_startup_failure(self):
        """测试记录启动失败"""
        alert = StartupFailureAlert()
        alert.record_startup_begin()

        try:
            raise ValueError("test error")
        except ValueError as e:
            await alert.record_startup_failure(e, phase="initialization")

        assert alert.is_startup_successful() is False
        last_alert = alert.get_last_alert()
        assert last_alert is not None
        assert last_alert.level == AlertLevel.ERROR
        assert "test error" in last_alert.message

    def test_get_alerts_filter(self):
        """测试告警过滤"""
        alert = StartupFailureAlert()
        alert.record_startup_begin()

        alert._alerts.append(StartupAlert(
            level=AlertLevel.INFO,
            message="info",
            timestamp=time.time()
        ))
        alert._alerts.append(StartupAlert(
            level=AlertLevel.ERROR,
            message="error",
            timestamp=time.time()
        ))

        errors = alert.get_alerts(level=AlertLevel.ERROR)
        assert len(errors) == 1
        assert errors[0].message == "error"


class TestConsoleAlertHandler:
    """测试控制台告警处理器"""

    @pytest.mark.asyncio
    async def test_handler(self):
        """测试处理器"""
        handler = ConsoleAlertHandler()
        test_alert = StartupAlert(
            level=AlertLevel.INFO,
            message="test message",
            timestamp=time.time()
        )

        await handler(test_alert)


class TestWebhookAlertHandler:
    """测试 Webhook 告警处理器"""

    @pytest.mark.asyncio
    async def test_handler_failure(self):
        """测试处理失败（网络错误）"""
        handler = WebhookAlertHandler("http://localhost:99999/invalid")
        test_alert = StartupAlert(
            level=AlertLevel.ERROR,
            message="test",
            timestamp=time.time()
        )

        await handler(test_alert)
