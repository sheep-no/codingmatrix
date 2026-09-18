"""
熔断器

防止级联故障，当服务持续失败时快速失败
"""
import asyncio
import logging
import threading
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
        return self._reconcile_state()

    def _reconcile_state(self) -> CircuitState:
        """将 OPEN 状态在超时后落实为 HALF_OPEN。

        `state` 以前只是在读取时派生出 HALF_OPEN，却从不更新 `_stats.state`，
        导致 `_on_success`/`_on_failure` 里 `_stats.state == HALF_OPEN` 的分支
        永远不成立——熔断器一旦 OPEN 就再也无法恢复。这里把转换真正落到内部状态。
        """
        if (
            self._stats.state == CircuitState.OPEN
            and time.time() - self._state_change_time >= self.config.timeout
        ):
            self._half_open_calls = 0
            self._transition(CircuitState.HALF_OPEN)
        return self._stats.state

    def _notify(self, old_state: CircuitState, new_state: CircuitState) -> None:
        """触发状态变更回调，回调异常不得影响主流程"""
        if self.callback is None:
            return
        try:
            self.callback(self.name, old_state, new_state)
        except Exception:
            logger.exception(f"CircuitBreaker callback error | name={self.name}")

    def _transition(self, new_state: CircuitState) -> None:
        """更新内部状态并通知回调"""
        old_state = self._stats.state
        if old_state == new_state:
            return
        self._stats.state = new_state
        self._state_change_time = time.time()
        self._notify(old_state, new_state)

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
        # 先落实 OPEN -> HALF_OPEN 转换，保证下面的成功/失败统计走对分支
        current_state = self._reconcile_state()

        if current_state == CircuitState.OPEN:
            self._stats.rejected_calls += 1
            logger.warning(f"CircuitBreaker OPEN | name={self.name} | rejected={self._stats.rejected_calls}")
            raise CircuitBreakerError(f"Circuit breaker '{self.name}' is OPEN", CircuitState.OPEN)

        half_open_slot = False
        if current_state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.config.half_open_max_calls:
                self._stats.rejected_calls += 1
                raise CircuitBreakerError(f"Circuit breaker '{self.name}' is HALF_OPEN (max calls)", CircuitState.HALF_OPEN)
            self._half_open_calls += 1
            half_open_slot = True

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
        finally:
            # 半开名额只在探测进行中占用；用完必须归还，否则 success_threshold
            # 大于 half_open_max_calls 时熔断器会被永久卡在 HALF_OPEN
            if half_open_slot:
                async with self._lock:
                    if self._half_open_calls > 0:
                        self._half_open_calls -= 1

    async def _on_success(self):
        """记录成功"""
        async with self._lock:
            self._stats.successful_calls += 1
            self._stats.consecutive_successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.time()

            if self._stats.state == CircuitState.HALF_OPEN:
                if self._stats.consecutive_successes >= self.config.success_threshold:
                    self._half_open_calls = 0
                    self._stats.consecutive_successes = 0
                    self._transition(CircuitState.CLOSED)
                    logger.info(f"CircuitBreaker CLOSED | name={self.name}")

    async def _on_failure(self):
        """记录失败"""
        async with self._lock:
            self._stats.failed_calls += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = time.time()

            if self._stats.state == CircuitState.HALF_OPEN:
                self._half_open_calls = 0
                self._transition(CircuitState.OPEN)
                logger.warning(f"CircuitBreaker OPEN (half_open failure) | name={self.name}")

            elif self._stats.consecutive_failures >= self.config.failure_threshold:
                self._transition(CircuitState.OPEN)
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
_circuit_breakers_lock = threading.Lock()


def get_circuit_breaker(name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
    """获取或创建熔断器"""
    with _circuit_breakers_lock:
        breaker = _circuit_breakers.get(name)
        if breaker is None:
            breaker = CircuitBreaker(name, config)
            _circuit_breakers[name] = breaker
        return breaker


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
