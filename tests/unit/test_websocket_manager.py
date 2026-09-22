"""WebSocketManager 连接回收与限额行为回归。"""

import pytest
from fastapi import WebSocketDisconnect

from app.services.websocket_manager import WebSocketManager


def test_global_manager_uses_configured_limit():
    """CFG3：全局管理器上限取自 settings.WS_MAX_CONNECTIONS，而非硬编码默认。"""
    from app.core.config import settings
    from app.services.websocket_manager import ws_manager

    assert ws_manager._max_connections == settings.WS_MAX_CONNECTIONS


class _FakeWebSocket:
    def __init__(self, fail_send: bool = False):
        self.accepted = False
        self.closed_code = None
        self.sent = []
        self._fail_send = fail_send

    async def accept(self):
        self.accepted = True

    async def close(self, code: int = 1000, reason: str = None):
        self.closed_code = code

    async def send_json(self, message):
        if self._fail_send:
            raise RuntimeError("connection lost")
        self.sent.append(message)


@pytest.mark.asyncio
async def test_connect_rejects_over_limit_without_accepting():
    manager = WebSocketManager(max_connections=1)
    first = _FakeWebSocket()
    await manager.connect(1, first)
    assert first.accepted is True

    second = _FakeWebSocket()
    with pytest.raises(WebSocketDisconnect):
        await manager.connect(2, second)

    # 超限连接应在握手期以 1013 拒绝，且不进入连接表
    assert second.closed_code == 1013
    assert manager.get_connection_count() == 1


@pytest.mark.asyncio
async def test_broadcast_cleans_up_failed_connections():
    manager = WebSocketManager()
    healthy = _FakeWebSocket()
    broken = _FakeWebSocket(fail_send=True)
    await manager.connect(1, healthy)
    await manager.connect(2, broken)

    await manager.broadcast({"type": "ping"})

    # 发送失败的连接应与 send_personal_message 一样被回收
    assert healthy.sent == [{"type": "ping"}]
    assert manager.get_connection_count() == 1
    assert manager.is_connected(1) is True
    assert manager.is_connected(2) is False


def test_max_connections_property_exposes_limit():
    assert WebSocketManager(max_connections=3).max_connections == 3
