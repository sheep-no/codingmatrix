"""retry 装饰器行为补测。"""

import asyncio

import pytest

from app.utils.retry import (
    retry_api_call,
    retry_db_operation,
    retry_on_failure,
    retry_with_circuit_breaker,
)


def test_retries_until_success():
    calls = {"n": 0}

    @retry_on_failure(max_attempts=3, min_wait=0, max_wait=0)
    async def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("fail")
        return "ok"

    assert asyncio.run(flaky()) == "ok"
    assert calls["n"] == 3


def test_reraises_after_exhaustion():
    calls = {"n": 0}

    @retry_on_failure(max_attempts=2, min_wait=0, max_wait=0)
    async def always_fail():
        calls["n"] += 1
        raise ValueError("nope")

    with pytest.raises(ValueError):
        asyncio.run(always_fail())
    assert calls["n"] == 2


def test_no_jitter_strategy():
    @retry_on_failure(max_attempts=1, min_wait=0, max_wait=0, enable_jitter=False)
    async def ok():
        return 1

    assert asyncio.run(ok()) == 1


def test_non_matching_exception_not_retried():
    calls = {"n": 0}

    @retry_on_failure(max_attempts=3, min_wait=0, max_wait=0, exceptions=(KeyError,))
    async def boom():
        calls["n"] += 1
        raise ValueError("unexpected")

    with pytest.raises(ValueError):
        asyncio.run(boom())
    assert calls["n"] == 1


def test_circuit_breaker_wrapper():
    from app.utils import circuit_breaker as cb_module

    cb_module._circuit_breakers.clear()

    @retry_with_circuit_breaker("wrap-test")
    async def ok():
        return "done"

    assert asyncio.run(ok()) == "done"


def test_api_and_db_factories_return_decorators():
    async def ok():
        return 1

    assert asyncio.run(retry_api_call(max_attempts=1)(ok)()) == 1
    assert asyncio.run(retry_db_operation(max_attempts=1)(ok)()) == 1


def test_file_operation_factory():
    from app.utils.retry import retry_file_operation

    async def ok():
        return "f"

    assert asyncio.run(retry_file_operation(max_attempts=1)(ok)()) == "f"
