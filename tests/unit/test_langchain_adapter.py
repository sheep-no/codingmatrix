from types import SimpleNamespace

from app.utils.aicloud.langchain_adapter import _message_to_dict


def test_message_to_dict_normalizes_text_and_metadata():
    message = SimpleNamespace(
        text="hello",
        content="hello",
        content_blocks=[{"type": "text", "text": "hello"}],
        tool_calls=[{"name": "search", "args": {"q": "x"}}],
        usage_metadata={"input_tokens": 2, "output_tokens": 3},
        response_metadata={"finish_reason": "stop"},
    )

    result = _message_to_dict(message)

    assert result["content"] == "hello"
    assert result["content_blocks"][0]["type"] == "text"
    assert result["tool_calls"][0]["name"] == "search"
    assert result["usage"]["input_tokens"] == 2


def test_message_to_dict_flattens_structured_content_when_text_missing():
    message = SimpleNamespace(
        text=None,
        content=[
            {"type": "reasoning", "reasoning": "thinking"},
            {"type": "text", "text": "answer"},
        ],
        content_blocks=[],
        tool_calls=[],
        usage_metadata={},
        response_metadata={},
    )

    result = _message_to_dict(message)

    assert result["content"] == "answer"
