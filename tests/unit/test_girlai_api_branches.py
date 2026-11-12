"""Branch coverage for the GirlAI API module."""

import asyncio
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import GirlAi as girl_module
from app.schema.girl_companion import (
    CompanionMemoryConfirmRequest,
    CompanionTurn,
    CompanionTurnRequest,
    MemoryCandidate,
)
from app.schema.girl_request import GirlRequest


def _db_with_scalars(values=None):
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = list(values or [])
    result.scalar.return_value = 0
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    return db


def _character():
    return {
        "id": "gentle",
        "name": "温柔姐姐",
        "description": "陪伴",
        "personality": "温柔",
        "speaking_style": "简洁",
        "greetings": ["你好"],
        "tags": ["温柔"],
        "model": "test-model",
        "temperature": 0.8,
        "max_tokens": 100,
    }


class TestHelpers:
    @pytest.mark.asyncio
    async def test_builtin_character_short_circuits_database(self):
        db = AsyncMock()

        character = await girl_module._get_character("gentle", 7, db)

        assert character is girl_module.CHARACTER_PROFILES["gentle"]
        db.execute.assert_not_awaited()

    def test_prompt_includes_preferences_messages_and_name(self):
        prompt = girl_module._build_emotion_prompt(
            _character(),
            "今天好累",
            [{"role": "user", "content": "在忙"}, {"role": "assistant", "content": "加油"}],
            user_name="小明",
            user_preferences=[{"key": "hobby", "value": "跑步"}],
        )

        assert "【你记住的用户信息】" in prompt
        assert "hobby：跑步" in prompt
        assert "【对话历史】" in prompt
        assert "用户称呼：小明" in prompt

    def test_clean_response_strips_role_and_bracket_prefixes(self):
        assert girl_module._clean_response("温柔姐姐: 你好", "温柔姐姐") == "你好"
        assert girl_module._clean_response("【心情】 你好", "温柔姐姐") == "你好"
        assert girl_module._clean_response('": 你好', "温柔姐姐") == "你好"

    def test_extract_llm_response_rejects_empty_content(self):
        with pytest.raises(RuntimeError, match="空响应"):
            girl_module._extract_llm_response(
                {"choices": [{"message": {"content": "   "}}]}
            )
        with pytest.raises(RuntimeError, match="空响应"):
            girl_module._extract_llm_response(
                {"choices": [{"message": {"content": None}}]}
            )

    @pytest.mark.asyncio
    async def test_record_failure_skips_without_session(self):
        db = AsyncMock()
        await girl_module._record_companion_turn_failure(
            db, 1, None, "turn", "error", None
        )
        db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_record_failure_swallows_persistence_errors(self, monkeypatch):
        db = AsyncMock()
        monkeypatch.setattr(
            girl_module,
            "fail_companion_turn_state",
            AsyncMock(side_effect=RuntimeError("boom")),
        )
        warning = MagicMock()
        monkeypatch.setattr(girl_module, "logger", SimpleNamespace(warning=warning))

        await girl_module._record_companion_turn_failure(
            db, 1, "session", "turn", "RuntimeError", "token"
        )

        db.rollback.assert_awaited_once()
        warning.assert_called_once()


class TestPreferenceExtraction:
    @pytest.mark.asyncio
    async def test_extracts_and_persists_preferences(self, monkeypatch):
        db = AsyncMock()
        session_cm = MagicMock()
        session_cm.__aenter__ = AsyncMock(return_value=db)
        session_cm.__aexit__ = AsyncMock(return_value=False)
        monkeypatch.setattr(girl_module, "async_session", MagicMock(return_value=session_cm))
        service = AsyncMock()
        monkeypatch.setattr(
            girl_module, "CompanionMemoryService", MagicMock(return_value=service)
        )

        await girl_module._extract_user_preferences("7", "我叫小明，我住在北京", "你好")

        candidates = service.create_candidates.await_args.args[1]
        keys = {candidate.key for candidate in candidates}
        assert {"name", "location"} <= keys
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_no_match_returns_without_persistence(self, monkeypatch):
        factory = MagicMock()
        monkeypatch.setattr(girl_module, "async_session", factory)

        await girl_module._extract_user_preferences("7", "今天天气不错", "是啊")

        factory.assert_not_called()

    @pytest.mark.asyncio
    async def test_persistence_errors_are_swallowed(self, monkeypatch):
        monkeypatch.setattr(
            girl_module,
            "async_session",
            MagicMock(side_effect=RuntimeError("db down")),
        )

        await girl_module._extract_user_preferences("7", "我叫小明", "你好")

    @pytest.mark.asyncio
    async def test_blank_extracted_value_is_dropped(self, monkeypatch):
        factory = MagicMock()
        monkeypatch.setattr(girl_module, "async_session", factory)

        await girl_module._extract_user_preferences("7", "我叫 ", "你好")

        factory.assert_not_called()


class TestCharacterEndpoints:
    @pytest.mark.asyncio
    async def test_get_characters_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.get_characters(token={})
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_characters_returns_profiles(self):
        result = await girl_module.get_characters(token={"sub": "7"})
        assert result["total"] == len(girl_module.CHARACTER_PROFILES)

    @pytest.mark.asyncio
    async def test_avatar_falls_back_to_default(self):
        response = await girl_module.get_character_avatar("unknown")
        assert response.media_type == "image/svg+xml"
        assert b"svg" in response.body

    @pytest.mark.asyncio
    async def test_avatar_returns_known_character(self):
        response = await girl_module.get_character_avatar("lively")
        assert response.body == girl_module.CHARACTER_AVATARS["lively"].encode()


class TestGenerateMessage:
    def _patch_success(self, monkeypatch, prefs=None):
        db = _db_with_scalars(prefs)
        history = AsyncMock()
        history.get_lightweight_context.return_value = ([], None)
        history.save_conversation_turn.return_value = [SimpleNamespace(id=1)]
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=history)
        )
        monkeypatch.setattr(
            girl_module, "_get_character", AsyncMock(return_value=_character())
        )
        llm = AsyncMock(
            return_value={
                "choices": [{"message": {"content": "温柔姐姐: 我在呢"}}],
                "usage": {"total_tokens": 4},
            }
        )
        monkeypatch.setattr(girl_module, "call_llm", llm)

        async def retry(callback, max_retries=3):
            return await callback()

        monkeypatch.setattr(girl_module, "call_with_retry", retry)
        monkeypatch.setattr(girl_module, "append_conversation_turn", AsyncMock())
        monkeypatch.setattr(girl_module, "_track_background_task", MagicMock())
        return db

    @pytest.mark.asyncio
    async def test_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.generate_message(
                GirlRequest(prompt="你好"), token={}, db=AsyncMock()
            )
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_success_records_turn_and_extracts_preferences(self, monkeypatch):
        pref = SimpleNamespace(preference_key="hobby", preference_value="跑步")
        db = self._patch_success(monkeypatch, prefs=[pref])
        track = girl_module._track_background_task

        response = await girl_module.generate_message(
            GirlRequest(prompt="你好", character_id="gentle"),
            token={"sub": "7"},
            db=db,
        )

        assert response.message == "我在呢"
        assert response.tokens_used == 4
        db.commit.assert_awaited_once()
        track.assert_called_once()

    @pytest.mark.asyncio
    async def test_preference_query_failure_is_ignored(self, monkeypatch):
        db = self._patch_success(monkeypatch)
        db.execute.side_effect = [RuntimeError("no table"), MagicMock()]

        response = await girl_module.generate_message(
            GirlRequest(prompt="你好"), token={"sub": "7"}, db=db
        )

        assert response.message == "我在呢"

    @pytest.mark.asyncio
    async def test_timeout_maps_to_gateway_timeout(self, monkeypatch):
        db = self._patch_success(monkeypatch)

        async def timeout_retry(callback, max_retries=3):
            raise asyncio.TimeoutError

        monkeypatch.setattr(girl_module, "call_with_retry", timeout_retry)

        with pytest.raises(HTTPException) as error:
            await girl_module.generate_message(
                GirlRequest(prompt="你好"), token={"sub": "7"}, db=db
            )

        assert error.value.status_code == 504
        db.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_upstream_http_error_maps_to_bad_gateway(self, monkeypatch):
        db = self._patch_success(monkeypatch)

        async def failing_retry(callback, max_retries=3):
            raise HTTPException(status_code=401, detail="bad")

        monkeypatch.setattr(girl_module, "call_with_retry", failing_retry)

        with pytest.raises(HTTPException) as error:
            await girl_module.generate_message(
                GirlRequest(prompt="你好"), token={"sub": "7"}, db=db
            )

        assert error.value.status_code == 502

    @pytest.mark.asyncio
    async def test_invalid_response_maps_to_internal_error(self, monkeypatch):
        db = self._patch_success(monkeypatch)
        monkeypatch.setattr(
            girl_module,
            "call_with_retry",
            AsyncMock(side_effect=RuntimeError("bad payload")),
        )

        with pytest.raises(HTTPException) as error:
            await girl_module.generate_message(
                GirlRequest(prompt="你好"), token={"sub": "7"}, db=db
            )

        assert error.value.status_code == 500


def _patch_companion_base(monkeypatch, db, event_type="companion.turn.processing",
                          created=True, reservation=None):
    monkeypatch.setattr(
        girl_module, "ChatHistoryService", MagicMock(return_value=AsyncMock())
    )
    monkeypatch.setattr(
        girl_module, "_get_character", AsyncMock(return_value=_character())
    )
    monkeypatch.setattr(
        girl_module,
        "ensure_session",
        AsyncMock(return_value=SimpleNamespace(id="session-1")),
    )
    reservation = reservation or SimpleNamespace(
        event_type=event_type, reservation_token="token-1", sequence=1
    )
    monkeypatch.setattr(
        girl_module,
        "reserve_companion_turn_state",
        AsyncMock(return_value=(reservation, created)),
    )
    monkeypatch.setattr(girl_module, "fail_companion_turn_state", AsyncMock())
    return db


class TestCompanionTurnErrors:
    @pytest.mark.asyncio
    async def test_ensure_session_http_error_is_reraised(self, monkeypatch):
        db = _db_with_scalars()
        _patch_companion_base(monkeypatch, db)
        monkeypatch.setattr(
            girl_module,
            "ensure_session",
            AsyncMock(side_effect=HTTPException(status_code=403, detail="denied")),
        )

        with pytest.raises(HTTPException) as error:
            await girl_module.generate_companion_turn(
                CompanionTurnRequest(prompt="你好"), token={"sub": "7"}, db=db
            )

        assert error.value.status_code == 403

    @pytest.mark.asyncio
    async def test_timeout_marks_turn_failed(self, monkeypatch):
        db = _db_with_scalars()
        _patch_companion_base(monkeypatch, db)
        history = AsyncMock()
        history.get_lightweight_context.return_value = ([], None)
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=history)
        )
        service = AsyncMock()
        service.get_authorized.return_value = []
        monkeypatch.setattr(
            girl_module, "CompanionMemoryService", MagicMock(return_value=service)
        )

        async def timeout_retry(callback, max_retries=3):
            raise asyncio.TimeoutError

        monkeypatch.setattr(girl_module, "call_with_retry", timeout_retry)

        with pytest.raises(HTTPException) as error:
            await girl_module.generate_companion_turn(
                CompanionTurnRequest(prompt="你好", turn_id="t1"),
                token={"sub": "7"},
                db=db,
            )

        assert error.value.status_code == 504
        girl_module.fail_companion_turn_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_value_error_marks_turn_failed(self, monkeypatch):
        db = _db_with_scalars()
        _patch_companion_base(monkeypatch, db)
        history = AsyncMock()
        history.get_lightweight_context.return_value = ([], None)
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=history)
        )
        service = AsyncMock()
        service.get_authorized.return_value = []
        monkeypatch.setattr(
            girl_module, "CompanionMemoryService", MagicMock(return_value=service)
        )
        monkeypatch.setattr(
            girl_module,
            "parse_companion_turn",
            MagicMock(side_effect=ValueError("bad turn")),
        )

        async def retry(callback, max_retries=3):
            return {"choices": [{"message": {"content": "x"}}], "usage": {}}

        monkeypatch.setattr(girl_module, "call_with_retry", retry)

        with pytest.raises(HTTPException) as error:
            await girl_module.generate_companion_turn(
                CompanionTurnRequest(prompt="你好", turn_id="t2"),
                token={"sub": "7"},
                db=db,
            )

        assert error.value.status_code == 502
        girl_module.fail_companion_turn_state.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_voice_output_and_memory_candidates_are_persisted(self, monkeypatch):
        db = _db_with_scalars()
        _patch_companion_base(monkeypatch, db)
        history = AsyncMock()
        history.get_lightweight_context.return_value = ([], None)
        history.save_conversation_turn.return_value = [SimpleNamespace(id=1)]
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=history)
        )
        user_pref = SimpleNamespace(
            id="mem-1", preference_key="hobby", preference_value="跑步"
        )
        service = AsyncMock()
        service.get_authorized.return_value = []
        service.create_candidates.return_value = [user_pref]
        monkeypatch.setattr(
            girl_module, "CompanionMemoryService", MagicMock(return_value=service)
        )
        turn = CompanionTurn(
            assistant_text="记得你喜欢跑步",
            memory_candidates=[
                MemoryCandidate(key="hobby", value="跑步", confidence=0.9)
            ],
        )
        monkeypatch.setattr(
            girl_module, "parse_companion_turn", MagicMock(return_value=turn)
        )
        monkeypatch.setattr(
            girl_module,
            "classify_companion_input",
            AsyncMock(return_value=SimpleNamespace()),
        )
        monkeypatch.setattr(
            girl_module, "apply_companion_policy", MagicMock(side_effect=lambda t, c: t)
        )
        monkeypatch.setattr(girl_module, "append_conversation_turn", AsyncMock())
        monkeypatch.setattr(
            girl_module,
            "append_companion_turn_state",
            AsyncMock(return_value=SimpleNamespace(sequence=2)),
        )

        async def retry(callback, max_retries=3):
            return {
                "choices": [{"message": {"content": "x"}}],
                "usage": {"total_tokens": 5},
            }

        monkeypatch.setattr(girl_module, "call_with_retry", retry)

        response = await girl_module.generate_companion_turn(
            CompanionTurnRequest(prompt="我喜欢跑步", turn_id="t3", voice_output=True),
            token={"sub": "7"},
            db=db,
        )

        assert response.voice_output.status == "unavailable"
        assert "voice_output" in response.degraded_capabilities
        assert response.memory_candidates[0].id == "mem-1"
        assert response.state_revision == 2


class TestHistoryEndpoints:
    @pytest.mark.asyncio
    async def test_search_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.search_history(q="x", token={}, db=AsyncMock())
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_history_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.get_history(token={}, db=AsyncMock(), limit=20, offset=0)
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_history_returns_records_and_has_more(self, monkeypatch):
        record = SimpleNamespace(
            id="1",
            role="user",
            content="你好",
            model="m",
            token_usage=3,
            created_at=datetime.now(),
        )
        service = AsyncMock()
        service.get_user_history.return_value = ([record], 5)
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=service)
        )

        response = await girl_module.get_history(
            token={"sub": "7"}, db=AsyncMock(), limit=20, offset=0
        )

        assert response.total == 5
        assert response.has_more is True

    @pytest.mark.asyncio
    async def test_history_error_maps_to_internal_error(self, monkeypatch):
        service = AsyncMock()
        service.get_user_history.side_effect = RuntimeError("boom")
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=service)
        )

        with pytest.raises(HTTPException) as error:
            await girl_module.get_history(
                token={"sub": "7"}, db=AsyncMock(), limit=20, offset=0
            )

        assert error.value.status_code == 500

    @pytest.mark.asyncio
    async def test_companion_state_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.get_companion_state(token={}, db=AsyncMock())
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_history_requires_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.delete_history(
                record_ids=None, all=False, token={}, db=AsyncMock()
            )
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_history_all_clears_messages(self, monkeypatch):
        service = AsyncMock()
        service.clear_user_history.return_value = 3
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=service)
        )
        clear = AsyncMock()
        monkeypatch.setattr(girl_module, "clear_messages_for_user", clear)
        db = AsyncMock()

        result = await girl_module.delete_history(
            record_ids=None, all=True, token={"sub": "7"}, db=db
        )

        assert result == {"status": "deleted", "count": 3}
        clear.assert_awaited_once_with(db, 7)
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_history_by_ids(self, monkeypatch):
        service = AsyncMock()
        service.delete_records.return_value = 1
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=service)
        )
        delete_messages = AsyncMock()
        monkeypatch.setattr(
            girl_module, "delete_messages_for_legacy_ids", delete_messages
        )

        result = await girl_module.delete_history(
            record_ids=["1"], all=False, token={"sub": "7"}, db=AsyncMock()
        )

        assert result["ids"] == ["1"]
        delete_messages.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_history_requires_records(self, monkeypatch):
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=AsyncMock())
        )

        with pytest.raises(HTTPException) as error:
            await girl_module.delete_history(
                record_ids=None, all=False, token={"sub": "7"}, db=AsyncMock()
            )

        assert error.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_history_error_maps_to_internal_error(self, monkeypatch):
        service = AsyncMock()
        service.clear_user_history.side_effect = RuntimeError("boom")
        monkeypatch.setattr(
            girl_module, "ChatHistoryService", MagicMock(return_value=service)
        )

        with pytest.raises(HTTPException) as error:
            await girl_module.delete_history(
                record_ids=None, all=True, token={"sub": "7"}, db=AsyncMock()
            )

        assert error.value.status_code == 500


class TestCustomCharacterEndpoints:
    @pytest.mark.asyncio
    async def test_list_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.list_custom_characters(token={}, db=AsyncMock())
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_list_serializes_characters(self):
        character = SimpleNamespace(
            id="c1",
            name="小助手",
            description="desc",
            personality="沉稳",
            speaking_style="简洁",
            greetings=json.dumps(["你好"]),
            tags=json.dumps(["测试"]),
            model="test-model",
            temperature=65,
            max_tokens=200,
            avatar_color="#fff",
            created_at=datetime.now(),
        )
        db = _db_with_scalars([character])

        result = await girl_module.list_custom_characters(token={"sub": "7"}, db=db)

        assert result["total"] == 1
        assert result["characters"][0]["temperature"] == 0.65
        assert result["characters"][0]["greetings"] == ["你好"]

    @pytest.mark.asyncio
    async def test_create_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.create_custom_character(
                body={"name": "x"}, token={}, db=AsyncMock()
            )
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_create_rejects_empty_and_long_name(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.create_custom_character(
                body={"name": "  "}, token={"sub": "7"}, db=AsyncMock()
            )
        assert error.value.status_code == 400

        with pytest.raises(HTTPException) as error:
            await girl_module.create_custom_character(
                body={"name": "x" * 51}, token={"sub": "7"}, db=AsyncMock()
            )
        assert error.value.status_code == 400

    @pytest.mark.asyncio
    async def test_create_rejects_when_limit_reached(self):
        db = AsyncMock()
        result = MagicMock()
        result.scalar.return_value = 10
        db.execute.return_value = result

        with pytest.raises(HTTPException) as error:
            await girl_module.create_custom_character(
                body={"name": "小助手"}, token={"sub": "7"}, db=db
            )

        assert error.value.status_code == 400

    @pytest.mark.asyncio
    async def test_delete_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.delete_custom_character(
                "c1", token={}, db=AsyncMock()
            )
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_removes_owned_character(self):
        character = SimpleNamespace(id="c1")
        db = _db_with_scalars()
        db.execute.return_value.scalar_one_or_none.return_value = character

        result = await girl_module.delete_custom_character(
            "c1", token={"sub": "7"}, db=db
        )

        assert result == {"status": "deleted", "id": "c1"}
        db.delete.assert_awaited_once_with(character)

    @pytest.mark.asyncio
    async def test_delete_missing_character_returns_404(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.delete_custom_character(
                "c1", token={"sub": "7"}, db=_db_with_scalars()
            )
        assert error.value.status_code == 404


class TestMemoryAndPreferenceEndpoints:
    @pytest.mark.asyncio
    async def test_memories_reject_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.get_companion_memories(
                token={}, db=AsyncMock(), limit=20, offset=0, memory_status=None
            )
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confirm_maps_not_found(self, monkeypatch):
        service = AsyncMock()
        service.confirm.side_effect = girl_module.CompanionMemoryNotFoundError("m")
        monkeypatch.setattr(
            girl_module, "CompanionMemoryService", MagicMock(return_value=service)
        )

        with pytest.raises(HTTPException) as error:
            await girl_module.confirm_companion_memory(
                "m",
                CompanionMemoryConfirmRequest(),
                token={"sub": "7"},
                db=AsyncMock(),
            )

        assert error.value.status_code == 404

    @pytest.mark.asyncio
    async def test_confirm_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.confirm_companion_memory(
                "m", CompanionMemoryConfirmRequest(), token={}, db=AsyncMock()
            )
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_confirm_maps_state_error(self, monkeypatch):
        service = AsyncMock()
        service.confirm.side_effect = girl_module.CompanionMemoryStateError("bad state")
        monkeypatch.setattr(
            girl_module, "CompanionMemoryService", MagicMock(return_value=service)
        )

        with pytest.raises(HTTPException) as error:
            await girl_module.confirm_companion_memory(
                "m",
                CompanionMemoryConfirmRequest(),
                token={"sub": "7"},
                db=AsyncMock(),
            )

        assert error.value.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_memory_soft_deletes(self, monkeypatch):
        service = AsyncMock()
        service.soft_delete.return_value = SimpleNamespace(id="m", status="deleted")
        monkeypatch.setattr(
            girl_module, "CompanionMemoryService", MagicMock(return_value=service)
        )
        db = AsyncMock()

        result = await girl_module.delete_companion_memory(
            "m", token={"sub": "7"}, db=db
        )

        assert result == {"status": "deleted", "id": "m"}
        db.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_delete_memory_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.delete_companion_memory("m", token={}, db=AsyncMock())
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_preferences_reject_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.get_user_preferences(token={}, db=AsyncMock())
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_preferences_serialize_records(self):
        preference = SimpleNamespace(
            id="p1",
            preference_key="hobby",
            preference_value="跑步",
            confidence=88,
            source="conversation",
            updated_at=datetime.now(),
        )
        db = _db_with_scalars([preference])

        result = await girl_module.get_user_preferences(token={"sub": "7"}, db=db)

        assert result["preferences"][0]["value"] == "跑步"

    @pytest.mark.asyncio
    async def test_delete_preference_rejects_missing_token(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.delete_user_preference("p1", token={}, db=AsyncMock())
        assert error.value.status_code == 401

    @pytest.mark.asyncio
    async def test_delete_preference_soft_deletes(self):
        preference = SimpleNamespace(id="p1", status="confirmed", visibility="companion_allowed")
        db = _db_with_scalars()
        db.execute.return_value.scalar_one_or_none.return_value = preference

        result = await girl_module.delete_user_preference(
            "p1", token={"sub": "7"}, db=db
        )

        assert result == {"status": "deleted", "id": "p1"}
        assert preference.status == "deleted"
        assert preference.visibility == "conversation_only"

    @pytest.mark.asyncio
    async def test_delete_preference_missing_returns_404(self):
        with pytest.raises(HTTPException) as error:
            await girl_module.delete_user_preference(
                "p1", token={"sub": "7"}, db=_db_with_scalars()
            )
        assert error.value.status_code == 404
