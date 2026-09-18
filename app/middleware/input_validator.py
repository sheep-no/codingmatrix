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

# 检测口径：只匹配「注入组合特征」，而非 SQL/JS 单词黑名单。
# 本平台是 AI 代码生成平台，需求文本天然包含 select/create/delete/update/eval 等词，
# 单词级黑名单会把正常业务文本判成攻击（IV1）。
SQL_INJECTION_PATTERNS = [
    # 引号闭合后的布尔注入：' OR 1=1、admin' AND '1'='1
    r"['\"]\s*(or|and)\s+['\"]?\w+['\"]?\s*=\s*['\"]?\w+",
    # 布尔恒等式（含引号或数字形式）
    r"\b\d+\s*=\s*\d+\b",
    r"['\"]\s*=\s*['\"]",
    # UNION [ALL] SELECT
    r"\bunion\b\s+(all\s+)?\bselect\b",
    # 堆叠语句：'; DROP / '; DELETE / '; INSERT ...
    r"['\"]\s*;\s*(drop|delete|insert|update|select|union|alter|truncate|exec|execute)\b",
    r";\s*(drop|truncate)\b",
    # SQL 行注释或块注释（-- 后必须紧跟空白，避免命中 well--known）
    r"--\s",
    r"/\*[\s\S]*?\*/",
    # 引号内闭合注入：' OR '、' AND '
    r"['\"]\s*(or|and)\s*['\"]",
]

# XSS 只保留明确的标签/协议/事件属性 payload，移除 eval()、document.* 这类
# 代码语义词汇（代码生成/解释场景的正常输入，见 IV1）。
XSS_PATTERNS = [
    r"<\s*script",
    r"<\s*/\s*script",
    r"javascript\s*:",
    r"\bon(error|load|click|mouse\w*|focus|blur|change|submit|key\w*)\s*=",
    r"<\s*iframe",
    r"<\s*object",
    r"<\s*embed",
    r"<\s*form",
    r"<\s*input[^>]*type\s*=\s*[\"']?file[\"']?",
    r"<\s*img[^>]+onerror\s*=",
    r"<\s*svg[^>]+onload\s*=",
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
    "/api/v1/agent/orchestrate",
    "/api/v1/agent/generate",
    "/api/v1/agent/modify",
    "/api/v1/ai-agent/orchestrate",
    "/api/v1/ai-agent/generate",
    "/api/v1/ai-agent/modify",
    "/api/v1/ai-agent/orchestrate/stream",
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


async def _read_body_safe(receive) -> bytes:
    """从 ASGI receive callable 读取完整 body"""
    body_chunks = []
    while True:
        message = await receive()
        if message["type"] == "http.request":
            body = message.get("body", b"")
            if body:
                body_chunks.append(body)
            if not message.get("more_body", False):
                break
        elif message["type"] == "http.disconnect":
            break
    body = b"".join(body_chunks)
    if len(body) > MAX_BODY_SIZE:
        return b"__TOO_LARGE__"
    return body


class InputValidatorMiddleware:
    """输入验证中间件（纯 ASGI 实现）

    为什么不用 BaseHTTPMiddleware:
    - 同 RequestLoggingMiddleware，避免 cancel scope 传播到 DB 层
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "")

        if path in SKIP_PATHS:
            await self.app(scope, receive, send)
            return

        # AI 主链路只跳过 SQL/XSS 内容扫描，仍必须通过 Content-Type 与请求体大小校验。
        # 采用路径段边界匹配，避免 /api/v1/agent/generate-evil 这类前缀碰撞。
        skip_content_scan = any(
            path == p or path.startswith(p + "/")
            for p in SKIP_SECURITY_CHECK_PATHS
        )

        if method not in ("POST", "PUT", "PATCH", "DELETE"):
            await self.app(scope, receive, send)
            return

        # 解析 headers (ASGI 中是 bytes list of tuples)
        raw_headers = scope.get("headers", [])
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in raw_headers}
        content_type = headers.get("content-type", "").lower()

        if content_type and not any(
            content_type.startswith(allowed) for allowed in ALLOWED_CONTENT_TYPES
        ):
            logger.warning(
                f"拒绝不支持的内容类型 | path={path} | content_type={content_type}"
            )
            await _send_json_response(
                send,
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                {
                    "code": "UNSUPPORTED_MEDIA_TYPE",
                    "message": f"不支持的内容类型: {content_type}",
                    "details": {"allowed": list(ALLOWED_CONTENT_TYPES)},
                },
            )
            return

        if method in ("POST", "PUT", "PATCH"):
            content_length = headers.get("content-length")
            if content_length and int(content_length) > MAX_BODY_SIZE:
                logger.warning(
                    f"请求体过大 | path={path} | size={content_length}"
                )
                await _send_json_response(
                    send,
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    {
                        "code": "REQUEST_TOO_LARGE",
                        "message": "请求体过大，最大允许 10MB",
                        "details": {"max_size_bytes": MAX_BODY_SIZE},
                    },
                )
                return

        if not content_type.startswith("application/json"):
            await self.app(scope, receive, send)
            return

        body = await _read_body_safe(receive)
        if body == b"__TOO_LARGE__":
            logger.warning(f"请求体过大 | path={path}")
            await _send_json_response(
                send,
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                {
                    "code": "REQUEST_TOO_LARGE",
                    "message": "请求体过大，最大允许 10MB",
                    "details": {"max_size_bytes": MAX_BODY_SIZE},
                },
            )
            return

        if body and not skip_content_scan:
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                await _send_json_response(
                    send,
                    status.HTTP_400_BAD_REQUEST,
                    {
                        "code": "INVALID_JSON",
                        "message": "请求体 JSON 格式无效",
                        "details": {},
                    },
                )
                return

            issues = list(set(_scan_value(data)))
            if issues:
                logger.warning(
                    f"输入验证失败 | path={path} | issues={issues}"
                )
                detail_parts = []
                if "sql_injection" in issues:
                    detail_parts.append("检测到疑似 SQL 注入内容")
                if "xss" in issues:
                    detail_parts.append("检测到疑似 XSS 攻击内容")
                await _send_json_response(
                    send,
                    status.HTTP_400_BAD_REQUEST,
                    {
                        "code": "INPUT_VALIDATION_FAILED",
                        "message": "；".join(detail_parts),
                        "details": {"detected_issues": issues},
                    },
                )
                return

        # 把读到的 body 重新塞回 receive，使下游能再次读取
        sent = False
        body_sent = False

        async def receive_replay():
            nonlocal sent, body_sent
            if not body_sent:
                body_sent = True
                return {
                    "type": "http.request",
                    "body": body,
                    "more_body": False,
                }
            # 下游可能还需要 receive 别的消息（如 disconnect）
            # 透传真实 receive
            return await _passthrough_receive(receive, sent_state=lambda: sent)

        await self.app(scope, receive_replay, send)


async def _passthrough_receive(receive, sent_state):
    """透传 receive 调用，下游真正读 body 后才转发"""
    # 此函数保留扩展位；当前实现中 body_sent=True 后下游 receive 会被 FastAPI
    # 用于等待 http.disconnect。我们直接转发原 receive 即可。
    return await receive()


async def _send_json_response(send, status_code: int, body: dict):
    """直接通过 ASGI send 发送 JSON 响应"""
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status_code,
        "headers": [
            (b"content-type", b"application/json; charset=utf-8"),
            (b"content-length", str(len(payload)).encode()),
        ],
    })
    await send({
        "type": "http.response.body",
        "body": payload,
        "more_body": False,
    })
