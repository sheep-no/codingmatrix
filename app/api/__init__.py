"""
API 版本管理

提供 API 版本路由注册和废弃标记功能:
- APIRouter with version prefix
- deprecation_header decorator
- version_middleware

API 版本策略:
- URL 路径版本化: /api/v1/, /api/v2/
- 支持废弃标记 (Deprecation header)
- 支持版本迁移提示
"""
from functools import wraps
from typing import Callable, Optional

from fastapi import APIRouter, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# 当前 API 主版本
API_VERSION_PREFIX = "/api"
LATEST_VERSION = "v2"

# 版本路由映射
VERSION_ROUTERS = {}


def get_version_router(version: str, **kwargs) -> APIRouter:
    """获取或创建指定版本的路由器

    Args:
        version: 版本号 (如 "v1", "v2")
        **kwargs: 传递给 APIRouter 的其他参数

    Returns:
        APIRouter: 带版本前缀的路由器
    """
    if version not in VERSION_ROUTERS:
        prefix = f"{API_VERSION_PREFIX}/{version}"
        VERSION_ROUTERS[version] = APIRouter(prefix=prefix, **kwargs)
    return VERSION_ROUTERS[version]


def include_all_version_routers(app) -> None:
    """将所有版本路由器注册到 FastAPI 应用

    Args:
        app: FastAPI 应用实例
    """
    for version, router in VERSION_ROUTERS.items():
        app.include_router(router)


def deprecated(
    since_version: str,
    removal_version: Optional[str] = None,
    alternative: Optional[str] = None,
    message: Optional[str] = None,
) -> Callable:
    """标记 API 端点为已废弃

    Args:
        since_version: 从哪个版本开始废弃
        removal_version: 预计移除版本
        alternative: 推荐替代方案
        message: 自定义废弃消息

    Returns:
        Callable: 装饰器
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            response: Optional[Response] = None

            # 如果原函数返回 Response，添加废弃头
            result = await func(*args, **kwargs)
            if isinstance(result, Response):
                response = result
            elif isinstance(result, tuple) and len(result) >= 1:
                if isinstance(result[0], Response):
                    response = result[0]

            if response is None:
                from fastapi.responses import JSONResponse

                response = JSONResponse(content=result) if not isinstance(result, Response) else result

            response.headers["Deprecation"] = f"version={since_version}"
            if removal_version:
                response.headers["Sunset"] = removal_version
            if alternative:
                response.headers["Link"] = f'<{alternative}>; rel="successor-version"'

            return result

        wrapper.__deprecated__ = True  # type: ignore
        wrapper.__deprecation_info__ = {  # type: ignore
            "since_version": since_version,
            "removal_version": removal_version,
            "alternative": alternative,
            "message": message or f"此接口已从 {since_version} 版本开始废弃",
        }
        return wrapper

    return decorator


class VersionMiddleware(BaseHTTPMiddleware):
    """API 版本中间件

    功能:
    - 添加当前版本头 X-API-Version
    - 检测废弃 API 调用并记录日志
    - 支持版本协商
    """

    def __init__(self, app, current_version: str = LATEST_VERSION):
        super().__init__(app)
        self.current_version = current_version

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # 添加版本头
        response.headers["X-API-Version"] = self.current_version

        # 检查请求路径中的版本
        path = request.url.path
        if "/api/v" in path:
            version = path.split("/api/")[1].split("/")[0]
            if version != self.current_version:
                response.headers["X-API-Current-Version"] = self.current_version
                response.headers["X-API-Deprecation-Notice"] = (
                    f"API version {version} is deprecated, please upgrade to {self.current_version}"
                )

        return response


def create_versioned_app_setup(app) -> None:
    """设置版本化应用

    Args:
        app: FastAPI 应用实例
    """
    # 添加版本中间件
    app.add_middleware(VersionMiddleware, current_version=LATEST_VERSION)

    # 注册所有版本路由器
    include_all_version_routers(app)
