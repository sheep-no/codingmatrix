"""
缓存装饰器模块
为 FastAPI 路由函数提供便捷的缓存支持
"""
import hashlib
import json
import logging
import functools
from typing import Optional, Callable, Any, Awaitable, Union
from fastapi import Request, Response
from fastapi.responses import JSONResponse

from app.utils.cache import get_cache_manager

logger = logging.getLogger(__name__)


def _generate_cache_key(
    key_prefix: str,
    func_name: str,
    args: tuple,
    kwargs: dict,
    request: Optional[Request] = None,
) -> str:
    parts = [key_prefix, func_name]

    if request:
        url_path = str(request.url.path)
        parts.append(url_path)
        query_params = dict(request.query_params)
        if query_params:
            parts.append(json.dumps(query_params, sort_keys=True))

    for arg in args:
        if isinstance(arg, (int, str, float, bool)):
            parts.append(str(arg))
        elif hasattr(arg, 'model_dump'):
            # Pydantic v2 model
            try:
                parts.append(json.dumps(arg.model_dump(), sort_keys=True, default=str))
            except Exception:
                pass
        elif hasattr(arg, 'dict'):
            # Pydantic v1 model
            try:
                parts.append(json.dumps(arg.dict(), sort_keys=True, default=str))
            except Exception:
                pass

    for k, v in sorted(kwargs.items()):
        if k not in ("request", "db", "token", "current_user", "user_id", "background_tasks"):
            if isinstance(v, (int, str, float, bool)):
                parts.append(f"{k}={v}")
            elif hasattr(v, 'model_dump'):
                try:
                    parts.append(f"{k}={json.dumps(v.model_dump(), sort_keys=True, default=str)}")
                except Exception:
                    pass
            elif hasattr(v, 'dict'):
                try:
                    parts.append(f"{k}={json.dumps(v.dict(), sort_keys=True, default=str)}")
                except Exception:
                    pass

    key_str = ":".join(parts)
    return hashlib.md5(key_str.encode("utf-8")).hexdigest()


def _should_cache_response(status_code: int, condition: Optional[Callable] = None) -> bool:
    if 200 <= status_code < 300:
        if condition:
            return condition()
        return True
    return False


def cache_response(
    ttl: int = 300,
    key_prefix: str = "api",
    condition: Optional[Callable] = None,
    invalidate_on: Optional[Callable] = None,
    cache_none: bool = True,
):
    """
    FastAPI 路由缓存装饰器

    参数:
        ttl: 缓存过期时间（秒），默认 300
        key_prefix: 缓存键前缀，默认 "api"
        condition: 条件函数，返回 True 时才缓存响应
        invalidate_on: 失效函数，返回 True 时清除缓存
        cache_none: 是否缓存 None/空响应，默认 True

    用法:
        @router.get("/api/v1/history")
        @cache_response(ttl=60, key_prefix="history")
        async def get_history(request: Request, db: AsyncSession, token: dict):
            ...
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            cache = await get_cache_manager()
            req = None
            for arg in args:
                if isinstance(arg, Request):
                    req = arg
                    break
            if req is None:
                req = kwargs.get("request")
                if not isinstance(req, Request):
                    req = None

            cache_key = _generate_cache_key(key_prefix, func.__name__, args, kwargs, req)

            if invalidate_on and invalidate_on(*args, **kwargs):
                await cache.invalidate_pattern(f"{key_prefix}:*")
                logger.debug(f"缓存失效触发 key_prefix={key_prefix}")

            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"缓存命中 key={cache_key[:16]}...")
                if isinstance(cached_value, dict) and "_cached_response" in cached_value:
                    return cached_value["_cached_response"]
                return cached_value

            try:
                result = await func(*args, **kwargs)
            except Exception as e:
                logger.error(f"路由执行失败 func={func.__name__}: {e}")
                raise

            status_code = 200
            if isinstance(result, Response):
                status_code = result.status_code
            elif isinstance(result, dict):
                status_code = result.get("status_code", 200)

            if _should_cache_response(status_code, condition):
                if result is None and not cache_none:
                    return result

                cache_data = {
                    "_cached_response": result,
                    "_cached_at": None,
                }
                await cache.set(cache_key, cache_data, ttl)
                logger.debug(f"缓存写入 key={cache_key[:16]}... ttl={ttl}")

            return result

        return wrapper
    return decorator


def invalidate_cache(key_prefix: str, pattern: Optional[str] = None):
    """
    手动缓存失效装饰器
    在修改操作后自动清除相关缓存

    参数:
        key_prefix: 缓存键前缀
        pattern: 可选的模式匹配，默认 "{key_prefix}:*"

    用法:
        @router.post("/conversations")
        @invalidate_cache(key_prefix="conversations")
        async def create_conversation(...):
            ...
    """
    def decorator(func: Callable[..., Awaitable[Any]]):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)

            cache = await get_cache_manager()
            invalidate_pattern = pattern or f"{key_prefix}:*"
            count = await cache.invalidate_pattern(invalidate_pattern)
            logger.info(f"缓存失效 key_prefix={key_prefix} pattern={invalidate_pattern} count={count}")

            return result
        return wrapper
    return decorator


async def invalidate_cache_by_prefix(key_prefix: str, pattern: Optional[str] = None) -> int:
    """
    手动清除指定前缀的缓存（供代码中直接调用）

    参数:
        key_prefix: 缓存键前缀
        pattern: 可选的模式匹配

    返回:
        失效的缓存键数量
    """
    cache = await get_cache_manager()
    invalidate_pattern = pattern or f"{key_prefix}:*"
    count = await cache.invalidate_pattern(invalidate_pattern)
    logger.info(f"手动缓存失效 key_prefix={key_prefix} count={count}")
    return count
