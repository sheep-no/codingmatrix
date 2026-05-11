"""
功能开关中间件

拦截对已禁用功能模块的请求，返回 503
"""
import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.services.feature_switch import feature_switch_service

logger = logging.getLogger(__name__)


class FeatureSwitchMiddleware(BaseHTTPMiddleware):
    """
    功能开关检查中间件

    拦截对已禁用功能模块的请求，返回 503 Service Unavailable
    """

    PATH_FEATURE_MAP = {
        "/api/v1/aicloud": "aicloud",
        "/api/v1/docker": "docker",
        "/api/v1/project": "project",
        "/api/v1/workflow": "workflow",
    }

    SKIP_PATHS = {
        "/health",
        "/ready",
        "/docs",
        "/openapi.json",
        "/favicon.ico",
    }

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        if path in self.SKIP_PATHS:
            return await call_next(request)

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

                    return JSONResponse(
                        status_code=503,
                        content={
                            "detail": f"{feature_name}已关闭，请联系管理员开启",
                            "code": "FEATURE_DISABLED",
                            "feature": feature
                        }
                    )
                break

        return await call_next(request)
