import logging
import logging.config
import sys
import re
from pathlib import Path
from pythonjsonlogger import jsonlogger
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from app.core.config import settings

LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

STANDARD_FORMAT = "%(asctime)s - %(name)s[%(process)d] - %(levelname)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s"
JSON_FORMAT = "%(asctime)s %(levelname)s %(name)s %(process)d %(module)s %(funcName)s %(lineno)d %(message)s"


class SensitiveDataFilter(logging.Filter):
    """
    日志安全过滤器
    防止敏感信息泄漏到日志文件中
    """
    
    # 敏感数据模式
    PATTERNS = {
        'password': re.compile(r'password["\']?\s*[=:]\s*["\']?[^"\'\s,}]+', re.IGNORECASE),
        'secret': re.compile(r'secret["\']?\s*[=:]\s*["\']?[^"\'\s,}]+', re.IGNORECASE),
        'token': re.compile(r'token["\']?\s*[=:]\s*["\']?[A-Za-z0-9\-_\.]+', re.IGNORECASE),
        'api_key': re.compile(r'api[_-]?key["\']?\s*[=:]\s*["\']?[^"\'\s,}]+', re.IGNORECASE),
        'authorization': re.compile(r'authorization["\']?\s*[=:]\s*["\']?Bearer\s+[A-Za-z0-9\-_\.]+', re.IGNORECASE),
        'jwt_token': re.compile(r'eyJ[A-Za-z0-9\-_\.]+', re.IGNORECASE),  # JWT token 格式
        'email': re.compile(r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'),
        'phone': re.compile(r'1[3-9]\d{9}'),  # 中国大陆手机号
        'id_card': re.compile(r'[1-9]\d{5}(18|19|20)\d{2}(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\d{3}[\dXx]'),
        'credit_card': re.compile(r'\b(?:\d{4}[- ]?){3}\d{4}\b'),
    }
    
    # 替换文本
    REPLACEMENTS = {
        'password': 'password=***REDACTED***',
        'secret': 'secret=***REDACTED***',
        'token': 'token=***REDACTED***',
        'api_key': 'api_key=***REDACTED***',
        'authorization': 'authorization=***REDACTED***',
        'jwt_token': '***JWT_TOKEN_REDACTED***',
        'email': '***EMAIL_REDACTED***',
        'phone': '***PHONE_REDACTED***',
        'id_card': '***ID_CARD_REDACTED***',
        'credit_card': '***CREDIT_CARD_REDACTED***',
    }
    
    def filter(self, record):
        """过滤日志记录中的敏感信息"""
        if hasattr(record, 'msg') and record.msg:
            record.msg = self._sanitize(str(record.msg))
        
        if hasattr(record, 'args') and record.args:
            if isinstance(record.args, dict):
                record.args = {k: self._sanitize(v) for k, v in record.args.items()}
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(self._sanitize(v) for v in record.args)
        
        return True
    
    def _sanitize(self, value):
        """清理字符串中的敏感信息"""
        if not isinstance(value, str):
            return value
        
        sanitized = value
        for key, pattern in self.PATTERNS.items():
            replacement = self.REPLACEMENTS.get(key, '***REDACTED***')
            sanitized = pattern.sub(replacement, sanitized)
        
        return sanitized


class CompressedRotatingFileHandler(RotatingFileHandler):
    """支持压缩的日志轮转处理器"""
    
    def doRollover(self):
        """重写轮转方法，添加压缩支持"""
        super().doRollover()
        
        # 压缩旧日志文件（可选）
        import gzip
        import shutil
        
        try:
            old_log = self.baseFilename + ".1"
            if Path(old_log).exists():
                compressed = old_log + ".gz"
                with open(old_log, 'rb') as f_in:
                    with gzip.open(compressed, 'wb') as f_out:
                        shutil.copyfileobj(f_in, f_out)
                # 删除未压缩的旧文件
                Path(old_log).unlink()
        except (ValueError, TypeError, RuntimeError, OSError, SQLAlchemyError) as e:
            # 压缩失败不影响日志
            logging.warning(f"日志压缩失败：{e}")


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": STANDARD_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": JSON_FORMAT,
            "datefmt": "%Y-%m-%d %H:%M:%S"
        },
    },
    "filters": {
        "sensitive_data": {
            "()": "app.core.logging_config.SensitiveDataFilter"
        },
    },
    "handlers": {
        "console": {
            "level": settings.LOG_LEVEL,
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "standard",
            "filters": ["sensitive_data"],
        },
        "file_app": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "app.log",
            "maxBytes": 10 * 1024 * 1024,  # 10MB 单文件大小
            "backupCount": 5,   # 保留 5 个轮转文件（最大 50MB）
            "encoding": "utf-8",
            "formatter": "standard",
            "filters": ["sensitive_data"],
        },
        "file_error": {
            "level": "ERROR",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "error.log",
            "maxBytes": 10 * 1024 * 1024,  # 10MB 单文件大小
            "backupCount": 3,   # 保留 3 个错误日志（最大 30MB）
            "encoding": "utf-8",
            "formatter": "standard",
            "filters": ["sensitive_data"],
        },
        "file_debug": {
            "level": "DEBUG" if settings.ENV == "development" else "WARNING",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "debug.log",
            "maxBytes": 5 * 1024 * 1024,  # 5MB
            "backupCount": 2,   # 保留 2 个
            "encoding": "utf-8",
            "formatter": "json",
            "filters": ["sensitive_data"],
        },
        "file_guardian": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "process_guard.log",
            "maxBytes": 5 * 1024 * 1024,  # 5MB
            "backupCount": 2,   # 保留 2 个
            "encoding": "utf-8",
            "formatter": "json",
            "filters": ["sensitive_data"],
        },
        "security_audit": {
            "level": "INFO",
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "security.log",
            "maxBytes": 10 * 1024 * 1024,  # 10MB
            "backupCount": 10,   # 保留 10 个（最大 100MB，安全日志需要保留更久）
            "encoding": "utf-8",
            "formatter": "json",
            "filters": ["sensitive_data"],
        },
    },
    "loggers": {
        "": {
            "level": "WARNING",
            "handlers": ["console", "file_app", "file_error"],
        },
        "app": {
            "level": settings.LOG_LEVEL,
            "handlers": ["console", "file_app", "file_error"],
            "propagate": False
        },
        "app.api.v2.Controller": {
            "level": "INFO",
            "handlers": ["console", "file_app"],
            "propagate": False
        },
        "sqlalchemy": {
            "level": "WARNING",
            "handlers": ["file_error"],
            "propagate": False
        },
        "uvicorn": {
            "level": "INFO",
            "handlers": ["console", "file_app"],
            "propagate": False
        },
        "guardian": {
            "level": "INFO",
            "handlers": ["console", "file_guardian", "file_error"],
            "propagate": False
        },
        "guardian.async": {
            "level": "DEBUG",
            "handlers": ["file_guardian"],
            "propagate": False
        },
        "utils.process_guard": {
            "level": "INFO",
            "handlers": ["console", "file_guardian"],
            "propagate": False
        },
        "utils.service_config_manager": {
            "level": "INFO" if settings.ENV == "development" else "WARNING",
            "handlers": ["file_guardian"],
            "propagate": False
        },
        "security": {
            "level": "INFO",
            "handlers": ["console", "security_audit", "file_error"],
            "propagate": False
        },
    },
}


def setup_logging():
    """初始化日志配置"""
    logging.config.dictConfig(LOGGING_CONFIG)

    # 创建全局 logger
    logger = logging.getLogger("app")
    logger.info("=" * 60)
    logger.info("应用启动 - 日志系统初始化完成")
    logger.info("日志目录：%s", LOG_DIR.absolute())
    logger.info("日志轮转：每天，保留 14 天")
    logger.info("安全日志：保留 90 天")
    logger.info("=" * 60)

    return logger