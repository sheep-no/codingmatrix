"""Record and resolve dual-write consistency differences."""

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unified_state import StateReconciliationRecord


async def record_difference(
    db: AsyncSession,
    module: str,
    resource_type: str,
    resource_id: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    user_id: Optional[int] = None,
) -> StateReconciliationRecord:
    differences = {
        key: {"expected": expected.get(key), "actual": actual.get(key)}
        for key in set(expected) | set(actual)
        if expected.get(key) != actual.get(key)
    }
    record = await db.scalar(
        select(StateReconciliationRecord).where(
            StateReconciliationRecord.module == module,
            StateReconciliationRecord.resource_type == resource_type,
            StateReconciliationRecord.resource_id == resource_id,
        )
    )
    if not differences:
        if record:
            record.status = "resolved"
            record.difference_json = {}
            record.resolved_at = datetime.utcnow()
            await db.flush()
        return record
    if record is None:
        record = StateReconciliationRecord(
            user_id=user_id,
            module=module,
            resource_type=resource_type,
            resource_id=resource_id,
            expected_json=expected,
            actual_json=actual,
            difference_json=differences,
        )
        db.add(record)
    else:
        record.expected_json = expected
        record.actual_json = actual
        record.difference_json = differences
        record.status = "open"
        record.resolved_at = None
    await db.flush()
    return record


async def schedule_difference_retry(
    db: AsyncSession,
    record_id: int,
    error: str,
    delay_seconds: int = 60,
) -> StateReconciliationRecord:
    record = await db.get(StateReconciliationRecord, record_id)
    if record is None:
        raise ValueError("核对记录不存在")
    record.status = "retryable"
    record.attempt_count += 1
    record.last_error = error
    record.next_retry_at = datetime.utcnow() + timedelta(seconds=max(1, delay_seconds))
    await db.flush()
    return record


async def list_open_differences(
    db: AsyncSession,
    module: Optional[str] = None,
    limit: int = 100,
) -> list[StateReconciliationRecord]:
    query = select(StateReconciliationRecord).where(
        StateReconciliationRecord.status.in_(("open", "retryable"))
    )
    if module:
        query = query.where(StateReconciliationRecord.module == module)
    query = query.order_by(StateReconciliationRecord.created_at.asc()).limit(max(1, min(limit, 1000)))
    return list((await db.scalars(query)).all())
