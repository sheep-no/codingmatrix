"""
结构化日志 + 请求链路追踪

功能：
- request_id 串联所有日志
- 结构化 JSON 日志输出
- 标准日志格式
"""
import logging
import json
import uuid
import traceback
from datetime import datetime
from contextvars import ContextVar
from typing import Optional, Any, Dict
from functools import wraps

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """获取当前请求的 request_id"""
    return request_id_var.get()


def generate_request_id() -> str:
    """生成新的 request_id"""
    return str(uuid.uuid4())[:16]


class StructuredLogger:
    """
    结构化日志记录器

    自动添加：
    - request_id
    - timestamp
    - logger_name
    - level
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _format_message(self, msg: str, extra: Dict[str, Any] = None) -> Dict:
        """格式化日志消息"""
        data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": "INFO",
            "logger": self.logger.name,
            "message": msg,
        }

        request_id = get_request_id()
        if request_id:
            data["request_id"] = request_id

        if extra:
            data.update(extra)

        return data

    def _log(self, level: int, msg: str, *args, **kwargs):
        """内部日志方法"""
        extra = kwargs.pop("extra", None)
        exc_info = kwargs.pop("exc_info", None)

        if extra:
            formatted = self._format_message(msg, extra)
        else:
            formatted = self._format_message(msg)

        if exc_info:
            formatted["traceback"] = traceback.format_exc()

        self.logger.log(level, json.dumps(formatted))

    def debug(self, msg: str, *args, **kwargs):
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args, **kwargs):
        self._log(logging.INFO, msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs):
        self._log(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs):
        self._log(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args, **kwargs):
        self._log(logging.CRITICAL, msg, *args, **kwargs)


class RequestContextLogger:
    """
    请求上下文日志记录器

    用法：
        logger = RequestContextLogger("app.api")
        logger.info("用户登录", user_id=123, action="login")
    """

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def _build_record(self, msg: str, **kwargs):
        """构建日志记录"""
        record = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": msg,
        }

        request_id = get_request_id()
        if request_id:
            record["request_id"] = request_id

        if kwargs:
            record["context"] = kwargs

        return json.dumps(record)

    def debug(self, msg: str, **kwargs):
        self.logger.debug(self._build_record(msg, **kwargs))

    def info(self, msg: str, **kwargs):
        self.logger.info(self._build_record(msg, **kwargs))

    def warning(self, msg: str, **kwargs):
        self.logger.warning(self._build_record(msg, **kwargs))

    def error(self, msg: str, **kwargs):
        self.logger.error(self._build_record(msg, **kwargs))

    def critical(self, msg: str, **kwargs):
        self.logger.critical(self._build_record(msg, **kwargs))


def log_with_context(logger_name: str = "app"):
    """
    日志上下文装饰器

    用法：
        @log_with_context("app.api")
        async def handler():
            logger.info("处理请求")
    """
    logger = logging.getLogger(logger_name)

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request_id = get_request_id() or generate_request_id()
            token = request_id_var.set(request_id)

            try:
                return await func(*args, **kwargs)
            finally:
                request_id_var.reset(token)

        return wrapper
    return decorator


def setup_request_context(request_id: str):
    """设置请求上下文"""
    request_id_var.set(request_id)


def clear_request_context():
    """清除请求上下文"""
    request_id_var.set(None)
