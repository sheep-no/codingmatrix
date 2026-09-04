from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import GirlAi as girl_module
from app.schema.girl_companion import CompanionMemoryConfirmRequest, CompanionTurnRequest


@pytest.mark.asyncio
async def test_companion_turn_returns_structured_response_and_persists_both_histories(monkeypatch):
    db = AsyncMock()
    preference_result = MagicMock()
    preference_result.scalars.return_value.all.return_value = []
    db.execute.return_value = preference_result
    history = AsyncMock()
    history.get_lightweight_context.return_value = ([{"role": "user", "content": "旧消息"}], None)
    history.save_conversation_turn.return_value = (
        SimpleNamespace(id=1),
        SimpleNamespace(id=2),
    )
    monkeypatch.setattr(girl_module, "ChatHistoryService", MagicMock(return_value=history))
    monkeypatch.setattr(
        girl_module,
        "_get_character",
        AsyncMock(return_value={
            "id": "gentle",
            "name": "温柔姐姐",
            "description": "陪伴",
            "personality": "温柔",
            "speaking_style": "简洁",
            "model": "test-model",
            "temperature": 0.8,
            "max_tokens": 100,
        }),
    )
    session = SimpleNamespace(id="girlai-session")
    monkeypatch.setattr(girl_module, "ensure_session", AsyncMock(return_value=session))
    append = AsyncMock()
    monkeypatch.setattr(girl_module, "append_conversation_turn", append)

    async def retry(callback, max_retries=3):
        return {
            "choices": [{"message": {"content": '{"assistant_text":"我来帮你。","intent":{"label":"planning"}}'}}],
            "usage": {"total_tokens": 9},
        }

    monkeypatch.setattr(girl_module, "call_with_retry", retry)

    response = await girl_module.generate_companion_turn(
        CompanionTurnRequest(prompt="请帮我规划", turn_id="turn-1"),
        token={"sub": "7"},
        db=db,
    )

    assert response.turn_id == "turn-1"
    assert response.conversation_id == "girlai-session"
    assert response.assistant_text == "我来帮你。"
    assert response.intent.label == "planning"
    assert response.tokens_used == 9
    history.save_conversation_turn.assert_awaited_once()
    append.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_companion_turn_rejects_missing_token():
    with pytest.raises(HTTPException) as error:
        await girl_module.generate_companion_turn(
            CompanionTurnRequest(prompt="你好"),
            token={},
            db=AsyncMock(),
        )

    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_companion_state_returns_authenticated_session(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        girl_module,
        "ensure_session",
        AsyncMock(return_value=SimpleNamespace(id="girlai-session")),
    )

    state = await girl_module.get_companion_state(token={"sub": "7"}, db=db)

    assert state["conversation_id"] == "girlai-session"
    assert state["capabilities"]["text"] is True
    assert state["state_revision"] == 0
    db.commit.assert_awaited_once()


def _memory(**overrides):
    values = {
        "id": "memory-1",
        "preference_key": "work",
        "preference_value": "开发平台",
        "confidence": 88,
        "source": "conversation",
        "status": "candidate",
        "consent_source": "system_derived",
        "visibility": "conversation_only",
        "last_used_at": None,
        "created_at": None,
        "updated_at": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


@pytest.mark.asyncio
async def test_memory_api_lists_and_confirms_owned_candidate(monkeypatch):
    db = AsyncMock()
    candidate = _memory()
    confirmed = _memory(
        preference_value="开发 AI 平台",
        status="confirmed",
        consent_source="user_confirmed",
        visibility="companion_allowed",
    )
    service = AsyncMock()
    service.list_memories.return_value = ([candidate], 1)
    service.confirm.return_value = confirmed
    monkeypatch.setattr(girl_module, "CompanionMemoryService", MagicMock(return_value=service))

    page = await girl_module.get_companion_memories(
        token={"sub": "7"}, db=db, limit=20, offset=0, memory_status=None
    )
    response = await girl_module.confirm_companion_memory(
        "memory-1",
        CompanionMemoryConfirmRequest(value="开发 AI 平台"),
        token={"sub": "7"},
        db=db,
    )

    assert page.total == 1
    assert page.memories[0].status == "candidate"
    assert response.status == "confirmed"
    assert response.value == "开发 AI 平台"
    service.confirm.assert_awaited_once_with(
        7,
        "memory-1",
        key=None,
        value="开发 AI 平台",
        visibility="companion_allowed",
    )
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_api_returns_not_found_for_other_user(monkeypatch):
    db = AsyncMock()
    service = AsyncMock()
    service.soft_delete.side_effect = girl_module.CompanionMemoryNotFoundError("memory-1")
    monkeypatch.setattr(girl_module, "CompanionMemoryService", MagicMock(return_value=service))

    with pytest.raises(HTTPException) as error:
        await girl_module.delete_companion_memory("memory-1", token={"sub": "8"}, db=db)

    assert error.value.status_code == 404
    db.rollback.assert_awaited_once()
