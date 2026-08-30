"""Single-pass recovery for unified tasks whose worker lease expired."""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.models.task import Task
from app.services.task_event_service import append_task_event


TASK_NAMES = {
    "project_generate": "app.tasks.project_tasks.generate_project",
    "code_generate": "app.tasks.code_tasks.generate_code",
    "ppt_generate": "app.tasks.ppt_tasks.generate_ppt",
    "ppt_generation": "app.tasks.ppt_tasks.generate_ppt",
}


async def recover_expired_tasks(
    db: AsyncSession,
    now: Optional[datetime] = None,
    limit: int = 100,
) -> list[str]:
    """Requeue lease-expired tasks once and return their task IDs."""
    current_time = now or datetime.utcnow()
    tasks = list((await db.scalars(
        select(Task)
        .where(Task.status == "running", Task.lease_until.isnot(None), Task.lease_until < current_time)
        .order_by(Task.updated_at.asc())
        .limit(max(1, min(limit, 500)))
    )).all())
    recovered: list[str] = []
    for task in tasks:
        if task.retry_count >= task.max_retries:
            task.status = "failed"
            task.error_message = "worker lease expired and retry limit was reached"
            await append_task_event(db, task.task_id, task.user_id, "task.recovery_exhausted", status="failed")
            continue

        task_name = TASK_NAMES.get(task.task_type)
        if not task_name:
            continue
        task.status = "pending"
        task.retry_count += 1
        task.lease_until = None
        send_kwargs = dict(task.params or {})
        send_kwargs.update({"task_id": task.task_id, "user_id": task.user_id})
        result = celery_app.send_task(task_name, kwargs=send_kwargs)
        task.celery_task_id = result.id
        await append_task_event(
            db,
            task.task_id,
            task.user_id,
            "task.recovered",
            payload={"reason": "lease_expired", "retry_count": task.retry_count},
            status="pending",
        )
        recovered.append(task.task_id)
    await db.flush()
    return recovered


__all__ = ["recover_expired_tasks"]
