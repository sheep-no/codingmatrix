"""AICloud legacy state adapter for the unified session/message model."""

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unified_state import Message, Session
from app.services.session_state_service import append_message, create_session
from app.services.state_migration_service import (
    resolve_compatibility_mapping,
    upsert_compatibility_mapping,
)


MODULE = "aicloud"
SESSION_TYPE = "aicloud_session"
MESSAGE_TYPE = "aicloud_message"


async def ensure_session(
    db: AsyncSession,
    user_id: int,
    legacy_session_id: str,
    title: Optional[str] = None,
) -> Session:
    """Return the unified session bound to an AICloud session identifier."""
    mapping = await resolve_compatibility_mapping(
        db,
        user_id,
        MODULE,
        SESSION_TYPE,
        str(legacy_session_id),
    )
    if mapping:
        session = await db.get(Session, mapping.unified_id)
        if session:
            return session

    session = await create_session(
        db,
        user_id,
        MODULE,
        external_id=str(legacy_session_id),
        title=title,
    )
    await upsert_compatibility_mapping(
        db,
        user_id,
        MODULE,
        SESSION_TYPE,
        str(legacy_session_id),
        "session",
        session.id,
        source_table="aicloud_sessions",
    )
    return session


async def append_legacy_message(
    db: AsyncSession,
    user_id: int,
    legacy_session_id: str,
    role: str,
    content: str,
    legacy_message_id: Optional[str] = None,
) -> Message:
    """Append an AICloud message and make replay idempotent when it has an ID."""
    session = await ensure_session(db, user_id, legacy_session_id)
    mapping = None
    if legacy_message_id is not None:
        mapping = await resolve_compatibility_mapping(
            db,
            user_id,
            MODULE,
            MESSAGE_TYPE,
            str(legacy_message_id),
        )
        if mapping:
            message = await db.get(Message, int(mapping.unified_id))
            if message:
                return message

    message = await append_message(
        db,
        session.id,
        user_id,
        role,
        content,
        metadata={
            "source": "aicloud",
            "legacy_session_id": str(legacy_session_id),
            "legacy_message_id": str(legacy_message_id) if legacy_message_id is not None else None,
        },
    )
    if legacy_message_id is not None:
        await upsert_compatibility_mapping(
            db,
            user_id,
            MODULE,
            MESSAGE_TYPE,
            str(legacy_message_id),
            "message",
            str(message.id),
            source_table="aicloud_messages",
            metadata={"session_id": session.id},
        )
    return message


async def list_session_messages(
    db: AsyncSession,
    user_id: int,
    legacy_session_id: str,
    limit: int = 100,
) -> list[Message]:
    """List unified messages for an AICloud legacy session."""
    from app.services.session_state_service import list_messages

    session = await ensure_session(db, user_id, legacy_session_id)
    return await list_messages(db, session.id, user_id, limit=limit)


__all__ = ["append_legacy_message", "ensure_session", "list_session_messages"]
