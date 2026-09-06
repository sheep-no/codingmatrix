"""Integration coverage for GirlAI session isolation and turn recovery."""

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models.Permission import Permission
from app.models.base import Base
from app.models.user import User
from app.schema.girl_companion import CompanionTurn
from app.services.girlai_companion_context import build_companion_context
from app.services.girlai_state_adapter import (
    append_companion_turn_state,
    get_companion_turn_state,
    get_latest_companion_turn_state,
    reserve_companion_turn_state,
)
from app.services.unified_state_service import (
    StateOwnershipError,
    append_message,
    create_session,
    list_messages,
)


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
        session.add_all(
            [
                User(id=1, username="companion-user-1", email="companion-1@example.com", hashed_password="hash"),
                User(id=2, username="companion-user-2", email="companion-2@example.com", hashed_password="hash"),
                Permission(user_id=1, permission_level="normal"),
                Permission(user_id=2, permission_level="normal"),
            ]
        )
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_companion_context_isolated_across_sessions(test_db):
    first_session = await create_session(test_db, 1, "girlai", external_id="user:1")
    second_session = await create_session(test_db, 2, "girlai", external_id="user:2")
    await append_message(test_db, first_session.id, 1, "user", "用户一的工作计划")
    await append_message(test_db, second_session.id, 2, "user", "用户二的旅行计划")

    first_messages = await list_messages(test_db, first_session.id, 1)
    second_messages = await list_messages(test_db, second_session.id, 2)
    first_context = build_companion_context(
        character={"name": "姬一", "description": "陪伴", "personality": "稳重"},
        user_prompt="继续安排",
        recent_messages=[{"role": item.role, "content": item.content} for item in first_messages],
        memories=[{"key": "项目", "value": "季度计划", "visibility": "companion_allowed"}],
        tasks=[{"title": "完成计划", "status": "pending"}],
    )
    second_context = build_companion_context(
        character={"name": "姬二", "description": "陪伴", "personality": "轻松"},
        user_prompt="继续安排",
        recent_messages=[{"role": item.role, "content": item.content} for item in second_messages],
        memories=[{"key": "目的地", "value": "海边", "visibility": "companion_allowed"}],
        tasks=[{"title": "预订酒店", "status": "pending"}],
    )

    assert "用户一的工作计划" in first_context.prompt
    assert "用户二的旅行计划" not in first_context.prompt
    assert "季度计划" in first_context.prompt
    assert "预订酒店" not in first_context.prompt
    assert "用户二的旅行计划" in second_context.prompt
    assert "用户一的工作计划" not in second_context.prompt
    assert first_session.id != second_session.id


@pytest.mark.integration
@pytest.mark.asyncio
async def test_companion_turn_recovery_preserves_model_context_and_ownership(test_db):
    first_session = await create_session(test_db, 1, "girlai", external_id="user:1")
    second_session = await create_session(test_db, 2, "girlai", external_id="user:2")
    turn = CompanionTurn(
        turn_id="turn-user-1",
        conversation_id=first_session.id,
        assistant_text="已恢复你的工作上下文。",
        model_context={
            "current_model": "conversation-model-v2",
            "classification_model": "classifier-model-v1",
            "current_agent": "companion-agent",
            "calls": 3,
            "fallback_used": True,
            "fallback_history": ["conversation-model-v1"],
        },
    )
    reservation, created = await reserve_companion_turn_state(
        test_db, 1, first_session.id, turn.turn_id
    )
    assert created is True
    persisted = await append_companion_turn_state(
        test_db,
        1,
        first_session.id,
        turn,
        model="conversation-model-v2",
        tokens_used=42,
        reservation_token=reservation.reservation_token,
    )
    await test_db.commit()

    recovered = await get_companion_turn_state(test_db, 1, first_session.id, turn.turn_id)
    latest = await get_latest_companion_turn_state(test_db, 1, first_session.id)

    assert recovered is not None
    assert latest is not None
    assert recovered.id == persisted.id == latest.id
    assert recovered.event_type == "companion.turn.completed"
    assert recovered.payload_json["model"] == "conversation-model-v2"
    assert recovered.payload_json["tokens_used"] == 42
    assert recovered.payload_json["conversation_id"] == first_session.id
    assert recovered.payload_json["model_context"] == {
        "current_model": "conversation-model-v2",
        "classification_model": "classifier-model-v1",
        "current_agent": "companion-agent",
        "calls": 3,
        "fallback_used": True,
        "fallback_history": ["conversation-model-v1"],
    }

    with pytest.raises(StateOwnershipError):
        await get_companion_turn_state(test_db, 2, first_session.id, turn.turn_id)
    assert await get_latest_companion_turn_state(test_db, 2, second_session.id) is None
