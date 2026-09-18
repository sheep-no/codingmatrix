"""error_handler / json_parser 错误处理族回归测试。

覆盖曾经真实存在的缺陷：
- json_parser._fix_common_errors 用全局正则修复，把字符串值里的撇号/冒号/
  `,}` 也当语法错误处理，损坏合法数据（如 "a,}b" -> "a}b"）；
- _extract_json_object 取第一个 `{` 到最后一个 `}`，多个 JSON 对象拼接时
  跨对象截取导致整体解析失败；
- integrity_error_handler 把原始 SQLAlchemy 错误（表名/约束名）返回给客户端。
"""
import json
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.utils.error_handler import integrity_error_handler
from app.utils.json_parser import RobustJSONParser, extract_json_from_llm


@pytest.fixture
def parser():
    return RobustJSONParser()


def test_apostrophe_in_value_is_preserved(parser):
    result = parser.parse("{'message': \"don't worry\", 'time': \"12:30\",}")
    assert result == {"message": "don't worry", "time": "12:30"}


def test_comma_brace_inside_string_is_not_stripped(parser):
    result = parser.parse("{'note': \"a,}b\", 'x': 1,}")
    assert result == {"note": "a,}b", "x": 1}


def test_colon_inside_quoted_key_is_preserved(parser):
    result = parser.parse('{"meeting time: 12:30": "ok",}')
    assert result == {"meeting time: 12:30": "ok"}


def test_unquoted_keys_and_trailing_commas_are_repaired(parser):
    result = parser.parse("{a: 1, b: [1, 2,],}")
    assert result == {"a": 1, "b": [1, 2]}


def test_single_quote_escape_is_normalized(parser):
    result = parser.parse("{name: 'O\\'Brien', city: 'Paris'}")
    assert result == {"name": "O'Brien", "city": "Paris"}


def test_comments_are_removed(parser):
    assert parser.parse('{"x": 1} // tail\n') == {"x": 1}
    assert parser.parse('/* head */ {"x": 1}') == {"x": 1}


def test_first_complete_object_is_extracted_from_concatenated_output(parser):
    assert parser.parse('{"a": 1}{"b": 2}') == {"a": 1}
    assert extract_json_from_llm('noise {"x": 1} tail {"y": 2}') == {"x": 1}


def test_brace_inside_string_does_not_end_object(parser):
    assert parser.parse('{"a": "}{"}') == {"a": "}{"}


@pytest.mark.asyncio
async def test_integrity_error_handler_hides_original_db_error():
    request = MagicMock()
    request.url.path = "/api/v1/things"
    exc = IntegrityError(
        "INSERT INTO secret_table (token) VALUES (?)",
        {"token": "x"},
        Exception('UNIQUE constraint failed: secret_table.token'),
    )

    response = await integrity_error_handler(request, exc)
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert "secret_table" not in response.body.decode()
    assert "original_error" not in payload["details"]
    assert payload["details"] == {"path": "/api/v1/things"}
