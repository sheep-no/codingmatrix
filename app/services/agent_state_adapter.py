"""Adapters from legacy Agent sessions and graph state to unified state."""

from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.state.models import State
from app.models.unified_state import Session
from app.services.session_state_service import create_session
from app.services.state_migration_service import (
    resolve_compatibility_mapping,
    upsert_compatibility_mapping,
)
from app.services.task_checkpoint_service import save_checkpoint
from app.services.task_event_service import append_task_event
from app.services.task_state_service import create_task
from app.services.artifact_service import create_artifact


MODULE = "agent"
_ARTIFACT_VERSION_STRIDE = 100_000


async def ensure_project_session(
    db: AsyncSession,
    user_id: int,
    legacy_session_id: str,
    title: Optional[str] = None,
) -> Session:
    """Map a ProjectSession or JSON session identifier to a unified session."""
    mapping = await resolve_compatibility_mapping(
        db, user_id, MODULE, "project_session", str(legacy_session_id)
    )
    if mapping:
        session = await db.get(Session, mapping.unified_id)
        if session:
            return session

    session = await create_session(
        db, user_id, MODULE, external_id=str(legacy_session_id), title=title
    )
    await upsert_compatibility_mapping(
        db, user_id, MODULE, "project_session", str(legacy_session_id),
        "session", session.id, source_table="project_sessions",
    )
    return session


async def save_graph_checkpoint(
    db: AsyncSession,
    user_id: int,
    state: State,
    idempotency_key: Optional[str] = None,
) -> str:
    """Ensure the graph task exists and persist its complete state snapshot."""
    task = await create_task(
        db,
        user_id,
        task_type="agent_graph",
        task_id=state.task_id,
        session_id=state.session_id,
        idempotency_key=idempotency_key,
        params={"module": MODULE},
    )
    await save_checkpoint(
        db,
        task.task_id,
        user_id,
        revision=state.revision,
        step="graph",
        state=state.to_dict(),
        idempotency_key=idempotency_key or f"agent-graph:{state.task_id}:{state.revision}",
    )
    return task.task_id


async def persist_agent_state(db: AsyncSession, user_id: int, state: State) -> str:
    """Persist a graph snapshot and its new messages/files in one adapter call."""
    session = await ensure_project_session(db, user_id, state.session_id)
    unified_state = State.from_dict(state.to_dict())
    unified_state.session_id = session.id
    task_id = await save_graph_checkpoint(db, user_id, unified_state)
    for message in state.messages:
        await append_task_event(
            db,
            task_id,
            user_id,
            message.type,
            payload=message.payload,
            status=state.status,
            progress=None,
        )
    for index, generated_file in enumerate(state.generated_files, start=1):
        await create_artifact(
            db,
            user_id,
            artifact_type="generated_file",
            storage_uri=str(generated_file.get("path") or generated_file.get("name") or "unknown"),
            task_id=task_id,
            session_id=session.id,
            # The schema keys artifacts by task/type/version; encode the
            # graph revision and file ordinal to keep each generated file unique.
            version=state.revision * _ARTIFACT_VERSION_STRIDE + index,
            content_hash=generated_file.get("content_hash"),
            metadata={"source": MODULE, "state_revision": state.revision},
        )
    await db.commit()
    return task_id


__all__ = ["ensure_project_session", "persist_agent_state", "save_graph_checkpoint"]
