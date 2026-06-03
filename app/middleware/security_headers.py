"""
安全响应头中间件
防止常见 Web 攻击 (XSS, Clickjacking, MIME sniffing 等)
"""
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response
import os


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """添加安全响应头的中间件"""
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        path = request.url.path
        
        # Swagger UI / ReDoc 需要加载 CDN 资源，使用宽松 CSP
        if path.startswith("/api/docs") or path.startswith("/api/redoc") or path.startswith("/api/openapi"):
            csp_policy = (
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
        else:
            csp_policy = (
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
        response.headers["Content-Security-Policy"] = csp_policy
        
        # X-Content-Type-Options
        # 防止 MIME 类型嗅探攻击
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # X-Frame-Options
        # 防止点击劫持攻击
        response.headers["X-Frame-Options"] = "DENY"
        
        # X-XSS-Protection
        # 启用浏览器 XSS 过滤器 (老旧浏览器)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Referrer-Policy
        # 控制 Referrer 信息泄漏
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Permissions-Policy (原 Feature-Policy)
        # 限制浏览器功能使用
        response.headers["Permissions-Policy"] = (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        )
        
        # X-Permitted-Cross-Domain-Policies
        # 限制 Adobe Flash 和 PDF 的跨域策略
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        
        # Cache-Control (针对 API 响应)
        # 防止敏感数据被缓存
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        
        # Cross-Origin-Opener-Policy
        # 防止跨源信息泄漏
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        
        # Cross-Origin-Embedder-Policy
        # docs/redoc 页面需要加载外部资源，跳过 COEP
        if not (path.startswith("/api/docs") or path.startswith("/api/redoc")):
            response.headers["Cross-Origin-Embedder-Policy"] = "require-corp"
        
        return response


# 使用示例（在 main.py 中注册）
"""
from app.middleware.security_headers import SecurityHeadersMiddleware

app.add_middleware(SecurityHeadersMiddleware)
"""
