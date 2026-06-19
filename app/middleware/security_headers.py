"""
安全响应头中间件
防止常见 Web 攻击 (XSS, Clickjacking, MIME sniffing 等)

纯 ASGI 实现，避免 BaseHTTPMiddleware 的 cancel scope 传播
"""
import os


def _csp_for_path(path: str) -> str:
    """根据路径返回合适的 CSP 策略"""
    if path.startswith("/api/docs") or path.startswith("/api/redoc") or path.startswith("/api/openapi"):
        return (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' data: https://cdn.jsdelivr.net; "
            "connect-src 'self' https: wss: ws:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
    return (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "font-src 'self' data:; "
        "connect-src 'self' https: wss: ws:; "
        "frame-ancestors 'none'; "
        "base-uri 'self'; "
        "form-action 'self'"
    )


def _build_security_headers(path: str) -> list:
    """构造所有安全响应头 (ASGI bytes list)"""
    headers = [
        (b"content-security-policy", _csp_for_path(path).encode()),
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"x-xss-protection", b"1; mode=block"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", (
            b"accelerometer=(), "
            b"camera=(), "
            b"geolocation=(), "
            b"gyroscope=(), "
            b"magnetometer=(), "
            b"microphone=(), "
            b"payment=(), "
            b"usb=()"
        )),
        (b"x-permitted-cross-domain-policies", b"none"),
        (b"cross-origin-opener-policy", b"same-origin"),
    ]
    if path.startswith("/api/"):
        headers.append((b"cache-control", b"no-store, no-cache, must-revalidate, private"))
        headers.append((b"pragma", b"no-cache"))
        headers.append((b"expires", b"0"))
    if not (path.startswith("/api/docs") or path.startswith("/api/redoc")):
        headers.append((b"cross-origin-embedder-policy", b"require-corp"))
    return headers


class SecurityHeadersMiddleware:
    """添加安全响应头的中间件（纯 ASGI 实现）"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        sec_headers = _build_security_headers(path)
        sent = False

        async def send_wrapper(message):
            nonlocal sent
            if message["type"] == "http.response.start" and not sent:
                sent = True
                existing = list(message.get("headers", []))
                # 去除可能由下游重复设置的安全头
                sec_keys = {k for k, _ in sec_headers}
                existing = [(k, v) for k, v in existing if k not in sec_keys]
                message["headers"] = existing + sec_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)
