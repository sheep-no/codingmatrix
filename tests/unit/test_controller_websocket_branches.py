"""app/api/v2/Controller.py 的 WebSocket 与监控分支覆盖。"""

import asyncio
import json
import types

import pytest
from starlette.websockets import WebSocketDisconnect

from app.api.v2 import Controller as ctl


class FakeWebSocket:
    def __init__(self, client=types.SimpleNamespace(host="1.2.3.4", port=9)):
        self.client = client
        self.accepted = False
        self.closed = []
        self.sent = []
        self.send_hook = None
        self.close_hook = None
        self.messages = []
        self.receive_gate = None

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=None):
        if self.close_hook:
            self.close_hook()
        self.closed.append((code, reason))

    async def send_json(self, payload):
        if self.send_hook:
            self.send_hook(payload)
        self.sent.append(payload)

    async def receive_text(self):
        if not self.messages:
            if self.receive_gate is not None:
                await self.receive_gate.wait()
            raise WebSocketDisconnect(code=1006, reason="gone")
        item = self.messages.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


def _token_result(valid=True, payload=None, code=None, reason=None):
    return valid, payload, code, reason


class TestPermissionHelper:
    @pytest.mark.parametrize(
        "level,expected",
        [("admin", True), ("superadmin", True), ("normal", False), ("unknown", False)],
    )
    def test_check_admin_permission(self, level, expected):
        assert ctl.check_admin_permission(level) is expected


class FakePool:
    def __init__(self, size=5, callable_size=False, missing=False):
        self.size = (lambda: size) if callable_size else size
        self._missing = missing

    def checkedin(self):
        return 2

    def checkedout(self):
        return 3

    def overflow(self):
        return 1


class FakeEngine:
    def __init__(self, pool=None):
        self.pool = pool or FakePool()


class TestPoolStats:
    @pytest.mark.asyncio
    async def test_callable_size_and_counters(self):
        stats = await ctl.get_db_pool_stats(FakeEngine(FakePool(callable_size=True)))

        assert stats == {
            "pool_size": 5,
            "checked_in": 2,
            "checked_out": 3,
            "overflow": 1,
            "invalidated": 0,
        }

    @pytest.mark.asyncio
    async def test_non_callable_size(self):
        stats = await ctl.get_db_pool_stats(FakeEngine(FakePool()))

        assert stats["pool_size"] == 5

    @pytest.mark.asyncio
    async def test_missing_counters_default_to_zero(self):
        class BarePool:
            size = 7

        stats = await ctl.get_db_pool_stats(FakeEngine(BarePool()))

        assert stats["checked_in"] == 0
        assert stats["checked_out"] == 0
        assert stats["overflow"] == 0

    @pytest.mark.asyncio
    async def test_failure_returns_zeroed_stats(self, monkeypatch):
        messages = []
        monkeypatch.setattr(ctl.logger, "debug", lambda message: messages.append(message))

        class Broken:
            @property
            def pool(self):
                raise RuntimeError("no pool")

        stats = await ctl.get_db_pool_stats(Broken())

        assert stats["pool_size"] == 0
        assert any("获取连接池统计失败" in message for message in messages)


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeConnection:
    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error

    async def execute(self, _statement):
        if self.error:
            raise self.error
        return self.result


class FakeConnectContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return False


class TestActiveQueries:
    @pytest.mark.asyncio
    async def test_sqlite(self):
        engine = types.SimpleNamespace(
            url="sqlite+aiosqlite:///db",
            connect=lambda: FakeConnectContext(FakeConnection(FakeResult(4))),
        )

        assert await ctl.get_active_queries(engine) == 4

    @pytest.mark.asyncio
    async def test_postgresql(self):
        engine = types.SimpleNamespace(
            url="postgresql+asyncpg://db",
            connect=lambda: FakeConnectContext(FakeConnection(FakeResult(2))),
        )

        assert await ctl.get_active_queries(engine) == 2

    @pytest.mark.asyncio
    async def test_other_dialect_returns_zero(self):
        engine = types.SimpleNamespace(
            url="mysql://db",
            connect=lambda: FakeConnectContext(FakeConnection(FakeResult(9))),
        )

        assert await ctl.get_active_queries(engine) == 0

    @pytest.mark.asyncio
    async def test_none_scalar_returns_zero(self):
        engine = types.SimpleNamespace(
            url="sqlite://",
            connect=lambda: FakeConnectContext(FakeConnection(FakeResult(None))),
        )

        assert await ctl.get_active_queries(engine) == 0

    @pytest.mark.asyncio
    async def test_failure_logs_and_returns_zero(self, monkeypatch):
        warnings = []
        monkeypatch.setattr(ctl.logger, "warning", lambda message: warnings.append(message))
        engine = types.SimpleNamespace(
            url="sqlite://",
            connect=lambda: FakeConnectContext(FakeConnection(error=RuntimeError("down"))),
        )

        assert await ctl.get_active_queries(engine) == 0
        assert any("查询活跃连接失败" in message for message in warnings)


class TestSysStatusSocket:
    @pytest.mark.asyncio
    async def test_rejects_invalid_token(self, monkeypatch):
        warnings = []
        socket = FakeWebSocket(client=None)

        async def verify(_token):
            return _token_result(False, None, 4001, "bad token")

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl.logger, "warning", lambda message: warnings.append(message))

        await ctl.controller(socket, token="abc")

        assert socket.accepted is False
        assert socket.closed == [(4001, "bad token")]
        assert any("WebSocket连接被拒绝" in message for message in warnings)

    @pytest.mark.asyncio
    async def test_rejects_non_admin(self, monkeypatch):
        warnings = []
        socket = FakeWebSocket()

        async def verify(_token):
            return _token_result(True, {"sub": "7", "permission_level": "normal"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl.logger, "warning", lambda message: warnings.append(message))

        await ctl.controller(socket, token="abc")

        assert socket.accepted is True
        assert socket.closed[0][0] == ctl.status.WS_1008_POLICY_VIOLATION
        assert any("权限不足拒绝连接" in message for message in warnings)

    @pytest.mark.asyncio
    async def test_send_runtime_error_breaks_loop(self, monkeypatch):
        socket = FakeWebSocket()
        socket.send_hook = lambda _payload: (_ for _ in ()).throw(RuntimeError("closed"))

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "get_system_stats", lambda: {"cpu": 1})

        await ctl.controller(socket, token="abc")

        assert socket.closed == [(1000, None)]
        assert socket.sent == []

    @pytest.mark.asyncio
    async def test_sleep_disconnect_after_successful_push(self, monkeypatch):
        socket = FakeWebSocket()

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        async def fake_sleep(_seconds):
            raise WebSocketDisconnect(code=1001, reason="bye")

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "get_system_stats", lambda: {"cpu": 2})
        monkeypatch.setattr(ctl.asyncio, "sleep", fake_sleep)

        await ctl.controller(socket, token="abc")

        assert socket.sent == [{"type": "system_stats", "data": {"cpu": 2}}]

    @pytest.mark.asyncio
    async def test_client_disconnect_logged(self, monkeypatch):
        socket = FakeWebSocket()
        messages = []

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        def stats():
            raise WebSocketDisconnect(code=1001, reason="bye")

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "get_system_stats", stats)
        monkeypatch.setattr(ctl.logger, "info", lambda message: messages.append(message))

        await ctl.controller(socket, token="abc")

        assert any("客户端主动断开" in message for message in messages)
        assert socket.closed == [(1000, None)]

    @pytest.mark.asyncio
    async def test_generic_error_logged(self, monkeypatch):
        socket = FakeWebSocket()
        errors = []

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        def stats():
            raise ValueError("bad stats")

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "get_system_stats", stats)
        monkeypatch.setattr(ctl.logger, "error", lambda *a, **k: errors.append(a))

        await ctl.controller(socket, token="abc")

        assert any("推送异常" in str(item) for item in errors)

    @pytest.mark.asyncio
    async def test_close_failure_swallowed(self, monkeypatch):
        socket = FakeWebSocket()
        debug = []

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        def stats():
            raise ValueError("bad stats")

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "get_system_stats", stats)
        monkeypatch.setattr(ctl.logger, "debug", lambda message: debug.append(message))
        socket.close_hook = lambda: (_ for _ in ()).throw(Exception("already closed"))

        await ctl.controller(socket, token="abc")

        assert any("连接已在别处关闭" in message for message in debug)


class FakeLogService:
    def __init__(self, lines=None, error=None):
        self.lines = lines or []
        self.error = error

    async def stream_logs_with_filter(self, log_type=None, filters=None):
        for line in self.lines:
            yield line
        if self.error:
            raise self.error


class FakeEngineForMonitor:
    dialect = types.SimpleNamespace(name="sqlite")
    pool = FakePool()
    url = "sqlite://"


class TestLogsSocket:
    @pytest.mark.asyncio
    async def test_rejects_invalid_token(self, monkeypatch):
        socket = FakeWebSocket(client=None)

        async def verify(_token):
            return _token_result(False, None, 4001, "nope")

        monkeypatch.setattr(ctl, "verify_token_ws", verify)

        await ctl.stream_logs_websocket(socket, token="abc")

        assert socket.closed == [(4001, "nope")]
        assert socket.accepted is False

    @pytest.mark.asyncio
    async def test_rejects_non_admin(self, monkeypatch):
        socket = FakeWebSocket()

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "normal"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)

        await ctl.stream_logs_websocket(socket, token="abc")

        assert socket.closed[0][0] == ctl.status.WS_1008_POLICY_VIOLATION

    @pytest.mark.asyncio
    async def test_handles_client_commands(self, monkeypatch):
        socket = FakeWebSocket()
        socket.messages = [
            json.dumps({"action": "ping"}),
            json.dumps({"action": "filter", "level": "ERROR", "keyword": "db"}),
            json.dumps({"action": "clear"}),
            json.dumps({"action": "unknown"}),
            "{not json",
            asyncio.TimeoutError(),
        ]

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=False)

        types_sent = [item["type"] for item in socket.sent]
        assert types_sent == ["pong", "status", "status", "error", "error", "ping"]

    @pytest.mark.asyncio
    async def test_ping_on_receive_timeout(self, monkeypatch):
        socket = FakeWebSocket()
        socket.messages = [asyncio.TimeoutError()]

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=False)

        assert {"type": "ping"} in socket.sent

    @pytest.mark.asyncio
    async def test_disconnect_logged(self, monkeypatch):
        socket = FakeWebSocket()
        messages = []

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())
        monkeypatch.setattr(ctl.logger, "info", lambda message: messages.append(message))

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=False)

        assert any("日志流客户端断开" in message for message in messages)

    @pytest.mark.asyncio
    async def test_generic_error_logged(self, monkeypatch):
        socket = FakeWebSocket()
        socket.messages = [ValueError("boom")]
        errors = []

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())
        monkeypatch.setattr(ctl.logger, "error", lambda *a, **k: errors.append(a))

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=False)

        assert any("日志流异常" in str(item) for item in errors)

    @pytest.mark.asyncio
    async def test_log_streamer_breaks_on_runtime_error(self, monkeypatch):
        socket = FakeWebSocket()

        def hook(payload):
            if payload["type"] == "log":
                raise RuntimeError("closed")

        socket.send_hook = hook

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService(lines=["line"]))

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=False)

        assert socket.closed == [(1000, None)]

    @pytest.mark.asyncio
    async def test_log_streamer_logs_generic_send_error(self, monkeypatch):
        socket = FakeWebSocket()
        errors = []

        def hook(payload):
            if payload["type"] == "log":
                raise OSError("broken pipe")

        socket.send_hook = hook

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService(lines=["line"]))
        monkeypatch.setattr(ctl.logger, "error", lambda message: errors.append(message))

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=False)

        assert any("日志流发送失败" in message for message in errors)

    @pytest.mark.asyncio
    async def test_db_monitor_pushes_status(self, monkeypatch):
        socket = FakeWebSocket()
        pushes = []

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        async def pool_stats(_engine):
            return {"pool_size": 1}

        async def active(_engine):
            return 2

        async def fake_sleep(_seconds):
            raise asyncio.CancelledError()

        class Process:
            def memory_info(self):
                return types.SimpleNamespace(rss=2 * 1024 * 1024)

            def cpu_percent(self):
                return 12.5

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())
        monkeypatch.setattr(ctl, "get_db_pool_stats", pool_stats)
        monkeypatch.setattr(ctl, "get_active_queries", active)
        monkeypatch.setattr(ctl.psutil, "Process", Process)
        monkeypatch.setattr(ctl.asyncio, "sleep", fake_sleep)
        monkeypatch.setitem(
            __import__("sys").modules,
            "app.db.database",
            types.SimpleNamespace(engine=FakeEngineForMonitor()),
        )

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=True)

        db_pushes = [p for p in pushes if p["type"] == "db_status"]
        assert db_pushes == []
        db_payloads = [p for p in socket.sent if p["type"] == "db_status"]
        assert db_payloads
        assert db_payloads[0]["data"]["memory_mb"] == 2.0
        assert db_payloads[0]["data"]["active_queries"] == 2

    @pytest.mark.asyncio
    async def test_db_monitor_applies_keyword_filter(self, monkeypatch):
        socket = FakeWebSocket()
        socket.receive_gate = asyncio.Event()
        socket.messages = [
            json.dumps({"action": "filter", "db_keyword": "absent"}),
        ]
        calls = {"count": 0}
        db_filtered = asyncio.Event()

        def send_hook(payload):
            if payload["type"] == "status":
                db_filtered.set()

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        async def pool_stats(_engine):
            calls["count"] += 1
            if calls["count"] == 1:
                await db_filtered.wait()
                return {}
            if calls["count"] > 1:
                socket.receive_gate.set()
                raise asyncio.CancelledError()
            return {}

        async def active(_engine):
            return 0

        async def fake_sleep(_seconds):
            return None

        class Process:
            def memory_info(self):
                return types.SimpleNamespace(rss=0)

            def cpu_percent(self):
                return 0

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())
        monkeypatch.setattr(ctl, "get_db_pool_stats", pool_stats)
        monkeypatch.setattr(ctl, "get_active_queries", active)
        monkeypatch.setattr(ctl.psutil, "Process", Process)
        monkeypatch.setattr(ctl.asyncio, "sleep", fake_sleep)
        socket.send_hook = send_hook
        monkeypatch.setitem(
            __import__("sys").modules,
            "app.db.database",
            types.SimpleNamespace(engine=FakeEngineForMonitor()),
        )

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=True)

        assert [p for p in socket.sent if p["type"] == "db_status"] == []

    @pytest.mark.asyncio
    async def test_finished_background_tasks_are_not_cancelled(self, monkeypatch):
        socket = FakeWebSocket()

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        class DoneTask:
            def done(self):
                return True

            def cancel(self):
                raise AssertionError("must not cancel finished task")

            def __await__(self):
                async def finished():
                    return None

                return finished().__await__()

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())
        def fake_create_task(coro):
            _close_coro(coro)
            return DoneTask()

        monkeypatch.setattr(ctl.asyncio, "create_task", fake_create_task)

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=True)

        assert socket.closed == [(1000, None)]

    @pytest.mark.asyncio
    async def test_close_runtime_error_swallowed(self, monkeypatch):
        socket = FakeWebSocket()

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        def close_hook():
            raise RuntimeError("closed")

        socket.close_hook = close_hook
        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=False)
    @pytest.mark.asyncio
    async def test_db_monitor_error_pushes_error_payload(self, monkeypatch):
        socket = FakeWebSocket()
        errors = []

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        async def broken(_engine):
            raise ValueError("no stats")

        async def fake_sleep(_seconds):
            raise asyncio.CancelledError()

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())
        monkeypatch.setattr(ctl, "get_db_pool_stats", broken)
        monkeypatch.setattr(ctl.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(ctl.logger, "error", lambda message: errors.append(message))
        monkeypatch.setitem(
            __import__("sys").modules,
            "app.db.database",
            types.SimpleNamespace(engine=FakeEngineForMonitor()),
        )

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=True)

        error_payloads = [p for p in socket.sent if p["type"] == "error"]
        assert error_payloads
        assert "DB监控错误" in error_payloads[0]["data"]
        assert any("数据库监控异常" in message for message in errors)

    @pytest.mark.asyncio
    async def test_db_monitor_keyword_match_still_pushes(self, monkeypatch):
        socket = FakeWebSocket()
        socket.receive_gate = asyncio.Event()
        socket.messages = [json.dumps({"action": "filter", "db_keyword": "sqlite"})]
        calls = {"count": 0}
        ready = asyncio.Event()

        def send_hook(payload):
            if payload["type"] == "status":
                ready.set()

        async def pool_stats(_engine):
            calls["count"] += 1
            if calls["count"] == 1:
                await ready.wait()
                return {}
            socket.receive_gate.set()
            raise asyncio.CancelledError()

        async def active(_engine):
            return 0

        class Process:
            def memory_info(self):
                return types.SimpleNamespace(rss=0)

            def cpu_percent(self):
                return 0

        async def fake_sleep(_seconds):
            return None

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())
        monkeypatch.setattr(ctl, "get_db_pool_stats", pool_stats)
        monkeypatch.setattr(ctl, "get_active_queries", active)
        monkeypatch.setattr(ctl.psutil, "Process", Process)
        monkeypatch.setattr(ctl.asyncio, "sleep", fake_sleep)
        socket.send_hook = send_hook
        monkeypatch.setitem(
            __import__("sys").modules,
            "app.db.database",
            types.SimpleNamespace(engine=FakeEngineForMonitor()),
        )

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=True)

        assert [p for p in socket.sent if p["type"] == "db_status"]

    @pytest.mark.asyncio
    async def test_pending_background_tasks_are_cancelled(self, monkeypatch):
        socket = FakeWebSocket()
        cancelled = []

        class PendingTask:
            def done(self):
                return False

            def cancel(self):
                cancelled.append(True)

            def __await__(self):
                async def raises():
                    raise asyncio.CancelledError()

                return raises().__await__()

        async def verify(_token):
            return _token_result(True, {"sub": "1", "permission_level": "admin"}, None, None)

        def fake_create_task(coro):
            coro.close()
            return PendingTask()

        monkeypatch.setattr(ctl, "verify_token_ws", verify)
        monkeypatch.setattr(ctl, "LogService", lambda: FakeLogService())
        monkeypatch.setattr(ctl.asyncio, "create_task", fake_create_task)

        await ctl.stream_logs_websocket(socket, token="abc", enable_db_monitor=True)

        assert cancelled == [True, True]


def _close_coro(coro):
    coro.close()
    return True
