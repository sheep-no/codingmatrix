"""中断部分响应的跨 worker 缓存（Redis）。

原先 `Aicode` 用模块级 dict 暂存中断的部分响应，生产以多 worker 运行
（uvicorn --workers 2 / gunicorn 2 workers）时，中断保存与恢复请求可能落到
不同进程，导致 resume_id 查不到、续写链断裂。这里改为 Redis 存储，TTL 与
原实现一致（5 分钟）。

Redis 不可用时回退进程内 dict（fail-open，与仓库其余 Redis 降级一致），
单进程/无 Redis 的开发环境行为不变。

使用同步客户端：调用点之一是流式生成被取消的 CancelledError 分支，
在取消上下文里 await 新协程可能再次抛出 CancelledError 导致保存丢失，
同步写入反而更可靠；该路径低频，阻塞开销可忽略。
"""
import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "partial_response:"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_FALLBACK_MAX_ENTRIES = 100

_client = None
_fallback: Dict[str, Tuple[dict, float]] = {}
_fallback_lock = threading.Lock()


def _key(resume_id: str) -> str:
    return f"{_KEY_PREFIX}{resume_id}"


def _get_client():
    global _client
    if _client is None:
        try:
            import redis
        except ImportError:
            logger.warning("redis 不可用，部分响应缓存回退进程内存储")
            return None
        url = (getattr(settings, "REDIS_URL", "") or "").strip() or _DEFAULT_REDIS_URL
        _client = redis.Redis.from_url(
            url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
    return _client


def set_store_client(client) -> None:
    """注入客户端；测试或需要复用既有连接时使用。"""
    global _client
    _client = client


def _prune_fallback(now: float) -> None:
    expired = [key for key, (_, expiry) in _fallback.items() if expiry <= now]
    for key in expired:
        _fallback.pop(key, None)
    if len(_fallback) > _FALLBACK_MAX_ENTRIES:
        oldest = sorted(_fallback.items(), key=lambda item: item[1][1])
        for key, _ in oldest[: len(_fallback) - _FALLBACK_MAX_ENTRIES]:
            _fallback.pop(key, None)


def _fallback_save(resume_id: str, payload: dict, ttl_seconds: int) -> None:
    with _fallback_lock:
        now = time.time()
        _prune_fallback(now)
        _fallback[resume_id] = (payload, now + ttl_seconds)


def _fallback_get(resume_id: str) -> Optional[dict]:
    with _fallback_lock:
        entry = _fallback.get(resume_id)
        if entry is None:
            return None
        payload, expiry = entry
        if expiry <= time.time():
            _fallback.pop(resume_id, None)
            return None
        return payload


def _fallback_pop(resume_id: str) -> Optional[dict]:
    with _fallback_lock:
        entry = _fallback.pop(resume_id, None)
    if entry is None:
        return None
    payload, expiry = entry
    if expiry <= time.time():
        return None
    return payload


def save_partial_response(resume_id: str, payload: dict, ttl_seconds: int) -> bool:
    """写入部分响应；Redis 写入失败时回退进程内存储。"""
    if ttl_seconds <= 0:
        return False
    client = _get_client()
    if client is not None:
        try:
            client.setex(_key(resume_id), ttl_seconds, json.dumps(payload, ensure_ascii=False))
            return True
        except Exception as e:
            logger.warning(f"部分响应写入 Redis 失败，回退进程内存储：{e}")
    _fallback_save(resume_id, payload, ttl_seconds)
    return True


def get_partial_response(resume_id: str) -> Optional[Dict[str, Any]]:
    """读取部分响应，不消费。"""
    client = _get_client()
    if client is not None:
        try:
            raw = client.get(_key(resume_id))
            if raw is not None:
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"部分响应读取 Redis 失败，回退进程内存储：{e}")
    return _fallback_get(resume_id)


def pop_partial_response(resume_id: str) -> Optional[Dict[str, Any]]:
    """读取并消费部分响应，避免被重复恢复。"""
    client = _get_client()
    if client is not None:
        try:
            raw = client.get(_key(resume_id))
            if raw is not None:
                try:
                    client.delete(_key(resume_id))
                except Exception as e:
                    logger.warning(f"部分响应消费（delete）失败：{e}")
                return json.loads(raw)
        except Exception as e:
            logger.warning(f"部分响应读取 Redis 失败，回退进程内存储：{e}")
    return _fallback_pop(resume_id)
