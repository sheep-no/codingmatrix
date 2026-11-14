"""girlai_state_adapter 会话冲突、回合状态与清理分支补测。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.unified_state import Session
from app.schema.girl_companion import CompanionTurn, ModelContext
from app.services import girlai_state_adapter as adapter


def _turn(**overrides):
    base = dict(
        turn_id="turn-1",
        conversation_id="session-1",
        assistant_text="hello",
        degraded_capabilities=[],
    )
    base.update(overrides)
    return CompanionTurn(**base)


def _db():
    db = AsyncMock()
    nested = MagicMock()
    nested.__aenter__ = AsyncMock(return_value=None)
    nested.__aexit__ = AsyncMock(return_value=False)
    db.begin_nested = MagicMock(return_value=nested)
    return db


def _conflict(message):
    return IntegrityError("insert", {}, Exception(message))


async def test_ensure_session_creates_session_with_character_title(monkeypatch):
    db = _db()
    db.scalar.return_value = None
    session = Session(id="new", user_id=7, module="girlai")
    create = AsyncMock(return_value=session)
    upsert = AsyncMock()
    monkeypatch.setattr(adapter, "resolve_compatibility_mapping", AsyncMock(return_value=None))
    monkeypatch.setattr(adapter, "create_session", create)
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", upsert)

    result = await adapter.ensure_session(db, 7, character_id="gentle")

    assert result is session
    assert create.await_args.kwargs["title"] == "GirlAI:gentle"
    assert create.await_args.kwargs["external_id"] == "user:7"
    upsert.assert_awaited_once()


async def test_ensure_session_uses_default_title_without_character(monkeypatch):
    db = _db()
    db.scalar.return_value = None
    create = AsyncMock(return_value=Session(id="new", user_id=7, module="girlai"))
    monkeypatch.setattr(adapter, "resolve_compatibility_mapping", AsyncMock(return_value=None))
    monkeypatch.setattr(adapter, "create_session", create)
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", AsyncMock())

    await adapter.ensure_session(db, 7)

    assert create.await_args.kwargs["title"] == "GirlAI"


async def test_ensure_session_reraises_unrelated_integrity_error(monkeypatch):
    db = _db()
    db.scalar.return_value = None
    monkeypatch.setattr(adapter, "resolve_compatibility_mapping", AsyncMock(return_value=None))
    monkeypatch.setattr(
        adapter, "create_session", AsyncMock(side_effect=_conflict("some other constraint"))
    )
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", AsyncMock())

    with pytest.raises(IntegrityError):
        await adapter.ensure_session(db, 7)


async def test_ensure_session_recovers_conflict_via_mapping(monkeypatch):
    db = _db()
    db.scalar.return_value = None
    existing = Session(id="existing", user_id=7, module="girlai")
    db.get.return_value = existing
    resolve = AsyncMock(side_effect=[
        None,
        SimpleNamespace(unified_id="existing"),
    ])
    monkeypatch.setattr(adapter, "resolve_compatibility_mapping", resolve)
    monkeypatch.setattr(
        adapter,
        "create_session",
        AsyncMock(side_effect=_conflict(
            "uq_sessions_user_module_external"
        )),
    )
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", AsyncMock())

    result = await adapter.ensure_session(db, 7)

    assert result is existing
    assert resolve.await_count == 2


async def test_ensure_session_recovers_conflict_via_scoped_lookup(monkeypatch):
    db = _db()
    existing = Session(id="scoped", user_id=7, module="girlai", external_id="user:7")
    db.scalar.return_value = None
    db.scalar.side_effect = [None, existing]
    monkeypatch.setattr(adapter, "resolve_compatibility_mapping", AsyncMock(return_value=None))
    monkeypatch.setattr(
        adapter,
        "create_session",
        AsyncMock(side_effect=_conflict(
            "sessions.user_id, sessions.module, sessions.external_id"
        )),
    )
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", AsyncMock())

    result = await adapter.ensure_session(db, 7)

    assert result is existing


async def test_ensure_session_recovers_conflict_without_mapping_target(monkeypatch):
    db = _db()
    db.scalar.return_value = None
    db.get.return_value = None
    monkeypatch.setattr(
        adapter,
        "resolve_compatibility_mapping",
        AsyncMock(side_effect=[None, SimpleNamespace(unified_id="missing")]),
    )
    monkeypatch.setattr(
        adapter,
        "create_session",
        AsyncMock(side_effect=_conflict("uq_sessions_user_module_external")),
    )
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", AsyncMock())

    with pytest.raises(IntegrityError):
        await adapter.ensure_session(db, 7)


async def test_append_companion_turn_state_requires_turn_id():
    with pytest.raises(ValueError, match="turn_id"):
        await adapter.append_companion_turn_state(
            AsyncMock(), 7, "session-1", _turn(turn_id="")
        )


async def test_append_companion_turn_state_completed_uses_model_context(monkeypatch):
    update = AsyncMock(return_value="event")
    monkeypatch.setattr(adapter, "update_session_event", update)
    turn = _turn(model_context=ModelContext(current_model="fallback-model"))

    result = await adapter.append_companion_turn_state(
        AsyncMock(), 7, "session-1", turn, tokens_used=-5
    )

    assert result == "event"
    args = update.await_args.args
    assert args[4] == "companion.turn.completed"
    assert args[5]["model"] == "fallback-model"
    assert args[5]["tokens_used"] == 0


async def test_append_companion_turn_state_explicit_model(monkeypatch):
    update = AsyncMock(return_value="event")
    monkeypatch.setattr(adapter, "update_session_event", update)

    await adapter.append_companion_turn_state(
        AsyncMock(), 7, "session-1", _turn(), model="explicit", tokens_used=10,
        reservation_token="tok",
    )

    assert update.await_args.args[5]["model"] == "explicit"
    assert update.await_args.kwargs["expected_reservation_token"] == "tok"


async def test_fail_companion_turn_state_marks_degraded(monkeypatch):
    update = AsyncMock(return_value="failed")
    monkeypatch.setattr(adapter, "update_session_event", update)

    result = await adapter.fail_companion_turn_state(
        AsyncMock(), 7, "session-1", "turn-1", "provider_error", reservation_token="tok"
    )

    assert result == "failed"
    assert update.await_args.args[4] == "companion.turn.failed"
    assert update.await_args.args[5]["degraded_capabilities"] == ["conversation"]
    assert update.await_args.kwargs["expected_reservation_token"] == "tok"


async def test_latest_and_turn_state_delegate(monkeypatch):
    latest = AsyncMock(return_value="latest")
    by_turn = AsyncMock(return_value="by-turn")
    monkeypatch.setattr(adapter, "get_latest_session_event", latest)
    monkeypatch.setattr(adapter, "get_session_event_by_turn_id", by_turn)

    assert await adapter.get_latest_companion_turn_state(AsyncMock(), 7, "s") == "latest"
    assert await adapter.get_companion_turn_state(AsyncMock(), 7, "s", "t") == "by-turn"
    latest.assert_awaited_once()
    by_turn.assert_awaited_once()


async def test_delete_messages_for_legacy_ids_skips_empty_and_missing_mapping(monkeypatch):
    db = AsyncMock()

    assert await adapter.delete_messages_for_legacy_ids(db, 7, []) == 0
    db.execute.assert_not_awaited()

    monkeypatch.setattr(adapter, "resolve_compatibility_mapping", AsyncMock(return_value=None))
    assert await adapter.delete_messages_for_legacy_ids(db, 7, [1]) == 0
    db.execute.assert_not_awaited()


async def test_delete_messages_for_legacy_ids_returns_zero_for_none_rowcount(monkeypatch):
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=None)
    monkeypatch.setattr(
        adapter, "resolve_compatibility_mapping",
        AsyncMock(return_value=SimpleNamespace(unified_id="girlai-session")),
    )

    assert await adapter.delete_messages_for_legacy_ids(db, 7, [1]) == 0


async def test_save_summary_checkpoint_falls_back_to_end_date(monkeypatch):
    create = AsyncMock(return_value=SimpleNamespace(task_id="t"))
    save = AsyncMock(return_value="checkpoint")
    monkeypatch.setattr(adapter, "create_task", create)
    monkeypatch.setattr(adapter, "save_checkpoint", save)
    from datetime import datetime

    start = datetime(2026, 1, 1)
    end = datetime(2026, 1, 2)

    result = await adapter.save_summary_checkpoint(AsyncMock(), 7, "摘要", start, end)

    assert result == "checkpoint"
    assert create.await_args.kwargs["idempotency_key"] == "girlai-summary:2026-01-02T00:00:00"
    assert save.await_args.kwargs["idempotency_key"] == (
        "girlai-summary-checkpoint:2026-01-02T00:00:00"
    )


async def test_clear_messages_returns_zero_when_rowcount_none(monkeypatch):
    db = AsyncMock()
    db.execute.return_value = SimpleNamespace(rowcount=None)
    monkeypatch.setattr(
        adapter, "resolve_compatibility_mapping",
        AsyncMock(return_value=SimpleNamespace(unified_id="girlai-session")),
    )

    assert await adapter.clear_messages_for_user(db, 7) == 0


async def test_ensure_session_falls_back_when_mapping_target_missing(monkeypatch):
    db = _db()
    found = Session(id="scoped", user_id=7, module="girlai", external_id="user:7")
    db.scalar.side_effect = [found]
    db.get.return_value = None
    mapping = SimpleNamespace(unified_id="ghost")
    monkeypatch.setattr(
        adapter, "resolve_compatibility_mapping", AsyncMock(return_value=mapping)
    )
    upsert = AsyncMock()
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", upsert)

    result = await adapter.ensure_session(db, 7)

    assert result is found
    upsert.assert_awaited_once()
