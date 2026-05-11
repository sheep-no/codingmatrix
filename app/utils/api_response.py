"""
统一 API 响应工具

提供标准化的成功、错误和分页响应格式:
- success_response(data, message, status_code)
- error_response(code, message, details, status_code)
- paginated_response(data, total, page, size)

标准响应格式:
成功:
{
    "success": true,
    "data": {...},
    "message": "操作成功",
    "timestamp": "2024-01-01T00:00:00Z"
}

错误:
{
    "success": false,
    "code": "ERROR_CODE",
    "message": "错误描述",
    "details": {...}
}

分页:
{
    "success": true,
    "data": [...],
    "pagination": {
        "total": 100,
        "page": 1,
        "size": 20,
        "pages": 5,
        "has_next": true,
        "has_prev": false
    }
}
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi.responses import JSONResponse

from app.utils.error_codes import ErrorCode


def success_response(
    data: Any = None,
    message: str = "操作成功",
    status_code: int = 200,
) -> JSONResponse:
    """成功响应

    Args:
        data: 响应数据
        message: 成功消息
        status_code: HTTP 状态码

    Returns:
        JSONResponse: 标准化成功响应
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def error_response(
    code: str | ErrorCode = ErrorCode.INTERNAL_ERROR,
    message: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    status_code: Optional[int] = None,
) -> JSONResponse:
    """错误响应

    Args:
        code: 错误码字符串或 ErrorCode 枚举
        message: 错误消息，若为 None 则使用 ErrorCode 默认消息
        details: 错误详情
        status_code: HTTP 状态码，若为 None 则使用 ErrorCode 默认状态码

    Returns:
        JSONResponse: 标准化错误响应
    """
    if isinstance(code, ErrorCode):
        error_code = code.code
        error_message = message or code.message
        error_status = status_code or code.http_status
    else:
        error_code = code
        error_message = message or "请求失败"
        error_status = status_code or 500

    return JSONResponse(
        status_code=error_status,
        content={
            "success": False,
            "code": error_code,
            "message": error_message,
            "details": details or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def paginated_response(
    data: List[Any],
    total: int,
    page: int = 1,
    size: int = 20,
    message: str = "操作成功",
    status_code: int = 200,
) -> JSONResponse:
    """分页响应

    Args:
        data: 当前页数据列表
        total: 总记录数
        page: 当前页码 (从 1 开始)
        size: 每页大小
        message: 成功消息
        status_code: HTTP 状态码

    Returns:
        JSONResponse: 标准化分页响应
    """
    pages = (total + size - 1) // size if total > 0 else 0
    has_next = page < pages
    has_prev = page > 1

    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "message": message,
            "pagination": {
                "total": total,
                "page": page,
                "size": size,
                "pages": pages,
                "has_next": has_next,
                "has_prev": has_prev,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


def cursor_paginated_response(
    data: List[Any],
    next_cursor: Optional[str] = None,
    has_more: bool = False,
    message: str = "操作成功",
    status_code: int = 200,
) -> JSONResponse:
    """游标分页响应

    适用于数据频繁变动或无限滚动场景。

    Args:
        data: 当前页数据列表
        next_cursor: 下一页游标
        has_more: 是否还有更多数据
        message: 成功消息
        status_code: HTTP 状态码

    Returns:
        JSONResponse: 标准化游标分页响应
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": True,
            "data": data,
            "message": message,
            "pagination": {
                "next_cursor": next_cursor,
                "has_more": has_more,
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )
