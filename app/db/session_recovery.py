"""Recover database sessions that cannot survive a process restart."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ProjectSession

logger = logging.getLogger(__name__)

INTERRUPTED_SESSION_MESSAGE = "服务重启，生成任务已中断；已生成文件保留以支持继续"


async def reconcile_interrupted_sessions(db: AsyncSession) -> int:
    """Mark sessions left running by a previous process as interrupted.

    Generated files are intentionally preserved so the user can resume from the
    last successful file instead of losing the whole project.
    """
    result = await db.execute(
        select(ProjectSession).where(ProjectSession.status == "running")
    )
    sessions = list(result.scalars().all())
    if not sessions:
        return 0

    now = datetime.now(timezone.utc)
    for session in sessions:
        session.status = "failed"
        session.error_message = INTERRUPTED_SESSION_MESSAGE
        session.completed_at = now
        session.last_activity_at = now

    await db.commit()
    logger.warning("已回收 %d 个重启前遗留的 running 会话", len(sessions))
    return len(sessions)
