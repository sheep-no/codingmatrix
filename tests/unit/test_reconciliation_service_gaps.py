"""reconciliation_service 差异记录、重试与查询分支补测。"""

from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.unified_state import StateReconciliationRecord
from app.services.reconciliation_service import (
    list_open_differences,
    record_difference,
    schedule_difference_retry,
)


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


async def test_record_without_difference_and_no_record_returns_none(db):
    result = await record_difference(db, "m", "t", "r", {"a": 1}, {"a": 1})
    assert result is None


async def test_record_new_then_update(db):
    first = await record_difference(db, "m", "t", "r1", {"a": 1}, {"a": 2}, user_id=7)
    await db.commit()
    assert first.user_id == 7
    assert first.difference_json == {"a": {"expected": 1, "actual": 2}}
    assert first.status == "open"

    second = await record_difference(db, "m", "t", "r1", {"a": 2}, {"a": 3})
    await db.commit()

    assert second.id == first.id
    assert second.status == "open"
    assert second.actual_json == {"a": 3}
    assert second.resolved_at is None


async def test_record_updated_snapshots_and_reopens(db):
    created = await record_difference(db, "m", "t", "r2", {"a": 1}, {"a": 2})
    await db.commit()
    created.status = "resolved"
    created.resolved_at = datetime.utcnow()
    await db.commit()

    reopened = await record_difference(db, "m", "t", "r2", {"a": 9}, {"a": 8})
    await db.commit()

    assert reopened.status == "open"
    assert reopened.resolved_at is None
    assert reopened.expected_json == {"a": 9}
    assert reopened.actual_json == {"a": 8}


async def test_record_resolves_existing_without_error(db):
    created = await record_difference(db, "m", "t", "r3", {"a": 1}, {"a": 2})
    await db.commit()
    resolved = await record_difference(db, "m", "t", "r3", {"a": 5}, {"a": 5})
    await db.commit()

    assert resolved.id == created.id
    assert resolved.status == "resolved"
    assert resolved.difference_json == {}
    assert resolved.resolved_at is not None


async def test_schedule_retry_missing_record(db):
    with pytest.raises(ValueError):
        await schedule_difference_retry(db, 12345, "err")


async def test_schedule_retry_increments_and_clamps_delay(db):
    record = await record_difference(db, "m", "t", "r4", {"a": 1}, {"a": 2})
    await db.commit()

    updated = await schedule_difference_retry(db, record.id, "boom", delay_seconds=0)
    await db.commit()

    assert updated.status == "retryable"
    assert updated.attempt_count == 1
    assert updated.last_error == "boom"
    assert updated.next_retry_at > datetime.utcnow()


async def test_list_open_differences_filters_and_orders(db):
    for idx in range(3):
        await record_difference(db, "m", "t", f"r{idx}", {"a": 1}, {"a": 2})
    await db.commit()
    other = await record_difference(db, "other", "t", "x", {"a": 1}, {"a": 2})
    await db.commit()
    await schedule_difference_retry(db, other.id, "e")
    await db.commit()

    all_open = await list_open_differences(db)
    assert len(all_open) == 4
    assert all(isinstance(r, StateReconciliationRecord) for r in all_open)

    filtered = await list_open_differences(db, module="m", limit=2)
    assert len(filtered) == 2

    assert len(await list_open_differences(db, limit=0)) >= 1
