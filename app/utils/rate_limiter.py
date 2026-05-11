"""
请求限流中间件
防止 API 滥用和 DDoS 攻击
"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.config import settings


# 创建限流器
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"]  # 默认限制：每分钟 100 次请求
)


# 限流超额处理
def init_rate_limit(app):
    """初始化限流中间件"""
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


def get_client_ip(request: Request) -> str:
    """获取客户端真实 IP（考虑代理）"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0]
    return request.client.host if request.client else "unknown"


# API 级别的限流装饰器
# 用法：@limiter.limit("10/minute")
# 高频 API 使用更严格的限制，如代码生成：@limiter.limit("5/minute")
# 低频 API 使用宽松限制，如系统状态：@limiter.limit("30/minute")
