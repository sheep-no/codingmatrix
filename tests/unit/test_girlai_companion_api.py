from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest
from fastapi import HTTPException

from app.api.v1 import GirlAi as girl_module
from app.schema.girl_companion import (
    CompanionMemoryConfirmRequest,
    CompanionTurnRequest,
    EmotionState,
    IntentState,
)
from app.services.girlai_companion_classifier import ClassificationResult


@pytest.mark.asyncio
async def test_companion_turn_returns_structured_response_and_persists_both_histories(monkeypatch):
    db = AsyncMock()
    preference_result = MagicMock()
    preference_result.scalars.return_value.all.return_value = []
    db.execute.return_value = preference_result
    history = create_autospec(girl_module.ChatHistoryService, instance=True)
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
    monkeypatch.setattr(
        girl_module,
        "reserve_companion_turn_state",
        AsyncMock(
            return_value=(
                SimpleNamespace(
                    event_type="companion.turn.processing",
                    reservation_token="reservation-1",
                ),
                True,
            )
        ),
    )
    append = AsyncMock()
    monkeypatch.setattr(girl_module, "append_conversation_turn", append)
    append_state = create_autospec(girl_module.append_companion_turn_state)
    append_state.return_value = SimpleNamespace(sequence=1)
    monkeypatch.setattr(girl_module, "append_companion_turn_state", append_state)
    monkeypatch.setattr(
        girl_module,
        "classify_companion_input",
        AsyncMock(
            return_value=ClassificationResult(
                emotion=EmotionState(label="focused", intensity=0.7, confidence=0.9),
                intent=IntentState(label="task_planning", confidence=0.9),
                model="classifier-model",
                calls=1,
            )
        ),
    )

    llm = AsyncMock(
        return_value={
            "choices": [{"message": {"content": '{"assistant_text":"我来帮你。","intent":{"label":"planning"}}'}}],
            "usage": {"total_tokens": 9},
        }
    )
    monkeypatch.setattr(girl_module, "call_llm", llm)

    async def retry(callback, max_retries=3):
        return await callback()

    monkeypatch.setattr(girl_module, "call_with_retry", retry)

    response = await girl_module.generate_companion_turn(
        CompanionTurnRequest(prompt="请帮我规划", turn_id="turn-1"),
        token={"sub": "7"},
        db=db,
    )

    assert response.turn_id == "turn-1"
    assert response.conversation_id == "girlai-session"
    assert response.assistant_text == "我来帮你。"
    assert response.intent.label == "task_planning"
    assert response.emotion.label == "focused"
    assert response.tokens_used == 9
    assert response.state_revision == 1
    assert llm.await_args.kwargs["max_tokens"] == 512
    assert llm.await_args.kwargs["temperature"] == 0.3
    assert "仅输出一个合法 JSON 对象" in llm.await_args.kwargs["system_prompt"]
    assert "请帮我规划" in llm.await_args.kwargs["prompt"]
    history.save_conversation_turn.assert_awaited_once()
    append.assert_awaited_once()
    append_state.assert_awaited_once()
    assert append_state.await_args.kwargs["reservation_token"] == "reservation-1"
    assert db.commit.await_count == 2


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
async def test_classification_failure_preserves_text_conversation(monkeypatch):
    db = AsyncMock()
    preference_result = MagicMock()
    preference_result.scalars.return_value.all.return_value = []
    db.execute.return_value = preference_result
    history = AsyncMock()
    history.get_lightweight_context.return_value = ([], None)
    history.save_conversation_turn.return_value = (
        SimpleNamespace(id=1),
        SimpleNamespace(id=2),
    )
    monkeypatch.setattr(girl_module, "ChatHistoryService", MagicMock(return_value=history))
    monkeypatch.setattr(
        girl_module,
        "_get_character",
        AsyncMock(
            return_value={
                "id": "gentle",
                "name": "温柔姐姐",
                "description": "陪伴",
                "personality": "温柔",
                "speaking_style": "简洁",
                "model": "test-model",
                "temperature": 0.8,
                "max_tokens": 100,
            }
        ),
    )
    monkeypatch.setattr(
        girl_module,
        "ensure_session",
        AsyncMock(return_value=SimpleNamespace(id="girlai-session")),
    )
    monkeypatch.setattr(
        girl_module,
        "reserve_companion_turn_state",
        AsyncMock(
            return_value=(
                SimpleNamespace(
                    event_type="companion.turn.processing",
                    reservation_token="reservation-2",
                ),
                True,
            )
        ),
    )
    monkeypatch.setattr(girl_module, "append_conversation_turn", AsyncMock())
    monkeypatch.setattr(
        girl_module,
        "append_companion_turn_state",
        AsyncMock(return_value=SimpleNamespace(sequence=2)),
    )
    monkeypatch.setattr(
        girl_module,
        "classify_companion_input",
        AsyncMock(
            return_value=ClassificationResult(
                degraded_capabilities=[
                    "emotion_classification",
                    "intent_classification",
                ],
                parse_failed=True,
            )
        ),
    )

    async def retry(callback, max_retries=3):
        return {
            "choices": [{"message": {"content": "我会继续陪你处理当前工作。"}}],
            "usage": {"total_tokens": 6},
        }

    monkeypatch.setattr(girl_module, "call_with_retry", retry)

    response = await girl_module.generate_companion_turn(
        CompanionTurnRequest(prompt="继续吧", turn_id="turn-degraded"),
        token={"sub": "7"},
        db=db,
    )

    assert response.assistant_text == "我会继续陪你处理当前工作。"
    assert response.emotion.label == "neutral"
    assert response.intent.label == "unknown"
    assert "emotion_classification" in response.degraded_capabilities
    assert response.state_revision == 2
    history.save_conversation_turn.assert_awaited_once()
    assert db.commit.await_count == 2


@pytest.mark.asyncio
async def test_duplicate_turn_id_replays_without_new_model_or_history_calls(monkeypatch):
    db = AsyncMock()
    history = AsyncMock()
    monkeypatch.setattr(girl_module, "ChatHistoryService", MagicMock(return_value=history))
    monkeypatch.setattr(
        girl_module,
        "_get_character",
        AsyncMock(
            return_value={
                "id": "gentle",
                "name": "温柔姐姐",
                "description": "陪伴",
                "personality": "温柔",
                "speaking_style": "简洁",
                "model": "test-model",
                "temperature": 0.8,
                "max_tokens": 100,
            }
        ),
    )
    monkeypatch.setattr(
        girl_module,
        "ensure_session",
        AsyncMock(return_value=SimpleNamespace(id="girlai-session")),
    )
    monkeypatch.setattr(
        girl_module,
        "reserve_companion_turn_state",
        AsyncMock(
            return_value=(
                SimpleNamespace(
                    event_type="companion.turn.completed",
                    sequence=3,
                    payload_json={
                        "assistant_text": "已保存的回复",
                        "model": "test-model",
                        "tokens_used": 7,
                    },
                ),
                False,
            )
        ),
    )
    classifier = AsyncMock()
    monkeypatch.setattr(girl_module, "classify_companion_input", classifier)

    response = await girl_module.generate_companion_turn(
        CompanionTurnRequest(prompt="重复请求", turn_id="turn-existing"),
        token={"sub": "7"},
        db=db,
    )

    assert response.assistant_text == "已保存的回复"
    assert response.state_revision == 3
    assert response.tokens_used == 7
    history.get_lightweight_context.assert_not_awaited()
    history.save_conversation_turn.assert_not_awaited()
    classifier.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_turn_reservation_returns_conflict(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(girl_module, "ChatHistoryService", MagicMock())
    monkeypatch.setattr(
        girl_module,
        "_get_character",
        AsyncMock(return_value={"model": "test-model"}),
    )
    monkeypatch.setattr(
        girl_module,
        "ensure_session",
        AsyncMock(return_value=SimpleNamespace(id="girlai-session")),
    )
    monkeypatch.setattr(
        girl_module,
        "reserve_companion_turn_state",
        AsyncMock(
            return_value=(
                SimpleNamespace(
                    event_type="companion.turn.processing",
                    sequence=1,
                    payload_json={},
                ),
                False,
            )
        ),
    )

    with pytest.raises(HTTPException) as error:
        await girl_module.generate_companion_turn(
            CompanionTurnRequest(prompt="重复请求", turn_id="turn-active"),
            token={"sub": "7"},
            db=db,
        )

    assert error.value.status_code == 409
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_model_failure_records_failed_event_with_stable_session_id(monkeypatch):
    db = AsyncMock()
    preference_result = MagicMock()
    preference_result.scalars.return_value.all.return_value = []
    db.execute.return_value = preference_result
    history = AsyncMock()
    history.get_lightweight_context.return_value = ([], None)
    monkeypatch.setattr(girl_module, "ChatHistoryService", MagicMock(return_value=history))
    monkeypatch.setattr(
        girl_module,
        "_get_character",
        AsyncMock(
            return_value={
                "id": "gentle",
                "name": "温柔姐姐",
                "description": "陪伴",
                "personality": "温柔",
                "speaking_style": "简洁",
                "model": "test-model",
                "temperature": 0.8,
                "max_tokens": 100,
            }
        ),
    )
    monkeypatch.setattr(
        girl_module,
        "ensure_session",
        AsyncMock(return_value=SimpleNamespace(id="girlai-session")),
    )
    monkeypatch.setattr(
        girl_module,
        "reserve_companion_turn_state",
        AsyncMock(
            return_value=(
                SimpleNamespace(
                    event_type="companion.turn.processing",
                    reservation_token="reservation-failed",
                ),
                True,
            )
        ),
    )
    fail_state = AsyncMock()
    monkeypatch.setattr(girl_module, "fail_companion_turn_state", fail_state)

    async def failed_retry(callback, max_retries=3):
        raise HTTPException(status_code=401, detail="provider failure")

    monkeypatch.setattr(girl_module, "call_with_retry", failed_retry)

    with pytest.raises(HTTPException) as error:
        await girl_module.generate_companion_turn(
            CompanionTurnRequest(prompt="继续", turn_id="turn-failed"),
            token={"sub": "7"},
            db=db,
        )

    assert error.value.status_code == 502
    fail_state.assert_awaited_once_with(
        db,
        7,
        "girlai-session",
        "turn-failed",
        "HTTPException",
        "reservation-failed",
    )
    assert db.commit.await_count == 2
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_companion_state_returns_authenticated_session(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        girl_module,
        "ensure_session",
        AsyncMock(return_value=SimpleNamespace(id="girlai-session")),
    )
    monkeypatch.setattr(
        girl_module,
        "get_latest_companion_turn_state",
        AsyncMock(return_value=None),
    )

    state = await girl_module.get_companion_state(token={"sub": "7"}, db=db)

    assert state["conversation_id"] == "girlai-session"
    assert state["capabilities"]["text"] is True
    assert state["state_revision"] == 0
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_companion_state_restores_latest_emotion_and_intent(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        girl_module,
        "ensure_session",
        AsyncMock(return_value=SimpleNamespace(id="girlai-session")),
    )
    monkeypatch.setattr(
        girl_module,
        "get_latest_companion_turn_state",
        AsyncMock(
            return_value=SimpleNamespace(
                sequence=4,
                payload_json={
                    "emotion": {"label": "stressed", "intensity": 0.8, "confidence": 0.9},
                    "intent": {"label": "task_blocked", "confidence": 0.85},
                    "care_required": True,
                    "response_style": "care",
                    "work_options": ["确认当前阻塞点"],
                    "degraded_capabilities": [],
                },
            )
        ),
    )

    state = await girl_module.get_companion_state(token={"sub": "7"}, db=db)

    assert state["emotion"]["label"] == "stressed"
    assert state["intent"]["label"] == "task_blocked"
    assert state["care_required"] is True
    assert state["state_revision"] == 4


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
