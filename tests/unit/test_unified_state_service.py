from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.task import Task
from app.models.unified_state import Artifact, Checkpoint, Message, Session, SessionEvent, TaskEvent
from app.services.unified_state_service import (
    StateConflictError,
    StateOwnershipError,
    append_message,
    append_session_event,
    append_task_event,
    create_artifact,
    create_session,
    create_task,
    list_messages,
    get_latest_session_event,
    reserve_session_event,
    replay_session_events,
    replay_task_events,
    save_checkpoint,
    transition_task,
    update_session_event,
)


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_unified_state_lifecycle_and_replay(db):
    session = await create_session(db, 1, "ppt")
    await append_message(db, session.id, 1, "user", "生成季度汇报")
    await append_message(db, session.id, 1, "assistant", "已开始")
    messages = await list_messages(db, session.id, 1)
    task = await create_task(db, 1, "ppt_generation", session_id=session.id)
    await transition_task(db, task.task_id, 1, "running", 20, "outline")
    await append_task_event(db, task.task_id, 1, "progress", {"step": "outline"}, "running", 20)
    await save_checkpoint(db, task.task_id, 1, 1, "outline", {"slides": []}, "outline-1")
    artifact = await create_artifact(db, 1, "pptx", "pptx_output/a.pptx", task.task_id, session.id)
    events = await replay_task_events(db, task.task_id, 1)

    assert [message.sequence for message in messages] == [1, 2]
    assert events[0].sequence == 1
    assert artifact.task_id == task.task_id


@pytest.mark.asyncio
async def test_unified_state_enforces_ownership(db):
    session = await create_session(db, 1, "ppt")
    with pytest.raises(StateOwnershipError):
        await append_message(db, session.id, 2, "user", "越权")


@pytest.mark.asyncio
async def test_session_scope_is_unique(db):
    await create_session(db, 1, "girlai", external_id="user:1")
    with pytest.raises(IntegrityError):
        await create_session(db, 1, "girlai", external_id="user:1")
    await db.rollback()


@pytest.mark.asyncio
async def test_session_events_are_replayable_and_idempotent(db):
    session = await create_session(db, 1, "girlai")
    first, created = await reserve_session_event(
        db,
        session.id,
        1,
        "companion.turn.completed",
        "turn-1",
        {"emotion": {"label": "focused"}},
    )
    duplicate, duplicate_created = await reserve_session_event(
        db,
        session.id,
        1,
        "companion.turn.completed",
        "turn-1",
        {"emotion": {"label": "neutral"}},
    )
    second = await append_session_event(
        db,
        session.id,
        1,
        "companion.turn.degraded",
        "turn-2",
        {"degraded_capabilities": ["emotion_classification"]},
    )

    events = await replay_session_events(db, session.id, 1)
    latest = await get_latest_session_event(db, session.id, 1)

    assert first.id == duplicate.id
    assert created is True
    assert duplicate_created is False
    assert first.schema_version == "1"
    assert [event.sequence for event in events] == [1, 2]
    assert second.sequence == 2
    assert latest.id == second.id

    with pytest.raises(StateOwnershipError):
        await replay_session_events(db, session.id, 2)


@pytest.mark.asyncio
async def test_stale_session_event_reservation_can_be_reclaimed(db):
    session = await create_session(db, 1, "girlai")
    first, created = await reserve_session_event(
        db,
        session.id,
        1,
        "companion.turn.processing",
        "turn-stale",
        {"attempt": 1},
        reclaim_after_seconds=60,
    )
    first.created_at = datetime.utcnow() - timedelta(seconds=61)
    await db.commit()

    reclaimed, reclaimed_created = await reserve_session_event(
        db,
        session.id,
        1,
        "companion.turn.processing",
        "turn-stale",
        {"attempt": 2},
        reclaim_after_seconds=60,
    )

    assert created is True
    assert reclaimed_created is True
    assert reclaimed.id == first.id
    assert reclaimed.sequence == first.sequence
    assert reclaimed.payload_json == {"attempt": 2}


@pytest.mark.asyncio
async def test_active_session_event_reservation_cannot_be_reclaimed(db):
    session = await create_session(db, 1, "girlai")
    first, _ = await reserve_session_event(
        db,
        session.id,
        1,
        "companion.turn.processing",
        "turn-active",
        {"attempt": 1},
        reclaim_after_seconds=60,
    )

    duplicate, duplicate_created = await reserve_session_event(
        db,
        session.id,
        1,
        "companion.turn.processing",
        "turn-active",
        {"attempt": 2},
        reclaim_after_seconds=60,
    )

    assert duplicate_created is False
    assert duplicate.id == first.id
    assert duplicate.payload_json == {"attempt": 1}


@pytest.mark.asyncio
async def test_reclaimed_reservation_fences_previous_owner(db):
    session = await create_session(db, 1, "girlai")
    first, _ = await reserve_session_event(
        db,
        session.id,
        1,
        "companion.turn.processing",
        "turn-fenced",
        reservation_token="owner-1",
        reclaim_after_seconds=60,
    )
    first.created_at = datetime.utcnow() - timedelta(seconds=61)
    await db.commit()

    reclaimed, reclaimed_created = await reserve_session_event(
        db,
        session.id,
        1,
        "companion.turn.processing",
        "turn-fenced",
        reservation_token="owner-2",
        reclaim_after_seconds=60,
    )

    assert reclaimed_created is True
    assert reclaimed.reservation_token == "owner-2"
    with pytest.raises(StateConflictError):
        await update_session_event(
            db,
            session.id,
            1,
            "turn-fenced",
            "companion.turn.completed",
            {"owner": 1},
            expected_reservation_token="owner-1",
        )

    completed = await update_session_event(
        db,
        session.id,
        1,
        "turn-fenced",
        "companion.turn.completed",
        {"owner": 2},
        expected_reservation_token="owner-2",
    )
    assert completed.event_type == "companion.turn.completed"
    assert completed.payload_json == {"owner": 2}
    assert completed.reservation_token is None
