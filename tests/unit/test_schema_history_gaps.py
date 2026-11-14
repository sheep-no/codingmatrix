"""schema.history 请求模型的字符串 ID 与默认值补测。"""

import pytest
from pydantic import ValidationError

from app.schema.history import (
    ConversationHistoryRequest,
    HistoryRequest,
    HistoryResponse,
)


def test_conversation_history_request_coerces_numeric_string():
    request = ConversationHistoryRequest(conversation_id="42")
    assert request.conversation_id == 42
    assert request.last_history_id is None
    assert request.limit == 20


def test_conversation_history_request_keeps_non_numeric_string():
    with pytest.raises(ValidationError):
        ConversationHistoryRequest(conversation_id="abc")


def test_conversation_history_request_keeps_int():
    request = ConversationHistoryRequest(conversation_id=7, last_history_id=3, limit=5)
    assert (request.conversation_id, request.last_history_id, request.limit) == (7, 3, 5)


def test_conversation_history_limit_bounds():
    with pytest.raises(ValidationError):
        ConversationHistoryRequest(conversation_id=1, limit=0)
    with pytest.raises(ValidationError):
        ConversationHistoryRequest(conversation_id=1, limit=101)


def test_history_response_round_trip():
    response = HistoryResponse(items=[{"id": 1}], total=1, limit=20, offset=0)
    assert response.model_dump() == {
        "items": [{"id": 1}], "total": 1, "limit": 20, "offset": 0,
    }


def test_history_request_keyword_default():
    assert HistoryRequest().prompt_keyword is None
    assert HistoryRequest(prompt_keyword="abc").prompt_keyword == "abc"
