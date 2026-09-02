"""Task checkpoint service contract."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unified_state import Checkpoint
from app.services.unified_state_service import save_checkpoint


async def get_latest_checkpoint(
    db: AsyncSession,
    task_id: str,
    user_id: int,
) -> Optional[Checkpoint]:
    """Load the newest checkpoint after validating task ownership."""
    from app.services.unified_state_service import get_owned_task

    await get_owned_task(db, task_id, user_id)
    return await db.scalar(
        select(Checkpoint)
        .where(Checkpoint.task_id == task_id)
        .order_by(Checkpoint.revision.desc())
        .limit(1)
    )


__all__ = ["get_latest_checkpoint", "save_checkpoint"]
