"""Integration coverage for GirlAI legacy and unified state consistency."""

from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1 import GirlAi as girl_module
from app.models.Permission import Permission
from app.models.base import Base
from app.models.chat_history import ChatHistory
from app.models.user import User
from app.models.unified_state import Message, SessionEvent
from app.schema.girl_companion import CompanionTurnRequest, EmotionState, IntentState
from app.services.girlai_companion_classifier import ClassificationResult


@pytest_asyncio.fixture
async def test_db() -> AsyncSession:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with session_factory() as session:
        session.add(User(id=1, username="girlai-consistency", email="girlai-consistency@example.com", hashed_password="hash"))
        session.add(Permission(user_id=1, permission_level="normal"))
        await session.commit()
        yield session
    await engine.dispose()


def _character():
    return {
        "id": "gentle",
        "name": "温柔姐姐",
        "description": "陪伴",
        "personality": "温柔",
        "speaking_style": "简洁",
        "model": "conversation-model",
        "temperature": 0.8,
        "max_tokens": 100,
    }


def _classification():
    return ClassificationResult(
        emotion=EmotionState(label="focused", intensity=0.7, confidence=0.9),
        intent=IntentState(label="task_planning", confidence=0.9),
        model="classifier-model",
        calls=1,
    )


async def _successful_retry(callback, max_retries=3):
    return await callback()


def _patch_companion_dependencies(monkeypatch, *, append=None):
    monkeypatch.setattr(girl_module, "_get_character", AsyncMock(return_value=_character()))
    monkeypatch.setattr(
        girl_module,
        "classify_companion_input",
        AsyncMock(return_value=_classification()),
    )
    monkeypatch.setattr(girl_module, "call_with_retry", _successful_retry)
    monkeypatch.setattr(
        girl_module,
        "call_llm",
        AsyncMock(
            return_value={
                "choices": [
                    {"message": {"content": '{"assistant_text":"已保存。"}'}},
                ],
                "usage": {"total_tokens": 11},
            }
        ),
    )
    if append is not None:
        monkeypatch.setattr(girl_module, "append_conversation_turn", append)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_companion_turn_commits_legacy_and_unified_records_together(test_db, monkeypatch):
    _patch_companion_dependencies(monkeypatch)

    response = await girl_module.generate_companion_turn(
        CompanionTurnRequest(prompt="请保存这个计划", turn_id="consistency-turn-1"),
        token={"sub": "1"},
        db=test_db,
    )

    legacy_records = list(
        (await test_db.scalars(select(ChatHistory).where(ChatHistory.user_id == 1))).all()
    )
    unified_messages = list(
        (await test_db.scalars(select(Message).where(Message.user_id == 1))).all()
    )
    events = list(
        (await test_db.scalars(select(SessionEvent).where(SessionEvent.user_id == 1))).all()
    )

    assert response.assistant_text == "已保存。"
    assert [(record.role, record.content) for record in legacy_records] == [
        ("user", "请保存这个计划"),
        ("assistant", "已保存。"),
    ]
    assert [(message.role, message.content) for message in unified_messages] == [
        ("user", "请保存这个计划"),
        ("assistant", "已保存。"),
    ]
    assert [record.metadata_json["legacy_message_id"] for record in unified_messages] == [
        legacy_records[0].id,
        legacy_records[1].id,
    ]
    completed = [event for event in events if event.event_type == "companion.turn.completed"]
    assert len(completed) == 1
    assert completed[0].payload_json["turn_id"] == "consistency-turn-1"
    assert completed[0].payload_json["conversation_id"] == response.conversation_id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_companion_turn_rolls_back_both_histories_when_unified_write_fails(
    test_db, monkeypatch
):
    append_failure = AsyncMock(side_effect=RuntimeError("unified write failed"))
    _patch_companion_dependencies(monkeypatch, append=append_failure)

    with pytest.raises(girl_module.HTTPException) as error:
        await girl_module.generate_companion_turn(
            CompanionTurnRequest(prompt="这次写入应回滚", turn_id="consistency-turn-rollback"),
            token={"sub": "1"},
            db=test_db,
        )

    legacy_records = list(
        (await test_db.scalars(select(ChatHistory).where(ChatHistory.user_id == 1))).all()
    )
    unified_messages = list(
        (await test_db.scalars(select(Message).where(Message.user_id == 1))).all()
    )
    events = list(
        (await test_db.scalars(select(SessionEvent).where(SessionEvent.user_id == 1))).all()
    )

    assert error.value.status_code == 502
    assert legacy_records == []
    assert unified_messages == []
    assert [event.event_type for event in events] == ["companion.turn.failed"]
    assert events[0].payload_json["turn_id"] == "consistency-turn-rollback"
    assert events[0].payload_json["error_type"] == "RuntimeError"
