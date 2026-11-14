"""circuit_breaker 状态机、回调与装饰器补测。"""

import asyncio

import pytest

from app.utils import circuit_breaker as module
from app.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
    circuit_breaker,
    get_circuit_breaker,
)


@pytest.fixture(autouse=True)
def _clear_registry():
    module._circuit_breakers.clear()
    yield
    module._circuit_breakers.clear()


def _breaker(**config):
    return CircuitBreaker("test", CircuitBreakerConfig(**config))


async def test_initial_state_closed():
    breaker = _breaker()
    assert breaker.state is CircuitState.CLOSED


async def test_open_after_threshold_failures():
    breaker = _breaker(failure_threshold=2)

    async def boom():
        raise RuntimeError("fail")

    for _ in range(2):
        with pytest.raises(RuntimeError):
            await breaker.call(boom)

    assert breaker.state is CircuitState.OPEN


async def test_open_rejects_calls():
    breaker = _breaker(failure_threshold=1)

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)

    with pytest.raises(CircuitBreakerError) as info:
        await breaker.call(boom)

    assert info.value.state is CircuitState.OPEN
    assert breaker.stats.rejected_calls == 1


async def test_open_transitions_to_half_open_after_timeout(monkeypatch):
    breaker = _breaker(failure_threshold=1, timeout=10)
    now = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN

    now[0] += 11
    assert breaker.state is CircuitState.HALF_OPEN


async def test_half_open_success_closes_after_threshold(monkeypatch):
    breaker = _breaker(failure_threshold=1, success_threshold=2, timeout=10)
    now = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)

    now[0] += 11

    async def ok():
        return "ok"

    await breaker.call(ok)
    assert breaker.state is CircuitState.HALF_OPEN
    await breaker.call(ok)
    assert breaker.state is CircuitState.CLOSED


async def test_half_open_failure_reopens(monkeypatch):
    breaker = _breaker(failure_threshold=1, timeout=10)
    now = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    now[0] += 11

    with pytest.raises(RuntimeError):
        await breaker.call(boom)

    assert breaker.state is CircuitState.OPEN


async def test_half_open_max_calls_rejects(monkeypatch):
    breaker = _breaker(failure_threshold=1, timeout=10, half_open_max_calls=1)
    now = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    now[0] += 11

    started = asyncio.Event()
    release = asyncio.Event()

    async def slow():
        started.set()
        await release.wait()
        return "ok"

    task = asyncio.create_task(breaker.call(slow))
    await started.wait()

    with pytest.raises(CircuitBreakerError) as info:
        await breaker.call(slow)
    assert info.value.state is CircuitState.HALF_OPEN

    release.set()
    assert await task == "ok"


async def test_sync_function_supported():
    breaker = _breaker()

    def add(a, b):
        return a + b

    assert await breaker.call(add, 1, 2) == 3


async def test_callback_invoked_on_transition():
    events = []
    breaker = CircuitBreaker(
        "cb",
        CircuitBreakerConfig(failure_threshold=1),
        callback=lambda name, old, new: events.append((name, old, new)),
    )

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)

    assert events == [("cb", CircuitState.CLOSED, CircuitState.OPEN)]


async def test_callback_exception_is_swallowed():
    def bad_callback(*args):
        raise RuntimeError("callback failed")

    breaker = CircuitBreaker(
        "cb", CircuitBreakerConfig(failure_threshold=1), callback=bad_callback
    )

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    assert breaker.state is CircuitState.OPEN


async def test_transition_to_same_state_is_noop():
    breaker = _breaker()
    breaker._transition(CircuitState.CLOSED)
    assert breaker.state is CircuitState.CLOSED


async def test_reset_restores_defaults():
    breaker = _breaker(failure_threshold=1)

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)

    await breaker.reset()

    assert breaker.state is CircuitState.CLOSED
    assert breaker.stats.total_calls == 0
    assert breaker.stats.failed_calls == 0


def test_get_status_structure():
    breaker = _breaker()
    status = breaker.get_status()
    assert status["name"] == "test"
    assert status["state"] == "closed"
    assert status["stats"]["total_calls"] == 0


async def test_get_circuit_breaker_singleton():
    first = get_circuit_breaker("shared")
    second = get_circuit_breaker("shared")
    assert first is second


async def test_decorator_passes_through_and_exposes_cb():
    @circuit_breaker("decorated")
    async def handler(value):
        return value * 2

    assert await handler(3) == 6
    assert handler.cb.name == "decorated"


async def test_decorator_records_failure():
    @circuit_breaker("decorated-fail", CircuitBreakerConfig(failure_threshold=1))
    async def broken():
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await broken()

    assert broken.cb.state is CircuitState.OPEN


async def test_half_open_slot_released_on_success(monkeypatch):
    breaker = _breaker(failure_threshold=1, timeout=10, half_open_max_calls=2)
    now = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    now[0] += 11

    async def ok():
        return 1

    await breaker.call(ok)
    assert breaker._half_open_calls == 0


async def test_half_open_slot_not_released_when_never_taken(monkeypatch):
    breaker = _breaker(failure_threshold=1, timeout=10)
    now = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    now[0] += 11

    # 触发 OPEN -> HALF_OPEN 转换后，模拟名额已被并发调用占满
    assert breaker.state is CircuitState.HALF_OPEN
    breaker._half_open_calls = breaker.config.half_open_max_calls
    with pytest.raises(CircuitBreakerError):
        await breaker.call(boom)
    assert breaker._half_open_calls == breaker.config.half_open_max_calls


async def test_half_open_slot_released_when_counter_already_zero(monkeypatch):
    breaker = _breaker(failure_threshold=1, timeout=10)
    now = [1000.0]
    monkeypatch.setattr(module.time, "time", lambda: now[0])

    async def boom():
        raise RuntimeError("fail")

    with pytest.raises(RuntimeError):
        await breaker.call(boom)
    now[0] += 11
    assert breaker.state is CircuitState.HALF_OPEN

    async def zero_then_ok():
        breaker._half_open_calls = 0
        return "ok"

    assert await breaker.call(zero_then_ok) == "ok"
    assert breaker._half_open_calls == 0
