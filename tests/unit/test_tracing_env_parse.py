"""TT1 回归：非法 OTEL 环境变量不得让 tracing 模块无法 import。

`app/agent/tracing.py` 在模块顶层解析 `OTEL_SAMPLING_RATE`，原实现直接
`float(...)`，非法值（如 "abc"、空串）抛 ValueError，导致 12 个消费模块
import 链整体崩溃。修复后回退默认值并告警；超出 [0,1] 的采样率被夹紧。
"""

from __future__ import annotations

import importlib

import pytest

from app.agent import tracing


@pytest.fixture
def reload_tracing():
    """按需 reload 模块，测试结束后恢复默认环境下的模块状态。"""
    yield importlib.reload
    importlib.reload(tracing)


class TestSamplingRateParsing:
    @pytest.mark.parametrize("raw", ["abc", "", "  ", "1.0x", "nan-", "nan", "inf-"])
    def test_invalid_value_falls_back(self, monkeypatch, reload_tracing, raw):
        monkeypatch.setenv("OTEL_SAMPLING_RATE", raw)
        mod = reload_tracing(tracing)
        assert mod._sampling_rate == 1.0

    @pytest.mark.parametrize(
        "raw,expected",
        [("0.5", 0.5), ("0", 0.0), ("1", 1.0), ("0.25", 0.25)],
    )
    def test_valid_value_preserved(self, monkeypatch, reload_tracing, raw, expected):
        monkeypatch.setenv("OTEL_SAMPLING_RATE", raw)
        mod = reload_tracing(tracing)
        assert mod._sampling_rate == expected

    @pytest.mark.parametrize("raw,expected", [("5.0", 1.0), ("-2", 0.0)])
    def test_out_of_range_clamped(self, monkeypatch, reload_tracing, raw, expected):
        monkeypatch.setenv("OTEL_SAMPLING_RATE", raw)
        mod = reload_tracing(tracing)
        assert mod._sampling_rate == expected

    def test_decorator_still_works_when_env_invalid(self, monkeypatch, reload_tracing):
        """非法采样率下模块仍可正常使用 traced 装饰器。"""
        monkeypatch.setenv("OTEL_SAMPLING_RATE", "not-a-number")
        mod = reload_tracing(tracing)

        @mod.traced("test.env")
        def fn():
            return 7

        assert fn() == 7


class TestBatchEnvParsing:
    def test_env_float_falls_back(self, monkeypatch):
        monkeypatch.setenv("OTEL_TEST_FLOAT", "oops")
        assert tracing._env_float("OTEL_TEST_FLOAT", 5.0) == 5.0

    def test_env_int_falls_back(self, monkeypatch):
        monkeypatch.setenv("OTEL_TEST_INT", "oops")
        assert tracing._env_int("OTEL_TEST_INT", 2048) == 2048

    def test_env_helpers_accept_valid(self, monkeypatch):
        monkeypatch.setenv("OTEL_TEST_FLOAT", "2.5")
        monkeypatch.setenv("OTEL_TEST_INT", "10")
        assert tracing._env_float("OTEL_TEST_FLOAT", 1.0) == 2.5
        assert tracing._env_int("OTEL_TEST_INT", 1) == 10
