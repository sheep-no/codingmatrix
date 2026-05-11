"""
测试优雅关闭管理器
"""
import pytest
import asyncio
from app.core.graceful_shutdown import (
    GracefulShutdownManager,
    ShutdownState,
    get_shutdown_manager,
    shutdown_manager
)


class TestGracefulShutdownManager:
    """测试优雅关闭管理器"""

    def test_singleton_pattern(self):
        """测试单例模式"""
        manager1 = get_shutdown_manager()
        manager2 = get_shutdown_manager()
        assert manager1 is manager2
        assert manager1 is shutdown_manager

    def test_initial_state(self):
        """测试初始状态"""
        manager = GracefulShutdownManager()
        assert manager.state == ShutdownState.RUNNING
        assert manager.is_running is True
        assert manager.is_draining is False

    def test_increment_decrement_connections(self):
        """测试连接计数"""
        manager = GracefulShutdownManager()

        assert manager.get_connections_inflight() == 0

        manager.increment_connections()
        assert manager.get_connections_inflight() == 1

        manager.increment_connections()
        assert manager.get_connections_inflight() == 2

        manager.decrement_connections()
        assert manager.get_connections_inflight() == 1

        manager.decrement_connections()
        assert manager.get_connections_inflight() == 0

    def test_decrement_below_zero(self):
        """测试计数不会低于零"""
        manager = GracefulShutdownManager()
        manager.decrement_connections()
        assert manager.get_connections_inflight() == 0

    def test_initiate_shutdown(self):
        """测试启动关闭"""
        manager = GracefulShutdownManager()
        manager.initiate_shutdown()

        assert manager.state == ShutdownState.DRAINING
        assert manager.is_draining is True
        assert manager.is_running is False

    def test_initiate_shutdown_idempotent(self):
        """测试多次调用关闭只生效一次"""
        manager = GracefulShutdownManager()
        manager.initiate_shutdown()
        manager.initiate_shutdown()

        assert manager.state == ShutdownState.DRAINING

    def test_get_status(self):
        """测试获取状态"""
        manager = GracefulShutdownManager()
        status = manager.get_status()

        assert status["state"] == "running"
        assert status["is_draining"] is False
        assert status["is_running"] is True
        assert status["connections_inflight"] == 0
        assert status["shutdown_timeout"] == 30

    def test_register_hooks(self):
        """测试注册钩子"""
        manager = GracefulShutdownManager()

        pre_called = []
        post_called = []

        def pre_hook():
            pre_called.append(1)

        async def post_hook():
            post_called.append(1)

        manager.register_pre_shutdown_hook(pre_hook)
        manager.register_post_shutdown_hook(post_hook)

        assert len(manager._pre_shutdown_hooks) == 1
        assert len(manager._post_shutdown_hooks) == 1

    def test_custom_timeout(self):
        """测试自定义超时"""
        manager = GracefulShutdownManager(
            shutdown_timeout=60,
            websocket_drain_timeout=15,
            celery_sigterm_timeout=45
        )

        assert manager.shutdown_timeout == 60


class TestShutdownState:
    """测试关闭状态枚举"""

    def test_state_values(self):
        """测试状态值"""
        assert ShutdownState.RUNNING.value == "running"
        assert ShutdownState.DRAINING.value == "draining"
        assert ShutdownState.SHUTTING_DOWN.value == "shutting_down"
        assert ShutdownState.TERMINATED.value == "terminated"


@pytest.mark.asyncio
class TestAsyncShutdown:
    """测试异步关闭流程"""

    async def test_wait_for_connections_drain_empty(self):
        """测试等待无连接时立即返回"""
        manager = GracefulShutdownManager()
        result = await manager.wait_for_connections_drain(timeout=1)
        assert result is True

    async def test_wait_for_connections_drain_with_timeout(self):
        """测试等待连接超时"""
        manager = GracefulShutdownManager()
        manager.increment_connections()
        manager.increment_connections()

        result = await manager.wait_for_connections_drain(timeout=1)
        assert result is False
