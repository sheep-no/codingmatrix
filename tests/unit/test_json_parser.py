"""
统一 JSON 解析层单元测试

覆盖：
- safe_parse_json: 5 层解析链
- parse_tool_call: 3 种工具调用解析策略
- extract_json_field: 字段提取
- _JsonParser 内部方法
"""

import json
import pytest
from app.agent.json_parser import (
    safe_parse_json,
    parse_tool_call,
    extract_json_field,
    _JsonParser,
    _get_parser,
)


class TestSafeParseJson:
    def test_valid_json(self):
        result = safe_parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_valid_json_array(self):
        result = safe_parse_json('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="空文本"):
            safe_parse_json("")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="空文本"):
            safe_parse_json("   ")

    def test_thinking_tags_removed(self):
        text = '<think>I need to think...</think>{"answer": 42}'
        result = safe_parse_json(text)
        assert result == {"answer": 42}

    def test_code_block_json(self):
        text = '```json\n{"key": "value"}\n```'
        result = safe_parse_json(text)
        assert result == {"key": "value"}

    def test_code_block_without_lang(self):
        text = '```\n{"key": "value"}\n```'
        result = safe_parse_json(text)
        assert result == {"key": "value"}

    def test_json_with_prefix_text(self):
        text = 'Here is the result:\n{"key": "value"}'
        result = safe_parse_json(text)
        assert result == {"key": "value"}

    def test_json_with_trailing_comma(self):
        text = '{"key": "value", "list": [1, 2,]}'
        result = safe_parse_json(text)
        assert result["key"] == "value"

    def test_json_with_line_comments(self):
        text = '{"key": "value" // comment\n}'
        result = safe_parse_json(text)
        assert result["key"] == "value"

    def test_json_array_with_prefix(self):
        text = 'Here:\n[1, 2, 3]'
        result = safe_parse_json(text)
        assert result == [1, 2, 3]

    def test_truncated_json_object(self):
        text = '{"key": "value", "nested": {"a": 1'
        result = safe_parse_json(text)
        assert isinstance(result, dict)
        assert result["key"] == "value"

    def test_truncated_json_with_colon(self):
        text = '{"key":'
        result = safe_parse_json(text)
        assert isinstance(result, dict)

    def test_single_quotes_fixed(self):
        text = "{'key': 'value'}"
        result = safe_parse_json(text)
        assert result == {"key": "value"}

    def test_unescaped_newlines_in_string(self):
        text = '{"key": "line1\nline2"}'
        result = safe_parse_json(text)
        assert "line1" in result["key"]


class TestParseToolCall:
    def test_simple_tool_call(self):
        content = '{"tool": "read_file", "params": {"file_path": "test.py"}}'
        result = parse_tool_call(content)
        assert result == {"tool": "read_file", "params": {"file_path": "test.py"}}

    def test_tool_call_in_code_block(self):
        content = '```json\n{"tool": "list_files", "params": {"directory": "."}}\n```'
        result = parse_tool_call(content)
        assert result is not None
        assert result["tool"] == "list_files"

    def test_tool_call_with_text_around(self):
        content = 'I will search for the file.\n{"tool": "read_file", "params": {"file_path": "main.py"}}\nDone.'
        result = parse_tool_call(content)
        assert result is not None
        assert result["tool"] == "read_file"

    def test_no_tool_call(self):
        content = "This is just text without any tool call."
        result = parse_tool_call(content)
        assert result is None

    def test_empty_content(self):
        result = parse_tool_call("")
        assert result is None

    def test_thinking_tags_removed(self):
        content = '<think>Should I call a tool?</think>{"tool": "run_command", "params": {"command": "ls"}}'
        result = parse_tool_call(content)
        assert result is not None
        assert result["tool"] == "run_command"

    def test_nested_params(self):
        content = '{"tool": "test", "params": {"nested": {"key": "value"}, "list": [1,2,3]}}'
        result = parse_tool_call(content)
        assert result is not None
        assert result["tool"] == "test"
        assert result["params"]["nested"]["key"] == "value"

    def test_non_tool_json_returns_none(self):
        content = '{"name": "test", "value": 123}'
        result = parse_tool_call(content)
        assert result is None


class TestExtractJsonField:
    def test_extract_existing_field(self):
        text = '{"status": "ok", "count": 5}'
        result = extract_json_field(text, "count")
        assert result == 5

    def test_extract_missing_field_default(self):
        text = '{"status": "ok"}'
        result = extract_json_field(text, "count", default=0)
        assert result == 0

    def test_extract_from_invalid_json(self):
        text = "not json at all"
        result = extract_json_field(text, "key", default=None)
        assert result is None

    def test_extract_from_list_returns_default(self):
        text = '[1, 2, 3]'
        result = extract_json_field(text, "key", default="N/A")
        assert result == "N/A"


class TestJsonParserInternals:
    def setup_method(self):
        self.parser = _JsonParser()

    def test_clean_thinking(self):
        text = '<think>analysis</think>{"result": true}'
        assert self.parser._clean_thinking(text) == '{"result": true}'

    def test_clean_thinking_no_tags(self):
        text = '{"result": true}'
        assert self.parser._clean_thinking(text) == '{"result": true}'

    def test_extract_code_block(self):
        text = '```json\n{"a": 1}\n```'
        assert self.parser._extract_code_block(text) == '{"a": 1}'

    def test_extract_code_block_no_block(self):
        text = '{"a": 1}'
        assert self.parser._extract_code_block(text) == '{"a": 1}'

    def test_remove_line_comments(self):
        text = '{"a": 1} // comment\n{"b": 2}'
        result = self.parser._remove_line_comments(text)
        assert "// comment" not in result
        assert '{"b": 2}' in result

    def test_remove_line_comments_preserves_strings(self):
        text = '{"url": "http://example.com"}'
        result = self.parser._remove_line_comments(text)
        assert "http://example.com" in result

    def test_fix_single_quotes(self):
        text = "{'key': 'value'}"
        result = self.parser._fix_single_quotes(text)
        assert '"' in result
        assert "'" not in result

    def test_fix_unescaped_newlines(self):
        text = '"line1\nline2"'
        result = self.parser._fix_unescaped_newlines(text)
        assert "\\n" in result

    def test_apply_common_fixes_trailing_comma(self):
        text = '{"a": 1, "b": 2,}'
        result = self.parser._apply_common_fixes(text)
        assert not result.rstrip().endswith(",}")

    def test_fix_truncation_complete_json(self):
        text = '{"a": 1, "b": 2}'
        result = self.parser._fix_truncation(text)
        assert result == {"a": 1, "b": 2}

    def test_fix_truncation_missing_brace(self):
        text = '{"a": 1, "b": {"c": 3'
        result = self.parser._fix_truncation(text)
        assert isinstance(result, dict)

    def test_fix_truncation_trailing_comma(self):
        text = '{"a": 1,'
        result = self.parser._fix_truncation(text)
        assert isinstance(result, dict)

    def test_parser_singleton(self):
        p1 = _get_parser()
        p2 = _get_parser()
        assert p1 is p2


class TestEdgeCases:
    def test_unicode_content(self):
        text = '{"message": "你好世界"}'
        result = safe_parse_json(text)
        assert result["message"] == "你好世界"

    def test_deeply_nested(self):
        text = '{"a": {"b": {"c": {"d": 1}}}}'
        result = safe_parse_json(text)
        assert result["a"]["b"]["c"]["d"] == 1

    def test_numeric_strings(self):
        text = '{"num": "123", "float": "3.14"}'
        result = safe_parse_json(text)
        assert result["num"] == "123"
        assert result["float"] == "3.14"

    def test_boolean_values(self):
        text = '{"flag": true, "disabled": false}'
        result = safe_parse_json(text)
        assert result["flag"] is True
        assert result["disabled"] is False

    def test_null_value(self):
        text = '{"value": null}'
        result = safe_parse_json(text)
        assert result["value"] is None
