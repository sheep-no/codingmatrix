import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
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


@pytest.mark.asyncio
async def test_reconciliation_records_difference_and_retry(db):
    record = await record_difference(db, "aicloud", "session", "legacy-1", {"count": 2}, {"count": 1}, 1)
    await schedule_difference_retry(db, record.id, "统一消息写入延迟", 5)
    open_records = await list_open_differences(db, "aicloud")
    assert open_records[0].status == "retryable"
    assert open_records[0].attempt_count == 1


@pytest.mark.asyncio
async def test_reconciliation_resolves_when_snapshots_match(db):
    record = await record_difference(db, "girlai", "task", "task-1", {"status": "running"}, {"status": "failed"})
    resolved = await record_difference(db, "girlai", "task", "task-1", {"status": "success"}, {"status": "success"})
    assert resolved.id == record.id
    assert resolved.status == "resolved"
    assert not await list_open_differences(db, "girlai")
