"""GirlAI legacy chat history adapter for unified state persistence."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unified_state import Checkpoint, Message, Session
from app.services.session_state_service import append_message, create_session, list_messages
from app.services.state_migration_service import (
    resolve_compatibility_mapping,
    upsert_compatibility_mapping,
)
from app.services.task_state_service import create_task
from app.services.task_checkpoint_service import save_checkpoint


MODULE = "girlai"
SESSION_TYPE = "girlai_history"
SUMMARY_TYPE = "girlai_summary"


def user_session_id(user_id: int) -> str:
    """Return the stable legacy session key used by user-scoped GirlAI history."""
    return f"user:{int(user_id)}"


async def ensure_session(db: AsyncSession, user_id: int, character_id: Optional[str] = None) -> Session:
    legacy_id = user_session_id(user_id)
    mapping = await resolve_compatibility_mapping(db, user_id, MODULE, SESSION_TYPE, legacy_id)
    if mapping:
        session = await db.get(Session, mapping.unified_id)
        if session:
            return session

    session = await create_session(
        db,
        user_id,
        MODULE,
        external_id=legacy_id,
        title=f"GirlAI:{character_id}" if character_id else "GirlAI",
    )
    await upsert_compatibility_mapping(
        db, user_id, MODULE, SESSION_TYPE, legacy_id, "session", session.id,
        source_table="chat_histories",
    )
    return session


async def append_conversation_turn(
    db: AsyncSession,
    user_id: int,
    user_content: str,
    assistant_content: str,
    model: Optional[str] = None,
    character_id: Optional[str] = None,
    legacy_message_ids: Optional[tuple[str, str]] = None,
) -> tuple[Message, Message]:
    """Write one GirlAI turn to unified messages."""
    session = await ensure_session(db, user_id, character_id)
    metadata = {"source": "girlai", "model": model, "character_id": character_id}
    user_metadata = dict(metadata)
    assistant_metadata = dict(metadata)
    if legacy_message_ids:
        user_metadata["legacy_message_id"] = legacy_message_ids[0]
        assistant_metadata["legacy_message_id"] = legacy_message_ids[1]
    user_message = await append_message(db, session.id, user_id, "user", user_content, user_metadata)
    assistant_message = await append_message(db, session.id, user_id, "assistant", assistant_content, assistant_metadata)
    return user_message, assistant_message


async def clear_messages_for_user(db: AsyncSession, user_id: int) -> int:
    """Delete unified GirlAI messages without creating a missing session."""
    legacy_id = user_session_id(user_id)
    mapping = await resolve_compatibility_mapping(db, user_id, MODULE, SESSION_TYPE, legacy_id)
    if not mapping:
        return 0
    result = await db.execute(
        delete(Message).where(Message.session_id == mapping.unified_id, Message.user_id == user_id)
    )
    return result.rowcount or 0


async def delete_messages_for_legacy_ids(
    db: AsyncSession,
    user_id: int,
    legacy_message_ids: list[str | int],
) -> int:
    """Delete unified messages linked to selected legacy history records."""
    if not legacy_message_ids:
        return 0
    mapping = await resolve_compatibility_mapping(
        db, user_id, MODULE, SESSION_TYPE, user_session_id(user_id)
    )
    if not mapping:
        return 0
    normalized_ids = [str(message_id) for message_id in legacy_message_ids]
    result = await db.execute(
        delete(Message).where(
            Message.session_id == mapping.unified_id,
            Message.user_id == user_id,
            Message.metadata_json["legacy_message_id"].as_string().in_(normalized_ids),
        )
    )
    return result.rowcount or 0


async def save_summary_checkpoint(
    db: AsyncSession,
    user_id: int,
    summary_text: str,
    start_date: datetime,
    end_date: datetime,
    source_summary_id: Optional[str] = None,
) -> Checkpoint:
    """Persist a GirlAI summary as an idempotent unified checkpoint."""
    task = await create_task(
        db,
        user_id,
        task_type="girlai_summary",
        idempotency_key=f"girlai-summary:{source_summary_id or end_date.isoformat()}",
        params={"module": MODULE, "source_summary_id": source_summary_id},
    )
    return await save_checkpoint(
        db,
        task.task_id,
        user_id,
        revision=1,
        step="summary",
        state={
            "summary": summary_text,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "source_summary_id": source_summary_id,
        },
        idempotency_key=f"girlai-summary-checkpoint:{source_summary_id or end_date.isoformat()}",
    )


async def list_messages_for_user(db: AsyncSession, user_id: int, limit: int = 100) -> list[Message]:
    session = await ensure_session(db, user_id)
    return await list_messages(db, session.id, user_id, limit=limit)


__all__ = [
    "append_conversation_turn",
    "clear_messages_for_user",
    "delete_messages_for_legacy_ids",
    "ensure_session",
    "list_messages_for_user",
    "save_summary_checkpoint",
    "user_session_id",
]
