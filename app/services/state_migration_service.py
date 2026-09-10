"""Compatibility mapping and retention lifecycle services."""

import hashlib
import shutil
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Protocol

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import OperationalError

from app.models.task import Task
from app.db.models import ProjectSession
from app.models.unified_state import Artifact, Checkpoint, Session, StateCompatibilityMapping, StateRetentionRecord


ACTIVE_TASK_STATUSES = {"pending", "running", "recovering"}
PROJECT_LIFECYCLE_STATUSES = {"active", "idle", "abandoned", "archived", "purge_candidate", "purged"}


@dataclass(frozen=True)
class RetentionPolicy:
    name: str
    archive_after_seconds: int
    cleanup_after_seconds: int


PROJECT_RETENTION_POLICIES = {
    "temporary": RetentionPolicy("project_temporary", 7 * 24 * 60 * 60, 30 * 24 * 60 * 60),
    "standard": RetentionPolicy("project_standard", 30 * 24 * 60 * 60, 90 * 24 * 60 * 60),
}


class ExternalStorageAdapter(Protocol):
    async def delete(self, storage_uri: str, idempotency_key: str) -> dict[str, Any]:
        """Delete an external object and return an idempotent execution result."""


class LocalFileStorageAdapter:
    """Adapter for file:// URIs used by local artifacts and tests."""

    async def delete(self, storage_uri: str, idempotency_key: str) -> dict[str, Any]:
        del idempotency_key
        if not storage_uri.startswith("file://"):
            return {"status": "skipped", "reason": "unsupported_storage_uri"}
        path = Path(storage_uri[7:]).resolve()
        if not path.exists():
            return {"status": "already_deleted", "path": str(path)}
        if path.is_dir():
            raise IsADirectoryError(str(path))
        path.unlink()
        return {"status": "deleted", "path": str(path)}


class LocalProjectStorageAdapter:
    """Remove only managed project directories below an explicit project root."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def resolve_project_path(self, project: ProjectSession) -> Path:
        if project.retention_class in {"user_owned", "external", "pinned"}:
            raise PermissionError("用户项目不允许自动物理清理")
        if not project.output_dir:
            raise ValueError("项目没有输出目录")
        candidate = Path(project.output_dir)
        path = candidate.resolve() if candidate.is_absolute() else (self.root / candidate).resolve()
        if path == self.root or not path.is_relative_to(self.root):
            raise PermissionError("项目目录超出托管根目录")
        return path

    async def delete_project(self, project: ProjectSession, idempotency_key: str) -> dict[str, Any]:
        del idempotency_key
        path = self.resolve_project_path(project)
        if not path.exists():
            return {"status": "already_deleted", "path": str(path)}
        if not path.is_dir():
            raise ValueError("项目输出路径不是目录")
        shutil.rmtree(path)
        return {"status": "deleted", "path": str(path)}


def _generation_is_active(session_id: str) -> bool:
    """True only when an in-memory generation task is still running."""
    try:
        from app.api.v1.ai_agent.orchestrate_endpoints import _active_tasks
    except Exception:
        return False
    active = _active_tasks.get(session_id)
    if not active:
        return False
    gen_task = active.get("gen_task")
    return gen_task is not None and not gen_task.done()


async def permanently_delete_project(
    db: AsyncSession,
    project: ProjectSession,
    project_storage: LocalProjectStorageAdapter,
) -> dict[str, Any]:
    """Immediately remove a user-requested project and its retention records."""
    if _generation_is_active(project.session_id):
        raise ValueError("项目仍有活动任务，暂时无法删除")
    try:
        active_task = await db.scalar(select(Task.task_id).where(
            Task.session_id == project.session_id,
            Task.status.in_(ACTIVE_TASK_STATUSES),
        ))
    except OperationalError:
        active_task = None
    if active_task is not None:
        raise ValueError("项目仍有活动任务，暂时无法删除")
    storage_result = await project_storage.delete_project(project, f"user-delete:{project.session_id}")
    try:
        await db.execute(delete(StateRetentionRecord).where(
            StateRetentionRecord.resource_type == "project",
            StateRetentionRecord.resource_id == project.session_id,
        ))
    except OperationalError:
        pass
    await db.delete(project)
    return {"session_id": project.session_id, "status": "deleted", "storage": storage_result}


def _cleanup_key(record: StateRetentionRecord) -> str:
    value = f"{record.resource_type}:{record.resource_id}:{record.policy_name}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _resource_is_blocked(db: AsyncSession, record: StateRetentionRecord) -> bool:
    if record.resource_type == "project":
        project = await db.scalar(
            select(ProjectSession).where(ProjectSession.session_id == record.resource_id)
        )
        if project is None:
            return False
        if project.pinned or project.status == "running":
            return True
        active_task = await db.scalar(
            select(Task).where(
                Task.session_id == record.resource_id,
                Task.status.in_(ACTIVE_TASK_STATUSES),
            )
        )
        if active_task is not None:
            return True
        return project.lifecycle_status in {"active", "idle"}
    if record.resource_type == "artifact":
        artifact = await db.get(Artifact, record.resource_id)
        if artifact is None:
            return False
        if artifact.task_id:
            task = await db.scalar(select(Task).where(Task.task_id == artifact.task_id))
            if task and task.status in ACTIVE_TASK_STATUSES:
                return True
        if artifact.session_id:
            session = await db.get(Session, artifact.session_id)
            if session and session.status == "active":
                return True
        return False
    if record.resource_type == "task":
        task = await db.scalar(select(Task).where(Task.task_id == record.resource_id))
        return bool(task and task.status in ACTIVE_TASK_STATUSES)
    if record.resource_type == "session":
        session = await db.get(Session, record.resource_id)
        return bool(session and session.status == "active")
    return False


async def process_retention_records(
    db: AsyncSession,
    policy: RetentionPolicy,
    now: Optional[datetime] = None,
    limit: int = 100,
    storage: Optional[ExternalStorageAdapter] = None,
    project_storage: Optional[LocalProjectStorageAdapter] = None,
) -> dict[str, int]:
    """Archive eligible resources and clean external artifacts safely and repeatably."""
    now = now or datetime.utcnow()
    storage = storage or LocalFileStorageAdapter()
    project_storage = project_storage
    counters = {"archived": 0, "blocked": 0, "cleaned": 0, "retryable": 0}
    records = list((await db.scalars(
        select(StateRetentionRecord)
        .where(
            StateRetentionRecord.policy_name == policy.name,
            or_(
                StateRetentionRecord.status.in_(("eligible", "retryable")),
                StateRetentionRecord.status == "blocked",
                StateRetentionRecord.status == "archived",
            ),
        )
        .order_by(StateRetentionRecord.id.asc())
        .limit(max(1, min(limit, 1000)))
    )).all())

    for record in records:
        if record.status == "blocked":
            if await _resource_is_blocked(db, record):
                counters["blocked"] += 1
                continue
            record.status = "eligible"
            record.last_error = None
            await db.flush()
        if record.status in {"eligible", "retryable"}:
            eligible_at = record.eligible_at or record.created_at
            if (now - eligible_at).total_seconds() < policy.archive_after_seconds:
                continue
            if await _resource_is_blocked(db, record):
                record.status = "blocked"
                counters["blocked"] += 1
                continue
            record.status = "archiving"
            record.last_error = None
            await db.flush()
            resource = await _load_resource(db, record)
            if resource is not None and hasattr(resource, "archived_at"):
                resource.archived_at = now
                if isinstance(resource, ProjectSession):
                    resource.lifecycle_status = "archived"
            record.status = "archived"
            record.archive_at = now
            counters["archived"] += 1

        if record.status != "archived":
            continue
        archive_at = record.archive_at or now
        if (now - archive_at).total_seconds() < policy.cleanup_after_seconds:
            continue
        if await _resource_is_blocked(db, record):
            record.status = "blocked"
            counters["blocked"] += 1
            continue
        record.status = "cleaning"
        record.cleanup_idempotency_key = record.cleanup_idempotency_key or _cleanup_key(record)
        record.cleanup_result_json = {
            "intent": "delete_external_resource",
            "resource_type": record.resource_type,
            "resource_id": record.resource_id,
            "version": _resource_version(await _load_resource(db, record)),
            "idempotency_key": record.cleanup_idempotency_key,
        }
        record.attempt_count += 1
        await db.flush()
        try:
            resource = await _load_resource(db, record)
            if isinstance(resource, Artifact):
                result = await storage.delete(resource.storage_uri, record.cleanup_idempotency_key)
            elif isinstance(resource, ProjectSession):
                if project_storage is None:
                    raise RuntimeError("项目存储适配器未配置")
                result = await project_storage.delete_project(resource, record.cleanup_idempotency_key)
                resource.lifecycle_status = "purged"
            else:
                result = {"status": "retained", "reason": "no_external_artifact"}
            record.cleanup_result_json = {**record.cleanup_result_json, "result": result}
            record.status = "cleaned"
            record.cleanup_at = now
            record.last_error = None
            counters["cleaned"] += 1
        except (OSError, RuntimeError, ValueError, TypeError) as error:
            record.status = "retryable"
            record.last_error = str(error)
            counters["retryable"] += 1
        await db.flush()
    return counters


async def _load_resource(db: AsyncSession, record: StateRetentionRecord) -> Any:
    if record.resource_type == "project":
        return await db.scalar(
            select(ProjectSession).where(ProjectSession.session_id == record.resource_id)
        )
    if record.resource_type == "artifact":
        return await db.get(Artifact, record.resource_id)
    if record.resource_type == "task":
        return await db.scalar(select(Task).where(Task.task_id == record.resource_id))
    if record.resource_type == "session":
        return await db.get(Session, record.resource_id)
    if record.resource_type == "checkpoint":
        return await db.get(Checkpoint, int(record.resource_id))
    return None


def _resource_version(resource: Any) -> Optional[int]:
    return getattr(resource, "version", None) if resource is not None else None


async def evaluate_project_lifecycle(
    db: AsyncSession,
    session_id: str,
    now: Optional[datetime] = None,
    idle_after: timedelta = timedelta(days=7),
    abandoned_after: timedelta = timedelta(days=30),
) -> ProjectSession:
    """Classify a project from user activity while preserving explicit archive state."""
    project = await db.scalar(
        select(ProjectSession).where(ProjectSession.session_id == session_id)
    )
    if project is None:
        raise ValueError("项目不存在")
    if project.pinned or project.lifecycle_status in {"archived", "purge_candidate", "purged"}:
        return project
    if project.status == "running":
        project.lifecycle_status = "active"
        return project
    now = now or datetime.utcnow()
    last_activity = project.last_activity_at.replace(tzinfo=None)
    age = now - last_activity
    if age >= abandoned_after:
        project.lifecycle_status = "abandoned"
    elif age >= idle_after:
        project.lifecycle_status = "idle"
    else:
        project.lifecycle_status = "active"
    await db.flush()
    return project


async def sweep_project_retention(
    db: AsyncSession,
    now: Optional[datetime] = None,
    limit: int = 100,
) -> dict[str, int]:
    """Create idempotent retention records for inactive managed projects."""
    now = now or datetime.utcnow()
    projects = list((await db.scalars(
        select(ProjectSession)
        .where(ProjectSession.lifecycle_status.in_(("active", "idle", "abandoned")))
        .order_by(ProjectSession.last_activity_at.asc())
        .limit(max(1, min(limit, 1000)))
    )).all())
    counters = {"scanned": 0, "abandoned": 0, "records_created": 0, "protected": 0}
    for project in projects:
        counters["scanned"] += 1
        if project.pinned or project.status == "running":
            counters["protected"] += 1
            continue
        policy = PROJECT_RETENTION_POLICIES.get(
            project.retention_class,
            PROJECT_RETENTION_POLICIES["standard"],
        )
        await evaluate_project_lifecycle(
            db,
            project.session_id,
            now=now,
            abandoned_after=timedelta(seconds=policy.archive_after_seconds),
        )
        if project.lifecycle_status != "abandoned":
            continue
        counters["abandoned"] += 1
        eligible_at = project.last_activity_at.replace(tzinfo=None) + timedelta(
            seconds=policy.archive_after_seconds
        )
        existing = await db.scalar(
            select(StateRetentionRecord).where(
                StateRetentionRecord.resource_type == "project",
                StateRetentionRecord.resource_id == project.session_id,
                StateRetentionRecord.policy_name == policy.name,
            )
        )
        if existing is None:
            await create_retention_record(
                db,
                "project",
                project.session_id,
                policy.name,
                eligible_at=eligible_at,
            )
            counters["records_created"] += 1
    await db.flush()
    return counters


async def upsert_compatibility_mapping(
    db: AsyncSession,
    user_id: int,
    module: str,
    legacy_type: str,
    legacy_id: str,
    unified_type: str,
    unified_id: str,
    source_table: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> StateCompatibilityMapping:
    mapping = await db.scalar(
        select(StateCompatibilityMapping).where(
            StateCompatibilityMapping.user_id == int(user_id),
            StateCompatibilityMapping.module == module,
            StateCompatibilityMapping.legacy_type == legacy_type,
            StateCompatibilityMapping.legacy_id == legacy_id,
        )
    )
    if mapping:
        if mapping.unified_id != unified_id or mapping.unified_type != unified_type:
            raise ValueError("旧标识已绑定其他统一资源")
        return mapping
    mapping = StateCompatibilityMapping(
        user_id=int(user_id),
        module=module,
        legacy_type=legacy_type,
        legacy_id=legacy_id,
        unified_type=unified_type,
        unified_id=unified_id,
        source_table=source_table,
        metadata_json=metadata or {},
    )
    db.add(mapping)
    await db.flush()
    return mapping


async def resolve_compatibility_mapping(
    db: AsyncSession,
    user_id: int,
    module: str,
    legacy_type: str,
    legacy_id: str,
) -> Optional[StateCompatibilityMapping]:
    return await db.scalar(
        select(StateCompatibilityMapping).where(
            StateCompatibilityMapping.user_id == int(user_id),
            StateCompatibilityMapping.module == module,
            StateCompatibilityMapping.legacy_type == legacy_type,
            StateCompatibilityMapping.legacy_id == legacy_id,
        )
    )


async def create_retention_record(
    db: AsyncSession,
    resource_type: str,
    resource_id: str,
    policy_name: str,
    eligible_at: Optional[datetime] = None,
) -> StateRetentionRecord:
    record = await db.scalar(
        select(StateRetentionRecord).where(
            StateRetentionRecord.resource_type == resource_type,
            StateRetentionRecord.resource_id == resource_id,
            StateRetentionRecord.policy_name == policy_name,
        )
    )
    if record:
        return record
    record = StateRetentionRecord(
        resource_type=resource_type,
        resource_id=resource_id,
        policy_name=policy_name,
        eligible_at=eligible_at,
        status="eligible",
    )
    db.add(record)
    await db.flush()
    return record


async def advance_retention_record(
    db: AsyncSession,
    record_id: int,
    status: str,
    error: Optional[str] = None,
) -> StateRetentionRecord:
    record = await db.get(StateRetentionRecord, record_id)
    if not record:
        raise ValueError("保留记录不存在")
    allowed = {
        "eligible": {"archiving", "blocked"},
        "blocked": {"eligible"},
        "archiving": {"archived", "retryable"},
        "archived": {"cleaning"},
        "cleaning": {"cleaned", "retryable"},
        "retryable": {"eligible", "archiving", "cleaning"},
        "cleaned": set(),
    }
    if status != record.status and status not in allowed.get(record.status, set()):
        raise ValueError(f"保留记录状态无法从 {record.status} 转为 {status}")
    record.status = status
    record.last_error = error
    if error:
        record.attempt_count += 1
    now = datetime.utcnow()
    if status == "archived":
        record.archive_at = now
    if status == "cleaned":
        record.cleanup_at = now
    await db.flush()
    return record


async def archive_project(db: AsyncSession, session_id: str, now: Optional[datetime] = None) -> ProjectSession:
    now = now or datetime.utcnow()
    project = await db.scalar(
        select(ProjectSession).where(ProjectSession.session_id == session_id)
    )
    if project is None:
        raise ValueError("项目不存在")
    active_task = await db.scalar(
        select(Task).where(
            Task.session_id == session_id,
            Task.status.in_(ACTIVE_TASK_STATUSES),
        )
    )
    if project.status == "running" or active_task is not None:
        raise ValueError("项目仍有活动任务，无法归档")
    policy = PROJECT_RETENTION_POLICIES.get(
        project.retention_class,
        PROJECT_RETENTION_POLICIES["standard"],
    )
    record = await create_retention_record(
        db,
        "project",
        session_id,
        policy.name,
        eligible_at=now,
    )
    project.lifecycle_status = "archived"
    project.archived_at = now
    project.purge_after = now + timedelta(seconds=policy.cleanup_after_seconds)
    record.status = "archived"
    record.archive_at = now
    record.last_error = None
    await db.flush()
    return project


async def restore_project(db: AsyncSession, session_id: str) -> ProjectSession:
    project = await db.scalar(
        select(ProjectSession).where(ProjectSession.session_id == session_id)
    )
    if project is None:
        raise ValueError("项目不存在")
    if project.lifecycle_status == "purged":
        raise ValueError("项目已清理，无法恢复")
    records = list((await db.scalars(
        select(StateRetentionRecord).where(
            StateRetentionRecord.resource_type == "project",
            StateRetentionRecord.resource_id == session_id,
        )
    )).all())
    for record in records:
        if record.status in {"cleaning", "cleaned"}:
            raise ValueError("项目正在清理，无法恢复")
        record.status = "eligible"
        record.archive_at = None
        record.cleanup_at = None
        record.last_error = None
    project.lifecycle_status = "active"
    project.archived_at = None
    project.purge_after = None
    project.last_activity_at = datetime.utcnow()
    for record in records:
        record.eligible_at = project.last_activity_at
    await db.flush()
    return project


async def set_project_pinned(db: AsyncSession, session_id: str, pinned: bool) -> ProjectSession:
    project = await db.scalar(
        select(ProjectSession).where(ProjectSession.session_id == session_id)
    )
    if project is None:
        raise ValueError("项目不存在")
    project.pinned = pinned
    if pinned and project.lifecycle_status in {"archived", "purge_candidate"}:
        project.lifecycle_status = "active"
        project.archived_at = None
        project.purge_after = None
    project.last_activity_at = datetime.utcnow()
    if not pinned:
        records = list((await db.scalars(
            select(StateRetentionRecord).where(
                StateRetentionRecord.resource_type == "project",
                StateRetentionRecord.resource_id == session_id,
            )
        )).all())
        for record in records:
            record.eligible_at = project.last_activity_at
    await db.flush()
    return project
