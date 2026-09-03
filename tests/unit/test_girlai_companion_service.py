from app.services.girlai_companion_service import parse_companion_turn


def test_parse_structured_companion_turn_with_defaults():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"assistant_text":"我来帮你拆解任务。","emotion":{"label":"focused"}}'
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


def test_invalid_structured_fields_fall_back_to_text():
    turn = parse_companion_turn(
        {
            "choices": [
                {
                    "message": {
                        "content": '{"assistant_text":"继续推进。","emotion":{"intensity":4}}'
                    }
                }
            ]
        }
    )

    assert turn.assistant_text == "继续推进。"
    assert turn.degraded_capabilities == ["structured_output"]
