from unittest.mock import AsyncMock

import pytest

from app.services import ppt_dispatch_service


@pytest.mark.asyncio
async def test_dispatch_ppt_creates_sql_task_and_submits_json_payload(monkeypatch):
    db = AsyncMock()
    task = type("Task", (), {"task_id": "ppt-1", "celery_task_id": None})()
    create = AsyncMock(return_value=task)
    monkeypatch.setattr(ppt_dispatch_service, "create_task", create)
    result = type("Result", (), {"id": "celery-1"})()
    send = lambda *args, **kwargs: result
    monkeypatch.setattr(ppt_dispatch_service.celery_app, "send_task", send)

    task_id, celery_id = await ppt_dispatch_service.dispatch_ppt_to_celery(
        db, 7, {"topic": "test", "output_format": "pptx"}
    )

    assert (task_id, celery_id) == ("ppt-1", "celery-1")
    assert task.celery_task_id == "celery-1"
    db.commit.assert_awaited_once()
