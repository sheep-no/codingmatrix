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


def test_json_config_content_is_accepted_for_json_path():
    """package.json 这类文件的内容本身就是 JSON 对象，不是包装元数据。"""
    payload = '{"name":"app","version":"1.0.0","dependencies":{"vue":"^2.7.0"}}'

    result = parse_file_response(payload, expected_path="package.json")

    assert result.kind == "code"
    assert result.content == payload


def test_json_array_content_is_accepted_for_json_path():
    payload = '["vue", "axios"]'

    result = parse_file_response(payload, expected_path="config/deps.json")

    assert result.kind == "code"
    assert result.content == payload


def test_json_metadata_is_still_rejected_for_non_json_path():
    """非 JSON 文件返回裸 JSON 对象仍判为元数据，避免放宽成「JSON 即合法」。"""
    result = parse_file_response('{"name":"app","version":"1.0.0"}', expected_path="app/main.py")

    assert result.kind == "metadata"
    assert result.content is None
    assert result.diagnostic == "model returned JSON metadata instead of file content"


def test_structured_wrapper_still_wins_for_json_path():
    """带 content 键的包装结构即使目标是 .json 也按结构化响应解包。"""
    result = parse_file_response(
        '{"path":"package.json","content":"{\\"name\\":\\"app\\"}"}',
        expected_path="package.json",
    )

    assert result.kind == "structured"
    assert result.content == '{"name":"app"}'
