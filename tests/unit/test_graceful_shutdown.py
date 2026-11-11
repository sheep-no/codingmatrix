"""GracefulShutdownManager 生命周期与信号处理测试。"""

import asyncio
import signal

import pytest

from app.core import graceful_shutdown as gs
from app.core.graceful_shutdown import (
    GracefulShutdownManager,
    ShutdownState,
    get_shutdown_manager,
)


def _manager(**kwargs):
    return GracefulShutdownManager(**kwargs)


class TestStateAndConnections:
    def test_initial_state(self):
        manager = _manager(shutdown_timeout=12)

        assert manager.state is ShutdownState.RUNNING
        assert manager.is_running is True
        assert manager.is_draining is False
        assert manager.shutdown_timeout == 12

    def test_increment_and_decrement_connections(self):
        manager = _manager()
        manager.increment_connections()
        manager.increment_connections()
        assert manager.get_connections_inflight() == 2
        manager.decrement_connections()
        assert manager.get_connections_inflight() == 1
        manager.decrement_connections()
        manager.decrement_connections()
        assert manager.get_connections_inflight() == 0

    def test_hooks_are_registered(self):
        manager = _manager()
        pre = []
        post = []
        manager.register_pre_shutdown_hook(lambda: pre.append(1))
        manager.register_post_shutdown_hook(lambda: post.append(1))

        assert len(manager._pre_shutdown_hooks) == 1
        assert len(manager._post_shutdown_hooks) == 1

    def test_get_status_before_and_after_drain(self):
        manager = _manager()
        before = manager.get_status()
        assert before["state"] == "running"
        assert before["drain_start_time"] is None

        manager.initiate_shutdown()
        after = manager.get_status()

        assert after["state"] == "draining"
        assert after["is_draining"] is True
        assert after["drain_start_time"] is not None

    def test_initiate_shutdown_is_idempotent(self):
        manager = _manager()
        calls = []
        manager.register_pre_shutdown_hook(lambda: calls.append(1))

        manager.initiate_shutdown()
        manager.initiate_shutdown()

        assert calls == [1]
        assert manager.state is ShutdownState.DRAINING


class TestInitiateShutdownHooks:
    def test_sync_and_async_pre_hooks(self):
        manager = _manager()
        events = []

        async def async_hook():
            events.append("async")

        manager.register_pre_shutdown_hook(lambda: events.append("sync"))
        manager.register_pre_shutdown_hook(async_hook)

        async def run():
            manager.initiate_shutdown()
            await asyncio.sleep(0)

        asyncio.run(run())

        assert sorted(events) == ["async", "sync"]

    def test_failing_pre_hook_is_logged(self, monkeypatch):
        manager = _manager()
        errors = []
        monkeypatch.setattr(gs.logger, "error", lambda message: errors.append(message))

        def broken():
            raise RuntimeError("hook-fail")

        manager.register_pre_shutdown_hook(broken)
        manager.initiate_shutdown()

        assert errors == ["关闭前钩子执行失败: hook-fail"]


class TestWaitForDrain:
    def test_returns_true_when_no_connections(self):
        manager = _manager()

        assert asyncio.run(manager.wait_for_connections_drain()) is True

    def test_returns_true_after_connection_closes(self, monkeypatch):
        manager = _manager()
        manager.increment_connections()
        sleep_calls = []

        async def fake_sleep(delay):
            sleep_calls.append(delay)
            manager.decrement_connections()

        monkeypatch.setattr(gs.asyncio, "sleep", fake_sleep)

        assert asyncio.run(manager.wait_for_connections_drain()) is True
        assert sleep_calls == [0.5]

    def test_returns_false_on_timeout(self, monkeypatch):
        manager = _manager()
        manager.increment_connections()
        warnings = []
        times = iter([0.0, 10.0])
        monkeypatch.setattr(gs.logger, "warning", lambda message: warnings.append(message))
        monkeypatch.setattr(
            gs.asyncio, "get_running_loop",
            lambda: type("L", (), {"time": staticmethod(lambda: next(times))})(),
        )

        assert asyncio.run(manager.wait_for_connections_drain(1)) is False
        assert "等待连接关闭超时" in warnings[0]

    def test_explicit_zero_timeout_uses_default(self, monkeypatch):
        manager = _manager(shutdown_timeout=7)
        seen = []
        manager.increment_connections()
        times = iter([0.0, 8.0])
        monkeypatch.setattr(
            gs.asyncio, "get_running_loop",
            lambda: type("L", (), {"time": staticmethod(lambda: next(times))})(),
        )
        monkeypatch.setattr(gs.logger, "warning", lambda m: seen.append(m))

        assert asyncio.run(manager.wait_for_connections_drain(0)) is False
        assert "timeout=7s" in seen[0]


class TestDoShutdown:
    @pytest.mark.asyncio
    async def test_full_shutdown_sequence(self, monkeypatch):
        manager = _manager()
        events = []

        async def drain():
            events.append("drain")
            return True

        async def ws():
            events.append("ws")

        async def celery():
            events.append("celery")

        async def db():
            events.append("db")

        monkeypatch.setattr(manager, "wait_for_connections_drain", drain)
        monkeypatch.setattr(manager, "_close_websocket_connections", ws)
        monkeypatch.setattr(manager, "_close_celery_workers", celery)
        monkeypatch.setattr(manager, "_close_database_pool", db)
        manager.register_post_shutdown_hook(lambda: events.append("sync-post"))
        manager._shutdown_event = asyncio.Event()

        await manager._do_shutdown()

        assert events == ["drain", "ws", "celery", "db", "sync-post"]
        assert manager.state is ShutdownState.TERMINATED
        assert manager._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_shutdown_stops_when_already_terminated(self, monkeypatch):
        manager = _manager()
        manager._state = ShutdownState.TERMINATED
        called = []
        monkeypatch.setattr(manager, "wait_for_connections_drain", lambda: called.append(1))

        await manager._do_shutdown()

        assert called == []

    @pytest.mark.asyncio
    async def test_drain_timeout_is_logged(self, monkeypatch):
        manager = _manager()
        warnings = []
        monkeypatch.setattr(gs.logger, "warning", lambda message: warnings.append(message))

        async def slow_drain():
            return False

        async def noop():
            return None

        monkeypatch.setattr(manager, "wait_for_connections_drain", slow_drain)
        monkeypatch.setattr(manager, "_close_websocket_connections", noop)
        monkeypatch.setattr(manager, "_close_celery_workers", noop)
        monkeypatch.setattr(manager, "_close_database_pool", noop)
        manager._shutdown_event = asyncio.Event()

        await manager._do_shutdown()

        assert "部分连接未能正常关闭，强制终止" in warnings

    @pytest.mark.asyncio
    async def test_async_post_hook_and_failures(self, monkeypatch):
        manager = _manager()
        events = []
        errors = []
        monkeypatch.setattr(gs.logger, "error", lambda message: errors.append(message))

        async def async_hook():
            events.append("async-post")

        def broken():
            raise RuntimeError("post-fail")

        async def noop():
            return None

        monkeypatch.setattr(manager, "wait_for_connections_drain", noop)
        monkeypatch.setattr(manager, "_close_websocket_connections", noop)
        monkeypatch.setattr(manager, "_close_celery_workers", noop)
        monkeypatch.setattr(manager, "_close_database_pool", noop)
        manager.register_post_shutdown_hook(async_hook)
        manager.register_post_shutdown_hook(broken)
        manager._shutdown_event = asyncio.Event()

        await manager._do_shutdown()

        assert events == ["async-post"]
        assert errors == ["关闭后钩子执行失败: post-fail"]


class TestCloseResources:
    @pytest.mark.asyncio
    async def test_websocket_with_connections(self, monkeypatch):
        manager = _manager(websocket_drain_timeout=0)
        import app.services.websocket_manager as ws_module

        class FakeManager:
            def get_connection_count(self):
                return 3

        monkeypatch.setattr(ws_module, "get_ws_manager", lambda: FakeManager())

        await manager._close_websocket_connections()

    @pytest.mark.asyncio
    async def test_websocket_without_connections(self, monkeypatch):
        manager = _manager()
        import app.services.websocket_manager as ws_module

        class FakeManager:
            def get_connection_count(self):
                return 0

        monkeypatch.setattr(ws_module, "get_ws_manager", lambda: FakeManager())

        await manager._close_websocket_connections()

    @pytest.mark.asyncio
    async def test_websocket_failure_is_logged(self, monkeypatch):
        manager = _manager()
        errors = []
        monkeypatch.setattr(gs.logger, "error", lambda message: errors.append(message))

        def boom():
            raise RuntimeError("ws-fail")

        import app.services.websocket_manager as ws_module
        monkeypatch.setattr(ws_module, "get_ws_manager", boom)

        await manager._close_websocket_connections()

        assert errors == ["关闭 WebSocket 连接失败: ws-fail"]

    @pytest.mark.asyncio
    async def test_celery_shutdown(self, monkeypatch):
        manager = _manager()
        calls = []
        import app.celery_app as celery_module

        class FakeControl:
            def shutdown(self, graceful):
                calls.append(graceful)

        class FakeCelery:
            control = FakeControl()

        monkeypatch.setattr(celery_module, "celery_app", FakeCelery())

        await manager._close_celery_workers()

        assert calls == [True]

    @pytest.mark.asyncio
    async def test_celery_absent_is_skipped(self, monkeypatch):
        manager = _manager()
        import app.celery_app as celery_module
        monkeypatch.setattr(celery_module, "celery_app", None)

        await manager._close_celery_workers()

    @pytest.mark.asyncio
    async def test_celery_failure_is_warned(self, monkeypatch):
        manager = _manager()
        warnings = []
        monkeypatch.setattr(gs.logger, "warning", lambda message: warnings.append(message))
        import app.celery_app as celery_module

        class FakeControl:
            def shutdown(self, graceful):
                raise RuntimeError("celery-fail")

        class FakeCelery:
            control = FakeControl()

        monkeypatch.setattr(celery_module, "celery_app", FakeCelery())

        await manager._close_celery_workers()

        assert "Celery 关闭失败" in warnings[0]

    @pytest.mark.asyncio
    async def test_database_pool_dispose(self, monkeypatch):
        manager = _manager()
        disposed = []
        import app.db.database as db_module

        class FakeEngine:
            async def dispose(self):
                disposed.append(True)

        monkeypatch.setattr(db_module, "engine", FakeEngine())

        await manager._close_database_pool()

        assert disposed == [True]

    @pytest.mark.asyncio
    async def test_database_pool_absent_is_skipped(self, monkeypatch):
        manager = _manager()
        import app.db.database as db_module
        monkeypatch.setattr(db_module, "engine", None)

        await manager._close_database_pool()

    @pytest.mark.asyncio
    async def test_database_pool_failure_is_logged(self, monkeypatch):
        manager = _manager()
        errors = []
        monkeypatch.setattr(gs.logger, "error", lambda message: errors.append(message))
        import app.db.database as db_module

        class FakeEngine:
            async def dispose(self):
                raise RuntimeError("db-fail")

        monkeypatch.setattr(db_module, "engine", FakeEngine())

        await manager._close_database_pool()

        assert errors == ["关闭数据库连接池失败: db-fail"]


class TestShutdownEntry:
    @pytest.mark.asyncio
    async def test_shutdown_async_creates_event_and_terminates(self, monkeypatch):
        manager = _manager()

        async def noop():
            return None

        monkeypatch.setattr(manager, "wait_for_connections_drain", noop)
        monkeypatch.setattr(manager, "_close_websocket_connections", noop)
        monkeypatch.setattr(manager, "_close_celery_workers", noop)
        monkeypatch.setattr(manager, "_close_database_pool", noop)

        await manager.shutdown_async()

        assert manager.state is ShutdownState.TERMINATED
        assert manager._shutdown_event is not None

    @pytest.mark.asyncio
    async def test_shutdown_async_reuses_existing_event(self, monkeypatch):
        manager = _manager()
        existing = asyncio.Event()
        manager._shutdown_event = existing

        async def noop():
            return None

        monkeypatch.setattr(manager, "wait_for_connections_drain", noop)
        monkeypatch.setattr(manager, "_close_websocket_connections", noop)
        monkeypatch.setattr(manager, "_close_celery_workers", noop)
        monkeypatch.setattr(manager, "_close_database_pool", noop)

        await manager.shutdown_async()

        assert manager._shutdown_event is existing
        assert existing.is_set()


class TestSignalHandlers:
    def test_asyncio_mode_registers_handlers(self, monkeypatch):
        manager = _manager()
        registered = []

        class FakeLoop:
            def add_signal_handler(self, sig, handler):
                registered.append((sig, handler))

        monkeypatch.setattr(gs.asyncio, "get_running_loop", lambda: FakeLoop())

        manager.setup_signal_handlers()

        assert [sig for sig, _ in registered] == [signal.SIGTERM, signal.SIGINT]

    def test_signal_mode_fallback(self, monkeypatch):
        manager = _manager()
        installed = []

        def fake_get_loop():
            raise RuntimeError("no loop")

        def fake_signal(sig, handler):
            installed.append((sig, handler))
            return signal.SIG_DFL

        monkeypatch.setattr(gs.asyncio, "get_running_loop", fake_get_loop)
        monkeypatch.setattr(gs.signal, "signal", fake_signal)

        manager.setup_signal_handlers()

        assert [sig for sig, _ in installed] == [signal.SIGTERM, signal.SIGINT]
        manager.initiate_shutdown()
        assert manager.state is ShutdownState.DRAINING

    def test_signal_mode_handlers_trigger_shutdown(self, monkeypatch):
        manager = _manager()
        installed = {}
        monkeypatch.setattr(
            gs.asyncio, "get_running_loop",
            lambda: (_ for _ in ()).throw(RuntimeError("no loop")),
        )
        monkeypatch.setattr(
            gs.signal, "signal",
            lambda sig, handler: installed.setdefault(sig, handler) and signal.SIG_DFL,
        )
        manager.setup_signal_handlers()

        installed[signal.SIGTERM](signal.SIGTERM, None)
        assert manager.state is ShutdownState.DRAINING

    def test_signal_mode_sigint_triggers_shutdown(self, monkeypatch):
        manager = _manager()
        installed = {}
        monkeypatch.setattr(
            gs.asyncio, "get_running_loop",
            lambda: (_ for _ in ()).throw(RuntimeError("no loop")),
        )
        monkeypatch.setattr(
            gs.signal, "signal",
            lambda sig, handler: installed.setdefault(sig, handler) and signal.SIG_DFL,
        )
        manager.setup_signal_handlers()

        installed[signal.SIGINT](signal.SIGINT, None)
        assert manager.state is ShutdownState.DRAINING

    def test_restore_handlers_when_original_present(self, monkeypatch):
        manager = _manager()
        manager._original_sigterm_handler = signal.SIG_IGN
        manager._original_sigint_handler = signal.SIG_IGN
        restored = []
        monkeypatch.setattr(gs.signal, "signal", lambda sig, handler: restored.append((sig, handler)))

        manager.restore_signal_handlers()

        assert [sig for sig, _ in restored] == [signal.SIGTERM, signal.SIGINT]

    def test_restore_handlers_skips_missing_originals(self, monkeypatch):
        manager = _manager()
        restored = []
        monkeypatch.setattr(gs.signal, "signal", lambda sig, handler: restored.append(sig))

        manager.restore_signal_handlers()

        assert restored == []

    def test_restore_sigterm_with_default_handler(self, monkeypatch):
        manager = _manager()
        manager._original_sigterm_handler = signal.SIG_DFL
        restored = []
        monkeypatch.setattr(gs.signal, "signal", lambda sig, handler: restored.append((sig, handler)))

        manager.restore_signal_handlers()

        assert restored == [(signal.SIGTERM, signal.SIG_DFL)]

    def test_handle_sigterm_schedules_shutdown(self, monkeypatch):
        manager = _manager()
        scheduled = []
        monkeypatch.setattr(gs.asyncio, "ensure_future", lambda coro: scheduled.append(coro))

        manager._handle_sigterm()

        assert manager.state is ShutdownState.DRAINING
        assert manager._shutdown_event is not None
        assert len(scheduled) == 1
        scheduled[0].close()

    def test_handle_sigterm_keeps_existing_event(self, monkeypatch):
        manager = _manager()
        existing = asyncio.Event()
        manager._shutdown_event = existing
        monkeypatch.setattr(gs.asyncio, "ensure_future", lambda coro: coro.close())

        manager._handle_sigterm()

        assert manager._shutdown_event is existing

    def test_handle_sigint_schedules_shutdown(self, monkeypatch):
        manager = _manager()
        scheduled = []
        monkeypatch.setattr(gs.asyncio, "ensure_future", lambda coro: scheduled.append(coro))

        manager._handle_sigint()

        assert manager.state is ShutdownState.DRAINING
        assert len(scheduled) == 1
        scheduled[0].close()

    def test_handle_sigint_keeps_existing_event(self, monkeypatch):
        manager = _manager()
        existing = asyncio.Event()
        manager._shutdown_event = existing
        monkeypatch.setattr(gs.asyncio, "ensure_future", lambda coro: coro.close())

        manager._handle_sigint()

        assert manager._shutdown_event is existing


def test_get_shutdown_manager_is_singleton(monkeypatch):
    monkeypatch.setattr(gs, "_shutdown_manager_instance", None)

    first = get_shutdown_manager()
    second = get_shutdown_manager()

    assert first is second
