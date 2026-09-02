from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from app.models.unified_state import Message, Session
from app.services import girlai_state_adapter


def test_user_session_id_is_stable():
    assert girlai_state_adapter.user_session_id("7") == "user:7"


@pytest.mark.asyncio
async def test_append_conversation_turn_writes_both_roles(monkeypatch):
    db = AsyncMock()
    session = Session(id="session-1", user_id=7, module="girlai")
    user_message = object()
    assistant_message = object()
    monkeypatch.setattr(girlai_state_adapter, "ensure_session", AsyncMock(return_value=session))
    append = AsyncMock(side_effect=[user_message, assistant_message])
    monkeypatch.setattr(girlai_state_adapter, "append_message", append)

    result = await girlai_state_adapter.append_conversation_turn(
        db, 7, "你好", "你好，我在。", model="test", character_id="gentle"
    )

    assert result == (user_message, assistant_message)
    assert append.await_count == 2
    assert append.await_args_list[0].args[3:6] == ("user", "你好", {"source": "girlai", "model": "test", "character_id": "gentle"})
    assert append.await_args_list[1].args[3:6] == ("assistant", "你好，我在。", {"source": "girlai", "model": "test", "character_id": "gentle"})


@pytest.mark.asyncio
async def test_clear_messages_for_user_reuses_mapping(monkeypatch):
    db = AsyncMock()
    mapping = type("Mapping", (), {"unified_id": "girlai-session"})()
    monkeypatch.setattr(
        girlai_state_adapter,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=mapping),
    )
    db.execute.return_value.rowcount = 4

    deleted = await girlai_state_adapter.clear_messages_for_user(db, 7)

    assert deleted == 4
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_clear_messages_for_user_skips_missing_mapping(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        girlai_state_adapter,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=None),
    )

    deleted = await girlai_state_adapter.clear_messages_for_user(db, 7)

    assert deleted == 0
    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_append_conversation_turn_links_legacy_message_ids(monkeypatch):
    db = AsyncMock()
    session = Session(id="session-1", user_id=7, module="girlai")
    monkeypatch.setattr(girlai_state_adapter, "ensure_session", AsyncMock(return_value=session))
    append = AsyncMock(side_effect=[object(), object()])
    monkeypatch.setattr(girlai_state_adapter, "append_message", append)

    await girlai_state_adapter.append_conversation_turn(
        db,
        7,
        "你好",
        "你好，我在。",
        legacy_message_ids=("legacy-user", "legacy-assistant"),
    )

    assert append.await_args_list[0].args[5]["legacy_message_id"] == "legacy-user"
    assert append.await_args_list[1].args[5]["legacy_message_id"] == "legacy-assistant"


@pytest.mark.asyncio
async def test_delete_messages_for_legacy_ids_uses_existing_mapping(monkeypatch):
    db = AsyncMock()
    mapping = type("Mapping", (), {"unified_id": "girlai-session"})()
    monkeypatch.setattr(
        girlai_state_adapter,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=mapping),
    )
    db.execute.return_value.rowcount = 2

    deleted = await girlai_state_adapter.delete_messages_for_legacy_ids(
        db, 7, [11, "12"]
    )

    assert deleted == 2
    db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_summary_checkpoint_uses_idempotent_task_key(monkeypatch):
    db = AsyncMock()
    task = type("Task", (), {"task_id": "task-1"})()
    checkpoint = object()
    create = AsyncMock(return_value=task)
    save = AsyncMock(return_value=checkpoint)
    monkeypatch.setattr(girlai_state_adapter, "create_task", create)
    monkeypatch.setattr(girlai_state_adapter, "save_checkpoint", save)
    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 2)

    result = await girlai_state_adapter.save_summary_checkpoint(db, 7, "摘要", start, end, "summary-1")

    assert result is checkpoint
    assert create.await_args.kwargs["idempotency_key"] == "girlai-summary:summary-1"
    assert save.await_args.kwargs["idempotency_key"] == "girlai-summary-checkpoint:summary-1"


@pytest.mark.asyncio
async def test_ensure_session_reuses_legacy_user_history_mapping(monkeypatch):
    db = AsyncMock()
    mapping = type("Mapping", (), {"unified_id": "girlai-session"})()
    session = Session(id="girlai-session", user_id=7, module="girlai")
    resolve = AsyncMock(return_value=mapping)
    monkeypatch.setattr(girlai_state_adapter, "resolve_compatibility_mapping", resolve)
    db.get.return_value = session

    result = await girlai_state_adapter.ensure_session(db, 7, character_id="gentle")

    assert result is session
    resolve.assert_awaited_once_with(db, 7, "girlai", "girlai_history", "user:7")
    db.get.assert_awaited_once_with(Session, "girlai-session")


@pytest.mark.asyncio
async def test_list_messages_for_user_reads_legacy_history_with_limit(monkeypatch):
    db = AsyncMock()
    session = Session(id="girlai-session", user_id=7, module="girlai")
    messages = [
        Message(id=1, session_id="girlai-session", user_id=7, sequence=1, role="user", content="你好"),
        Message(id=2, session_id="girlai-session", user_id=7, sequence=2, role="assistant", content="你好，我在。"),
    ]
    monkeypatch.setattr(girlai_state_adapter, "ensure_session", AsyncMock(return_value=session))
    list_messages = AsyncMock(return_value=messages)
    monkeypatch.setattr(girlai_state_adapter, "list_messages", list_messages)

    result = await girlai_state_adapter.list_messages_for_user(db, 7, limit=2)

    assert result == messages
    list_messages.assert_awaited_once_with(db, "girlai-session", 7, limit=2)
