from app.agent.file_response import parse_file_response


def test_structured_file_response_is_normalized():
    result = parse_file_response(
        '{"path":"app/main.py","content":"app = FastAPI()"}',
        expected_path="app/main.py",
    )

    assert result.kind == "structured"
    assert result.content == "app = FastAPI()"


def test_tool_call_json_is_classified_for_retry():
    result = parse_file_response('{"tool_calls":[{"function":{"name":"write_file"}}]}')

    assert result.kind == "tool_call"
    assert result.content is None
    assert result.diagnostic == "model returned tool-call JSON"


def test_code_fence_and_thinking_are_normalized():
    result = parse_file_response("<think>plan</think>\n```python\nVALUE = 1\n```")

    assert result.kind == "code"
    assert result.content == "VALUE = 1"
