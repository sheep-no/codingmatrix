"""
请求重试装饰器

使用 tenacity 实现智能重试机制
适用于外部 API 调用、数据库操作等易失败场景
"""
import logging
import random
from functools import wraps
from typing import Optional, Callable, Any

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_log,
    after_log,
)

logger = logging.getLogger(__name__)


def retry_on_failure(
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    exceptions: tuple = (Exception,),
    log_level: int = logging.WARNING,
    enable_jitter: bool = True,
):
    """
    通用重试装饰器

    Args:
        max_attempts: 最大重试次数（包含首次尝试）
        min_wait: 最小等待时间（秒）
        max_wait: 最大等待时间（秒）
        exceptions: 触发重试的异常类型元组
        log_level: 重试日志级别
        enable_jitter: 是否启用抖动

    Returns:
        重试装饰器

    用法:
        @retry_on_failure(max_attempts=3, min_wait=2, max_wait=30)
        async def call_external_api():
            ...
    """
    def decorator(func: Callable) -> Callable:
        if enable_jitter:
            wait_strategy = wait_exponential(
                multiplier=1,
                min=min_wait,
                max=max_wait
            )
        else:
            wait_strategy = wait_exponential(
                multiplier=1,
                min=min_wait,
                max=max_wait
            )

        @wraps(func)
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_strategy,
            retry=retry_if_exception_type(exceptions),
            before=before_log(logger, log_level),
            after=after_log(logger, log_level),
            reraise=True
        )
        async def wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def retry_with_circuit_breaker(
    circuit_breaker_name: str,
    max_attempts: int = 3,
    min_wait: float = 1.0,
    max_wait: float = 10.0,
    exceptions: tuple = (Exception,),
    log_level: int = logging.WARNING
):
    """
    带熔断器的重试装饰器

    组合重试 + 熔断器，提供更强的容错能力

    Args:
        circuit_breaker_name: 熔断器名称
        max_attempts: 最大重试次数
        min_wait: 最小等待时间
        max_wait: 最大等待时间
        exceptions: 触发重试的异常类型
        log_level: 日志级别
    """
    def decorator(func: Callable) -> Callable:
        from app.utils.circuit_breaker import get_circuit_breaker, CircuitBreakerError

        @wraps(func)
        async def wrapper(*args, **kwargs):
            cb = get_circuit_breaker(circuit_breaker_name)
            try:
                return await cb.call(func, *args, **kwargs)
            except CircuitBreakerError:
                raise
            except Exception as e:
                if isinstance(e, exceptions):
                    raise
                raise

        return wrapper

    return decorator


def retry_api_call(max_attempts: int = 5):
    """
    外部 API 调用重试策略

    适用于：
    - AI 模型 API 调用
    - 第三方服务请求
    - 网络请求
    """
    import httpx
    return retry_on_failure(
        max_attempts=max_attempts,
        min_wait=2.0,
        max_wait=60.0,
        exceptions=(ConnectionError, httpx.TimeoutException, httpx.ConnectError, OSError),
        log_level=logging.WARNING,
        enable_jitter=True
    )


def retry_db_operation(max_attempts: int = 3):
    """
    数据库操作重试策略

    适用于：
    - 数据库查询
    - 写入操作
    - 连接获取
    """
    return retry_on_failure(
        max_attempts=max_attempts,
        min_wait=0.5,
        max_wait=5.0,
        exceptions=(Exception,),
        log_level=logging.DEBUG,
        enable_jitter=False
    )


def retry_file_operation(max_attempts: int = 3):
    """
    文件操作重试策略

    适用于：
    - 文件读写
    - 文件上传/下载
    - 临时文件处理
    """
    return retry_on_failure(
        max_attempts=max_attempts,
        min_wait=0.5,
        max_wait=10.0,
        exceptions=(IOError, OSError),
        log_level=logging.DEBUG,
        enable_jitter=False
    )
