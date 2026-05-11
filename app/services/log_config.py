"""
日志配置服务

提供动态日志级别控制
"""
import logging
from typing import Dict, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class LogLevel(Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    @classmethod
    def from_string(cls, value: str) -> "LogLevel":
        try:
            return cls(value.upper())
        except ValueError:
            return cls.INFO


class LogConfigService:
    """
    日志配置服务

    支持动态修改日志级别，无需重启应用
    """

    _instance: Optional["LogConfigService"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        self._current_level: Dict[str, str] = {}
        self._log_to_file: bool = True

    def get_log_level(self, logger_name: str = "app") -> str:
        """
        获取指定 logger 的日志级别

        Args:
            logger_name: Logger 名称

        Returns:
            日志级别字符串
        """
        return self._current_level.get(logger_name, "INFO")

    def set_log_level(self, logger_name: str, level: str) -> bool:
        """
        设置指定 logger 的日志级别

        Args:
            logger_name: Logger 名称
            level: 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL)

        Returns:
            是否成功
        """
        try:
            log_level = LogLevel.from_string(level)
            py_level = getattr(logging, log_level.value)

            target_logger = logging.getLogger(logger_name)
            target_logger.setLevel(py_level)

            self._current_level[logger_name] = log_level.value

            logger.info(f"日志级别已更新 | logger={logger_name} | level={log_level.value}")
            return True
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"设置日志级别失败 | logger={logger_name} | level={level} | error={e}")
            return False

    def get_all_levels(self) -> Dict[str, str]:
        """
        获取所有已配置的日志级别

        Returns:
            Logger 名称到级别的映射
        """
        return dict(self._current_level)

    def set_global_level(self, level: str) -> bool:
        """
        设置全局日志级别

        Args:
            level: 日志级别

        Returns:
            是否成功
        """
        try:
            log_level = LogLevel.from_string(level)
            py_level = getattr(logging, log_level.value)

            logging.root.setLevel(py_level)

            self._current_level[""] = log_level.value
            logger.info(f"全局日志级别已更新 | level={log_level.value}")
            return True
        except (ValueError, TypeError, RuntimeError, OSError) as e:
            logger.error(f"设置全局日志级别失败 | level={level} | error={e}")
            return False

    def is_file_logging_enabled(self) -> bool:
        """
        检查是否启用了文件日志

        Returns:
            是否启用
        """
        return self._log_to_file

    def set_file_logging(self, enabled: bool) -> bool:
        """
        启用/禁用文件日志

        Args:
            enabled: 是否启用

        Returns:
            是否成功
        """
        self._log_to_file = enabled
        logger.info(f"文件日志已{'启用' if enabled else '禁用'}")
        return True

    def get_config(self) -> dict:
        """
        获取当前日志配置

        Returns:
            日志配置字典
        """
        return {
            "log_level": self.get_log_level("app"),
            "global_level": self.get_log_level(""),
            "log_to_file": self._log_to_file,
            "log_to_console": True
        }


log_config_service = LogConfigService()
