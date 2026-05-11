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
from starlette.middleware.base import BaseHTTPMiddleware

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


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件

    功能:
    - 生成唯一 request_id 并添加到响应头
    - 记录请求开始/结束日志
    - 记录请求方法、路径、状态码、耗时
    """

    def __init__(self, app, logger_name: str = "app.request"):
        super().__init__(app)
        self.logger = get_json_logger(logger_name)

    async def dispatch(self, request: Request, call_next):
        request_id = generate_request_id()
        set_request_context(request_id)

        start_time = time.time()

        self.logger.info(
            "请求开始",
            extra={
                "extra_data": {
                    "method": request.method,
                    "path": request.url.path,
                    "query_params": dict(request.query_params) if request.query_params else None,
                    "client_host": request.client.host if request.client else None,
                }
            },
        )

        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id

            duration_ms = round((time.time() - start_time) * 1000, 2)

            log_level = logging.INFO
            if response.status_code >= 500:
                log_level = logging.ERROR
            elif response.status_code >= 400:
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
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            }

            if log_level == logging.ERROR:
                self.logger.error(JsonFormatter().format(record))
            elif log_level == logging.WARNING:
                self.logger.warning(JsonFormatter().format(record))
            else:
                self.logger.info(JsonFormatter().format(record))

            return response

        except Exception as exc:
            duration_ms = round((time.time() - start_time) * 1000, 2)
            log_error(
                self.logger,
                "请求处理异常",
                exc,
                method=request.method,
                path=request.url.path,
                duration_ms=duration_ms,
            )
            raise
        finally:
            clear_request_context()
