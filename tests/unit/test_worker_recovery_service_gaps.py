"""worker_recovery_service 重试耗尽与未知任务类型分支补测。"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.services import worker_recovery_service


def _task(**kwargs):
    base = dict(
        task_id="task-1",
        task_type="ppt_generation",
        status="running",
        lease_until=datetime.utcnow() - timedelta(seconds=1),
        retry_count=0,
        max_retries=3,
        params={},
        user_id=1,
        updated_at=datetime.utcnow(),
        error_message=None,
        celery_task_id=None,
    )
    base.update(kwargs)
    return type("Task", (), base)()


def _db(tasks):
    db = AsyncMock()
    db.scalars = AsyncMock(return_value=type("R", (), {"all": lambda self: tasks})())
    return db


async def test_exhausted_task_marked_failed(monkeypatch):
    task = _task(retry_count=3, max_retries=3)
    events = []

    async def record(_db, task_id, user_id, event, **kwargs):
        events.append((task_id, event, kwargs))

    monkeypatch.setattr(worker_recovery_service, "append_task_event", record)

    recovered = await worker_recovery_service.recover_expired_tasks(_db([task]))

    assert recovered == []
    assert task.status == "failed"
    assert task.error_message
    assert events[0][1] == "task.recovery_exhausted"


async def test_unknown_task_type_skipped(monkeypatch):
    task = _task(task_type="unknown")

    recovered = await worker_recovery_service.recover_expired_tasks(_db([task]))

    assert recovered == []
    assert task.status == "running"


async def test_limit_is_clamped(monkeypatch):
    db = _db([])
    await worker_recovery_service.recover_expired_tasks(db, limit=0)
    await worker_recovery_service.recover_expired_tasks(db, limit=5000)

    assert db.scalars.await_count == 2


async def test_recovery_writes_recovered_event(monkeypatch):
    task = _task()
    events = []

    async def record(_db, task_id, user_id, event, **kwargs):
        events.append((event, kwargs))

    monkeypatch.setattr(worker_recovery_service, "append_task_event", record)
    monkeypatch.setattr(
        worker_recovery_service.celery_app,
        "send_task",
        lambda *a, **k: type("R", (), {"id": "celery-2"})(),
    )

    recovered = await worker_recovery_service.recover_expired_tasks(_db([task]))

    assert recovered == ["task-1"]
    assert task.celery_task_id == "celery-2"
    assert events[0][0] == "task.recovered"
    assert events[0][1]["payload"]["reason"] == "lease_expired"
