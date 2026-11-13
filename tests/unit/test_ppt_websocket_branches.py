"""WebSocket branch coverage for the PPT progress endpoint."""

import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.api.v1 import aiGeneratorPptx as pptx
from app.main import app


USER_ID = "1"


class FakeSessionContext:
    def __init__(self, db=None):
        self.db = db or SimpleNamespace(
            execute=AsyncMock(),
            commit=AsyncMock(),
        )

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc):
        return False


@pytest.fixture
def client():
    yield TestClient(app)


def _auth(monkeypatch):
    monkeypatch.setattr(
        pptx, "verify_token_ws",
        AsyncMock(return_value=(True, {"sub": USER_ID}, 1000, "")),
    )
    monkeypatch.setattr(pptx, "_verify_ppt_owner", lambda *_args: None)


def _patch_manager(monkeypatch, infos):
    manager = MagicMock()
    manager.get_task_info_async = AsyncMock(side_effect=list(infos))
    monkeypatch.setattr("app.utils.task_manager.task_manager", manager)
    return manager


def _patch_events(monkeypatch, events=(), error=None):
    async def replay(*_args, **_kwargs):
        if error:
            raise error
        return list(events)

    monkeypatch.setattr("app.services.task_event_service.replay_task_events", replay)
    monkeypatch.setattr(pptx, "async_session", lambda: FakeSessionContext())


@pytest.mark.parametrize(
    ("valid", "payload"),
    [(False, None), (True, {})],
)
def test_websocket_rejects_invalid_token(client, monkeypatch, valid, payload):
    monkeypatch.setattr(
        pptx, "verify_token_ws",
        AsyncMock(return_value=(valid, payload, 1008, "bad")),
    )
    task_id = str(uuid.uuid4())
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
            ws.receive_json()


def test_websocket_rejects_foreign_owner(client, monkeypatch):
    from fastapi import HTTPException

    monkeypatch.setattr(
        pptx, "verify_token_ws",
        AsyncMock(return_value=(True, {"sub": USER_ID}, 1000, "")),
    )
    monkeypatch.setattr(
        pptx, "_verify_ppt_owner",
        MagicMock(side_effect=HTTPException(status_code=403, detail="无权访问")),
    )
    task_id = str(uuid.uuid4())
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
            ws.receive_json()


def test_websocket_success_sends_completed(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    _patch_manager(
        monkeypatch,
        [{"user_id": USER_ID, "status": "success", "progress": 100,
          "progress_message": "done", "result": {"ppt_id": "t1"}}],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        message = ws.receive_json()
    assert message["type"] == "completed"
    assert message["result"] == {"ppt_id": "t1"}


@pytest.mark.parametrize("status", ["failed", "cancelled"])
def test_websocket_failure_and_cancel(client, monkeypatch, status):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    _patch_manager(
        monkeypatch,
        [{"user_id": USER_ID, "status": status, "progress": 40,
          "progress_message": "stop", "error_message": "boom"}],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        message = ws.receive_json()
    assert message["type"] == "error"
    assert message["progress"] == 0.4


def test_websocket_progress_then_ping(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    _patch_manager(
        monkeypatch,
        [
            {"user_id": USER_ID, "status": "running", "progress": 10,
             "progress_message": "working"},
            {"user_id": USER_ID, "status": "success", "progress": 100,
             "progress_message": "done", "result": {}},
        ],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        progress = ws.receive_json()
        assert progress["type"] == "progress"
        ws.send_text("ping")
        assert ws.receive_text() == "pong"
        completed = ws.receive_json()
    assert completed["type"] == "completed"


def test_websocket_replays_events_and_snapshot(client, monkeypatch):
    _auth(monkeypatch)
    event = SimpleNamespace(
        event_type="progress",
        sequence=3,
        status="running",
        progress=30,
        payload_json={"step": "x"},
        created_at=None,
    )
    _patch_events(monkeypatch, events=[event])
    monkeypatch.setattr(
        "app.services.task_checkpoint_service.get_latest_checkpoint",
        AsyncMock(return_value=SimpleNamespace(
            revision=2, step="planning", state_json={"a": 1},
        )),
    )
    _patch_manager(
        monkeypatch,
        [{"user_id": USER_ID, "status": "success", "progress": 100,
          "progress_message": "done", "result": {}}],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(
        f"/api/v1/ws/ppt/{task_id}?token=x&after_sequence=9"
    ) as ws:
        replayed = ws.receive_json()
        completed = ws.receive_json()
    assert replayed["sequence"] == 3
    assert completed["type"] == "completed"


def test_websocket_sends_checkpoint_snapshot(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    monkeypatch.setattr(
        "app.services.task_checkpoint_service.get_latest_checkpoint",
        AsyncMock(return_value=SimpleNamespace(
            revision=2, step="planning", state_json={"a": 1},
        )),
    )
    _patch_manager(
        monkeypatch,
        [{"user_id": USER_ID, "status": "success", "progress": 100,
          "progress_message": "done", "result": {}}],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(
        f"/api/v1/ws/ppt/{task_id}?token=x&after_sequence=9"
    ) as ws:
        snapshot = ws.receive_json()
        completed = ws.receive_json()
    assert snapshot["type"] == "snapshot_recovery"
    assert snapshot["revision"] == 2
    assert completed["type"] == "completed"


def test_websocket_snapshot_falls_back_to_record(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    _patch_manager(monkeypatch, [None])
    record = SimpleNamespace(
        task_id="t1",
        status="success",
        progress=100,
        progress_message="done",
        result={"ok": True},
        result_json=None,
        error_message=None,
    )
    result = SimpleNamespace(scalar_one_or_none=lambda: record)
    db = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock())
    monkeypatch.setattr(pptx, "async_session", lambda: FakeSessionContext(db))
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        message = ws.receive_json()
    assert message["type"] == "completed"
    assert message["result"] == {"ok": True}


def test_websocket_missing_task_sends_error(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    _patch_manager(monkeypatch, [None])
    record_result = SimpleNamespace(scalar_one_or_none=lambda: None)
    db = SimpleNamespace(execute=AsyncMock(return_value=record_result), commit=AsyncMock())
    monkeypatch.setattr(pptx, "async_session", lambda: FakeSessionContext(db))
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        message = ws.receive_json()
    assert message == {"type": "error", "error": "任务不存在"}


def test_websocket_event_replay_error_is_ignored(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch, error=RuntimeError("db down"))
    _patch_manager(
        monkeypatch,
        [{"user_id": USER_ID, "status": "success", "progress": 100,
          "progress_message": "done", "result": {}}],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        message = ws.receive_json()
    assert message["type"] == "completed"


def test_websocket_bad_after_sequence_defaults(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    _patch_manager(
        monkeypatch,
        [{"user_id": USER_ID, "status": "success", "progress": 100,
          "progress_message": "done", "result": {}}],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(
        f"/api/v1/ws/ppt/{task_id}?token=x&after_sequence=abc"
    ) as ws:
        message = ws.receive_json()
    assert message["type"] == "completed"


def test_websocket_unexpected_error_sends_error(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    _patch_manager(monkeypatch, [RuntimeError("boom")])
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        message = ws.receive_json()
    assert message["type"] == "error"
    assert message["error"] == "服务器发生错误，请稍后重试"


def test_websocket_disconnect_is_handled(client, monkeypatch):
    _auth(monkeypatch)
    _patch_events(monkeypatch)
    _patch_manager(
        monkeypatch,
        [{"user_id": USER_ID, "status": "running", "progress": 10,
          "progress_message": "working"}],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        ws.receive_json()
        ws.close()
    assert json.dumps({"ok": True})


class _FailingSocket:
    """Socket whose sends and close both raise, mimicking a dropped connection."""

    def __init__(self):
        self.query_params = {}
        self.accept = AsyncMock()
        self.send_json = AsyncMock(side_effect=RuntimeError("发送失败"))
        self.close = AsyncMock(side_effect=RuntimeError("已关闭"))
        self.receive_text = AsyncMock(side_effect=RuntimeError("boom"))


@pytest.mark.asyncio
async def test_websocket_error_and_close_failures_are_swallowed(monkeypatch):
    task_id = str(uuid.uuid4())
    monkeypatch.setattr(
        pptx, "verify_token_ws",
        AsyncMock(return_value=(True, {"sub": USER_ID}, 1000, "")),
    )
    monkeypatch.setattr(pptx, "_verify_ppt_owner", lambda *_args: None)
    _patch_events(monkeypatch)
    _patch_manager(monkeypatch, [RuntimeError("boom")])

    socket = _FailingSocket()
    await pptx.ppt_progress_websocket(socket, task_id)

    assert socket.send_json.await_count >= 1
    assert socket.close.await_count == 1
