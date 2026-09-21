"""API Key 请求体校验（APY4）。

context_lengths 与 custom_fallback_chain 原无任何值校验：非整数/布尔值/越界值
可写入用户元数据，降级链元素可为任意对象。
"""

import pytest
from pydantic import ValidationError

from app.api.v1.apikey import (
    UpdateContextLengthsRequest,
    UpdateFallbackPreferenceRequest,
)


def test_valid_context_lengths_accepted():
    payload = {"Qwen/Qwen3-8B": 32768, "deepseek-chat": 65536}
    request = UpdateContextLengthsRequest(context_lengths=payload)
    assert request.context_lengths == payload


@pytest.mark.parametrize(
    "context_lengths",
    [
        {"m": "32768"},
        {"m": True},
        {"m": 0},
        {"m": -1},
        {"m": 10_000_001},
        {"": 1024},
        {"m" * 201: 1024},
        {f"m{i}": 1024 for i in range(201)},
    ],
)
def test_invalid_context_lengths_rejected(context_lengths):
    with pytest.raises(ValidationError):
        UpdateContextLengthsRequest(context_lengths=context_lengths)


def test_empty_context_lengths_allowed():
    assert UpdateContextLengthsRequest(context_lengths={}).context_lengths == {}


def test_valid_fallback_chain_accepted():
    request = UpdateFallbackPreferenceRequest(
        fallback_preference="custom",
        custom_fallback_chain=["Qwen/Qwen3-8B", "custom-model-x"],
    )
    assert request.custom_fallback_chain == ["Qwen/Qwen3-8B", "custom-model-x"]


@pytest.mark.parametrize(
    "chain",
    [
        ["ok", ""],
        ["ok", "   "],
        ["ok", 123],
        ["ok", {"a": 1}],
        ["m" * 201],
        [f"m{i}" for i in range(21)],
    ],
)
def test_invalid_fallback_chain_rejected(chain):
    with pytest.raises(ValidationError):
        UpdateFallbackPreferenceRequest(custom_fallback_chain=chain)
