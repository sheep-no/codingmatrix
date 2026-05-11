"""
测试熔断器
"""
import pytest
import asyncio
from app.utils.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerError,
    CircuitState,
    circuit_breaker,
    get_circuit_breaker
)


class TestCircuitBreaker:
    """测试熔断器"""

    def test_initial_state(self):
        """测试初始状态"""
        cb = CircuitBreaker("test_initial", CircuitBreakerConfig(failure_threshold=3))
        assert cb.state == CircuitState.CLOSED

    def test_failure_threshold(self):
        """测试失败阈值触发熔断"""
        cb = CircuitBreaker("test_failure", CircuitBreakerConfig(failure_threshold=3))

        async def failing_func():
            raise ValueError("fail")

        for _ in range(3):
            with pytest.raises(ValueError):
                asyncio.run(cb.call(failing_func))

        assert cb.state == CircuitState.OPEN

    def test_successful_call(self):
        """测试成功调用"""
        cb = CircuitBreaker("test_success", CircuitBreakerConfig(failure_threshold=3))

        async def success_func():
            return "success"

        result = asyncio.run(cb.call(success_func))
        assert result == "success"
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self):
        """测试超时后进入半开状态"""
        cb = CircuitBreaker(
            "test_half_open",
            CircuitBreakerConfig(failure_threshold=1, timeout=0.1)
        )

        async def failing_func():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await cb.call(failing_func)

        assert cb.state == CircuitState.OPEN

        await asyncio.sleep(0.2)

        assert cb.state == CircuitState.HALF_OPEN

    def test_get_status(self):
        """测试获取状态"""
        cb = CircuitBreaker("test_status", CircuitBreakerConfig(failure_threshold=3))
        status = cb.get_status()

        assert "name" in status
        assert "state" in status
        assert "stats" in status
        assert status["name"] == "test_status"


class TestCircuitBreakerDecorator:
    """测试熔断器装饰器"""

    def test_decorator_opens_after_failures(self):
        """测试装饰器在失败后打开熔断器"""
        cb_instance = None
        call_count = 0

        @circuit_breaker("decorated_test_fail", CircuitBreakerConfig(failure_threshold=2))
        async def my_func():
            nonlocal call_count, cb_instance
            call_count += 1
            raise ValueError("fail")

        with pytest.raises(ValueError):
            asyncio.run(my_func())

        with pytest.raises(ValueError):
            asyncio.run(my_func())

        assert call_count == 2
