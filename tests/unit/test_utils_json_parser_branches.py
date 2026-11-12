"""Branch coverage for app/utils/json_parser.py."""

import json

import pytest

from app.utils import json_parser as jp
from app.utils.json_parser import (
    RobustJSONParser,
    extract_code_from_markdown,
    extract_json_from_llm,
    parse_json,
)


class TestFindBalancedEnd:
    def test_finds_matching_brace(self):
        assert jp._find_balanced_end('{"a": {"b": 1}}', 0, "{", "}") == 14

    def test_returns_minus_one_when_unbalanced(self):
        assert jp._find_balanced_end('{"a": 1', 0, "{", "}") == -1

    def test_skips_brackets_inside_strings(self):
        text = '{"a": "}"}'
        assert jp._find_balanced_end(text, 0, "{", "}") == len(text) - 1

    def test_handles_escaped_quotes(self):
        text = '{"a": "x\\"}"}'
        assert jp._find_balanced_end(text, 0, "{", "}") == len(text) - 1

    def test_handles_single_quoted_strings(self):
        text = "{'a': '}'}"
        assert jp._find_balanced_end(text, 0, "{", "}") == len(text) - 1


class TestParseStrategies:
    def test_empty_input_raises(self):
        with pytest.raises(ValueError, match="Empty input"):
            RobustJSONParser().parse("   ")

    def test_direct_valid_json(self):
        assert RobustJSONParser().parse('{"a": 1}') == {"a": 1}

    def test_extracts_object_from_noise(self):
        assert RobustJSONParser().parse('prefix {"a": 1} suffix') == {"a": 1}

    def test_object_extraction_fails_json_loads_then_fixes(self):
        # Balanced braces so extraction picks it, but content is invalid JSON.
        result = RobustJSONParser().parse("{'a': 1}")
        assert result == {"a": 1}

    def test_extracts_array_from_noise(self):
        assert RobustJSONParser().parse('prefix [1, 2, 3] suffix') == [1, 2, 3]

    def test_unparseable_raises(self):
        with pytest.raises(ValueError, match="Cannot parse JSON"):
            RobustJSONParser().parse("totally broken {")

    def test_array_branch_with_bad_array(self):
        # Array candidate found but invalid; falls through to error.
        with pytest.raises(ValueError):
            RobustJSONParser().parse("[1, 2,")

    def test_array_candidate_invalid_after_fixes(self):
        # Balanced array candidate that fixes cannot repair.
        with pytest.raises(ValueError):
            RobustJSONParser().parse("[1,,2]")

    def test_object_candidate_unbalanced_braces_in_string(self):
        # Balanced-end scan ignores braces in strings, so the count check rejects it.
        with pytest.raises(ValueError):
            RobustJSONParser().parse('prefix {"a": "{"} tail')


class TestExtractionHelpers:
    def test_extract_object_no_brace(self):
        assert RobustJSONParser()._extract_json_object("no braces") is None

    def test_extract_object_unbalanced(self):
        assert RobustJSONParser()._extract_json_object('{"a": 1') is None

    def test_extract_array_no_bracket(self):
        assert RobustJSONParser()._extract_json_array("no bracket") is None

    def test_extract_array_unbalanced(self):
        assert RobustJSONParser()._extract_json_array("[1, 2") is None

    def test_extract_array_non_array_candidate(self):
        assert RobustJSONParser()._extract_json_array("x ] [") is None

    def test_looks_like_json_empty(self):
        assert RobustJSONParser()._looks_like_json("   ") is False


class TestFixCommonErrors:
    def test_strips_bom_and_single_quotes(self):
        fixed = RobustJSONParser()._fix_common_errors("\ufeff{'a': 'b'}")
        assert json.loads(fixed) == {"a": "b"}

    def test_trailing_comma_removed(self):
        fixed = RobustJSONParser()._fix_common_errors('{"a": 1,}')
        assert json.loads(fixed) == {"a": 1}

    def test_trailing_comma_array_removed(self):
        fixed = RobustJSONParser()._fix_common_errors("[1, 2,]")
        assert json.loads(fixed) == [1, 2]

    def test_line_comment_removed(self):
        fixed = RobustJSONParser()._fix_common_errors('{"a": 1 // hi\n}')
        assert json.loads(fixed) == {"a": 1}

    def test_line_comment_at_end(self):
        fixed = RobustJSONParser()._fix_common_errors('{"a": 1} // no newline')
        assert json.loads(fixed) == {"a": 1}

    def test_block_comment_removed(self):
        fixed = RobustJSONParser()._fix_common_errors('{"a": /* x */ 1}')
        assert json.loads(fixed) == {"a": 1}

    def test_unterminated_block_comment(self):
        fixed = RobustJSONParser()._fix_common_errors('{"a": 1} /* open')
        assert json.loads(fixed) == {"a": 1}

    def test_unquoted_key_gets_quoted(self):
        fixed = RobustJSONParser()._fix_common_errors('{a: 1}')
        assert json.loads(fixed) == {"a": 1}

    def test_unquoted_underscore_key(self):
        fixed = RobustJSONParser()._fix_common_errors('{a_b: 1}')
        assert json.loads(fixed) == {"a_b": 1}

    def test_word_without_colon_left_alone(self):
        fixed = RobustJSONParser()._fix_common_errors('{"a": value}')
        assert "value" in fixed

    def test_escaped_single_quote_inside_single_string(self):
        fixed = RobustJSONParser()._fix_common_errors("{'a': 'it\\'s'}")
        assert json.loads(fixed) == {"a": "it's"}

    def test_escape_sequence_preserved(self):
        fixed = RobustJSONParser()._fix_common_errors('{"a": "x\\ny"}')
        assert json.loads(fixed) == {"a": "x\ny"}

    def test_bare_double_quote_in_single_string_escaped(self):
        fixed = RobustJSONParser()._fix_common_errors("{'a': 'he said \"hi\"'}")
        assert json.loads(fixed) == {"a": 'he said "hi"'}

    def test_comma_inside_string_preserved(self):
        fixed = RobustJSONParser()._fix_common_errors('{"a,}": "b"}')
        assert json.loads(fixed) == {"a,}": "b"}


class TestModuleFunctions:
    def test_parse_json_success(self):
        assert parse_json('{"a": 1}') == {"a": 1}

    def test_parse_json_returns_default(self):
        assert parse_json("broken", default={"x": 1}) == {"x": 1}

    def test_parse_json_type_error_returns_default(self):
        assert parse_json(None, default=[]) == []

    def test_extract_llm_empty(self):
        assert extract_json_from_llm("") is None

    def test_extract_llm_code_block(self):
        text = 'pre ```json\n{"a": 1}\n``` post'
        assert extract_json_from_llm(text) == {"a": 1}

    def test_extract_llm_code_block_invalid_then_direct(self):
        text = '```json\nnot json\n```'
        assert extract_json_from_llm(text) is None

    def test_extract_llm_plain(self):
        assert extract_json_from_llm('{"a": 1}') == {"a": 1}

    def test_extract_llm_balanced_object(self):
        assert extract_json_from_llm('noise {"a": {"b": 2}} tail') == {"a": {"b": 2}}

    def test_extract_llm_balanced_object_invalid(self):
        assert extract_json_from_llm('noise {"a": } tail') is None

    def test_extract_llm_falls_back_to_parser(self):
        assert extract_json_from_llm("{a: 1}") == {"a": 1}

    def test_extract_llm_unparseable(self):
        assert extract_json_from_llm("no json at all") is None

    def test_extract_code_empty(self):
        assert extract_code_from_markdown("") is None

    def test_extract_code_specific_language(self):
        text = "```python\nprint(1)\n```"
        assert extract_code_from_markdown(text, "python") == "print(1)"

    def test_extract_code_specific_language_missing(self):
        text = "```js\nlet a = 1;\n```"
        assert extract_code_from_markdown(text, "python") == "let a = 1;"

    def test_extract_code_any_block(self):
        text = "```sql\nSELECT 1;\n```"
        assert extract_code_from_markdown(text) == "SELECT 1;"

    def test_extract_code_plain_text(self):
        assert extract_code_from_markdown("  plain  ") == "plain"
