"""
请求限流中间件
防止 API 滥用和 DDoS 攻击
"""
import ipaddress
import logging
import time

from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

# 限流存储的 Redis 读写/连接超时（秒）。缺省值是无限等待，Redis 卡住或网络
# 黑洞时会把请求线程永久挂住；`in_memory_fallback_enabled` 只在存储抛异常时
# 才生效，对阻塞无效，所以必须给 socket 设超时让失败快速冒泡到内存回退。
REDIS_SOCKET_TIMEOUT_SECONDS = 2


def _is_trusted_peer(host: str) -> bool:
    """直连对端是否为可信反向代理（内网/回环地址）。"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP（代理感知）。

    仅当直连对端是内网/回环地址时才采信代理头，避免公网客户端伪造
    X-Forwarded-For / X-Real-IP 绕过限流。优先取代理覆写的 X-Real-IP；
    退回 X-Forwarded-For 的最后一段（nginx 用 $proxy_add_x_forwarded_for
    追加，真实客户端在末段，首段可被客户端伪造）。
    """
    peer = request.client.host if request.client else "unknown"
    if not _is_trusted_peer(peer):
        return peer

    real_ip = request.headers.get("X-Real-IP")
    if real_ip and real_ip.strip():
        return real_ip.strip()

    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        entries = [part.strip() for part in forwarded.split(",") if part.strip()]
        if entries:
            return entries[-1]
    return peer


def _resolve_storage_uri() -> str | None:
    """限流计数存储；配置 Redis 时跨进程共享，否则退化单进程内存。"""
    return (settings.REDIS_URL or "").strip() or None


def _create_limiter() -> Limiter:
    storage_uri = _resolve_storage_uri()
    if storage_uri:
        try:
            return Limiter(
                key_func=get_client_ip,
                default_limits=["100/minute"],
                storage_uri=storage_uri,
                storage_options={
                    "socket_connect_timeout": REDIS_SOCKET_TIMEOUT_SECONDS,
                    "socket_timeout": REDIS_SOCKET_TIMEOUT_SECONDS,
                },
                in_memory_fallback_enabled=True,
            )
        except Exception as e:  # 存储不可用不得阻断启动，退化为单进程内存限流
            logger.warning(f"限流存储初始化失败，退化为内存限流: {e}")
    return Limiter(
        key_func=get_client_ip,
        default_limits=["100/minute"],
    )


# 创建限流器
limiter = _create_limiter()


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """统一 429 响应格式，并尽量附带 Retry-After 重试窗口。"""
    headers = {}
    current_limit = getattr(request.state, "view_rate_limit", None)
    limiter_state = getattr(request.app.state, "limiter", None)
    if current_limit is not None and limiter_state is not None:
        try:
            reset_at, _remaining = limiter_state.limiter.get_window_stats(
                current_limit[0], *current_limit[1]
            )
            headers["Retry-After"] = str(max(0, int(reset_at - time.time())))
        except Exception:
            pass

    return JSONResponse(
        status_code=429,
        content={
            "code": "RATE_LIMIT_EXCEEDED",
            "message": "请求过于频繁，请稍后重试",
            "details": {"limit": str(exc.detail)},
        },
        headers=headers,
    )


# 限流超额处理
def init_rate_limit(app):
    """初始化限流中间件"""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)


# API 级别的限流装饰器
# 用法：@limiter.limit("10/minute")
# 高频 API 使用更严格的限制，如代码生成：@limiter.limit("5/minute")
# 低频 API 使用宽松限制，如系统状态：@limiter.limit("30/minute")
