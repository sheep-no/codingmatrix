"""
统一异常处理

提供标准化的错误响应格式和全局异常捕获：
- ValidationError (Pydantic)
- HTTPException (FastAPI)
- SQLAlchemyError
- 未知异常兜底

标准错误格式:
{
    "code": "ERROR_CODE",
    "message": "可读错误描述",
    "details": {}
}
"""
import logging
from typing import Any, Dict
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError, IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi import HTTPException

logger = logging.getLogger(__name__)


def _error_response(
    code: str,
    message: str,
    status_code: int,
    details: Dict[str, Any] | None = None,
    headers: Dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "code": code,
            "message": message,
            "details": details or {},
        },
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        loc = ".".join(str(l) for l in error.get("loc", []))
        errors.append({
            "field": loc,
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        })
    logger.warning(
        f"请求验证失败 | path={request.url.path} | method={request.method} | errors={errors}"
    )
    return _error_response(
        code="VALIDATION_ERROR",
        message="请求参数验证失败",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors},
    )


async def pydantic_validation_exception_handler(
    request: Request, exc: ValidationError
) -> JSONResponse:
    errors = []
    for error in exc.errors():
        loc = ".".join(str(l) for l in error.get("loc", []))
        errors.append({
            "field": loc,
            "message": error.get("msg", ""),
            "type": error.get("type", ""),
        })
    logger.warning(
        f"Pydantic 验证失败 | path={request.url.path} | errors={errors}"
    )
    return _error_response(
        code="VALIDATION_ERROR",
        message="数据验证失败",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        details={"errors": errors},
    )


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        502: "BAD_GATEWAY",
        503: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    logger.warning(
        f"HTTP 异常 | path={request.url.path} | status={exc.status_code} | detail={detail}"
    )
    headers = {}
    if exc.status_code == 429:
        headers["Retry-After"] = "60"
    return _error_response(
        code=code,
        message=detail,
        status_code=exc.status_code,
        details={"path": request.url.path},
        headers=headers if headers else None,
    )


async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    return _error_response(
        code="HTTP_ERROR",
        message=exc.detail,
        status_code=exc.status_code,
        details={"path": request.url.path},
    )


async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    logger.error(f"数据库完整性错误 | path={request.url.path} | error={str(exc.orig)}")
    return _error_response(
        code="DATABASE_INTEGRITY_ERROR",
        message="数据库操作违反约束条件",
        status_code=status.HTTP_409_CONFLICT,
        details={"original_error": str(exc.orig)},
    )


async def operational_error_handler(
    request: Request, exc: OperationalError
) -> JSONResponse:
    logger.error(f"数据库操作错误 | path={request.url.path} | error={str(exc)}")
    return _error_response(
        code="DATABASE_ERROR",
        message="数据库操作失败",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={},
    )


async def sqlalchemy_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.error(f"数据库异常 | path={request.url.path} | error={str(exc)}")
    return _error_response(
        code="DATABASE_ERROR",
        message="数据库操作异常",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={},
    )


async def generic_exception_handler(
    request: Request, exc: Exception
) -> JSONResponse:
    logger.error(
        f"未捕获异常 | path={request.url.path} | method={request.method} | error={str(exc)}",
        exc_info=True,
    )
    return _error_response(
        code="INTERNAL_ERROR",
        message="服务器内部错误",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        details={},
    )


def register_exception_handlers(app):
    """注册所有异常处理器到 FastAPI 应用"""
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(ValidationError, pydantic_validation_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(OperationalError, operational_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
