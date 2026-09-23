"""VisualAnalyzer._fix_json_format 的容错回归（VPX14）。

原实现用全局 `str.replace("True", "true")` 等修 Python 字面量，会把字符串
里的 "True story"、"https://..." 一并改写，并把单引号转义成非法的 `\\'`。
这些用例锁定「只改结构、不动字符串内容」的行为。
"""

import json

from app.utils.visual.visual_analyzer import VisualAnalyzer


def _fix(content: str) -> str:
    return VisualAnalyzer()._fix_json_format(content)


def test_true_substring_inside_string_is_preserved():
    content = '{"note": "True story", "flag": True, "off": False}'

    parsed = json.loads(_fix(content))

    assert parsed == {"note": "True story", "flag": True, "off": False}


def test_python_literals_outside_strings_are_converted():
    content = "{a: True, b: False, c: Null}"

    parsed = json.loads(_fix(content))

    assert parsed == {"a": True, "b": False, "c": None}


def test_word_prefixed_identifiers_are_not_rewritten():
    """TrueFlag / isFalse 这类标识符不能被当成字面量切开。"""
    content = '{"TrueFlag": 1, "isFalse": 2, "value": True}'

    parsed = json.loads(_fix(content))

    assert parsed == {"TrueFlag": 1, "isFalse": 2, "value": True}


def test_single_quoted_strings_are_converted_to_json():
    content = "{'name': 'alpha', 'count': 2}"

    parsed = json.loads(_fix(content))

    assert parsed == {"name": "alpha", "count": 2}


def test_inner_apostrophe_is_not_escaped_illegally():
    """双引号串内的单引号此前会被替换成非法转义 `\\'`。"""
    content = '{"name": "don\'t", "flag": True}'

    parsed = json.loads(_fix(content))

    assert parsed == {"name": "don't", "flag": True}


def test_escaped_quote_in_single_quoted_string_is_decoded():
    content = r"{'name': 'don\'t', 'flag': True}"

    parsed = json.loads(_fix(content))

    assert parsed == {"name": "don't", "flag": True}


def test_double_quote_inside_single_quoted_string_is_escaped():
    content = """{'quote': 'say "hi"', 'ok': True}"""

    parsed = json.loads(_fix(content))

    assert parsed == {"quote": 'say "hi"', "ok": True}


def test_line_comment_outside_strings_is_removed():
    content = '{"a": 1} // trailing note'

    parsed = json.loads(_fix(content))

    assert parsed == {"a": 1}


def test_double_slash_inside_url_is_preserved():
    content = '{"url": "https://example.com/x", "ok": True}'

    parsed = json.loads(_fix(content))

    assert parsed == {"url": "https://example.com/x", "ok": True}


def test_block_comment_outside_strings_is_removed():
    content = "{'a': 'b', /* note */ 'c': True}"

    parsed = json.loads(_fix(content))

    assert parsed == {"a": "b", "c": True}


def test_trailing_comma_and_unquoted_key_are_fixed():
    content = '{key: "value", flag: True,}'

    parsed = json.loads(_fix(content))

    assert parsed == {"key": "value", "flag": True}
