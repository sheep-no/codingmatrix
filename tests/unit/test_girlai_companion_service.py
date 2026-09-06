import json
from itertools import product

from app.services.girlai_companion_service import parse_companion_turn


def _structured_turn_payloads():
    """Generate a deterministic property matrix for structured turn fields."""
    for index, (emotion_label, intent_label, include_memory, include_options, include_context) in enumerate(
        product(
            ("focused", "anxious"),
            ("task_planning", "help_request"),
            (False, True),
            (False, True),
            (False, True),
        ),
        start=1,
    ):
        payload = {
            "assistant_text": f"第 {index} 个结构化回合。",
            "emotion": {
                "label": emotion_label,
                "intensity": 0.25 if emotion_label == "anxious" else 0.8,
                "confidence": 0.95,
            },
            "intent": {"label": intent_label, "confidence": 0.95},
            "care_required": emotion_label == "anxious",
            "response_style": "care" if emotion_label == "anxious" else "standard",
            "work_options": ["拆解任务", "安排下一步"] if include_options else [],
            "memory_candidates": (
                [{"key": "工作节奏", "value": "上午适合深度工作", "confidence": 0.9}]
                if include_memory
                else []
            ),
            "degraded_capabilities": ["memory_selection"] if include_memory else [],
            "schema_version": 1,
        }
        if include_context:
            payload["model_context"] = {
                "current_model": "companion-test-model",
                "classification_model": "classifier-test-model",
                "calls": 2,
                "fallback_used": False,
                "fallback_history": [],
            }
        yield payload


def test_structured_turn_field_completeness_property():
    """Every valid structured payload produces a complete versioned turn contract."""
    for payload in _structured_turn_payloads():
        turn = parse_companion_turn(
            {
                "choices": [{"message": {"content": json.dumps(payload, ensure_ascii=False)}}],
                "usage": {"total_tokens": 24},
            },
            model="fallback-test-model",
        )

        assert turn.assistant_text.strip()
        assert turn.emotion.label in {
            "neutral",
            "happy",
            "sad",
            "anxious",
            "stressed",
            "tired",
            "angry",
            "overwhelmed",
            "focused",
        }
        assert 0.0 <= turn.emotion.intensity <= 1.0
        assert 0.0 <= turn.emotion.confidence <= 1.0
        assert turn.intent.label in {
            "unknown",
            "chat",
            "acknowledge",
            "task_planning",
            "task_execution",
            "task_review",
            "task_blocked",
            "rest_request",
            "help_request",
            "remember_preference",
        }
        assert 0.0 <= turn.intent.confidence <= 1.0
        assert len(turn.work_options) <= 3
        assert isinstance(turn.memory_candidates, list)
        assert isinstance(turn.degraded_capabilities, list)
        assert turn.model_context.calls >= 1
        assert turn.schema_version >= 1


def test_parse_structured_companion_turn_with_defaults():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"assistant_text":"我来帮你拆解任务。","emotion":{"label":"focused","confidence":0.9}}'
                    }
                }
            ],
            "usage": {"total_tokens": 12},
        },
        model="test-model",
    )

    assert turn.assistant_text == "我来帮你拆解任务。"
    assert turn.emotion.label == "focused"
    assert turn.emotion.intensity == 0.0
    assert turn.intent.label == "unknown"
    assert turn.model_context.current_model == "test-model"
    assert turn.schema_version == 1


def test_plain_text_response_uses_safe_degraded_turn():
    turn = parse_companion_turn(
        {"choices": [{"message": {"content": "先休息五分钟，再继续处理。"}}]}
    )

    assert turn.assistant_text == "先休息五分钟，再继续处理。"
    assert "structured_output" in turn.degraded_capabilities
    assert turn.emotion.label == "neutral"
    assert turn.intent.label == "unknown"


def test_reasoning_trace_is_not_returned_as_assistant_text():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "分析用户输入：用户很焦虑。\n"
                            "我需要：提供工作顺序。\n"
                            "输出必须是JSON格式。\n"
                            "assistant_text 示例：这里是内部草稿。"
                        )
                    }
                }
            ]
        },
        character_name="小柔",
    )

    assert turn.assistant_text == "小柔暂时没能整理好回复，请稍后再试一次。"
    assert "分析用户输入" not in turn.assistant_text
    assert turn.degraded_capabilities == ["structured_output", "emotion", "intent"]


def test_think_block_is_removed_from_plain_text_response():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": "<think>内部推理过程</think>先处理登录问题，再补测试。"
                    }
                }
            ]
        }
    )

    assert turn.assistant_text == "先处理登录问题，再补测试。"


def test_reasoning_trace_is_filtered_when_structured_payload_is_invalid():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"assistant_text":"分析用户输入：内部草稿。",'
                            '"memory_candidates":[{"invalid":"shape"}]}'
                        )
                    }
                }
            ]
        },
        character_name="小柔",
    )

    assert turn.assistant_text == "小柔暂时没能整理好回复，请稍后再试一次。"
    assert turn.degraded_capabilities == ["structured_output"]


def test_fenced_json_response_is_parsed():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": '```json\n{"assistant_text":"收到。","intent":{"label":"acknowledge","confidence":0.8}}\n```'
                    }
                }
            ]
        }
    )

    assert turn.assistant_text == "收到。"
    assert turn.intent.label == "acknowledge"
    assert turn.intent.confidence == 0.8


def test_json_after_reasoning_text_is_parsed():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": (
                            "<think>分析用户输入</think>\n"
                            "结果如下：\n"
                            '{"assistant_text":"先确认阻塞点。","schema_version":1}\n'
                            "以上是结构化结果。"
                        )
                    }
                }
            ]
        }
    )

    assert turn.assistant_text == "先确认阻塞点。"
    assert turn.degraded_capabilities == []


def test_out_of_range_emotion_values_are_normalized():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"assistant_text":"继续推进。","emotion":{"label":"专注","intensity":4,"confidence":0.9}}'
                    }
                }
            ]
        }
    )

    assert turn.assistant_text == "继续推进。"
    assert turn.emotion.label == "focused"
    assert turn.emotion.intensity == 1.0
