from unittest.mock import AsyncMock

import pytest

from app.schema.girl_companion import CompanionTurn, EmotionState, IntentState
from app.services.girlai_companion_classifier import (
    ClassificationResult,
    apply_companion_policy,
    classify_companion_input,
    normalize_emotion,
    normalize_intent,
    parse_classification_response,
)
from app.services.girlai_companion_service import parse_companion_turn


def test_standardizes_labels_and_preserves_low_confidence():
    emotion = normalize_emotion(
        {"label": "焦虑", "intensity": 1.4, "confidence": 0.4},
        threshold=0.6,
    )
    intent = normalize_intent(
        {"label": "planning", "confidence": 0.9},
        threshold=0.6,
    )

    assert emotion.label == "neutral"
    assert emotion.raw_label == "焦虑"
    assert emotion.intensity == 1.0
    assert emotion.confidence == 0.4
    assert emotion.low_confidence is True
    assert intent.label == "task_planning"
    assert intent.raw_label == "planning"
    assert intent.low_confidence is False


def test_classification_parser_accepts_fenced_json():
    result = parse_classification_response(
        {
            "choices": [
                {
                    "message": {
                        "content": "```json\n{\"emotion\":{\"label\":\"tired\",\"intensity\":0.8,\"confidence\":0.9},\"intent\":{\"label\":\"rest_request\",\"confidence\":0.8}}\n```"
                    }
                }
            ]
        }
    )

    assert result.emotion.label == "tired"
    assert result.intent.label == "rest_request"


@pytest.mark.asyncio
async def test_classifier_uses_fallback_model():
    model_service = AsyncMock()
    model_service.select_models.return_value = {
        "classification": "primary-model",
        "fallback": "fallback-model",
    }
    caller = AsyncMock(
        side_effect=[
            RuntimeError("provider unavailable"),
            {
                "choices": [
                    {
                        "message": {
                            "content": '{"emotion":{"label":"focused","intensity":0.7,"confidence":0.9},"intent":{"label":"task_execution","confidence":0.9}}'
                        }
                    }
                ]
            },
        ]
    )

    result = await classify_companion_input(
        "继续实现功能",
        model_service=model_service,
        llm_caller=caller,
    )

    assert result.model == "fallback-model"
    assert result.fallback_used is True
    assert result.fallback_history == ["primary-model"]
    assert result.calls == 2
    assert result.intent.label == "task_execution"
    assert all(
        call.kwargs["thinking_budget"] > 0
        for call in caller.await_args_list
    )


@pytest.mark.asyncio
async def test_classifier_failure_keeps_neutral_state():
    model_service = AsyncMock()
    model_service.select_models.return_value = {
        "classification": "primary-model",
        "fallback": "fallback-model",
    }
    result = await classify_companion_input(
        "继续",
        model_service=model_service,
        llm_caller=AsyncMock(side_effect=RuntimeError("unavailable")),
    )

    assert result.emotion.label == "neutral"
    assert result.intent.label == "unknown"
    assert result.parse_failed is True
    assert result.degraded_capabilities == [
        "emotion_classification",
        "intent_classification",
    ]


@pytest.mark.asyncio
async def test_classifier_failure_modes_keep_text_mainline_available():
    failure_cases = ("model_selection", "provider_calls")
    for failure_case in failure_cases:
        model_service = AsyncMock()
        if failure_case == "model_selection":
            model_service.select_models.side_effect = RuntimeError("router unavailable")
            caller = AsyncMock()
        else:
            model_service.select_models.return_value = {
                "classification": "primary-model",
                "fallback": "fallback-model",
            }
            caller = AsyncMock(side_effect=RuntimeError("provider unavailable"))

        result = await classify_companion_input(
            "继续处理当前工作",
            model_service=model_service,
            llm_caller=caller,
        )
        turn = CompanionTurn(assistant_text="文字主链路仍然可用。")
        updated = apply_companion_policy(turn, result)

        assert updated.assistant_text == "文字主链路仍然可用。"
        assert updated.emotion.label == "neutral"
        assert updated.intent.label == "unknown"
        assert updated.response_style == "neutral"
        assert set(("emotion_classification", "intent_classification")).issubset(
            updated.degraded_capabilities
        )


def test_care_policy_keeps_text_and_adds_work_options():
    turn = CompanionTurn(
        assistant_text="我来陪你处理。",
        degraded_capabilities=["structured_output", "emotion", "intent"],
    )
    result = ClassificationResult(
        emotion=EmotionState(label="stressed", intensity=0.8, confidence=0.9),
        intent=IntentState(label="task_blocked", confidence=0.9),
        model="classifier",
        calls=1,
    )

    updated = apply_companion_policy(turn, result)

    assert updated.care_required is True
    assert updated.response_style == "care"
    assert len(updated.work_options) == 3
    assert "我来陪你处理" in updated.assistant_text
    assert "你可以选择" in updated.assistant_text
    assert updated.model_context.classification_model == "classifier"
    assert updated.degraded_capabilities == ["structured_output"]


@pytest.mark.parametrize(
    "provider_content",
    [
        "继续处理当前工作。",
        '{"assistant_text":"先整理最小步骤。","intent":{"label":"task_planning"}}',
        "```json\n{\"assistant_text\":\"我会陪你继续。\"}\n```",
    ],
)
@pytest.mark.parametrize(
    "initial_degraded",
    [[], ["structured_output"], ["memory_retrieval"]],
)
def test_classifier_failure_preserves_text_across_turn_shapes(
    provider_content, initial_degraded
):
    turn = parse_companion_turn(
        {"choices": [{"message": {"content": provider_content}}]},
        character_name="虚拟姬",
        model="conversation-model",
    )
    turn.degraded_capabilities = list(initial_degraded)
    result = ClassificationResult(
        degraded_capabilities=["emotion_classification", "intent_classification"],
        parse_failed=True,
    )

    updated = apply_companion_policy(turn, result)

    assert updated.assistant_text.strip()
    assert updated.emotion.label == "neutral"
    assert updated.intent.label == "unknown"
    assert updated.response_style == "neutral"
    assert updated.work_options
    assert "emotion_classification" in updated.degraded_capabilities
    assert "intent_classification" in updated.degraded_capabilities
