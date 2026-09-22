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

from app.core.config import settings

logger = logging.getLogger(__name__)

# 常规请求体（JSON/表单等）上限
MAX_BODY_SIZE = 10 * 1024 * 1024  # 10MB
# 单请求上传上限：与上传端点（app/api/v1/file_upload.py）共用同一配置。
# 若两者不一致，10MB~上传配额之间的整体上传会在中间件被 413 提前拦截（P2-3）。
MAX_UPLOAD_BODY_SIZE = settings.max_upload_size_mb * 1024 * 1024

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


def _parse_content_length(value) -> int:
    """解析 Content-Length；缺失或非数字返回 None，交由读取阶段兜底限流。"""
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _size_limit_for(content_type: str) -> int:
    """按内容类型选择请求体体积上限。

    multipart 上传按文件上传配额放行，其余仍按 10MB 严格限制。
    """
    if content_type.startswith("multipart/form-data"):
        return MAX_UPLOAD_BODY_SIZE
    return MAX_BODY_SIZE


def _scan_value(value) -> list:
    issues = []
    if isinstance(value, str):
        if _check_sql_injection(value):
            issues.append("sql_injection")
        if _check_xss(value):
            issues.append("xss")
    elif isinstance(value, dict):
        # 键同样参与扫描：仅检查 value 会让 `{"<script>...": "clean"}` 这类
        # 键承载的 payload 漏检。
        for key, item in value.items():
            issues.extend(_scan_value(key))
            issues.extend(_scan_value(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            issues.extend(_scan_value(item))
    return issues


async def _read_body_safe(receive, limit: int) -> bytes:
    """从 ASGI receive callable 读取完整 body。

    分块传输无 Content-Length，必须在读取过程中累计大小并及时中断，
    否则客户端可先让服务端缓冲任意数据再收到 413。
    """
    body_chunks = []
    total = 0
    while True:
        message = await receive()
        if message["type"] == "http.request":
            body = message.get("body", b"")
            if body:
                total += len(body)
                if total > limit:
                    return b"__TOO_LARGE__"
                body_chunks.append(body)
            if not message.get("more_body", False):
                break
        elif message["type"] == "http.disconnect":
            break
    return b"".join(body_chunks)


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
        # 缺失 Content-Type 时无法判定类型：白名单校验跳过，但仍按 JSON 尝试扫描，
        # 避免仅去掉一个 header 就绕过注入检测。
        content_type_declared = bool(content_type)

        if content_type_declared and not any(
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
            body_size_limit = _size_limit_for(content_type)
            content_length = headers.get("content-length")
            declared_length = _parse_content_length(content_length)
            if declared_length is not None and declared_length > body_size_limit:
                logger.warning(
                    f"请求体过大 | path={path} | size={content_length}"
                )
                await _send_json_response(
                    send,
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    {
                        "code": "REQUEST_TOO_LARGE",
                        "message": f"请求体过大，最大允许 {body_size_limit // 1024 // 1024}MB",
                        "details": {"max_size_bytes": body_size_limit},
                    },
                )
                return

        # 只有明确声明为 JSON 或未声明类型时才需要读取 body 做内容扫描；
        # 其它已声明的非 JSON 类型直接透传。
        if content_type_declared and not content_type.startswith("application/json"):
            await self.app(scope, receive, send)
            return

        body = await _read_body_safe(receive, _size_limit_for(content_type))
        if body == b"__TOO_LARGE__":
            logger.warning(f"请求体过大 | path={path}")
            await _send_json_response(
                send,
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                {
                    "code": "REQUEST_TOO_LARGE",
                    "message": f"请求体过大，最大允许 {_size_limit_for(content_type) // 1024 // 1024}MB",
                    "details": {"max_size_bytes": _size_limit_for(content_type)},
                },
            )
            return

        if body and not skip_content_scan:
            try:
                data = json.loads(body)
            except RecursionError:
                # 深层嵌套 JSON（远小于体积上限）会让解析栈溢出，需按非法 JSON 处理。
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
            except json.JSONDecodeError:
                if content_type_declared:
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
                # 未声明 Content-Type 且不是 JSON：无法扫描，按原样透传。
                data = None

            try:
                issues = list(set(_scan_value(data))) if data is not None else []
            except RecursionError:
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
