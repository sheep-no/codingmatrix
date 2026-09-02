"""Compatibility mapping and retention lifecycle services."""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Protocol

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.unified_state import Artifact, Checkpoint, Session, StateCompatibilityMapping, StateRetentionRecord


ACTIVE_TASK_STATUSES = {"pending", "running", "recovering"}


@dataclass(frozen=True)
class RetentionPolicy:
    name: str
    archive_after_seconds: int
    cleanup_after_seconds: int


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


def _cleanup_key(record: StateRetentionRecord) -> str:
    value = f"{record.resource_type}:{record.resource_id}:{record.policy_name}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def _resource_is_blocked(db: AsyncSession, record: StateRetentionRecord) -> bool:
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
) -> dict[str, int]:
    """Archive eligible resources and clean external artifacts safely and repeatably."""
    now = now or datetime.utcnow()
    storage = storage or LocalFileStorageAdapter()
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
