"""ai_reviewer 非 dict 响应、异常分支与文件操作校验补测。"""

import json
from unittest.mock import AsyncMock, patch

from app.agent.ai_reviewer import AIReviewer


def _resp(content):
    return {"choices": [{"message": {"content": content}}]}


async def test_review_code_non_dict_response_rejected():
    reviewer = AIReviewer()
    with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as llm:
        llm.return_value = _resp(json.dumps([1, 2]))
        result = await reviewer.review_code("x")
    assert result.approved is False
    assert "dict" in result.issues[0]


async def test_review_code_unexpected_exception_rejected():
    reviewer = AIReviewer()
    with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as llm:
        llm.side_effect = RuntimeError("network down")
        result = await reviewer.review_code("x")
    assert result.approved is False
    assert "network down" in result.issues[0]


async def test_review_file_operation_rejects_unsafe_path():
    reviewer = AIReviewer()
    result = await reviewer.review_file_operation("write", "/etc/passwd")
    assert result.approved is False
    assert result.risk_level == "high"


async def test_review_file_operation_rejects_dangerous_content():
    reviewer = AIReviewer()
    result = await reviewer.review_file_operation(
        "write", "src/safe.py", content="import os\nos.system('rm -rf /')\n"
    )
    assert result.approved is False
    assert "内容验证失败" in result.issues[0]


async def test_review_file_operation_accepts_safe_write():
    reviewer = AIReviewer()
    result = await reviewer.review_file_operation(
        "write", "src/safe.py", content="print('hi')\n"
    )
    assert result.approved is True
    assert result.risk_level == "low"


async def test_review_file_operation_without_content_skips_content_check():
    reviewer = AIReviewer()
    result = await reviewer.review_file_operation("read", "src/safe.py")
    assert result.approved is True


async def test_review_plan_non_dict_response_rejected():
    reviewer = AIReviewer()
    with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as llm:
        llm.return_value = _resp(json.dumps(["nope"]))
        result = await reviewer.review_plan([{"type": "ai_call"}])
    assert result.approved is False
    assert result.risk_level == "high"
    assert "格式异常" in result.issues[0]


async def test_review_plan_unexpected_exception_rejected():
    reviewer = AIReviewer()
    with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as llm:
        llm.side_effect = RuntimeError("boom")
        result = await reviewer.review_plan([{"type": "ai_call"}])
    assert result.approved is False
    assert "boom" in result.issues[0]


async def test_review_plan_empty_response_uses_empty_dict():
    reviewer = AIReviewer()
    with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as llm:
        llm.return_value = {}
        result = await reviewer.review_plan([{"type": "ai_call"}])
    assert result.approved is False


async def test_review_code_empty_response_uses_empty_dict():
    reviewer = AIReviewer()
    with patch("app.agent.ai_reviewer.call_llm", new_callable=AsyncMock) as llm:
        llm.return_value = {}
        result = await reviewer.review_code("x")
    assert result.approved is False
