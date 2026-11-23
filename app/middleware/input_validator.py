"""
输入验证中间件

提供请求输入安全验证：
- SQL 注入检测
- XSS 攻击检测
- 请求体大小限制
- 内容类型验证
"""
import json
import logging
import re

from fastapi import status

from app.core.config import settings
from app.utils.security_audit import log_security_event

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


def _mime_type(content_type: str) -> str:
    """取 MIME 主类型，去掉 charset/boundary 等参数。"""
    return content_type.split(";", 1)[0].strip().lower()


def _is_json_content_type(mime: str) -> bool:
    """JSON 系类型：application/json 以及结构化后缀 +json（如 application/vnd.api+json）。

    用 startswith("application/json") 判定会把 application/jsonp 误当 JSON，
    进而对非 JSON body 返回 400；直接比较 MIME 主类型并识别后缀可同时消除
    误判（jsonp）与漏判（vnd.api+json 被 415 拒绝）。
    """
    return mime == "application/json" or mime.endswith("+json")


def _is_allowed_content_type(content_type: str) -> bool:
    mime = _mime_type(content_type)
    return mime in ALLOWED_CONTENT_TYPES or _is_json_content_type(mime)


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

# AI 提示词字段：这些内容会原样进入模型上下文，用户让模型解释或修复
# `<script>`、`onclick=` 是编程场景的正常输入。XSS 的真正防线是前端渲染层的
# DOMPurify 消毒；中间件对这类字段只记录审计，不拦截。
#
# 作用范围严格限定为 POST /api/v1/chat 与 POST /api/v1/agent 的 prompt 字段
# （Agent 侧字段名为 requirement）。SQL 注入检测、其他字段、其他接口以及
# /api/v1/agent/apikey* 仍按原规则严格拦截。
PROMPT_RELAXED_PATHS = {"/api/v1/chat"}
PROMPT_RELAXED_PREFIXES = {"/api/v1/agent"}
PROMPT_RELAXED_EXCLUDED_PREFIXES = {
    "/api/v1/agent/apikey",
    "/api/v1/agent/apikeys",
}
PROMPT_FIELDS = frozenset({"prompt", "requirement"})


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
    if _mime_type(content_type) == "multipart/form-data":
        return MAX_UPLOAD_BODY_SIZE
    return MAX_BODY_SIZE


def _scan_value(value, relaxed_xss_keys=frozenset(), _is_root=True) -> list:
    """递归扫描 SQL/XSS 内容。

    relaxed_xss_keys 仅作用于根对象的直接字段：AI 提示词里的标签与事件属性
    属于用户要模型处理的代码样本，XSS 交由渲染层消毒，不在入口拦截。
    """
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
            if _is_root and key in relaxed_xss_keys and isinstance(item, str):
                # 提示词字段只跳过 XSS 正则，SQL 注入检测照常执行。
                if _check_sql_injection(item):
                    issues.append("sql_injection")
                continue
            issues.extend(_scan_value(item, _is_root=False))
    elif isinstance(value, (list, tuple)):
        for item in value:
            issues.extend(_scan_value(item, _is_root=False))
    return issues


def _prompt_fields_with_xss(data) -> list:
    """返回根对象中命中 XSS 正则的提示词字段名，用于审计记录。"""
    if not isinstance(data, dict):
        return []
    return [
        field
        for field in PROMPT_FIELDS
        if isinstance(data.get(field), str) and _check_xss(data[field])
    ]


def _is_prompt_relaxed_path(path: str) -> bool:
    """是否为提示词 XSS 放行路径：/api/v1/chat 与 /api/v1/agent（排除 apikey）。"""
    if path in PROMPT_RELAXED_PATHS:
        return True
    if any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in PROMPT_RELAXED_EXCLUDED_PREFIXES
    ):
        return False
    return any(
        path == prefix or path.startswith(prefix + "/")
        for prefix in PROMPT_RELAXED_PREFIXES
    )


async def _audit_prompt_xss_relaxed(path: str, fields: list, ip_address: str) -> None:
    """记录提示词 XSS 特征放行事件，写入安全审计日志。"""
    await log_security_event(
        "prompt_xss_relaxed",
        user_id=None,
        details={
            "path": path,
            "detected_issues": ["xss"],
            "fields": fields,
            "policy": "render_layer_sanitization",
        },
        ip_address=ip_address,
        success=True,
    )


def _client_ip(scope) -> str:
    """取客户端 IP；代理场景优先 X-Forwarded-For 的第一跳。"""
    headers = {
        k.decode("latin-1").lower(): v.decode("latin-1")
        for k, v in scope.get("headers", [])
    }
    forwarded = headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = scope.get("client")
    return client[0] if client else ""


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

        # AI 提示词字段只放宽 XSS 字面拦截，SQL 检测、Content-Type 与体积校验不变。
        # 采用路径段边界匹配，避免 /api/v1/agent-evil 这类前缀碰撞。
        relax_prompt_xss = method == "POST" and _is_prompt_relaxed_path(path)

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

        if content_type_declared and not _is_allowed_content_type(content_type):
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
        if content_type_declared and not _is_json_content_type(_mime_type(content_type)):
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

        if body:
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

            relaxed_keys = PROMPT_FIELDS if relax_prompt_xss else frozenset()
            if data is not None and relaxed_keys:
                # 放行前留痕：记录哪些提示词字段命中 XSS 特征，便于事后审计。
                relaxed_hits = _prompt_fields_with_xss(data)
                if relaxed_hits:
                    logger.warning(
                        "提示词 XSS 特征已放行（渲染层消毒）| path=%s | detected_issues=%s | fields=%s",
                        path,
                        ["xss"],
                        relaxed_hits,
                    )
                    await _audit_prompt_xss_relaxed(path, relaxed_hits, _client_ip(scope))

            try:
                if data is None:
                    issues = []
                elif relaxed_keys:
                    issues = list(set(_scan_value(data, relaxed_keys)))
                else:
                    issues = list(set(_scan_value(data)))
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
                    detail_parts.append(
                        "检测到疑似 SQL 注入内容，请移除引号闭合、UNION SELECT、堆叠语句等片段后重试"
                    )
                if "xss" in issues:
                    detail_parts.append(
                        "检测到疑似 XSS 攻击内容，请移除脚本标签、事件属性或 javascript: 协议后重试"
                    )
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
