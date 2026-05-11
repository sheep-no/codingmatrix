"""
熔断器

防止级联故障，当服务持续失败时快速失败
"""
import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Optional, Any
from dataclasses import dataclass, field
from functools import wraps

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """熔断器状态"""
    CLOSED = "closed"       # 正常，请求通过
    OPEN = "open"          # 熔断，请求直接失败
    HALF_OPEN = "half_open"  # 半开，允许部分请求


@dataclass
class CircuitBreakerConfig:
    """熔断器配置"""
    failure_threshold: int = 5       # 失败次数达到此值则开启熔断
    success_threshold: int = 3       # 半开状态下成功次数达到此值则关闭熔断
    timeout: float = 30.0           # 熔断持续时间（秒）
    half_open_max_calls: int = 3    # 半开状态允许的请求数


@dataclass
class CircuitBreakerStats:
    """熔断器统计"""
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    state: CircuitState = CircuitState.CLOSED


class CircuitBreakerError(Exception):
    """熔断器异常"""
    def __init__(self, message: str, state: CircuitState):
        super().__init__(message)
        self.state = state


class CircuitBreaker:
    """
    熔断器

    状态转换：
    CLOSED → (失败次数达到阈值) → OPEN
    OPEN → (超时) → HALF_OPEN
    HALF_OPEN → (成功次数达到阈值) → CLOSED
    HALF_OPEN → (失败) → OPEN
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
        callback: Optional[Callable] = None
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.callback = callback
        self._stats = CircuitBreakerStats()
        self._lock = asyncio.Lock()
        self._half_open_calls = 0
        self._state_change_time = time.time()

    @property
    def state(self) -> CircuitState:
        """获取当前状态"""
        if self._stats.state == CircuitState.OPEN:
            if time.time() - self._state_change_time >= self.config.timeout:
                return CircuitState.HALF_OPEN
        return self._stats.state

    @property
    def stats(self) -> CircuitBreakerStats:
        """获取统计信息"""
        return self._stats

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        通过熔断器执行函数

        Args:
            func: 要执行的异步函数
            *args, **kwargs: 函数参数

        Returns:
            函数返回值

        Raises:
            CircuitBreakerError: 熔断开启时
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            self._stats.rejected_calls += 1
            logger.warning(f"CircuitBreaker OPEN | name={self.name} | rejected={self._stats.rejected_calls}")
            raise CircuitBreakerError(f"Circuit breaker '{self.name}' is OPEN", CircuitState.OPEN)

        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.config.half_open_max_calls:
                self._stats.rejected_calls += 1
                raise CircuitBreakerError(f"Circuit breaker '{self.name}' is HALF_OPEN (max calls)", CircuitState.HALF_OPEN)
            self._half_open_calls += 1

        self._stats.total_calls += 1

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self):
        """记录成功"""
        async with self._lock:
            self._stats.successful_calls += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.time()

            if self._stats.state == CircuitState.HALF_OPEN:
                if self._stats.consecutive_successes >= self.config.success_threshold:
                    self._stats.state = CircuitState.CLOSED
                    self._state_change_time = time.time()
                    self._half_open_calls = 0
                    self._stats.consecutive_successes = 0
                    logger.info(f"CircuitBreaker CLOSED | name={self.name}")

    async def _on_failure(self):
        """记录失败"""
        async with self._lock:
            self._stats.failed_calls += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = time.time()

            if self._stats.state == CircuitState.HALF_OPEN:
                self._stats.state = CircuitState.OPEN
                self._state_change_time = time.time()
                self._half_open_calls = 0
                logger.warning(f"CircuitBreaker OPEN (half_open failure) | name={self.name}")

            elif self._stats.consecutive_failures >= self.config.failure_threshold:
                self._stats.state = CircuitState.OPEN
                self._state_change_time = time.time()
                logger.warning(f"CircuitBreaker OPEN | name={self.name} | failures={self._stats.consecutive_failures}")

    def get_status(self) -> dict:
        """获取熔断器状态"""
        return {
            "name": self.name,
            "state": self.state.value,
            "stats": {
                "total_calls": self._stats.total_calls,
                "successful_calls": self._stats.successful_calls,
                "failed_calls": self._stats.failed_calls,
                "rejected_calls": self._stats.rejected_calls,
                "consecutive_failures": self._stats.consecutive_failures,
                "last_failure_time": self._stats.last_failure_time,
                "last_success_time": self._stats.last_success_time,
            }
        }

    async def reset(self):
        """重置熔断器"""
        async with self._lock:
            self._stats = CircuitBreakerStats()
            self._half_open_calls = 0
            self._state_change_time = time.time()


_circuit_breakers: dict = {}


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """获取或创建熔断器"""
    if name not in _circuit_breakers:
        _circuit_breakers[name] = CircuitBreaker(name, config)
    return _circuit_breakers[name]


def circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None):
    """
    熔断器装饰器

    用法：
        @circuit_breaker("api_call")
        async def call_api():
            ...
    """
    def decorator(func):
        cb = get_circuit_breaker(name, config)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)

        wrapper.cb = cb
        return wrapper
    return decorator
