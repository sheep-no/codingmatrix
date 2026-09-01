"""Dispatch PPT generation through the serializable Celery task."""

from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.services.task_state_service import create_task


async def dispatch_ppt_to_celery(
    db: AsyncSession,
    user_id: int,
    request_data: dict[str, Any],
) -> tuple[str, str]:
    """Create the SQL task record and submit the matching Celery job."""
    task_id = str(uuid4())
    task = await create_task(
        db,
        int(user_id),
        task_type="ppt_generation",
        task_id=task_id,
        idempotency_key=f"ppt:{task_id}",
        params={"request_data": request_data},
    )
    # Commit before publishing so a worker can always see the task row.
    await db.commit()
    result = celery_app.send_task(
        "app.tasks.ppt_tasks.generate_ppt",
        kwargs={"task_id": task.task_id, "user_id": int(user_id), "request_data": request_data},
    )
    task.celery_task_id = result.id
    await db.commit()
    return task.task_id, result.id


__all__ = ["dispatch_ppt_to_celery"]
