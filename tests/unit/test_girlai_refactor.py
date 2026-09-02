import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import GirlAi as girl_module
from app.api.v1.GirlAi import _build_emotion_prompt, _extract_llm_response, _get_character
from app.db.chat_history_service import ChatHistoryService
from app.db import chat_archiver as archiver_module
from app.db.chat_archiver import ChatArchiver
from app.models.chat_history import ChatHistory, CustomCharacter


@pytest.mark.asyncio
async def test_custom_character_is_loaded_for_owner():
    character = CustomCharacter(
        id="character-1",
        user_id=7,
        name="测试角色",
        description="描述",
        personality="沉稳",
        speaking_style="简洁",
        greetings=json.dumps(["你好"]),
        tags=json.dumps(["测试"]),
        model="test-model",
        temperature=65,
        max_tokens=240,
    )
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = character
    db.execute.return_value = result

    loaded = await _get_character("custom_character-1", 7, db)

    assert loaded["id"] == "custom_character-1"
    assert loaded["personality"] == "沉稳"
    assert loaded["temperature"] == 0.65
    assert loaded["greetings"] == ["你好"]


@pytest.mark.asyncio
async def test_missing_custom_character_returns_not_found():
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result

    with pytest.raises(HTTPException) as error:
        await _get_character("custom_missing", 7, db)

    assert error.value.status_code == 404


def test_history_summary_is_included_in_prompt():
    character = {
        "name": "测试角色",
        "description": "描述",
        "personality": "沉稳",
        "speaking_style": "简洁",
        "greetings": ["你好"],
    }

    prompt = _build_emotion_prompt(
        character,
        "继续聊",
        [],
        history_summary="用户之前在准备发布计划。",
    )

    assert "【较早对话摘要】" in prompt
    assert "用户之前在准备发布计划。" in prompt


def test_llm_response_validation_allows_missing_usage():
    content, tokens = _extract_llm_response({
        "choices": [{"message": {"content": "有效回复"}}]
    })

    assert content == "有效回复"
    assert tokens == 0


def test_llm_response_validation_rejects_missing_content():
    with pytest.raises(RuntimeError, match="无效响应"):
        _extract_llm_response({"choices": []})


@pytest.mark.asyncio
async def test_legacy_turn_flushes_without_committing():
    db = AsyncMock()
    service = ChatHistoryService(db)

    records = await service.save_conversation_turn(
        user_id="7",
        user_content="你好",
        assistant_content="你好，我在。",
        model="test-model",
        tokens_used=5,
    )

    assert len(records) == 2
    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_clear_history_commits_legacy_and_unified_together(monkeypatch):
    db = AsyncMock()
    service = AsyncMock()
    service.clear_user_history.return_value = 2
    monkeypatch.setattr(girl_module, "ChatHistoryService", MagicMock(return_value=service))
    clear_unified = AsyncMock(return_value=2)
    monkeypatch.setattr(girl_module, "clear_messages_for_user", clear_unified)

    response = await girl_module.delete_history(
        record_ids=None,
        all=True,
        token={"sub": "7"},
        db=db,
    )

    assert response == {"status": "deleted", "count": 2}
    service.clear_user_history.assert_awaited_once_with("7")
    clear_unified.assert_awaited_once_with(db, 7)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_archiver_flushes_summary_and_syncs_unified_state(monkeypatch):
    db = AsyncMock()
    now = datetime.utcnow()
    messages = [
        ChatHistory(id=11, user_id=7, role="user", content="问题", created_at=now - timedelta(days=5)),
        ChatHistory(id=12, user_id=7, role="assistant", content="回答", created_at=now - timedelta(days=5)),
    ]
    no_summary = MagicMock()
    no_summary.scalar_one_or_none.return_value = None
    no_overlap = MagicMock()
    no_overlap.scalar_one_or_none.return_value = None
    history_result = MagicMock()
    history_result.scalars.return_value.all.return_value = messages
    delete_result = MagicMock(rowcount=2)
    db.execute.side_effect = [no_summary, no_overlap, history_result, delete_result]
    archiver = ChatArchiver(db)
    monkeypatch.setattr(archiver, "_generate_summary_with_ai", AsyncMock(return_value="对话摘要"))
    save_checkpoint = AsyncMock()
    delete_unified = AsyncMock(return_value=2)
    monkeypatch.setattr(archiver_module, "save_summary_checkpoint", save_checkpoint)
    monkeypatch.setattr(archiver_module, "delete_messages_for_legacy_ids", delete_unified)

    await archiver._archive_user(7, 3, 13)

    db.flush.assert_awaited_once()
    save_checkpoint.assert_awaited_once()
    delete_unified.assert_awaited_once_with(db, 7, [11, 12])
    db.commit.assert_not_awaited()
