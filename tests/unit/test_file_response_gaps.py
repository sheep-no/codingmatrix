"""file_response 非文本、空响应与路径不匹配分支补测。"""

import pytest

from app.agent.file_response import parse_file_response


def test_non_text_response_is_invalid():
    result = parse_file_response(None)
    assert result == type(result)("invalid", diagnostic="model response is not text")


def test_empty_response_is_invalid():
    assert parse_file_response("   \n").diagnostic == "model response is empty"


def test_only_thinking_block_is_empty():
    assert parse_file_response("<think>plan</think>").diagnostic == "model response is empty"


def test_invalid_json_object_falls_through_to_code():
    raw = "{not json at all}"
    result = parse_file_response(raw)
    assert result.kind == "code"
    assert result.content == raw


def test_response_path_mismatch_is_rejected():
    result = parse_file_response(
        '{"path":"other.py","content":"X = 1"}', expected_path="app/main.py"
    )
    assert result.kind == "invalid"
    assert "other.py" in result.diagnostic


def test_matching_file_path_key_is_accepted():
    result = parse_file_response(
        '{"file_path":"app/main.py","content":"X = 1"}', expected_path="app/main.py"
    )
    assert result.kind == "structured"
    assert result.content == "X = 1"


def test_invalid_json_array_falls_through_to_code():
    raw = "[not, json]"
    result = parse_file_response(raw)
    assert result.kind == "code"
    assert result.content == raw


def test_json_array_metadata_rejected_for_code_path():
    result = parse_file_response('["a", "b"]', expected_path="app/main.py")
    assert result.kind == "metadata"


def test_code_key_with_blank_value_skipped():
    result = parse_file_response('{"content":"   ","name":"x"}', expected_path="app/main.py")
    assert result.kind == "metadata"


@pytest.mark.parametrize("key", ["code", "file_content", "source", "body", "implementation"])
def test_all_code_keys_are_recognized(key):
    result = parse_file_response('{"%s":"VALUE = 1"}' % key)
    assert result.kind == "structured"
    assert result.content == "VALUE = 1"


@pytest.mark.parametrize("key", ["function_call", "function", "action", "operation"])
def test_all_tool_keys_are_recognized(key):
    result = parse_file_response('{"%s":{}}' % key)
    assert result.kind == "tool_call"


def test_jsonc_suffix_is_treated_as_json():
    result = parse_file_response('{"compilerOptions":{}}', expected_path="tsconfig.jsonc")
    assert result.kind == "code"


def test_empty_code_fence_is_invalid():
    result = parse_file_response("```python\n```")
    assert result.kind == "invalid"
    assert result.diagnostic == "normalized file content is empty"
