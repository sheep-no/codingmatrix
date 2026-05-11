"""
输入验证中间件

提供请求输入安全验证：
- SQL 注入检测
- XSS 攻击检测
- 请求体大小限制
- 内容类型验证
"""
import re
import json
import logging
from typing import Set
from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB

ALLOWED_CONTENT_TYPES = {
    "application/json",
    "application/x-www-form-urlencoded",
    "multipart/form-data",
    "text/plain",
    "application/octet-stream",
    "image/png",
    "image/jpeg",
    "image/gif",
    "image/webp",
    "text/event-stream",
}

SQL_INJECTION_PATTERNS = [
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION|ALTER|CREATE|EXEC|EXECUTE)\b)",
    r"(--|;|/\*|\*/)",
    r"(\b(OR|AND)\b\s+\d+\s*=\s*\d+)",
    r"(\b(OR|AND)\b\s+['\"]?\w+['\"]?\s*=\s*['\"]?\w+['\"]?)",
    r"(\bUNION\b\s+\b(SELECT|ALL)\b)",
    r"(\'\s*(OR|AND)\s*\')",
    r"(1\s*=\s*1)",
    r"(\'\s*=\s*\')",
]

XSS_PATTERNS = [
    r"<script[^>]*>",
    r"javascript\s*:",
    r"on(load|error|click|mouse|focus|blur|change|submit|key)\s*=",
    r"<iframe[^>]*>",
    r"<object[^>]*>",
    r"<embed[^>]*>",
    r"<form[^>]*>",
    r"<input[^>]*type\s*=\s*[\"']?file[\"']?",
    r"eval\s*\(",
    r"document\.(cookie|write|location)",
    r"window\.(location|open|alert)",
    r"<img[^>]+onerror\s*=",
]

SQL_INJECTION_REGEXES = [re.compile(p, re.IGNORECASE) for p in SQL_INJECTION_PATTERNS]
XSS_REGEXES = [re.compile(p, re.IGNORECASE) for p in XSS_PATTERNS]

SKIP_PATHS = {
    "/health",
    "/ready",
    "/live",
    "/docs",
    "/openapi.json",
    "/favicon.ico",
    "/api/v1/health",
}

# 跳过 SQL/XSS 检查的路径（AI 项目生成需要包含代码描述）
SKIP_SECURITY_CHECK_PATHS = {
    "/api/v1/agent/orchestrate/stream",
    "/api/v1/agent/generate",
    "/api/v1/ai_agent/process",
    "/api/v1/ai_agent/process/stream",
    "/api/v1/ai_agent/react/process",
}


def _check_sql_injection(text: str) -> bool:
    for regex in SQL_INJECTION_REGEXES:
        if regex.search(text):
            return True
    return False


def _check_xss(text: str) -> bool:
    for regex in XSS_REGEXES:
        if regex.search(text):
            return True
    return False


def _scan_value(value) -> list:
    issues = []
    if isinstance(value, str):
        if _check_sql_injection(value):
            issues.append("sql_injection")
        if _check_xss(value):
            issues.append("xss")
    elif isinstance(value, dict):
        for v in value.values():
            issues.extend(_scan_value(v))
    elif isinstance(value, (list, tuple)):
        for item in value:
            issues.extend(_scan_value(item))
    return issues


async def _read_body_safe(request: Request) -> bytes:
    body = await request.body()
    if len(body) > MAX_BODY_SIZE:
        return b"__TOO_LARGE__"
    return body


class InputValidatorMiddleware(BaseHTTPMiddleware):
    """输入验证中间件"""

    async def dispatch(self, request: Request, call_next):
        if request.url.path in SKIP_PATHS:
            return await call_next(request)

        # 跳过 AI 项目生成端点的安全检查（需求描述可能包含代码/SQL 关键词）
        # 使用 startswith 匹配，支持带查询参数或末尾斜杠的变体
        if any(request.url.path.startswith(skip_path) for skip_path in SKIP_SECURITY_CHECK_PATHS):
            return await call_next(request)

        if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
            return await call_next(request)

        content_type = request.headers.get("content-type", "").lower()

        if content_type and not any(
            content_type.startswith(allowed) for allowed in ALLOWED_CONTENT_TYPES
        ):
            logger.warning(
                f"拒绝不支持的内容类型 | path={request.url.path} | content_type={content_type}"
            )
            return JSONResponse(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                content={
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": f"不支持的内容类型: {content_type}",
                    "details": {"allowed": list(ALLOWED_CONTENT_TYPES)},
                },
            )

        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_BODY_SIZE:
                logger.warning(
                    f"请求体过大 | path={request.url.path} | size={content_length}"
                )
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "code": "REQUEST_TOO_LARGE",
                        "message": "请求体过大，最大允许 10MB",
                        "details": {"max_size_bytes": MAX_BODY_SIZE},
                    },
                )

        if content_type.startswith("application/json"):
            body = await _read_body_safe(request)
            if body == b"__TOO_LARGE__":
                logger.warning(f"请求体过大 | path={request.url.path}")
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "code": "REQUEST_TOO_LARGE",
                        "message": "请求体过大，最大允许 10MB",
                        "details": {"max_size_bytes": MAX_BODY_SIZE},
                    },
                )

            if body:
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={
                            "code": "INVALID_JSON",
                            "message": "请求体 JSON 格式无效",
                            "details": {},
                        },
                    )

                issues = list(set(_scan_value(data)))
                if issues:
                    logger.warning(
                        f"输入验证失败 | path={request.url.path} | issues={issues}"
                    )
                    detail_parts = []
                    if "sql_injection" in issues:
                        detail_parts.append("检测到疑似 SQL 注入内容")
                    if "xss" in issues:
                        detail_parts.append("检测到疑似 XSS 攻击内容")
                    return JSONResponse(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        content={
                            "code": "INPUT_VALIDATION_FAILED",
                            "message": "；".join(detail_parts),
                            "details": {"detected_issues": issues},
                        },
                    )

                request._body = body

        return await call_next(request)
