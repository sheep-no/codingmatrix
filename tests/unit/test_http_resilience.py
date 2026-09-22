"""http_client / retry / circuit_breaker 网络容错模块回归测试。

覆盖曾经真实存在的缺陷：
- 熔断器 OPEN 超时后只在读取时“派生” HALF_OPEN，内部状态从不更新，
  导致一旦打开就永远无法回到 CLOSED；
- 半开探测名额只增不减，success_threshold 大于 half_open_max_calls 时永久卡死；
- HTTPClientPool 不检查 is_closed，客户端被关闭后持续复用坏连接；
- retry_on_failure 的 enable_jitter 两个分支完全相同，抖动从未生效。
"""
import time

import httpx
import pytest
import tenacity

from app.utils import circuit_breaker as cb_module
from app.utils import http_client as pool_module
from app.utils import retry as retry_module
from app.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitState,
    get_circuit_breaker,
)


async def _boom():
    raise RuntimeError("boom")


async def _ok(value="ok"):
    return value


def _open_breaker(name: str, **config_kwargs) -> CircuitBreaker:
    breaker = CircuitBreaker(
        name,
        # 超时窗口取 0.3s：断言 OPEN 是紧随失败之后的同步操作，50ms 窗口在
        # 高负载 CI 上会被跨过，导致「OPEN 断言读到 HALF_OPEN」的偶发失败。
        CircuitBreakerConfig(failure_threshold=1, timeout=0.3, **config_kwargs),
    )
    return breaker


def _wait_for_state(breaker: CircuitBreaker, state: CircuitState, timeout: float = 3.0) -> bool:
    """轮询等待目标状态，避免用固定 sleep 与超时赛跑。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if breaker.state == state:
            return True
        time.sleep(0.005)
    return breaker.state == state


@pytest.mark.asyncio
async def test_breaker_recovers_from_open_to_closed_after_timeout():
    breaker = _open_breaker("recover", success_threshold=2)

    with pytest.raises(RuntimeError):
        await breaker.call(_boom)
    assert breaker.state == CircuitState.OPEN

    assert _wait_for_state(breaker, CircuitState.HALF_OPEN)

    assert await breaker.call(_ok) == "ok"
    assert await breaker.call(_ok) == "ok"
    assert breaker.state == CircuitState.CLOSED


@pytest.mark.asyncio
async def test_half_open_slot_is_released_between_probes():
    # success_threshold 大于 half_open_max_calls：名额若不归还，第 3 次探测就被拒
    breaker = _open_breaker(
        "slots", success_threshold=5, half_open_max_calls=2
    )

    with pytest.raises(RuntimeError):
        await breaker.call(_boom)

    assert _wait_for_state(breaker, CircuitState.HALF_OPEN)
    for _ in range(5):
        assert await breaker.call(_ok) == "ok"

    assert breaker.state == CircuitState.CLOSED
    assert breaker.stats.rejected_calls == 0


@pytest.mark.asyncio
async def test_half_open_failure_reopens_and_rearms_timeout():
    breaker = _open_breaker("rearm", success_threshold=3)

    with pytest.raises(RuntimeError):
        await breaker.call(_boom)
    assert _wait_for_state(breaker, CircuitState.HALF_OPEN)

    with pytest.raises(RuntimeError):
        await breaker.call(_boom)
    assert breaker.state == CircuitState.OPEN


@pytest.mark.asyncio
async def test_state_change_callback_is_invoked():
    events = []
    breaker = CircuitBreaker(
        "callback",
        CircuitBreakerConfig(failure_threshold=1, success_threshold=1, timeout=0.3),
        callback=lambda name, old, new: events.append((name, old, new)),
    )

    with pytest.raises(RuntimeError):
        await breaker.call(_boom)
    assert _wait_for_state(breaker, CircuitState.HALF_OPEN)
    await breaker.call(_ok)

    assert events == [
        ("callback", CircuitState.CLOSED, CircuitState.OPEN),
        ("callback", CircuitState.OPEN, CircuitState.HALF_OPEN),
        ("callback", CircuitState.HALF_OPEN, CircuitState.CLOSED),
    ]


def test_get_circuit_breaker_returns_singleton(monkeypatch):
    monkeypatch.setattr(cb_module, "_circuit_breakers", {})

    first = get_circuit_breaker("singleton")
    second = get_circuit_breaker("singleton")

    assert first is second


@pytest.mark.asyncio
async def test_http_client_pool_rebuilds_closed_client():
    pool = pool_module.HTTPClientPool(timeout=1.0)
    client = await pool.get_client()
    await client.aclose()

    rebuilt = await pool.get_client()

    assert rebuilt.is_closed is False
    await pool.close()


@pytest.mark.asyncio
async def test_http_client_pool_close_clears_client():
    pool = pool_module.HTTPClientPool(timeout=1.0)
    await pool.get_client()

    await pool.close()

    assert pool._client is None


def test_retry_on_failure_enables_jitter_only_when_requested():
    @retry_module.retry_on_failure(max_attempts=2, enable_jitter=True)
    async def with_jitter():
        return None

    @retry_module.retry_on_failure(max_attempts=2, enable_jitter=False)
    async def without_jitter():
        return None

    assert isinstance(with_jitter.retry.wait, tenacity.wait_random_exponential)
    assert isinstance(without_jitter.retry.wait, tenacity.wait_exponential)
    assert not isinstance(without_jitter.retry.wait, tenacity.wait_random_exponential)


@pytest.mark.asyncio
async def test_retry_with_circuit_breaker_returns_result():
    calls = {"n": 0}

    @retry_module.retry_with_circuit_breaker("decorated")
    async def target():
        calls["n"] += 1
        return "done"

    assert await target() == "done"
    assert calls["n"] == 1
