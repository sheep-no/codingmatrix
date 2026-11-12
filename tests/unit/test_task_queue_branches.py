from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, WebSocketDisconnect

from app.api.v1 import task_queue
from app.services.unified_state_service import (
    StateConflictError,
    StateNotFoundError,
    StateOwnershipError,
)


class _Result:
    def __init__(self, record=None, rows=None, scalar_value=None):
        self._record = record
        self._rows = rows or []
        self._scalar = scalar_value

    def scalar_one_or_none(self):
        return self._record

    def scalar(self):
        return self._scalar

    def scalars(self):
        return SimpleNamespace(all=lambda: self._rows)


class _DB:
    def __init__(self, results=()):
        self._results = list(results)
        self.commits = 0
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, stmt):
        return self._results.pop(0)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        obj.created_at = datetime(2026, 1, 1)


def _task(**overrides):
    base = {
        "task_id": "t1",
        "user_id": 7,
        "task_type": "code_generate",
        "status": "running",
        "celery_task_id": "c1",
        "priority": 5,
        "timeout": 300,
        "max_retries": 3,
        "progress": 0,
        "progress_message": None,
        "result": None,
        "error_message": None,
        "retry_count": 0,
        "parent_task_id": None,
        "created_at": None,
        "started_at": None,
        "completed_at": None,
        "params": {},
        "worker_id": "w1",
        "lease_until": datetime(2026, 1, 1),
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_get_task_maps_not_found_and_ownership_errors():
    with patch.object(task_queue, "get_owned_task", AsyncMock(side_effect=StateNotFoundError("gone"))):
        with pytest.raises(HTTPException) as exc:
            await task_queue.get_task("t1", {"sub": "7"}, _DB())
    assert exc.value.status_code == 404

    with patch.object(task_queue, "get_owned_task", AsyncMock(side_effect=StateOwnershipError("no"))):
        with pytest.raises(HTTPException) as exc:
            await task_queue.get_task("t1", {"sub": "7"}, _DB())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_task_without_celery_id_returns_persisted_state():
    record = _task(status="success", celery_task_id=None, progress=100, progress_message="done")
    with patch.object(task_queue, "get_owned_task", AsyncMock(return_value=record)):
        response = await task_queue.get_task("t1", {"sub": "7"}, _DB())
    assert response.status == "success"
    assert response.progress == 100
    assert response.progress_message == "done"


@pytest.mark.asyncio
async def test_get_task_merges_celery_info_progress_and_message():
    record = _task(status="running", progress=10, progress_message="old")

    class _AsyncResult:
        state = "STARTED"
        info = {"progress": 55, "message": "halfway"}

    with patch.object(task_queue, "get_owned_task", AsyncMock(return_value=record)), \
            patch.object(task_queue.celery_app, "AsyncResult", return_value=_AsyncResult()):
        response = await task_queue.get_task("t1", {"sub": "7"}, _DB())
    assert response.status == "running"
    assert response.progress == 55
    assert response.progress_message == "halfway"


@pytest.mark.asyncio
async def test_get_task_events_serialises_and_maps_errors():
    event = SimpleNamespace(
        sequence=3, event_type="progress", status="running", progress=40,
        payload_json='{"x":1}', created_at=datetime(2026, 1, 1),
    )
    with patch.object(task_queue, "replay_task_events", AsyncMock(return_value=[event])):
        payload = await task_queue.get_task_events("t1", 1, 10, {"sub": "7"}, _DB())
    assert payload["after_sequence"] == 1
    assert payload["events"][0]["created_at"] == "2026-01-01T00:00:00"

    for error, status in (
        (StateNotFoundError("gone"), 404),
        (StateOwnershipError("no"), 403),
    ):
        with patch.object(task_queue, "replay_task_events", AsyncMock(side_effect=error)):
            with pytest.raises(HTTPException) as exc:
                await task_queue.get_task_events("t1", 0, 500, {"sub": "7"}, _DB())
        assert exc.value.status_code == status


@pytest.mark.asyncio
async def test_heartbeat_returns_lease_and_maps_conflicts():
    record = _task()
    db = _DB()
    with patch.object(task_queue, "heartbeat_task", AsyncMock(return_value=record)):
        payload = await task_queue.task_heartbeat("t1", "w1", 60, {"sub": "7"}, db)
    assert payload["worker_id"] == "w1"
    assert db.commits == 1

    for error, status in (
        (StateNotFoundError("gone"), 404),
        (StateOwnershipError("no"), 403),
        (StateConflictError("terminal"), 409),
    ):
        with patch.object(task_queue, "heartbeat_task", AsyncMock(side_effect=error)):
            with pytest.raises(HTTPException) as exc:
                await task_queue.task_heartbeat("t1", "w1", 60, {"sub": "7"}, _DB())
        assert exc.value.status_code == status


@pytest.mark.asyncio
async def test_list_tasks_applies_filters_and_serialises_rows():
    row = _task(status="pending", created_at=datetime(2026, 2, 2), started_at=datetime(2026, 2, 2))
    db = _DB([_Result(scalar_value=1), _Result(rows=[row])])
    response = await task_queue.list_tasks(
        2, 10, "pending", "code_generate", {"sub": "7"}, db
    )
    assert response.total == 1
    assert response.page == 2
    assert response.tasks[0].created_at == "2026-02-02T00:00:00"

    db = _DB([_Result(scalar_value=None), _Result(rows=[])])
    response = await task_queue.list_tasks(1, 20, None, None, {"sub": "7"}, db)
    assert response.total == 0
    assert response.tasks == []


@pytest.mark.asyncio
async def test_cancel_task_errors_and_without_celery_id():
    missing = _DB([_Result(record=None)])
    with pytest.raises(HTTPException) as exc:
        await task_queue.cancel_task("t1", {"sub": "7"}, missing)
    assert exc.value.status_code == 404

    other = _task(user_id=99)
    with pytest.raises(HTTPException) as exc:
        await task_queue.cancel_task("t1", {"sub": "7"}, _DB([_Result(record=other)]))
    assert exc.value.status_code == 403

    terminal = _task(status="success")
    with pytest.raises(HTTPException) as exc:
        await task_queue.cancel_task("t1", {"sub": "7"}, _DB([_Result(record=terminal)]))
    assert exc.value.status_code == 400

    record = _task(status="pending", celery_task_id=None)
    db = _DB([_Result(record=record)])
    with patch.object(task_queue, "append_task_event", AsyncMock()):
        await task_queue.cancel_task("t1", {"sub": "7"}, db)
    assert record.status == "cancelled"
    assert record.completed_at is not None
    assert db.commits == 1


@pytest.mark.asyncio
async def test_retry_task_error_paths():
    with pytest.raises(HTTPException) as exc:
        await task_queue.retry_task("t1", {"sub": "7"}, _DB([_Result(record=None)]))
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await task_queue.retry_task("t1", {"sub": "7"}, _DB([_Result(record=_task(user_id=99))]))
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await task_queue.retry_task("t1", {"sub": "7"}, _DB([_Result(record=_task(status="running"))]))
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_retry_task_serialises_response_when_record_has_timestamps():
    record = _task(
        status="failed", created_at=datetime(2026, 3, 3),
        started_at=datetime(2026, 3, 3), completed_at=datetime(2026, 3, 3),
    )
    with patch.object(task_queue.celery_app, "send_task", return_value=SimpleNamespace(id="c-new")):
        response = await task_queue.retry_task("t1", {"sub": "7"}, _DB([_Result(record=record)]))
    assert response.status == "pending"
    assert response.celery_task_id == "c-new"
    assert response.progress_message == "等待重试..."


@pytest.mark.asyncio
async def test_recover_task_rejects_non_recoverable_and_maps_state_errors():
    with patch.object(task_queue, "get_owned_task", AsyncMock(return_value=_task(status="running"))):
        with pytest.raises(HTTPException) as exc:
            await task_queue.recover_task("t1", {"sub": "7"}, _DB())
    assert exc.value.status_code == 400

    for error, status in (
        (StateNotFoundError("gone"), 404),
        (StateOwnershipError("no"), 403),
        (StateConflictError("conflict"), 409),
    ):
        with patch.object(task_queue, "get_owned_task", AsyncMock(side_effect=error)):
            with pytest.raises(HTTPException) as exc:
                await task_queue.recover_task("t1", {"sub": "7"}, _DB())
        assert exc.value.status_code == status


class _WS:
    def __init__(self, messages):
        self.query_params = {}
        self._messages = list(messages)
        self.sent = []
        self.closed = None

    async def close(self, code=1000, reason=""):
        self.closed = (code, reason)

    async def receive_text(self):
        if not self._messages:
            raise WebSocketDisconnect()
        item = self._messages.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def send_text(self, data):
        self.sent.append(data)


@pytest.mark.asyncio
async def test_websocket_ping_pong_then_disconnect(monkeypatch):
    manager = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    monkeypatch.setattr(task_queue, "ws_manager", manager)
    monkeypatch.setattr(
        task_queue, "verify_token_ws", AsyncMock(return_value=(True, {"sub": "7"}, None, None))
    )
    websocket = _WS(["ping", "other"])

    await task_queue.task_websocket(websocket, 7)

    assert websocket.sent == ["pong"]
    manager.connect.assert_awaited_once()
    manager.disconnect.assert_awaited_once_with(7)


@pytest.mark.asyncio
async def test_websocket_rejects_invalid_token_with_fallback_code(monkeypatch):
    manager = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    monkeypatch.setattr(task_queue, "ws_manager", manager)
    monkeypatch.setattr(
        task_queue, "verify_token_ws", AsyncMock(return_value=(False, None, None, None))
    )
    websocket = _WS([])

    await task_queue.task_websocket(websocket, 7)

    assert websocket.closed == (1008, "未授权")
    manager.connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_websocket_rejects_token_for_another_user(monkeypatch):
    manager = SimpleNamespace(connect=AsyncMock(), disconnect=AsyncMock())
    monkeypatch.setattr(task_queue, "ws_manager", manager)
    monkeypatch.setattr(
        task_queue, "verify_token_ws", AsyncMock(return_value=(True, {"sub": "8"}, None, None))
    )
    websocket = _WS([])

    await task_queue.task_websocket(websocket, 7)

    assert websocket.closed == (1008, "无权订阅其他用户的任务")
    manager.connect.assert_not_awaited()


def test_build_task_kwargs_covers_all_branches():
    assert task_queue._build_task_kwargs("project_generate", "t", 1, None)["requirement"] == ""
    code = task_queue._build_task_kwargs("code_generate", "t", 1, {})
    assert code["prompt"] == "" and code["language"] == "python"
    modify = task_queue._build_task_kwargs("modify_with_test", "t", 1, {})
    assert modify["target_files"] is None
    assert task_queue._build_task_kwargs("unknown", "t", 1, {}) == {"task_id": "t", "user_id": 1}


def test_merge_runtime_state_uses_persisted_progress_when_info_missing():
    record = _task(status="running", progress=30, progress_message=None)
    assert task_queue._merge_task_runtime_state(record, None, "not-a-dict") == ("running", 30, "")
    assert task_queue._merge_task_runtime_state(record, "SUCCESS", {"progress": "n/a", "message": ""}) == (
        "success", 30, ""
    )


@pytest.mark.asyncio
async def test_create_task_rejects_supported_schema_value_missing_from_registry():
    body = SimpleNamespace(
        task_type=SimpleNamespace(value="legacy_task"),
        priority=SimpleNamespace(value="medium"),
        timeout=300,
        params={},
        input_file_id=None,
        parent_task_id=None,
    )

    with pytest.raises(HTTPException) as exc:
        await task_queue.create_task(body, {"sub": "7"}, _DB())

    assert exc.value.status_code == 400
    assert "legacy_task" in exc.value.detail
