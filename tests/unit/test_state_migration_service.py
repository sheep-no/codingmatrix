from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.unified_state import Artifact, Session
from app.services.state_migration_service import (
    RetentionPolicy,
    advance_retention_record,
    create_retention_record,
    process_retention_records,
    resolve_compatibility_mapping,
    upsert_compatibility_mapping,
)


class FakeStorage:
    def __init__(self, result=None, error=None):
        self.calls = []
        self.result = result or {"status": "deleted"}
        self.error = error

    async def delete(self, storage_uri, idempotency_key):
        self.calls.append((storage_uri, idempotency_key))
        if self.error:
            raise self.error
        return self.result


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
async def test_compatibility_mapping_is_idempotent(db):
    first = await upsert_compatibility_mapping(db, 1, "aicloud", "session", "legacy-1", "session", "unified-1")
    second = await upsert_compatibility_mapping(db, 1, "aicloud", "session", "legacy-1", "session", "unified-1")
    resolved = await resolve_compatibility_mapping(db, 1, "aicloud", "session", "legacy-1")
    assert first.id == second.id == resolved.id


@pytest.mark.asyncio
async def test_retention_record_tracks_archive_and_cleanup(db):
    record = await create_retention_record(db, "artifact", "artifact-1", "default")
    await advance_retention_record(db, record.id, "archiving")
    await advance_retention_record(db, record.id, "archived")
    await advance_retention_record(db, record.id, "cleaning")
    await advance_retention_record(db, record.id, "cleaned")
    assert record.archive_at is not None
    assert record.cleanup_at is not None


@pytest.mark.asyncio
async def test_retention_processor_records_delete_intent_and_result(db):
    artifact = Artifact(
        id="artifact-retention",
        user_id=1,
        artifact_type="generated_file",
        version=3,
        storage_uri="s3://bucket/object",
        metadata_json={},
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    db.add(artifact)
    record = await create_retention_record(
        db,
        "artifact",
        artifact.id,
        "short",
        eligible_at=datetime.utcnow() - timedelta(days=10),
    )
    storage = FakeStorage({"status": "deleted", "provider": "fake"})

    result = await process_retention_records(
        db,
        RetentionPolicy("short", archive_after_seconds=0, cleanup_after_seconds=0),
        storage=storage,
    )

    assert result == {"archived": 1, "blocked": 0, "cleaned": 1, "retryable": 0}
    assert record.status == "cleaned"
    assert record.cleanup_idempotency_key
    assert record.cleanup_result_json["version"] == 3
    assert record.cleanup_result_json["result"]["provider"] == "fake"
    assert storage.calls == [("s3://bucket/object", record.cleanup_idempotency_key)]


@pytest.mark.asyncio
async def test_retention_processor_blocks_active_session_artifact(db):
    session = Session(
        id="active-session",
        user_id=1,
        module="agent",
        status="active",
    )
    artifact = Artifact(
        id="artifact-blocked",
        user_id=1,
        session_id=session.id,
        artifact_type="generated_file",
        version=1,
        storage_uri="file:///tmp/blocked",
        metadata_json={},
        created_at=datetime.utcnow() - timedelta(days=10),
    )
    db.add_all([session, artifact])
    record = await create_retention_record(
        db,
        "artifact",
        artifact.id,
        "short",
        eligible_at=datetime.utcnow() - timedelta(days=10),
    )

    result = await process_retention_records(
        db,
        RetentionPolicy("short", archive_after_seconds=0, cleanup_after_seconds=0),
    )

    assert result["archived"] == 0
    assert result["blocked"] == 1
    assert record.status == "blocked"
