"""Branch coverage for app/agent/json_parser.py."""

import json

import pytest

from app.agent import json_parser as jp
from app.agent.json_parser import (
    _JsonParser,
    _get_parser,
    extract_first_json_object,
    parse_tool_call,
    safe_parse_json,
)


# ---------------------------------------------------------------------------
# extract_first_json_object
# ---------------------------------------------------------------------------


def test_extract_first_json_object_skips_invalid_brace() -> None:
    text = 'broken {"bad" oops} then {"good": 1}'

    assert extract_first_json_object(text) == {"good": 1}


def test_extract_first_json_object_returns_none_for_unclosed() -> None:
    assert extract_first_json_object('{"unclosed": ') is None


def test_extract_first_json_object_skips_embedded_non_dict() -> None:
    assert extract_first_json_object('"[{\\"a\\": 1}]"') is None


# ---------------------------------------------------------------------------
# safe_parse_json fallbacks
# ---------------------------------------------------------------------------


def test_object_candidate_that_still_fails_json_falls_through(
    monkeypatch,
) -> None:
    monkeypatch.setattr(jp, "HAS_JSON_REPAIR", False)
    parser = _JsonParser()

    with pytest.raises(ValueError, match="无法解析 JSON"):
        parser.safe_parse_json('{"a": @}')


def test_array_candidate_that_still_fails_json_falls_through(
    monkeypatch,
) -> None:
    monkeypatch.setattr(jp, "HAS_JSON_REPAIR", False)
    parser = _JsonParser()

    with pytest.raises(ValueError, match="无法解析 JSON"):
        parser.safe_parse_json("[1, @]")


def test_json_repair_skipped_when_disabled(monkeypatch) -> None:
    monkeypatch.setattr(jp, "HAS_JSON_REPAIR", False)
    parser = _JsonParser()

    with pytest.raises(ValueError, match="无法解析 JSON"):
        parser.safe_parse_json("plain text")


def test_json_repair_returns_none_still_raises(monkeypatch) -> None:
    monkeypatch.setattr(jp, "HAS_JSON_REPAIR", True)
    monkeypatch.setattr(
        _JsonParser, "_fix_json_repair", staticmethod(lambda text: None)
    )

    with pytest.raises(ValueError, match="无法解析 JSON"):
        _JsonParser().safe_parse_json("plain text")


def test_json_repair_success_returns_container(monkeypatch) -> None:
    monkeypatch.setattr(jp, "HAS_JSON_REPAIR", True)
    monkeypatch.setattr(
        _JsonParser, "_fix_json_repair", staticmethod(lambda text: {"repaired": True})
    )

    assert _JsonParser().safe_parse_json("plain text") == {"repaired": True}


def test_get_parser_is_memoized(monkeypatch) -> None:
    monkeypatch.setattr(jp, "_parser_instance", None)

    assert _get_parser() is _get_parser()


# ---------------------------------------------------------------------------
# parse_tool_call strategies
# ---------------------------------------------------------------------------


def test_parse_tool_call_only_thinking_returns_none() -> None:
    assert parse_tool_call("<think>nothing else</think>") is None


def test_code_block_without_tool_key_falls_through() -> None:
    content = '```json\n{"name": "value"}\n```'

    assert parse_tool_call(content) is None


def test_code_block_with_invalid_json_falls_through(monkeypatch) -> None:
    original = json.loads
    calls = {"count": 0}

    def flaky_loads(value):
        calls["count"] += 1
        if calls["count"] == 1:
            raise json.JSONDecodeError("boom", value, 0)
        return original(value)

    monkeypatch.setattr(jp.json, "loads", flaky_loads)
    content = '```json\n{"tool": "read_file", "params": {"file_path": "a.py"}}\n```'

    result = parse_tool_call(content, known_tools={"read_file"})

    assert result == {"tool": "read_file", "params": {"file_path": "a.py"}}


def test_brace_strategy_invalid_json_breaks_to_split(monkeypatch) -> None:
    original = json.loads
    calls = {"count": 0}

    def flaky_loads(value):
        calls["count"] += 1
        if calls["count"] == 1:
            raise json.JSONDecodeError("boom", value, 0)
        return original(value)

    content = 'read_file\n{"file_path": "a.py"}'
    monkeypatch.setattr(jp.json, "loads", flaky_loads)

    result = parse_tool_call(content, known_tools={"read_file"})

    assert result == {"tool": "read_file", "params": {"file_path": "a.py"}}


def test_state_machine_handles_escaped_quotes() -> None:
    content = '{"tool": "read_file", "params": {"file_path": "a\\"b.py", "nested": {"k": 1}}}'

    result = parse_tool_call(content, known_tools={"read_file"})

    assert result is not None
    assert result["params"]["file_path"] == 'a"b.py'


def test_state_machine_handles_escaped_backslash() -> None:
    content = '{"tool": "read_file", "params": {"file_path": "a\\\\b.py", "nested": {"k": 1}}}'

    result = parse_tool_call(content, known_tools={"read_file"})

    assert result is not None
    assert result["params"]["file_path"] == "a\\b.py"


def test_brace_strategy_invalid_json_falls_through(monkeypatch) -> None:
    original = json.loads
    calls = {"count": 0}

    def flaky_loads(value):
        calls["count"] += 1
        if calls["count"] == 1:
            raise json.JSONDecodeError("boom", value, 0)
        return original(value)

    content = '{"tool": "read_file", "params": {"file_path": "a.py"}}'
    monkeypatch.setattr(jp.json, "loads", flaky_loads)

    result = parse_tool_call(content, known_tools={"read_file"})

    assert result == {"tool": "read_file", "params": {"file_path": "a.py"}}


def test_state_machine_unbalanced_falls_to_split() -> None:
    content = '{"tool": "read_file"'

    assert parse_tool_call(content, known_tools={"read_file"}) is None


def test_state_machine_invalid_nested_json_breaks_to_split() -> None:
    content = '{"tool": "read_file", bad}'

    assert parse_tool_call(content, known_tools={"read_file"}) is None


# ---------------------------------------------------------------------------
# _parse_split_tool_call
# ---------------------------------------------------------------------------


def test_split_tool_call_without_braces_returns_none() -> None:
    parser = _JsonParser()

    assert parser._parse_split_tool_call("read_file no params", known_tools=set()) is None


def test_split_tool_call_rejects_text_after_object() -> None:
    parser = _JsonParser()

    assert parser._parse_split_tool_call(
        'read_file\n{"file_path": "a.py"} trailing', known_tools={"read_file"}
    ) is None


def test_split_tool_call_rejects_missing_prefix() -> None:
    parser = _JsonParser()

    assert parser._parse_split_tool_call('{"file_path": "a.py"}', known_tools={"read_file"}) is None


def test_split_tool_call_rejects_invalid_tool_name() -> None:
    parser = _JsonParser()

    assert parser._parse_split_tool_call(
        'not a tool!\n{"file_path": "a.py"}', known_tools={"read_file"}
    ) is None


def test_split_tool_call_rejects_unknown_tool() -> None:
    parser = _JsonParser()

    assert parser._parse_split_tool_call(
        'unknown_tool\n{"file_path": "a.py"}', known_tools={"read_file"}
    ) is None


def test_split_tool_call_rejects_unparseable_params(monkeypatch) -> None:
    parser = _JsonParser()
    monkeypatch.setattr(
        _JsonParser, "safe_parse_json", lambda self, text: (_ for _ in ()).throw(ValueError())
    )

    assert parser._parse_split_tool_call(
        'read_file\n{"file_path": @}', known_tools={"read_file"}
    ) is None


def test_split_tool_call_rejects_non_dict_params() -> None:
    parser = _JsonParser()

    assert parser._parse_split_tool_call(
        'read_file({"file_path": "a.py"})', known_tools={"read_file"}
    ) == {"tool": "read_file", "params": {"file_path": "a.py"}}
    assert parser._parse_split_tool_call(
        'read_file([1, 2])', known_tools={"read_file"}
    ) is None


def test_split_tool_call_rejects_non_dict_repaired_params(monkeypatch) -> None:
    parser = _JsonParser()
    original = json.loads

    def failing_loads(value):
        raise json.JSONDecodeError("boom", value, 0)

    monkeypatch.setattr(jp.json, "loads", failing_loads)
    monkeypatch.setattr(_JsonParser, "safe_parse_json", lambda self, text: [1, 2])

    assert parser._parse_split_tool_call(
        'read_file\n{"file_path": "a.py"}', known_tools={"read_file"}
    ) is None
    monkeypatch.setattr(jp.json, "loads", original)


def test_split_tool_call_returns_existing_tool_wrapper() -> None:
    parser = _JsonParser()

    result = parser._parse_split_tool_call(
        'read_file({"tool": "read_file", "params": {"file_path": "a.py"}})',
        known_tools={"read_file"},
    )

    assert result == {"tool": "read_file", "params": {"file_path": "a.py"}}


def test_split_tool_call_imports_specialist_tools_by_default() -> None:
    parser = _JsonParser()

    result = parser._parse_split_tool_call(
        'read_file\n{"file_path": "a.py"}', known_tools=None
    )

    assert result == {"tool": "read_file", "params": {"file_path": "a.py"}}


# ---------------------------------------------------------------------------
# Low-level fixers
# ---------------------------------------------------------------------------


def test_remove_line_comments_handles_mismatched_quote() -> None:
    parser = _JsonParser()

    result = parser._remove_line_comments("{'a\": 1}")

    assert result == "{'a\": 1}"


def test_fix_single_quotes_keeps_other_quote_inside_string() -> None:
    parser = _JsonParser()

    assert parser._fix_single_quotes('"it\'s"') == '"it\'s"'


def test_fix_single_quotes_copies_escaped_character() -> None:
    parser = _JsonParser()

    assert parser._fix_single_quotes('"a\\"b"') == '"a\\"b"'


def test_fix_unescaped_newlines_keeps_mismatched_quote_inside_string() -> None:
    parser = _JsonParser()

    assert parser._fix_unescaped_newlines('"it\'s"') == '"it\'s"'


def test_fix_unescaped_newlines_copies_escaped_character() -> None:
    parser = _JsonParser()

    assert parser._fix_unescaped_newlines('"a\\nb"') == '"a\\nb"'


def test_fix_truncation_handles_escaped_quote() -> None:
    parser = _JsonParser()

    assert parser._fix_truncation('{"a": "x\\"y"}') == {"a": 'x"y'}


def test_fix_truncation_unmatched_closing_bracket_returns_none() -> None:
    parser = _JsonParser()

    assert parser._fix_truncation('{"a": 1]') is None


def test_fix_truncation_terminates_open_string() -> None:
    parser = _JsonParser()

    assert parser._fix_truncation('{"a": "open') == {"a": "open"}


def test_fix_json_repair_returns_list(monkeypatch) -> None:
    monkeypatch.setattr(jp.json_repair, "loads", lambda text: [1, 2])

    assert _JsonParser._fix_json_repair("whatever") == [1, 2]


def test_fix_json_repair_returns_none_for_scalar(monkeypatch) -> None:
    monkeypatch.setattr(jp.json_repair, "loads", lambda text: 7)

    assert _JsonParser._fix_json_repair("whatever") is None


def test_fix_json_repair_swallows_exceptions(monkeypatch) -> None:
    def boom(text):
        raise RuntimeError("repair failed")

    monkeypatch.setattr(jp.json_repair, "loads", boom)

    assert _JsonParser._fix_json_repair("whatever") is None
