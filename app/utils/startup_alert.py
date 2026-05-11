"""
启动失败告警

服务启动失败时发送告警通知
"""
import asyncio
import logging
import time
import traceback
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class AlertLevel(Enum):
    """告警级别"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class StartupAlert:
    """启动告警"""
    level: AlertLevel
    message: str
    timestamp: float
    details: Dict[str, Any] = field(default_factory=dict)
    recovered: bool = False
    recovered_at: Optional[float] = None


class StartupFailureAlert:
    """
    启动失败告警管理器

    功能：
    - 记录启动过程
    - 失败时发送告警
    - 恢复时发送恢复通知
    - 告警历史记录
    """

    def __init__(self):
        self._alerts: List[StartupAlert] = []
        self._max_alerts = 50
        self._handlers: List[Callable] = []
        self._start_time: Optional[float] = None
        self._startup_successful = False
        self._lock = asyncio.Lock()

    def add_handler(self, handler: Callable):
        """
        添加告警处理器

        Args:
            handler: 异步函数，签名为 (alert: StartupAlert) -> None
        """
        self._handlers.append(handler)

    async def notify_handlers(self, alert: StartupAlert):
        """通知所有处理器"""
        for handler in self._handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(alert)
                else:
                    handler(alert)
            except Exception as e:
                logger.error(f"告警处理器执行失败: {e}")

    def record_startup_begin(self):
        """记录启动开始"""
        self._start_time = time.time()
        self._startup_successful = False
        logger.info("=" * 60)
        logger.info("服务启动中...")
        logger.info("=" * 60)

    async def record_startup_success(self, duration: float):
        """
        记录启动成功

        Args:
            duration: 启动耗时（秒）
        """
        self._startup_successful = True
        logger.info("=" * 60)
        logger.info(f"服务启动成功 | duration={duration:.2f}s")
        logger.info("=" * 60)

        if self._alerts:
            alert = StartupAlert(
                level=AlertLevel.INFO,
                message="服务启动成功",
                timestamp=time.time(),
                details={"duration": duration, "startup_alerts": len(self._alerts)},
                recovered=True,
                recovered_at=time.time()
            )
            self._alerts.append(alert)
            await self.notify_handlers(alert)

    async def record_startup_failure(
        self,
        error: Exception,
        phase: str = "unknown",
        details: Dict[str, Any] = None
    ):
        """
        记录启动失败

        Args:
            error: 异常
            phase: 失败阶段
            details: 额外详情
        """
        duration = time.time() - self._start_time if self._start_time else 0

        tb = traceback.format_exc()
        alert = StartupAlert(
            level=AlertLevel.ERROR,
            message=f"服务启动失败 [{phase}]: {str(error)}",
            timestamp=time.time(),
            details={
                "duration": duration,
                "phase": phase,
                "error_type": type(error).__name__,
                "traceback": tb,
                **(details or {})
            }
        )
        self._alerts.append(alert)

        logger.error("=" * 60)
        logger.error(f"服务启动失败 | phase={phase} | error={error}")
        logger.error(f"启动耗时: {duration:.2f}s")
        logger.error("=" * 60)

        await self.notify_handlers(alert)

    async def send_recovery_alert(self):
        """发送恢复告警（服务从失败状态恢复）"""
        if not self._startup_successful:
            return

        alert = StartupAlert(
            level=AlertLevel.INFO,
            message="服务已恢复",
            timestamp=time.time(),
            recovered=True,
            recovered_at=time.time()
        )
        self._alerts.append(alert)
        await self.notify_handlers(alert)

    def get_alerts(
        self,
        level: Optional[AlertLevel] = None,
        limit: int = 10,
        only_unrecovered: bool = False
    ) -> List[StartupAlert]:
        """
        获取告警历史

        Args:
            level: 过滤级别
            limit: 返回数量
            only_unrecovered: 只返回未恢复的
        """
        alerts = self._alerts

        if level:
            alerts = [a for a in alerts if a.level == level]

        if only_unrecovered:
            alerts = [a for a in alerts if not a.recovered]

        return alerts[-limit:]

    def get_last_alert(self) -> Optional[StartupAlert]:
        """获取最新告警"""
        return self._alerts[-1] if self._alerts else None

    def is_startup_successful(self) -> bool:
        """检查启动是否成功"""
        return self._startup_successful


class WebhookAlertHandler:
    """
    Webhook 告警处理器

    将告警发送到 HTTP Webhook
    """

    def __init__(self, webhook_url: str, timeout: float = 5.0):
        self.webhook_url = webhook_url
        self.timeout = timeout

    async def __call__(self, alert: StartupAlert):
        """发送告警到 Webhook"""
        try:
            import httpx

            payload = {
                "level": alert.level.value,
                "message": alert.message,
                "timestamp": alert.timestamp,
                "details": alert.details,
                "recovered": alert.recovered
            }

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                await client.post(self.webhook_url, json=payload)

            logger.info(f"告警已发送至 Webhook | url={self.webhook_url}")

        except Exception as e:
            logger.error(f"Webhook 告警发送失败: {e}")


class ConsoleAlertHandler:
    """
    控制台告警处理器

    仅输出到日志（用于开发调试）
    """

    async def __call__(self, alert: StartupAlert):
        """输出告警到控制台"""
        if alert.level == AlertLevel.ERROR:
            logger.error(f"[启动告警] {alert.message}")
        elif alert.level == AlertLevel.WARNING:
            logger.warning(f"[启动告警] {alert.message}")
        else:
            logger.info(f"[启动告警] {alert.message}")


_startup_alert: Optional[StartupFailureAlert] = None


def get_startup_alert() -> StartupFailureAlert:
    """获取启动告警管理器单例"""
    global _startup_alert
    if _startup_alert is None:
        _startup_alert = StartupFailureAlert()
    return _startup_alert
