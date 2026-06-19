"""
优雅关闭管理器

确保服务关闭时：
1. 不接受新请求
2. 等待现有请求处理完成
3. 关闭 WebSocket 连接
4. 等待 Celery 任务完成
5. 关闭数据库连接池
"""
import asyncio
import logging
import signal
import threading
from enum import Enum
from typing import Optional, Callable, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ShutdownState(Enum):
    """关闭状态"""
    RUNNING = "running"
    DRAINING = "draining"
    SHUTTING_DOWN = "shutting_down"
    TERMINATED = "terminated"


class GracefulShutdownManager:
    """
    优雅关闭管理器

    状态转换：RUNNING → DRAINING → SHUTTING_DOWN → TERMINATED
    """

    def __init__(
        self,
        shutdown_timeout: int = 30,
        websocket_drain_timeout: int = 10,
        celery_sigterm_timeout: int = 20
    ):
        self._state = ShutdownState.RUNNING
        self._lock = threading.RLock()
        self._shutdown_timeout = shutdown_timeout
        self._websocket_drain_timeout = websocket_drain_timeout
        self._celery_sigterm_timeout = celery_sigterm_timeout

        self._shutdown_event: Optional[asyncio.Event] = None
        self._drain_start_time: Optional[datetime] = None

        self._pre_shutdown_hooks: List[Callable] = []
        self._post_shutdown_hooks: List[Callable] = []

        self._connections_inflight = 0
        self._connections_lock = threading.Lock()

        self._original_sigterm_handler: Optional[signal.Handler] = None
        self._original_sigint_handler: Optional[signal.Handler] = None

    @property
    def state(self) -> ShutdownState:
        return self._state

    @property
    def is_draining(self) -> bool:
        return self._state == ShutdownState.DRAINING

    @property
    def is_running(self) -> bool:
        return self._state == ShutdownState.RUNNING

    @property
    def shutdown_timeout(self) -> int:
        return self._shutdown_timeout

    def register_pre_shutdown_hook(self, hook: Callable):
        """注册关闭前钩子"""
        self._pre_shutdown_hooks.append(hook)

    def register_post_shutdown_hook(self, hook: Callable):
        """注册关闭后钩子"""
        self._post_shutdown_hooks.append(hook)

    def increment_connections(self):
        """增加进行中的连接数"""
        with self._connections_lock:
            self._connections_inflight += 1

    def decrement_connections(self):
        """减少进行中的连接数"""
        with self._connections_lock:
            self._connections_inflight = max(0, self._connections_inflight - 1)

    def get_connections_inflight(self) -> int:
        """获取进行中的连接数"""
        with self._connections_lock:
            return self._connections_inflight

    async def wait_for_connections_drain(self, timeout: Optional[int] = None):
        """等待所有连接处理完成"""
        timeout = timeout or self._shutdown_timeout
        start_time = asyncio.get_running_loop().time()

        while self.get_connections_inflight() > 0:
            if asyncio.get_running_loop().time() - start_time > timeout:
                logger.warning(
                    f"等待连接关闭超时 | timeout={timeout}s | "
                    f"remaining={self.get_connections_inflight()}"
                )
                return False
            await asyncio.sleep(0.5)

        logger.info("所有连接已关闭")
        return True

    def initiate_shutdown(self):
        """
        开始关闭流程（同步调用，由信号处理器触发）
        """
        with self._lock:
            if self._state != ShutdownState.RUNNING:
                logger.debug(f"关闭流程已启动，状态: {self._state}")
                return

            logger.info("=" * 50)
            logger.info("收到关闭信号，开始优雅关闭...")
            logger.info("=" * 50)

            self._state = ShutdownState.DRAINING
            self._drain_start_time = datetime.utcnow()

            for hook in self._pre_shutdown_hooks:
                try:
                    if asyncio.iscoroutinefunction(hook):
                        asyncio.create_task(hook())
                    else:
                        hook()
                except Exception as e:
                    logger.error(f"关闭前钩子执行失败: {e}")

    async def _do_shutdown(self):
        """
        执行关闭流程（异步）
        """
        with self._lock:
            if self._state == ShutdownState.TERMINATED:
                return
            self._state = ShutdownState.SHUTTING_DOWN

        logger.info("进入关闭阶段，等待连接处理完成...")

        drain_success = await self.wait_for_connections_drain()

        if not drain_success:
            logger.warning("部分连接未能正常关闭，强制终止")

        logger.info("执行 WebSocket 关闭...")
        await self._close_websocket_connections()

        logger.info("执行 Celery 关闭...")
        await self._close_celery_workers()

        logger.info("关闭数据库连接池...")
        await self._close_database_pool()

        for hook in self._post_shutdown_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook()
                else:
                    hook()
            except Exception as e:
                logger.error(f"关闭后钩子执行失败: {e}")

        with self._lock:
            self._state = ShutdownState.TERMINATED

        self._shutdown_event.set()
        logger.info("优雅关闭完成")

    async def _close_websocket_connections(self):
        """关闭 WebSocket 连接"""
        try:
            from app.services.websocket_manager import get_ws_manager
            ws_manager = get_ws_manager()
            connection_count = await ws_manager.get_connection_count()

            if connection_count > 0:
                logger.info(f"正在关闭 {connection_count} 个 WebSocket 连接...")
                await asyncio.sleep(self._websocket_drain_timeout)

        except Exception as e:
            logger.error(f"关闭 WebSocket 连接失败: {e}")

    async def _close_celery_workers(self):
        """发送 SIGTERM 到 Celery workers"""
        try:
            from app.celery_app import celery_app
            if celery_app:
                logger.info("正在关闭 Celery workers...")
                celery_app.control.shutdown(graceful=True)
        except Exception as e:
            logger.warning(f"Celery 关闭失败（可能已停止）: {e}")

    async def _close_database_pool(self):
        """关闭数据库连接池"""
        try:
            from app.db.database import engine
            if engine:
                await engine.dispose()
                logger.info("数据库连接池已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接池失败: {e}")

    async def shutdown_async(self):
        """异步关闭入口"""
        self.initiate_shutdown()
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        await self._do_shutdown()

    def setup_signal_handlers(self):
        """设置信号处理器"""
        try:
            loop = asyncio.get_running_loop()
            loop.add_signal_handler(signal.SIGTERM, self._handle_sigterm)
            loop.add_signal_handler(signal.SIGINT, self._handle_sigint)
            logger.info("信号处理器已设置（asyncio 模式）")
        except (NotImplementedError, RuntimeError):
            # Windows 不支持 add_signal_handler，回退到 signal.signal
            def sigterm_handler(signum, frame):
                logger.info("收到 SIGTERM 信号")
                self.initiate_shutdown()

            def sigint_handler(signum, frame):
                logger.info("收到 SIGINT (Ctrl+C) 信号")
                self.initiate_shutdown()

            self._original_sigterm_handler = signal.signal(signal.SIGTERM, sigterm_handler)
            self._original_sigint_handler = signal.signal(signal.SIGINT, sigint_handler)
            logger.info("信号处理器已设置（signal 模式）")

    def _handle_sigterm(self):
        logger.info("收到 SIGTERM 信号")
        self.initiate_shutdown()
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        asyncio.ensure_future(self._do_shutdown())

    def _handle_sigint(self):
        logger.info("收到 SIGINT (Ctrl+C) 信号")
        self.initiate_shutdown()
        if self._shutdown_event is None:
            self._shutdown_event = asyncio.Event()
        asyncio.ensure_future(self._do_shutdown())

    def restore_signal_handlers(self):
        """恢复原始信号处理器"""
        if self._original_sigterm_handler:
            signal.signal(signal.SIGTERM, self._original_sigterm_handler)
        if self._original_sigint_handler:
            signal.signal(signal.SIGINT, self._original_sigint_handler)
        logger.info("信号处理器已恢复")

    def get_status(self) -> dict:
        """获取关闭状态"""
        return {
            "state": self._state.value,
            "is_draining": self.is_draining,
            "is_running": self.is_running,
            "connections_inflight": self.get_connections_inflight(),
            "drain_start_time": self._drain_start_time.isoformat() if self._drain_start_time else None,
            "shutdown_timeout": self._shutdown_timeout
        }


_shutdown_manager_instance: Optional[GracefulShutdownManager] = None


def get_shutdown_manager() -> GracefulShutdownManager:
    """获取关闭管理器单例"""
    global _shutdown_manager_instance
    if _shutdown_manager_instance is None:
        _shutdown_manager_instance = GracefulShutdownManager()
    return _shutdown_manager_instance


shutdown_manager = get_shutdown_manager()
