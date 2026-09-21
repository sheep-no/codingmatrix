"""Aicode 响应处理与恢复链加固（AIC2/AIC3/AIC6）。

- AIC3: 非流式响应解析原用裸索引，结构异常抛 KeyError/IndexError 逃逸
- AIC2: CodeRequest 缺 resume_id 字段，`/code` 的 resume_from 恒为 None
- AIC6: 恢复缓存不校验归属，他人 resume_id 可注入其部分响应
"""

import pytest

from app.api.v1 import Aicode
from app.api.v1.Aicode import extract_response_text
from app.schema.codeRequest import CodeRequest


def test_extract_response_text_valid():
    result = {"choices": [{"message": {"content": "hello"}}]}
    assert extract_response_text(result) == "hello"


@pytest.mark.parametrize(
    "result",
    [
        None,
        {},
        {"choices": []},
        {"choices": [{}]},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": None}}]},
    ],
)
def test_extract_response_text_malformed_raises_runtime_error(result):
    with pytest.raises(RuntimeError):
        extract_response_text(result)


def test_code_request_accepts_resume_id():
    request = CodeRequest(prompt="hi", resume_id="abc-123")
    assert request.resume_id == "abc-123"

    defaulted = CodeRequest(prompt="hi")
    assert defaulted.resume_id is None


@pytest.fixture
def clean_partial_cache():
    Aicode._partial_response_cache.clear()
    yield Aicode._partial_response_cache
    Aicode._partial_response_cache.clear()


def test_restore_prefix_returns_own_cache(clean_partial_cache):
    clean_partial_cache["rid"] = {"user_id": "42", "partial_response": "abc"}

    assert Aicode._restore_partial_prefix("rid", "42") == "abc"
    # 取出即消费，避免重复恢复
    assert "rid" not in clean_partial_cache


def test_restore_prefix_rejects_other_user(clean_partial_cache):
    clean_partial_cache["rid"] = {"user_id": "42", "partial_response": "abc"}

    assert Aicode._restore_partial_prefix("rid", "7") == ""


def test_restore_prefix_handles_missing(clean_partial_cache):
    assert Aicode._restore_partial_prefix(None, "1") == ""
    assert Aicode._restore_partial_prefix("absent", "1") == ""


def test_store_partial_response_records_conversation_id(clean_partial_cache):
    task_id = Aicode._store_partial_response(
        prompt="写个函数", partial_text="def f():\n    return 1", model="m1",
        user_id="42", conversation_id=7,
    )

    assert task_id and task_id in clean_partial_cache
    cached = clean_partial_cache[task_id]
    assert cached["conversation_id"] == 7
    assert cached["prompt"] == "写个函数"
    assert cached["model"] == "m1"
    assert cached["user_id"] == "42"


def test_store_partial_response_skips_too_short(clean_partial_cache):
    assert Aicode._store_partial_response("p", "short", "m", "1", 3) is None
    assert clean_partial_cache == {}


@pytest.mark.asyncio
async def test_resume_saves_back_into_original_conversation(monkeypatch, clean_partial_cache):
    """恢复续写必须写回原会话，不能另起新会话导致上下文断裂。"""
    captured = {}

    def _fake_stream_response(**kwargs):
        captured.update(kwargs)

        async def _gen():
            yield "chunk"

        return _gen()

    monkeypatch.setattr(Aicode, "stream_response", _fake_stream_response)
    clean_partial_cache["rid"] = {
        "prompt": "原始需求",
        "partial_response": "已经生成的部分内容",
        "model": "m1",
        "user_id": "42",
        "conversation_id": 7,
    }

    await Aicode.resume_code_generation(
        request=None, body={"resume_id": "rid"}, token={"sub": "42"}, db=None
    )

    assert captured["conversation_id"] == 7
    assert captured["resume_from"] == "rid"


@pytest.mark.asyncio
async def test_resume_keeps_none_when_original_had_no_conversation(monkeypatch, clean_partial_cache):
    """中断时尚未建立会话，恢复侧应为 None 交由保存逻辑新建。"""
    captured = {}

    def _fake_stream_response(**kwargs):
        captured.update(kwargs)

        async def _gen():
            yield "chunk"

        return _gen()

    monkeypatch.setattr(Aicode, "stream_response", _fake_stream_response)
    clean_partial_cache["rid"] = {
        "prompt": "p",
        "partial_response": "partial enough text",
        "model": "m1",
        "user_id": "42",
        "conversation_id": None,
    }

    await Aicode.resume_code_generation(
        request=None, body={"resume_id": "rid"}, token={"sub": "42"}, db=None
    )

    assert captured["conversation_id"] is None
