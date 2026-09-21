"""Token 吊销黑名单（Redis denylist）。

JWT 无状态，签发后无法作废。登出时把 token 的 sha256 摘要写入 Redis，TTL 设为
token 剩余有效期；`verify_token` / `verify_token_ws` / `/refresh` 校验时查这份
黑名单，命中即拒绝。

Redis 不可用时按 fail-open 处理（视为未吊销）并告警：与仓库其余 Redis 降级
策略一致，可用性优先；此时吊销能力弱化为仅当前进程内不可用。
"""
import hashlib
import logging
from typing import Optional

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY_PREFIX = "token_denylist:"
_DEFAULT_REDIS_URL = "redis://localhost:6379/0"
_client = None


def _token_key(token: str) -> str:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return f"{_KEY_PREFIX}{digest}"


def _get_client():
    global _client
    if _client is None:
        try:
            import redis.asyncio as aioredis
        except ImportError:
            logger.warning("redis.asyncio 不可用，Token 吊销黑名单降级为 no-op")
            return None
        url = (getattr(settings, "REDIS_URL", "") or "").strip() or _DEFAULT_REDIS_URL
        _client = aioredis.from_url(
            url,
            decode_responses=True,
            socket_timeout=1.0,
            socket_connect_timeout=1.0,
        )
    return _client


def set_denylist_client(client) -> None:
    """注入客户端；测试或需要复用既有连接时使用。"""
    global _client
    _client = client


async def revoke_token(token: Optional[str], ttl_seconds: int) -> bool:
    """把 token 写入黑名单；ttl_seconds<=0 表示已过期，无需吊销。"""
    if not token or ttl_seconds <= 0:
        return False
    client = _get_client()
    if client is None:
        return False
    try:
        await client.setex(_token_key(token), ttl_seconds, "1")
        return True
    except Exception as e:
        logger.warning(f"Token 吊销写入失败：{e}")
        return False


async def is_token_revoked(token: Optional[str]) -> bool:
    """token 是否已被吊销；Redis 异常时按未吊销处理（fail-open）。"""
    if not token:
        return False
    client = _get_client()
    if client is None:
        return False
    try:
        return bool(await client.exists(_token_key(token)))
    except Exception as e:
        logger.warning(f"Token 吊销查询失败，按未吊销处理：{e}")
        return False
