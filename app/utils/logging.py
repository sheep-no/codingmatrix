"""
结构化日志工具

功能:
- JSON 格式日志输出
- 包含: timestamp, level, service, message, request_id, user_id, duration_ms
- 错误日志包含堆栈跟踪
- 请求日志中间件
"""
import logging
import json
import uuid
import time
import traceback
from datetime import datetime, timezone
from contextvars import ContextVar
from typing import Optional, Any, Dict
from pathlib import Path

from fastapi import Request, Response

# 纯 ASGI 中间件不再依赖 starlette.middleware.base.BaseHTTPMiddleware

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)

SERVICE_NAME = "ai-backend"


def generate_request_id() -> str:
    """生成唯一的 request_id"""
    return str(uuid.uuid4())[:16]


def get_request_id() -> Optional[str]:
    """获取当前请求的 request_id"""
    return request_id_var.get()


def get_user_id() -> Optional[str]:
    """获取当前请求的 user_id"""
    return user_id_var.get()


def set_request_context(request_id: str, user_id: Optional[str] = None):
    """设置请求上下文"""
    request_id_var.set(request_id)
    if user_id:
        user_id_var.set(user_id)


def clear_request_context():
    """清除请求上下文"""
    request_id_var.set(None)
    user_id_var.set(None)


class JsonFormatter(logging.Formatter):
    """JSON 格式日志格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": SERVICE_NAME,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id

        user_id = get_user_id()
        if user_id:
            log_data["user_id"] = user_id

        if record.exc_info and record.exc_info[0] is not None:
            log_data["traceback"] = self.formatException(record.exc_info)

        if hasattr(record, "duration_ms"):
            log_data["duration_ms"] = record.duration_ms

        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        return json.dumps(log_data, ensure_ascii=False, default=str)


def get_json_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    """获取 JSON 格式 logger"""
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(level)
    return logger


def log_error(logger: logging.Logger, message: str, exc: Exception, **kwargs):
    """记录错误日志，包含堆栈跟踪"""
    extra = {
        "error_type": type(exc).__name__,
        "error_message": str(exc),
        "traceback": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }
    extra.update(kwargs)
    record = logging.LogRecord(
        name=logger.name,
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg=message,
        args=(),
        exc_info=None,
    )
    record.extra_data = extra
    formatter = JsonFormatter()
    logger.error(formatter.format(record))


class RequestLoggingMiddleware:
    """请求日志中间件（纯 ASGI 实现）

    功能:
    - 生成唯一 request_id 并添加到响应头
    - 记录请求开始/结束日志
    - 记录请求方法、路径、状态码、耗时

    为什么不用 BaseHTTPMiddleware:
    - BaseHTTPMiddleware 在内部使用 anyio TaskGroup 包装 call_next
    - 客户端断开时 cancel scope 传播到下游所有 await
    - 导致 SQLAlchemy async session.close() 中的 await terminate() 被取消
    - 连接无法归还到池，触发 _finalize_fairy GC 警告
    - 纯 ASGI 直接 await self.app()，不引入 TaskGroup 包装层
    """

    def __init__(self, app, logger_name: str = "app.request"):
        self.app = app
        self.logger = get_json_logger(logger_name)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = generate_request_id()
        set_request_context(request_id)

        start_time = time.time()
        status_code = 500
        method = scope.get("method", "")
        path = scope.get("path", "")
        query_string = scope.get("query_string", b"")
        client = scope.get("client")
        client_host = client[0] if client else None

        self.logger.info(
            "请求开始",
            extra={
                "extra_data": {
                    "method": method,
                    "path": path,
                    "query_params": _parse_query(query_string),
                    "client_host": client_host,
                }
            },
        )

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            log_error(
                self.logger,
                "请求处理异常",
                exc,
                method=method,
                path=path,
                duration_ms=duration_ms,
            )
            raise
        finally:
            duration_ms = round((time.time() - start_time) * 1000, 2)

            log_level = logging.INFO
            if status_code >= 500:
                log_level = logging.ERROR
            elif status_code >= 400:
                log_level = logging.WARNING

            record = logging.LogRecord(
                name=self.logger.name,
                level=log_level,
                pathname="",
                lineno=0,
                msg="请求结束",
                args=(),
                exc_info=None,
            )
            record.duration_ms = duration_ms
            record.extra_data = {
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }

            if log_level == logging.ERROR:
                self.logger.error(JsonFormatter().format(record))
            elif log_level == logging.WARNING:
                self.logger.warning(JsonFormatter().format(record))
            else:
                self.logger.info(JsonFormatter().format(record))

            clear_request_context()


def _parse_query(query_string: bytes) -> Optional[dict]:
    """解析 ASGI scope 中的 query_string 为 dict"""
    if not query_string:
        return None
    from urllib.parse import parse_qs
    parsed = parse_qs(query_string.decode("utf-8", errors="replace"))
    return {k: v[0] if len(v) == 1 else v for k, v in parsed.items()}
