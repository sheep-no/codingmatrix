"""任务状态 WebSocket 端点必须校验 token 并限制只能订阅本人任务。

/tasks/ws/{user_id} 原先零认证：任意连接者用可枚举的整数 user_id 即可订阅
他人任务推送。修复后握手需带 ?token=，且 token 主体必须与路径一致。
"""

import pytest
from fastapi import WebSocketDisconnect

from app.api.v1 import task_queue
from app.utils.security import create_access_token


class _FakeWebSocket:
    def __init__(self, token=None):
        self.query_params = {"token": token} if token is not None else {}
        self.closed = None
        self.accepted = False
        self.sent = []

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        raise WebSocketDisconnect()

    async def send_text(self, data):
        self.sent.append(data)


class _FakeWsManager:
    def __init__(self):
        self.connected = []
        self.disconnected = []

    async def connect(self, user_id, websocket):
        self.connected.append(user_id)

    async def disconnect(self, user_id):
        self.disconnected.append(user_id)


@pytest.fixture
def ws_manager(monkeypatch):
    fake = _FakeWsManager()
    monkeypatch.setattr(task_queue, "ws_manager", fake)
    return fake


@pytest.mark.asyncio
async def test_missing_token_rejected(ws_manager):
    websocket = _FakeWebSocket(token=None)

    await task_queue.task_websocket(websocket, 123)

    assert websocket.closed is not None
    assert websocket.closed[0] == 1008
    assert ws_manager.connected == []


@pytest.mark.asyncio
async def test_token_for_other_user_rejected(ws_manager):
    token = create_access_token(sub="456", permission_level="normal")
    websocket = _FakeWebSocket(token=token)

    await task_queue.task_websocket(websocket, 123)

    assert websocket.closed == (1008, "无权订阅其他用户的任务")
    assert ws_manager.connected == []


@pytest.mark.asyncio
async def test_matching_token_connects_and_disconnects(ws_manager):
    token = create_access_token(sub="123", permission_level="normal")
    websocket = _FakeWebSocket(token=token)

    await task_queue.task_websocket(websocket, 123)

    assert websocket.closed is None
    assert ws_manager.connected == [123]
    assert ws_manager.disconnected == [123]
