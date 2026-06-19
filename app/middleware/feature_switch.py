"""
功能开关中间件

拦截对已禁用功能模块的请求，返回 503
"""
import logging
import json
from fastapi import Request
from fastapi.responses import JSONResponse

from app.services.feature_switch import feature_switch_service

logger = logging.getLogger(__name__)


class FeatureSwitchMiddleware:
    """
    功能开关检查中间件（纯 ASGI 实现）

    拦截对已禁用功能模块的请求，返回 503 Service Unavailable

    为什么不用 BaseHTTPMiddleware:
    - 同 RequestLoggingMiddleware，避免 cancel scope 传播到 DB 层
    """

    PATH_FEATURE_MAP = {
        "/api/v1/aicloud": "aicloud",
        "/api/v1/docker": "docker",
        "/api/v1/agent": "project",
        "/api/v1/workflow": "workflow",
    }

    SKIP_PATHS = {
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
    }

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        if path in self.SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        for path_prefix, feature in self.PATH_FEATURE_MAP.items():
            if path.startswith(path_prefix):
                is_enabled = await feature_switch_service.is_feature_enabled(feature)

                if not is_enabled:
                    feature_name = {
                        "aicloud": "AI Cloud 功能",
                        "docker": "Docker 功能",
                        "project": "项目生成功能",
                        "workflow": "工作流功能",
                    }.get(feature, feature)

                    logger.warning(
                        f"尝试访问已禁用的功能 | path={path} | feature={feature_name}"
                    )

                    payload = {
                        "detail": f"{feature_name}已关闭，请联系管理员开启",
                        "code": "FEATURE_DISABLED",
                        "feature": feature,
                    }
                    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                    await send({
                        "type": "http.response.start",
                        "status": 503,
                        "headers": [
                            (b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    })
                    await send({
                        "type": "http.response.body",
                        "body": body,
                        "more_body": False,
                    })
                    return
                break

        await self.app(scope, receive, send)
