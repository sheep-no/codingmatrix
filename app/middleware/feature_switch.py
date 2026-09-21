"""
功能开关中间件

拦截对已禁用功能模块的请求，返回 503
"""
import logging
import json

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

    def __init__(self, app):
        self.app = app

    @classmethod
    def _match_feature(cls, path: str) -> str:
        """返回该路径归属的功能名，无归属时返回空串

        按路径段边界匹配：/api/v1/agentfoo 不属于 /api/v1/agent 管辖范围，
        不应因 agent 被关闭而收到 503。
        """
        for path_prefix, feature in cls.PATH_FEATURE_MAP.items():
            if path == path_prefix or path.startswith(path_prefix + "/"):
                return feature
        return ""

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        feature = self._match_feature(path)

        if not feature:
            await self.app(scope, receive, send)
            return

        if await feature_switch_service.is_feature_enabled(feature):
            await self.app(scope, receive, send)
            return

        # 功能名沿用服务侧单一来源，避免两处中文名漂移
        feature_name = feature_switch_service.FEATURE_NAMES.get(feature, feature)
        logger.warning(f"尝试访问已禁用的功能 | path={path} | feature={feature_name}")

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
