from datetime import datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.services import worker_recovery_service


@pytest.mark.asyncio
async def test_recovery_service_requeues_expired_tasks(monkeypatch):
    db = AsyncMock()
    task = type("Task", (), {
        "task_id": "ppt-1",
        "task_type": "ppt_generation",
        "status": "running",
        "lease_until": datetime.utcnow() - timedelta(seconds=1),
        "retry_count": 0,
        "max_retries": 3,
        "params": {"request_data": {"topic": "test"}},
        "user_id": 7,
        "updated_at": datetime.utcnow(),
    })()
    scalar_result = type("ScalarResult", (), {"all": lambda self: [task]})()
    db.scalars = AsyncMock(return_value=scalar_result)
    send_result = type("Result", (), {"id": "celery-1"})()
    monkeypatch.setattr(worker_recovery_service.celery_app, "send_task", lambda *args, **kwargs: send_result)
    monkeypatch.setattr(worker_recovery_service, "append_task_event", AsyncMock())

    result = await worker_recovery_service.recover_expired_tasks(db)

    assert result == ["ppt-1"]
    assert task.status == "pending"
    assert task.retry_count == 1
    assert task.celery_task_id == "celery-1"


def test_recovery_service_has_supported_task_names():
    assert worker_recovery_service.TASK_NAMES["ppt_generation"] == "app.tasks.ppt_tasks.generate_ppt"
