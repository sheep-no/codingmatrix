from app.services.girlai_companion_service import parse_companion_turn


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
