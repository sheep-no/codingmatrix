from unittest.mock import AsyncMock

import pytest

from app.models.unified_state import Message, Session
from app.services import aicloud_state_adapter


@pytest.mark.asyncio
async def test_ensure_session_reuses_compatibility_mapping(monkeypatch):
    db = AsyncMock()
    mapping = type("Mapping", (), {"unified_id": "unified-session"})()
    session = Session(id="unified-session", user_id=7, module="aicloud")
    monkeypatch.setattr(aicloud_state_adapter, "resolve_compatibility_mapping", AsyncMock(return_value=mapping))
    db.get.return_value = session

    result = await aicloud_state_adapter.ensure_session(db, 7, "legacy-session")

    assert result is session
    db.get.assert_awaited_once_with(Session, "unified-session")


@pytest.mark.asyncio
async def test_append_legacy_message_is_idempotent(monkeypatch):
    db = AsyncMock()
    mapping = type("Mapping", (), {"unified_id": "12"})()
    message = Message(id=12, session_id="session", user_id=7, sequence=1, role="user", content="hello")
    monkeypatch.setattr(aicloud_state_adapter, "ensure_session", AsyncMock())
    monkeypatch.setattr(aicloud_state_adapter, "resolve_compatibility_mapping", AsyncMock(return_value=mapping))
    db.get.side_effect = [message]

    result = await aicloud_state_adapter.append_legacy_message(
        db, 7, "legacy-session", "user", "hello", legacy_message_id="42"
    )

    assert result is message
    db.get.assert_awaited_once_with(Message, 12)


@pytest.mark.asyncio
async def test_ensure_session_creates_mapping_for_legacy_history(monkeypatch):
    db = AsyncMock()
    session = Session(id="new-session", user_id=7, module="aicloud")
    resolve = AsyncMock(return_value=None)
    create = AsyncMock(return_value=session)
    upsert = AsyncMock()
    monkeypatch.setattr(aicloud_state_adapter, "resolve_compatibility_mapping", resolve)
    monkeypatch.setattr(aicloud_state_adapter, "create_session", create)
    monkeypatch.setattr(aicloud_state_adapter, "upsert_compatibility_mapping", upsert)

    result = await aicloud_state_adapter.ensure_session(db, 7, "legacy-session", title="旧会话")

    assert result is session
    resolve.assert_awaited_once_with(db, 7, "aicloud", "aicloud_session", "legacy-session")
    create.assert_awaited_once_with(
        db, 7, "aicloud", external_id="legacy-session", title="旧会话"
    )
    upsert.assert_awaited_once_with(
        db,
        7,
        "aicloud",
        "aicloud_session",
        "legacy-session",
        "session",
        "new-session",
        source_table="aicloud_sessions",
    )


@pytest.mark.asyncio
async def test_list_session_messages_reads_legacy_session_with_limit(monkeypatch):
    db = AsyncMock()
    session = Session(id="session-1", user_id=7, module="aicloud")
    messages = [
        Message(id=1, session_id="session-1", user_id=7, sequence=1, role="user", content="旧问题"),
        Message(id=2, session_id="session-1", user_id=7, sequence=2, role="assistant", content="旧回答"),
    ]
    monkeypatch.setattr(aicloud_state_adapter, "ensure_session", AsyncMock(return_value=session))
    list_messages = AsyncMock(return_value=messages)
    monkeypatch.setattr("app.services.session_state_service.list_messages", list_messages)

    result = await aicloud_state_adapter.list_session_messages(db, 7, "legacy-session", limit=2)

    assert result == messages
    list_messages.assert_awaited_once_with(db, "session-1", 7, limit=2)


@pytest.mark.asyncio
async def test_legacy_session_mapping_is_scoped_to_user(monkeypatch):
    db = AsyncMock()
    resolve = AsyncMock(return_value=None)
    monkeypatch.setattr(aicloud_state_adapter, "resolve_compatibility_mapping", resolve)
    monkeypatch.setattr(
        aicloud_state_adapter,
        "create_session",
        AsyncMock(side_effect=[
            Session(id="user-7-session", user_id=7, module="aicloud"),
            Session(id="user-8-session", user_id=8, module="aicloud"),
        ]),
    )
    monkeypatch.setattr(aicloud_state_adapter, "upsert_compatibility_mapping", AsyncMock())

    await aicloud_state_adapter.ensure_session(db, 7, "same-legacy-id")
    await aicloud_state_adapter.ensure_session(db, 8, "same-legacy-id")

    assert [call.args[1] for call in resolve.await_args_list] == [7, 8]
