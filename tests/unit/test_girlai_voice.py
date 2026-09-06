from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.api.v1 import GirlAi as girl_module
from app.schema.girl_companion import (
    CompanionTurnResponse,
    VoiceTranscriptionRequest,
)


def test_voice_transcription_schema_validates_metadata_bounds():
    request = VoiceTranscriptionRequest(
        transcript="请继续刚才的计划",
        provider="sense-voice",
        confidence=0.93,
        duration_ms=1200,
    )

    assert request.transcript == "请继续刚才的计划"
    assert request.provider == "sense-voice"
    assert request.duration_ms == 1200


def test_voice_transcription_schema_rejects_empty_transcript():
    with pytest.raises(ValueError):
        VoiceTranscriptionRequest(transcript=" ")


@pytest.mark.asyncio
async def test_voice_transcription_reuses_companion_turn(monkeypatch):
    companion_response = CompanionTurnResponse(
        assistant_text="我继续陪你梳理。",
        model="test-model",
        turn_id="voice-turn-1",
        conversation_id="session-1",
        state_revision=4,
    )
    generate = AsyncMock(return_value=companion_response)
    monkeypatch.setattr(girl_module, "generate_companion_turn", generate)

    response = await girl_module.create_voice_transcription_turn(
        VoiceTranscriptionRequest(
            transcript="继续刚才的计划",
            character_id="gentle",
            turn_id="voice-turn-1",
            provider="sense-voice",
            confidence=0.9,
            duration_ms=800,
        ),
        token={"sub": "7"},
        db=SimpleNamespace(),
    )

    request = generate.await_args.args[0]
    assert request.prompt == "继续刚才的计划"
    assert request.turn_id == "voice-turn-1"
    assert request.character_id == "gentle"
    assert response.voice_input.status == "received"
    assert response.voice_input.provider == "sense-voice"
    assert response.voice_input.confidence == 0.9
    assert response.voice_input.duration_ms == 800


@pytest.mark.asyncio
async def test_voice_transcription_requires_authentication():
    with pytest.raises(HTTPException) as error:
        await girl_module.create_voice_transcription_turn(
            VoiceTranscriptionRequest(transcript="你好"),
            token={},
            db=SimpleNamespace(),
        )

    assert error.value.status_code == 401
