"""Adapters from legacy workflow history to unified task events and artifacts."""

from typing import Any, Iterable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.artifact_service import create_artifact
from app.services.state_migration_service import (
    resolve_compatibility_mapping,
    upsert_compatibility_mapping,
)
from app.services.task_event_service import append_task_event
from app.services.task_state_service import create_task


MODULE = "workflow"


async def ensure_workflow_task(
    db: AsyncSession,
    user_id: int,
    workflow_id: str,
    request: str = "",
) -> str:
    """Return the unified task ID associated with a WorkflowHistory record."""
    mapping = await resolve_compatibility_mapping(
        db, user_id, MODULE, "workflow_history", str(workflow_id)
    )
    if mapping:
        return mapping.unified_id

    task = await create_task(
        db,
        user_id,
        task_type="workflow",
        task_id=str(workflow_id),
        idempotency_key=f"workflow:{workflow_id}",
        params={"request": request, "module": MODULE},
    )
    await upsert_compatibility_mapping(
        db, user_id, MODULE, "workflow_history", str(workflow_id),
        "task", task.task_id, source_table="workflow_history",
    )
    return task.task_id


async def record_workflow_stage(
    db: AsyncSession,
    user_id: int,
    workflow_id: str,
    event_type: str,
    payload: Optional[dict[str, Any]] = None,
    status: Optional[str] = None,
    progress: Optional[int] = None,
) -> str:
    task_id = await ensure_workflow_task(db, user_id, workflow_id)
    await append_task_event(db, task_id, user_id, event_type, payload, status, progress)
    return task_id


async def register_workflow_artifacts(
    db: AsyncSession,
    user_id: int,
    workflow_id: str,
    artifacts: Iterable[dict[str, Any]],
) -> list[str]:
    """Register generated workflow files as versioned unified artifacts."""
    task_id = await ensure_workflow_task(db, user_id, workflow_id)
    registered: list[str] = []
    for item in artifacts:
        artifact = await create_artifact(
            db,
            user_id,
            artifact_type=str(item.get("artifact_type", "generated_file")),
            storage_uri=str(item.get("storage_uri") or item.get("path") or item.get("name")),
            task_id=task_id,
            version=int(item.get("version", 1)),
            content_hash=item.get("content_hash"),
            metadata=item.get("metadata") or {"source": MODULE},
        )
        registered.append(artifact.id)
    return registered


__all__ = ["ensure_workflow_task", "record_workflow_stage", "register_workflow_artifacts"]
