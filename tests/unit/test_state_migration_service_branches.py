from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import ProjectSession
from app.models.base import Base
from app.models.task import Task
from app.models.unified_state import Artifact, Session, StateRetentionRecord
from app.services.state_migration_service import (
    LocalFileStorageAdapter,
    LocalProjectStorageAdapter,
    PROJECT_RETENTION_POLICIES,
    RetentionPolicy,
    advance_retention_record,
    archive_project,
    create_retention_record,
    evaluate_project_lifecycle,
    permanently_delete_project,
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


def _operational_error():
    return OperationalError("select 1", {}, Exception("db unavailable"))


def _project(session_id="p", **overrides):
    values = {
        "session_id": session_id,
        "user_id": "1",
        "requirement": "demo",
        "status": "completed",
        "lifecycle_status": "archived",
    }
    values.update(overrides)
    return ProjectSession(**values)


@pytest.mark.asyncio
async def test_local_file_storage_adapter_handles_every_uri_shape(tmp_path):
    adapter = LocalFileStorageAdapter()
    file_path = tmp_path / "artifact.bin"
    file_path.write_bytes(b"data")
    directory = tmp_path / "dir"
    directory.mkdir()

    assert await adapter.delete("s3://bucket/key", "k") == {
        "status": "skipped",
        "reason": "unsupported_storage_uri",
    }
    assert (await adapter.delete(f"file://{tmp_path/'missing'}", "k"))["status"] == "already_deleted"
    with pytest.raises(IsADirectoryError):
        await adapter.delete(f"file://{directory}", "k")
    assert (await adapter.delete(f"file://{file_path}", "k"))["status"] == "deleted"
    assert not file_path.exists()


@pytest.mark.asyncio
async def test_local_project_storage_adapter_skips_missing_and_rejects_files(tmp_path):
    adapter = LocalProjectStorageAdapter(tmp_path)
    missing = _project("missing", output_dir="1/missing")
    assert (await adapter.delete_project(missing, "k"))["status"] == "already_deleted"

    file_path = tmp_path / "1" / "not-a-dir"
    file_path.parent.mkdir(parents=True)
    file_path.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="不是目录"):
        await adapter.delete_project(_project("file", output_dir="1/not-a-dir"), "k")

    with pytest.raises(ValueError, match="没有输出目录"):
        adapter.resolve_project_path(_project("no-output", output_dir=None))


@pytest.mark.asyncio
async def test_evaluate_project_lifecycle_handles_missing_running_and_active(db):
    with pytest.raises(ValueError, match="项目不存在"):
        await evaluate_project_lifecycle(db, "ghost")

    running = _project("running", status="running", lifecycle_status="active")
    db.add(running)
    await db.flush()
    result = await evaluate_project_lifecycle(db, "running")
    assert result.lifecycle_status == "active"

    fresh = _project(
        "fresh",
        lifecycle_status="active",
        last_activity_at=datetime.utcnow() - timedelta(hours=1),
    )
    db.add(fresh)
    await db.flush()
    result = await evaluate_project_lifecycle(
        db,
        "fresh",
        now=datetime.utcnow(),
        idle_after=timedelta(days=7),
        abandoned_after=timedelta(days=30),
    )
    assert result.lifecycle_status == "active"


@pytest.mark.asyncio
async def test_resource_is_blocked_handles_missing_and_active_resources(db):
    from app.services.state_migration_service import _resource_is_blocked

    missing = StateRetentionRecord(
        resource_type="project", resource_id="missing", policy_name="p", status="eligible"
    )
    assert await _resource_is_blocked(db, missing) is False

    pinned = _project("pinned", pinned=True, lifecycle_status="active")
    db.add(pinned)
    await db.flush()
    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="project", resource_id="pinned", policy_name="p", status="eligible"
    ))

    missing_artifact = StateRetentionRecord(
        resource_type="artifact", resource_id="ghost", policy_name="p", status="eligible"
    )
    assert await _resource_is_blocked(db, missing_artifact) is False

    task = Task(task_id="active-task", user_id=1, task_type="code_generate", status="running")
    artifact = Artifact(
        id="artifact-task",
        user_id=1,
        task_id="active-task",
        artifact_type="generated_file",
        version=1,
        storage_uri="file:///tmp/x",
        metadata_json={},
    )
    db.add_all([task, artifact])
    await db.flush()
    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="artifact", resource_id="artifact-task", policy_name="p", status="eligible"
    ))

    orphan = Artifact(
        id="artifact-orphan",
        user_id=1,
        session_id="no-session",
        artifact_type="generated_file",
        version=2,
        storage_uri="file:///tmp/y",
        metadata_json={},
    )
    db.add(orphan)
    await db.flush()
    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="artifact", resource_id="artifact-orphan", policy_name="p", status="eligible"
    )) is False

    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="task", resource_id="active-task", policy_name="p", status="eligible"
    ))
    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="task", resource_id="ghost-task", policy_name="p", status="eligible"
    )) is False

    active_session = Session(id="active-session", user_id=1, module="agent", status="active")
    db.add(active_session)
    await db.flush()
    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="session", resource_id="active-session", policy_name="p", status="eligible"
    ))
    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="session", resource_id="ghost-session", policy_name="p", status="eligible"
    )) is False
    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="unknown", resource_id="anything", policy_name="p", status="eligible"
    )) is False


@pytest.mark.asyncio
async def test_process_unblocks_missing_project_and_keeps_pinned_blocked(db):
    missing = await create_retention_record(
        db, "project", "vanished", "unblock",
        eligible_at=datetime.utcnow() - timedelta(days=1),
    )
    pinned = _project("still-pinned", pinned=True)
    db.add(pinned)
    pinned_record = await create_retention_record(
        db, "project", "still-pinned", "unblock",
        eligible_at=datetime.utcnow() - timedelta(days=1),
    )
    pinned_record.status = "blocked"

    result = await process_retention_records(
        db,
        RetentionPolicy("unblock", archive_after_seconds=0, cleanup_after_seconds=0),
    )

    assert result["blocked"] == 1
    assert missing.status == "cleaned"
    assert missing.cleanup_result_json["result"]["status"] == "retained"
    assert pinned_record.status == "blocked"


@pytest.mark.asyncio
async def test_process_unblocks_record_that_is_not_yet_due(db):
    historical = await create_retention_record(
        db, "project", "long-gone", "not-due",
        eligible_at=datetime.utcnow(),
    )
    historical.status = "blocked"
    historical.last_error = "was pinned"
    await db.flush()

    result = await process_retention_records(
        db,
        RetentionPolicy("not-due", archive_after_seconds=3600, cleanup_after_seconds=3600),
    )

    assert result == {"archived": 0, "blocked": 0, "cleaned": 0, "retryable": 0}
    assert historical.status == "eligible"
    assert historical.last_error is None


@pytest.mark.asyncio
async def test_resource_is_blocked_ignores_finished_task_with_closed_session(db):
    from app.services.state_migration_service import _resource_is_blocked

    task = Task(task_id="finished-task", user_id=1, task_type="code_generate", status="success")
    session = Session(id="closed-session", user_id=1, module="agent", status="closed")
    artifact = Artifact(
        id="artifact-finished",
        user_id=1,
        task_id="finished-task",
        session_id="closed-session",
        artifact_type="generated_file",
        version=1,
        storage_uri="file:///tmp/finished",
        metadata_json={},
    )
    db.add_all([task, session, artifact])
    await db.flush()

    assert await _resource_is_blocked(db, StateRetentionRecord(
        resource_type="artifact", resource_id="artifact-finished", policy_name="p", status="eligible"
    )) is False


@pytest.mark.asyncio
async def test_process_skips_archive_until_eligible_and_cleanup_until_due(db):
    record = await create_retention_record(db, "checkpoint", "999", "waiting")
    result = await process_retention_records(
        db,
        RetentionPolicy("waiting", archive_after_seconds=3600, cleanup_after_seconds=3600),
    )
    assert result == {"archived": 0, "blocked": 0, "cleaned": 0, "retryable": 0}
    assert record.status == "eligible"

    record.eligible_at = datetime.utcnow() - timedelta(hours=2)
    result = await process_retention_records(
        db,
        RetentionPolicy("waiting", archive_after_seconds=0, cleanup_after_seconds=3600),
    )
    assert result["archived"] == 1
    assert record.status == "archived"


@pytest.mark.asyncio
async def test_process_loads_task_and_session_resources(db):
    task = Task(task_id="retained-task", user_id=1, task_type="code_generate", status="success")
    session = Session(id="retained-session", user_id=1, module="agent", status="closed")
    db.add_all([task, session])
    await db.flush()

    task_record = await create_retention_record(
        db, "task", "retained-task", "retain",
        eligible_at=datetime.utcnow() - timedelta(days=1),
    )
    session_record = await create_retention_record(
        db, "session", "retained-session", "retain",
        eligible_at=datetime.utcnow() - timedelta(days=1),
    )
    unknown_record = await create_retention_record(
        db, "mystery", "whatever", "retain",
        eligible_at=datetime.utcnow() - timedelta(days=1),
    )

    result = await process_retention_records(
        db,
        RetentionPolicy("retain", archive_after_seconds=0, cleanup_after_seconds=0),
    )

    assert result["cleaned"] == 3
    assert task_record.cleanup_result_json["result"]["reason"] == "no_external_artifact"
    assert session_record.status == "cleaned"
    assert unknown_record.status == "cleaned"


@pytest.mark.asyncio
async def test_process_marks_project_cleanup_retryable_without_storage(db):
    project = _project("needs-storage")
    db.add(project)
    await db.flush()
    record = await create_retention_record(
        db, "project", "needs-storage", "project_retry",
        eligible_at=datetime.utcnow() - timedelta(days=1),
    )

    result = await process_retention_records(
        db,
        RetentionPolicy("project_retry", archive_after_seconds=0, cleanup_after_seconds=0),
    )

    assert result["retryable"] == 1
    assert record.status == "retryable"
    assert "适配器未配置" in record.last_error
    assert record.attempt_count == 1


@pytest.mark.asyncio
async def test_process_marks_artifact_storage_errors_retryable(db):
    artifact = Artifact(
        id="artifact-error",
        user_id=1,
        artifact_type="generated_file",
        version=1,
        storage_uri="s3://bucket/error",
        metadata_json={},
    )
    db.add(artifact)
    await db.flush()
    record = await create_retention_record(
        db, "artifact", "artifact-error", "error",
        eligible_at=datetime.utcnow() - timedelta(days=1),
    )
    storage = FakeStorage(error=OSError("disk gone"))

    result = await process_retention_records(
        db,
        RetentionPolicy("error", archive_after_seconds=0, cleanup_after_seconds=0),
        storage=storage,
    )

    assert result["retryable"] == 1
    assert record.status == "retryable"
    assert record.last_error == "disk gone"


@pytest.mark.asyncio
async def test_sweep_protects_pinned_and_running_and_skips_fresh(db):
    pinned = _project("sweep-pinned", pinned=True, lifecycle_status="active")
    running = _project(
        "sweep-running", user_id="2", status="running", lifecycle_status="active"
    )
    fresh = _project("sweep-fresh", user_id="3", lifecycle_status="active")
    db.add_all([pinned, running, fresh])
    await db.flush()

    result = await sweep_project_retention(db, now=datetime.utcnow())

    assert result["scanned"] == 3
    assert result["protected"] == 2
    assert result["abandoned"] == 0
    assert result["records_created"] == 0


@pytest.mark.asyncio
async def test_sweep_uses_temporary_policy_and_is_idempotent(db):
    abandoned = _project(
        "temporary-abandoned",
        retention_class="temporary",
        lifecycle_status="active",
        last_activity_at=datetime.utcnow() - timedelta(days=10),
    )
    db.add(abandoned)
    await db.flush()

    first = await sweep_project_retention(db, now=datetime.utcnow())
    second = await sweep_project_retention(db, now=datetime.utcnow())

    assert first["abandoned"] == 1
    assert first["records_created"] == 1
    assert second["records_created"] == 0
    record = await db.scalar(select(StateRetentionRecord))
    assert record.policy_name == PROJECT_RETENTION_POLICIES["temporary"].name


@pytest.mark.asyncio
async def test_compatibility_mapping_detects_conflicting_unified_identity(db):
    await upsert_compatibility_mapping(
        db, 1, "aicloud", "session", "legacy", "session", "unified-a",
        source_table="legacy_sessions", metadata={"origin": "test"},
    )
    with pytest.raises(ValueError, match="旧标识已绑定其他统一资源"):
        await upsert_compatibility_mapping(
            db, 1, "aicloud", "session", "legacy", "session", "unified-b"
        )
    assert await resolve_compatibility_mapping(db, 1, "aicloud", "session", "absent") is None


@pytest.mark.asyncio
async def test_create_retention_record_is_idempotent(db):
    first = await create_retention_record(db, "artifact", "same", "policy")
    second = await create_retention_record(db, "artifact", "same", "policy")
    assert first.id == second.id


@pytest.mark.asyncio
async def test_advance_retention_record_rejects_missing_and_invalid_transitions(db):
    with pytest.raises(ValueError, match="保留记录不存在"):
        await advance_retention_record(db, 123456, "archived")

    record = await create_retention_record(db, "artifact", "advance", "policy")
    with pytest.raises(ValueError, match="无法从"):
        await advance_retention_record(db, record.id, "cleaned")

    advanced = await advance_retention_record(
        db, record.id, "blocked", error="temporary failure"
    )
    assert advanced.status == "blocked"
    assert advanced.attempt_count == 1
    assert advanced.last_error == "temporary failure"

    same = await advance_retention_record(db, record.id, "blocked")
    assert same.attempt_count == 1


@pytest.mark.asyncio
async def test_archive_project_rejects_missing_running_and_active_task(db):
    with pytest.raises(ValueError, match="项目不存在"):
        await archive_project(db, "ghost")

    running = _project("archive-running", status="running", lifecycle_status="active")
    db.add(running)
    await db.flush()
    with pytest.raises(ValueError, match="活动任务"):
        await archive_project(db, "archive-running")

    busy = _project("archive-busy", lifecycle_status="active")
    task = Task(task_id="archive-busy-task", session_id="archive-busy", user_id=1,
                task_type="code_generate", status="running")
    db.add_all([busy, task])
    await db.flush()
    with pytest.raises(ValueError, match="活动任务"):
        await archive_project(db, "archive-busy")


@pytest.mark.asyncio
async def test_restore_project_rejects_missing_purged_and_cleaning(db):
    with pytest.raises(ValueError, match="项目不存在"):
        await restore_project(db, "ghost")

    purged = _project("restore-purged", lifecycle_status="purged")
    cleaning = _project("restore-cleaning", lifecycle_status="archived")
    db.add_all([purged, cleaning])
    await db.flush()
    await create_retention_record(db, "project", "restore-cleaning", "policy")
    record = await db.scalar(
        select(StateRetentionRecord).where(
            StateRetentionRecord.resource_id == "restore-cleaning"
        )
    )
    record.status = "cleaning"
    await db.flush()

    with pytest.raises(ValueError, match="已清理"):
        await restore_project(db, "restore-purged")
    with pytest.raises(ValueError, match="正在清理"):
        await restore_project(db, "restore-cleaning")


@pytest.mark.asyncio
async def test_set_project_pinned_rejects_missing_project(db):
    with pytest.raises(ValueError, match="项目不存在"):
        await set_project_pinned(db, "ghost", True)


@pytest.mark.asyncio
async def test_permanently_delete_tolerates_task_and_record_query_failures(db, tmp_path, monkeypatch):
    project = _project(
        "delete-degraded",
        output_dir="1/delete-degraded",
        lifecycle_status="active",
    )
    db.add(project)
    await db.flush()

    async def _raise_scalar(*args, **kwargs):
        raise _operational_error()

    monkeypatch.setattr(db, "scalar", _raise_scalar)
    result = await permanently_delete_project(db, project, LocalProjectStorageAdapter(tmp_path))

    assert result["status"] == "deleted"
    assert result["storage"]["status"] == "already_deleted"


@pytest.mark.asyncio
async def test_permanently_delete_ignores_record_delete_failure(db, tmp_path, monkeypatch):
    project = _project(
        "delete-records-fail",
        output_dir="1/delete-records-fail",
        lifecycle_status="active",
    )
    db.add(project)
    await db.flush()

    async def _raise_execute(*args, **kwargs):
        raise _operational_error()

    monkeypatch.setattr(db, "execute", _raise_execute)
    result = await permanently_delete_project(db, project, LocalProjectStorageAdapter(tmp_path))

    assert result["status"] == "deleted"


@pytest.mark.asyncio
async def test_permanently_delete_rejects_active_task_in_database(db, tmp_path):
    project = _project(
        "delete-active-task",
        output_dir="1/delete-active-task",
        lifecycle_status="active",
    )
    task = Task(task_id="delete-active", session_id="delete-active-task", user_id=1,
                task_type="code_generate", status="running")
    db.add_all([project, task])
    await db.flush()

    with pytest.raises(ValueError, match="活动任务"):
        await permanently_delete_project(db, project, LocalProjectStorageAdapter(tmp_path))
