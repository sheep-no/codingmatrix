"""
速率限制中间件

防止暴力破解、API 滥用和 DDoS 攻击

支持多级限流策略：
- 全局限流
- IP 限流
- 用户限流
- 端点限流
"""
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from collections import defaultdict
from datetime import datetime, timedelta
import time
import json
import threading
from typing import Dict, List, Optional, Tuple
from jose import jwt
from app.core.config import settings
from app.services.rate_limit_config import rate_limit_config


class RateLimitTier:
    """限流层级"""

    GLOBAL = "global"
    IP = "ip"
    USER = "user"
    ENDPOINT = "endpoint"


class RateLimiter:
    """
    内存中的速率限制器

    支持多级限流：全局 → IP → 用户 → 端点
    注意：生产环境建议使用 Redis 实现分布式限流
    """

    def __init__(self):
        self._history: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self._config = rate_limit_config

        self.endpoint_limits = {
            "/api/v1/login": (5, 60),
            "/api/v1/register": (10, 60),
            "/api/v1/refresh": (10, 60),
            "/api/v1/files/upload": (20, 60),
            "/api/v1/code": (60, 60),
            "/api/v1/generate": (60, 60),
            "/api/v1/pptx": (60, 60),
            "/api/v1/ai_agent": (10, 60),
            "/api/v1/aicloud": (10, 60),
            "/api/v1/workflow": (10, 60),
            "default": (60, 60),
        }

    def _cleanup_old_records(self, key: str, window_start: float):
        """清理过期记录（需要持有锁）"""
        self._history[key] = [
            ts for ts in self._history[key]
            if ts > window_start
        ]
        if not self._history[key]:
            del self._history[key]

    def _get_key_count(self, key: str, window_seconds: int) -> int:
        """获取键在窗口内的请求数"""
        current_time = time.time()
        window_start = current_time - window_seconds
        return len([ts for ts in self._history[key] if ts > window_start])

    def check_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int
    ) -> Tuple[bool, int, int]:
        """
        检查限流（线程安全）

        Returns:
            Tuple[是否超限, 剩余请求数, 窗口秒数]
        """
        current_time = time.time()
        window_start = current_time - window_seconds

        with self._lock:
            self._cleanup_old_records(key, window_start)

            request_count = len(self._history[key])
            remaining = max(0, limit - request_count)

            if request_count >= limit:
                return (True, 0, window_seconds)

            self._history[key].append(current_time)
            return (False, remaining - 1, window_seconds)

    def check_multi_tier(
        self,
        ip: str,
        user_id: Optional[str],
        endpoint: str
    ) -> Tuple[bool, str, int, int]:
        """
        多级限流检查

        检查顺序：全局 → IP → 用户 → 端点

        Returns:
            Tuple[是否超限, 触发的层级, 限制数, 窗口秒数]
        """
        if not self._config.enabled:
            return (False, "", 0, 0)

        current_time = time.time()

        global_limit, global_window = self._config.global_limit
        ip_limit, ip_window = self._config.ip_limit
        user_limit, user_window = self._config.user_limit
        endpoint_limit, endpoint_window = self._config.get_endpoint_rule(endpoint)

        global_key = f"global:{int(current_time / global_window)}"
        ip_key = f"ip:{ip}:{int(current_time / ip_window)}"
        user_key = f"user:{user_id}:{int(current_time / user_window)}" if user_id else None
        endpoint_key = f"ep:{endpoint}:{int(current_time / endpoint_window)}"

        with self._lock:
            self._cleanup_old_records(global_key, current_time - global_window)
            self._cleanup_old_records(ip_key, current_time - ip_window)
            if user_key:
                self._cleanup_old_records(user_key, current_time - user_window)
            self._cleanup_old_records(endpoint_key, current_time - endpoint_window)

            global_count = len(self._history[global_key])
            ip_count = len(self._history[ip_key])
            user_count = len(self._history[user_key]) if user_key else 0
            endpoint_count = len(self._history[endpoint_key])

            if global_count >= global_limit:
                return (True, RateLimitTier.GLOBAL, global_limit, global_window)
            if ip_count >= ip_limit:
                return (True, RateLimitTier.IP, ip_limit, ip_window)
            if user_id and user_count >= user_limit:
                return (True, RateLimitTier.USER, user_limit, user_window)
            if endpoint_count >= endpoint_limit:
                return (True, RateLimitTier.ENDPOINT, endpoint_limit, endpoint_window)

            self._history[global_key].append(current_time)
            self._history[ip_key].append(current_time)
            if user_key:
                self._history[user_key].append(current_time)
            self._history[endpoint_key].append(current_time)

            return (False, "", 0, 0)

    def is_rate_limited(self, client_id: str, endpoint: str) -> bool:
        """
        检查请求是否超过限制（线程安全，兼容旧接口）

        Returns:
            bool: 是否应该限制（True 表示超限）
        """
        current_time = time.time()

        limit_config = self.endpoint_limits.get(
            endpoint,
            self.endpoint_limits["default"]
        )
        max_requests, window_seconds = limit_config

        window_start = current_time - window_seconds

        with self._lock:
            self._cleanup_old_records(client_id, window_start)

            request_count = len(self._history[client_id])
            if request_count >= max_requests:
                return True

            self._history[client_id].append(current_time)
            return False

    def get_client_id(self, request: Request) -> str:
        """
        获取客户端唯一标识

        优先级：用户 ID > IP 地址
        """
        client_ip = request.client.host

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header[7:]
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                user_id = payload.get("sub")
                if user_id:
                    return f"user:{user_id}"
            except Exception:
                pass

        return f"ip:{client_ip}"

    def get_client_identifiers(self, request: Request) -> Tuple[str, Optional[str]]:
        """
        获取客户端标识信息

        Returns:
            Tuple[IP, 用户ID或None]
        """
        client_ip = request.client.host
        user_id = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                token = auth_header[7:]
                payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                user_id = payload.get("sub")
            except Exception:
                pass

        return (client_ip, user_id)

    def get_stats(self) -> Dict:
        """获取限流统计信息"""
        current_time = time.time()
        with self._lock:
            return {
                "enabled": self._config.enabled,
                "total_keys": len(self._history),
                "config": self._config.to_dict()
            }


rate_limiter = RateLimiter()


class RateLimitMiddleware:
    """速率限制中间件（纯 ASGI 实现）

    为什么不用 BaseHTTPMiddleware:
    - 同 RequestLoggingMiddleware，避免 cancel scope 传播到 DB 层
    """

    SKIP_PATHS = {
        "/health",
        "/ready",
        "/live",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
        "/api/v1/health",
        "/api/v1/health/ready",
        "/api/v1/health/live",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        import os
        if os.getenv("ENV") == "testing":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path in self.SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        if not rate_limit_config.enabled:
            await self.app(scope, receive, send)
            return

        # 解析 IP / 用户 ID（从 headers 中提取 Authorization）
        client = scope.get("client")
        ip = client[0] if client else ""
        user_id = _extract_user_id_from_scope(scope)

        endpoint = path

        is_limited, tier, limit, window = rate_limiter.check_multi_tier(
            ip, user_id, endpoint
        )

        if is_limited:
            tier_names = {
                RateLimitTier.GLOBAL: "全局",
                RateLimitTier.IP: "IP",
                RateLimitTier.USER: "用户",
                RateLimitTier.ENDPOINT: "端点",
            }
            payload = {
                "error": "请求过于频繁",
                "detail": f"{tier_names.get(tier, tier)}限制：{limit}次/{window}秒",
                "retry_after": window // 2,
                "tier": tier,
            }
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            await send({
                "type": "http.response.start",
                "status": status.HTTP_429_TOO_MANY_REQUESTS,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"content-length", str(len(body)).encode()),
                    (b"retry-after", str(window).encode()),
                    (b"x-ratelimit-limit", str(limit).encode()),
                    (b"x-ratelimit-remaining", b"0"),
                    (b"x-ratelimit-tier", tier.encode()),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
                "more_body": False,
            })
            return

        # 包装 send 注入剩余配额响应头
        endpoint_limit, endpoint_window = rate_limit_config.get_endpoint_rule(endpoint)
        endpoint_key = f"ep:{endpoint}:{int(time.time() / endpoint_window)}"
        with rate_limiter._lock:
            count = len(rate_limiter._history.get(endpoint_key, []))
        remaining = max(0, endpoint_limit - count)

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-ratelimit-limit", str(endpoint_limit).encode()))
                headers.append((b"x-ratelimit-remaining", str(remaining).encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


def _extract_user_id_from_scope(scope) -> Optional[str]:
    """从 ASGI scope headers 中提取 JWT sub"""
    raw_headers = scope.get("headers", [])
    for k, v in raw_headers:
        if k == b"authorization":
            auth_header = v.decode("latin-1")
            if auth_header.startswith("Bearer "):
                try:
                    token = auth_header[7:]
                    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
                    sub = payload.get("sub")
                    if sub:
                        return sub
                except Exception:
                    return None
    return None


class LoginAttemptTracker:
    """跟踪登录失败尝试（线程安全）"""

    def __init__(self):
        self.failed_attempts: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
        self.max_attempts = 5
        self.window_seconds = 300

    def record_failed_attempt(self, identifier: str):
        """记录失败尝试（线程安全）"""
        current_time = time.time()
        with self._lock:
            self.failed_attempts[identifier].append(current_time)

    def is_blocked(self, identifier: str) -> bool:
        """检查是否被封锁（线程安全）"""
        current_time = time.time()
        window_start = current_time - self.window_seconds

        with self._lock:
            self.failed_attempts[identifier] = [
                ts for ts in self.failed_attempts[identifier]
                if ts > window_start
            ]
            return len(self.failed_attempts[identifier]) >= self.max_attempts

    def clear_failed_attempts(self, identifier: str):
        """登录成功后清除失败记录（线程安全）"""
        with self._lock:
            self.failed_attempts[identifier] = []


login_tracker = LoginAttemptTracker()


def check_login_rate_limit(identifier: str) -> bool:
    """
    检查登录尝试限制

    测试环境中跳过限制（ENV=testing）

    Args:
        identifier: 用户名或 IP

    Returns:
        bool: 是否允许尝试（True 表示允许）
    """
    import os
    if os.getenv("ENV") == "testing":
        return True
    if login_tracker.is_blocked(identifier):
        return False
    return True


def record_login_failure(identifier: str):
    """记录登录失败"""
    login_tracker.record_failed_attempt(identifier)


def record_login_success(identifier: str):
    """登录成功后清除记录"""
    login_tracker.clear_failed_attempts(identifier)
