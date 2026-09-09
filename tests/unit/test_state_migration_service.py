from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.db.models import ProjectSession
from app.models.task import Task
from app.models.unified_state import Artifact, Session, StateRetentionRecord
from app.services.state_migration_service import (
    LocalProjectStorageAdapter,
    RetentionPolicy,
    advance_retention_record,
    archive_project,
    create_retention_record,
    evaluate_project_lifecycle,
    process_retention_records,
    resolve_compatibility_mapping,
    restore_project,
    set_project_pinned,
    sweep_project_retention,
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


@pytest.mark.asyncio
async def test_project_lifecycle_uses_activity_and_preserves_archive(db):
    now = datetime.utcnow()
    project = ProjectSession(
        session_id="project-lifecycle",
        user_id="1",
        requirement="create an app",
        status="completed",
        last_activity_at=now - timedelta(days=10),
    )
    db.add(project)
    await db.flush()

    result = await evaluate_project_lifecycle(
        db,
        project.session_id,
        now=now,
        idle_after=timedelta(days=7),
        abandoned_after=timedelta(days=30),
    )

    assert result.lifecycle_status == "idle"

    project.lifecycle_status = "archived"
    result = await evaluate_project_lifecycle(db, project.session_id, now=now)
    assert result.lifecycle_status == "archived"


@pytest.mark.asyncio
async def test_project_retention_is_blocked_while_project_is_active(db):
    project = ProjectSession(
        session_id="active-project",
        user_id="1",
        requirement="create an app",
        status="completed",
        lifecycle_status="active",
    )
    db.add(project)
    record = await create_retention_record(
        db,
        "project",
        project.session_id,
        "short",
        eligible_at=datetime.utcnow() - timedelta(days=10),
    )

    result = await process_retention_records(
        db,
        RetentionPolicy("short", archive_after_seconds=0, cleanup_after_seconds=0),
    )

    assert result["blocked"] == 1
    assert record.status == "blocked"


@pytest.mark.asyncio
async def test_project_sweeper_creates_one_record_for_abandoned_project(db):
    now = datetime.utcnow()
    project = ProjectSession(
        session_id="abandoned-project",
        user_id="1",
        requirement="create an app",
        status="completed",
        last_activity_at=now - timedelta(days=31),
    )
    db.add(project)
    await db.flush()

    first = await sweep_project_retention(db, now=now)
    second = await sweep_project_retention(db, now=now)
    records = list((await db.scalars(
        select(StateRetentionRecord).where(
            StateRetentionRecord.resource_type == "project",
            StateRetentionRecord.resource_id == project.session_id,
        )
    )).all())

    assert first["abandoned"] == 1
    assert first["records_created"] == 1
    assert second["records_created"] == 0
    assert project.lifecycle_status == "abandoned"
    assert len(records) == 1


@pytest.mark.asyncio
async def test_project_cleanup_removes_only_managed_directory(db, tmp_path):
    project_dir = tmp_path / "1" / "managed-project"
    project_dir.mkdir(parents=True)
    (project_dir / "main.py").write_text("print('ok')\n", encoding="utf-8")
    project = ProjectSession(
        session_id="purge-project",
        user_id="1",
        requirement="create an app",
        output_dir="1/managed-project",
        status="completed",
        lifecycle_status="archived",
    )
    db.add(project)
    record = await create_retention_record(
        db,
        "project",
        project.session_id,
        "project_standard",
        eligible_at=datetime.utcnow() - timedelta(days=1),
    )
    record.archive_at = datetime.utcnow() - timedelta(days=1)
    record.status = "archived"

    result = await process_retention_records(
        db,
        RetentionPolicy("project_standard", archive_after_seconds=0, cleanup_after_seconds=0),
        project_storage=LocalProjectStorageAdapter(tmp_path),
    )

    assert result["cleaned"] == 1
    assert project.lifecycle_status == "purged"
    assert not project_dir.exists()


def test_project_storage_rejects_protected_and_root_paths(tmp_path):
    adapter = LocalProjectStorageAdapter(tmp_path)
    user_project = ProjectSession(
        session_id="user-project",
        user_id="1",
        requirement="keep it",
        output_dir="1/user-project",
        retention_class="user_owned",
    )
    root_project = ProjectSession(
        session_id="root-project",
        user_id="1",
        requirement="keep it",
        output_dir=".",
    )

    with pytest.raises(PermissionError):
        adapter.resolve_project_path(user_project)
    with pytest.raises(PermissionError):
        adapter.resolve_project_path(root_project)


@pytest.mark.asyncio
async def test_project_retention_is_blocked_by_active_task(db, tmp_path):
    project = ProjectSession(
        session_id="task-protected-project",
        user_id="1",
        requirement="keep it",
        output_dir="1/task-protected-project",
        status="completed",
        lifecycle_status="archived",
    )
    task = Task(
        task_id="active-project-task",
        session_id=project.session_id,
        task_type="code_generate",
        status="running",
        user_id=1,
    )
    db.add_all([project, task])
    record = await create_retention_record(
        db,
        "project",
        project.session_id,
        "project_standard",
        eligible_at=datetime.utcnow() - timedelta(days=100),
    )
    record.status = "archived"
    record.archive_at = datetime.utcnow() - timedelta(days=100)

    result = await process_retention_records(
        db,
        RetentionPolicy("project_standard", archive_after_seconds=0, cleanup_after_seconds=0),
        project_storage=LocalProjectStorageAdapter(tmp_path),
    )

    assert result["blocked"] == 1
    assert record.status == "blocked"


@pytest.mark.asyncio
async def test_project_archive_restore_and_pin_are_idempotent(db):
    project = ProjectSession(
        session_id="lifecycle-api-project",
        user_id="1",
        requirement="lifecycle",
        output_dir="1/lifecycle-api-project",
        status="completed",
    )
    db.add(project)
    await db.flush()

    archived = await archive_project(db, project.session_id, now=datetime.utcnow())
    assert archived.lifecycle_status == "archived"
    assert archived.archived_at is not None
    record = await db.scalar(
        select(StateRetentionRecord).where(
            StateRetentionRecord.resource_type == "project",
            StateRetentionRecord.resource_id == project.session_id,
        )
    )
    assert record.status == "archived"

    pinned = await set_project_pinned(db, project.session_id, True)
    assert pinned.pinned is True
    restored = await restore_project(db, project.session_id)
    assert restored.lifecycle_status == "active"
    assert restored.archived_at is None
    assert record.status == "eligible"
    assert record.eligible_at == restored.last_activity_at

    unpinned = await set_project_pinned(db, project.session_id, False)
    assert unpinned.pinned is False
    assert record.eligible_at == unpinned.last_activity_at
