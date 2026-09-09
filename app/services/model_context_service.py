"""Versioned model context persistence for Agent sessions."""

import uuid
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task import Task
from app.models.unified_state import Checkpoint, Session
from app.services.unified_state_service import (
    StateConflictError,
    StateNotFoundError,
    save_checkpoint,
)


MODEL_CONTEXT_TASK_TYPE = "agent_model_context"
MODEL_CONTEXT_SCHEMA_VERSION = "1"
MODEL_CONTEXT_TASK_NAMESPACE = uuid.UUID("fe624d7d-bcbf-4b57-9607-0ec582e55b42")


@dataclass(frozen=True)
class ModelContextSnapshot:
    context: dict[str, Any]
    revision: int


def build_runtime_model_context() -> dict[str, Any]:
    """Build a credential-free model context from the current Agent config."""
    config: dict[str, Any] = {}
    try:
        from app.agent.dynamic_model_router import load_agent_model_config

        config = load_agent_model_config() or {}
    except (OSError, TypeError, ValueError):
        config = {}

    roles = config.get("roles") or {}
    assignments = {
        role: {"model": model, "calls": 0, "success_rate": 100.0}
        for role, model in roles.items()
    }
    return {
        "schema_version": MODEL_CONTEXT_SCHEMA_VERSION,
        "config_version": str(config.get("version") or ""),
        "roles": dict(roles),
        "current_model": None,
        "current_agent": None,
        "assignments": assignments,
        "fallback_history": [],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def merge_model_context(current: Optional[dict[str, Any]], update: dict[str, Any]) -> dict[str, Any]:
    """Merge a partial update into a complete, bounded model context."""
    merged = deepcopy(current or build_runtime_model_context())

    for key in ("config_version", "current_model", "current_agent"):
        if key in update:
            merged[key] = update[key]

    if "roles" in update:
        merged["roles"] = dict(update.get("roles") or {})

    assignments = deepcopy(merged.get("assignments", {}))
    if "roles" in update:
        assignments = {
            role: assignment
            for role, assignment in assignments.items()
            if role in merged["roles"]
        }
    for role, assignment in (update.get("assignments") or {}).items():
        assignments[role] = {**assignments.get(role, {}), **assignment}
    merged["assignments"] = assignments

    if "fallback_history" in update:
        merged["fallback_history"] = list(update.get("fallback_history") or [])[-50:]

    merged["schema_version"] = MODEL_CONTEXT_SCHEMA_VERSION
    merged["updated_at"] = datetime.now(timezone.utc).isoformat()
    return merged


async def get_model_context(
    db: AsyncSession,
    user_id: int,
    unified_session_id: str,
) -> Optional[dict[str, Any]]:
    snapshot = await get_model_context_snapshot(db, user_id, unified_session_id)
    return snapshot.context if snapshot else None


async def get_model_context_snapshot(
    db: AsyncSession,
    user_id: int,
    unified_session_id: str,
) -> Optional[ModelContextSnapshot]:
    task = await db.scalar(
        select(Task).where(
            Task.user_id == int(user_id),
            Task.session_id == unified_session_id,
            Task.task_type == MODEL_CONTEXT_TASK_TYPE,
        ).order_by(Task.id.desc()).limit(1)
    )
    if not task:
        return None

    checkpoint = await db.scalar(
        select(Checkpoint)
        .where(Checkpoint.task_id == task.task_id)
        .order_by(Checkpoint.revision.desc())
        .limit(1)
    )
    if not checkpoint:
        return None
    context = deepcopy((checkpoint.state_json or {}).get("model_context"))
    if not isinstance(context, dict):
        return None
    return ModelContextSnapshot(context=context, revision=int(checkpoint.revision))


async def save_model_context(
    db: AsyncSession,
    user_id: int,
    unified_session_id: str,
    update: dict[str, Any],
    expected_revision: Optional[int] = None,
) -> ModelContextSnapshot:
    """Save a full model context snapshot using an independent revision stream."""
    session = await db.scalar(
        select(Session)
        .where(Session.id == unified_session_id, Session.user_id == int(user_id))
        .with_for_update()
    )
    if not session:
        raise StateNotFoundError("会话不存在")

    idempotency_key = f"agent-model-context:{unified_session_id}"
    task_id = str(uuid.uuid5(MODEL_CONTEXT_TASK_NAMESPACE, f"{user_id}:{unified_session_id}"))
    task = await db.scalar(
        select(Task)
        .where(
            Task.user_id == int(user_id),
            Task.session_id == unified_session_id,
            Task.task_type == MODEL_CONTEXT_TASK_TYPE,
        )
        .order_by(Task.id.desc())
        .limit(1)
        .with_for_update()
    )
    if task is None:
        task = Task(
            task_id=task_id,
            session_id=unified_session_id,
            idempotency_key=idempotency_key,
            task_type=MODEL_CONTEXT_TASK_TYPE,
            user_id=int(user_id),
            params={"module": "agent", "idempotency_key": idempotency_key},
            status="pending",
        )
        try:
            async with db.begin_nested():
                db.add(task)
                await db.flush()
        except IntegrityError:
            task = await db.scalar(
                select(Task).where(Task.task_id == task_id).with_for_update()
            )
            if task is None:
                raise StateConflictError("模型上下文任务创建冲突")

    revision_query = sql_update(Task).where(Task.id == task.id)
    if expected_revision is not None:
        revision_query = revision_query.where(Task.revision == expected_revision)
    revision = await db.scalar(
        revision_query
        .values(revision=Task.revision + 1)
        .returning(Task.revision)
    )
    if revision is None:
        raise StateConflictError("模型上下文版本已变化")
    current_snapshot = await get_model_context_snapshot(db, int(user_id), unified_session_id)
    current = current_snapshot.context if current_snapshot else None
    context = merge_model_context(current, update)
    await save_checkpoint(
        db,
        task.task_id,
        int(user_id),
        revision=int(revision),
        step="model_context",
        state={"session_id": unified_session_id, "model_context": context},
        idempotency_key=f"{idempotency_key}:{revision}",
    )
    await db.flush()
    return ModelContextSnapshot(context=context, revision=int(revision))


__all__ = [
    "MODEL_CONTEXT_SCHEMA_VERSION",
    "MODEL_CONTEXT_TASK_TYPE",
    "ModelContextSnapshot",
    "build_runtime_model_context",
    "get_model_context",
    "get_model_context_snapshot",
    "merge_model_context",
    "save_model_context",
]
