"""WebSocketManager 断开、点对点发送与统计补测。"""

import pytest

from app.services.websocket_manager import WebSocketManager, get_ws_manager


class _WS:
    def __init__(self, fail=False):
        self.fail = fail
        self.accepted = False
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def close(self, code=1000, reason=None):
        pass

    async def send_json(self, message):
        if self.fail:
            raise RuntimeError("gone")
        self.sent.append(message)


async def test_disconnect_unknown_user_noop():
    manager = WebSocketManager()
    await manager.disconnect(123)
    assert manager.get_connection_count() == 0


async def test_disconnect_all_connections_for_user():
    manager = WebSocketManager()
    await manager.connect(1, _WS())
    await manager.connect(1, _WS())
    await manager.disconnect(1)
    assert manager.is_connected(1) is False


async def test_disconnect_specific_connection_only():
    manager = WebSocketManager()
    first, second = _WS(), _WS()
    await manager.connect(1, first)
    await manager.connect(1, second)

    await manager.disconnect(1, first)

    assert manager.get_connection_count() == 1
    assert manager._connections[1][0].websocket is second


async def test_disconnect_specific_last_removes_user():
    manager = WebSocketManager()
    ws = _WS()
    await manager.connect(1, ws)

    await manager.disconnect(1, ws)

    assert 1 not in manager._connections


async def test_send_personal_message_without_connection():
    manager = WebSocketManager()
    await manager.send_personal_message(1, {"x": 1})
    assert manager.get_connection_count() == 0


async def test_send_personal_message_success_and_failure_cleanup():
    manager = WebSocketManager()
    ok, bad = _WS(), _WS(fail=True)
    await manager.connect(1, ok)
    await manager.connect(1, bad)

    await manager.send_personal_message(1, {"x": 1})

    assert ok.sent == [{"x": 1}]
    assert manager.get_connection_count() == 1


async def test_failed_cleanup_removes_user_when_no_connections_left():
    manager = WebSocketManager()
    bad = _WS(fail=True)
    await manager.connect(1, bad)

    await manager.send_personal_message(1, {"x": 1})

    assert 1 not in manager._connections


async def test_failed_cleanup_skips_removed_user(monkeypatch):
    manager = WebSocketManager()
    bad = _WS(fail=True)
    await manager.connect(1, bad)

    class RemovingLock:
        def __init__(self, inner):
            self.inner = inner

        async def __aenter__(self):
            await self.inner.acquire()
            manager._connections.pop(1, None)
            return self

        async def __aexit__(self, *exc):
            self.inner.release()
            return False

    await manager.send_personal_message(1, {"x": 1})

    # 正常路径已覆盖清理；此处再构造锁内已无该用户的场景
    manager2 = WebSocketManager()
    bad2 = _WS(fail=True)
    await manager2.connect(1, bad2)
    original_send = bad2.send_json

    async def send_then_remove(message):
        manager2._connections.pop(1, None)
        await original_send(message)

    bad2.send_json = send_then_remove
    await manager2.send_personal_message(1, {"x": 2})
    assert 1 not in manager2._connections


async def test_send_task_update_builds_message():
    manager = WebSocketManager()
    ws = _WS()
    await manager.connect(1, ws)

    await manager.send_task_update(1, "task-9", {"status": "done"})

    message = ws.sent[0]
    assert message["type"] == "task_update"
    assert message["task_id"] == "task-9"
    assert message["data"] == {"status": "done"}
    assert "timestamp" in message


async def test_broadcast_removes_user_when_last_connection_fails():
    manager = WebSocketManager()
    bad = _WS(fail=True)
    await manager.connect(1, bad)

    await manager.broadcast({"type": "ping"})

    assert 1 not in manager._connections


async def test_broadcast_ignores_already_removed_connection():
    manager = WebSocketManager()
    first = _WS(fail=True)
    second = _WS()
    await manager.connect(1, second)
    await manager.connect(2, first)

    async def remove_then_fail(message):
        manager._connections.pop(2, None)
        raise RuntimeError("gone")

    first.send_json = remove_then_fail

    await manager.broadcast({"type": "ping"})

    assert manager.get_connection_count() == 1


async def test_connection_stats_and_counts():
    manager = WebSocketManager(max_connections=2)
    await manager.connect(1, _WS())
    await manager.connect(2, _WS())

    assert manager.get_connection_count() == 2
    assert manager.get_user_count() == 2
    assert manager.is_connected(1) is True
    assert manager.is_connected(3) is False
    assert await manager.get_connection_info() == {
        "current": 2, "max": 2, "available": 0,
    }


async def test_connection_info_available_never_negative():
    manager = WebSocketManager(max_connections=1)
    await manager.connect(1, _WS())
    # 模拟并发下已有连接数超过上限的内部状态
    from app.services.websocket_manager import ConnectionInfo

    manager._connections[1].append(ConnectionInfo(websocket=_WS(), user_id=1))

    info = await manager.get_connection_info()

    assert info["current"] == 2
    assert info["available"] == 0


def test_get_ws_manager_returns_global():
    assert get_ws_manager() is get_ws_manager()


async def test_broadcast_without_failures_skips_cleanup():
    manager = WebSocketManager()
    first, second = _WS(), _WS()
    await manager.connect(1, first)
    await manager.connect(2, second)

    await manager.broadcast({"type": "ping"})

    assert first.sent == [{"type": "ping"}]
    assert second.sent == [{"type": "ping"}]
    assert manager.get_connection_count() == 2
