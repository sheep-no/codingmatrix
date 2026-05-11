"""
测试日志配置服务 (LogConfigService)

测试日志级别动态调整功能
"""
import pytest
import logging
from app.services.log_config import LogConfigService, log_config_service, LogLevel


class TestLogConfigService:
    """日志配置服务测试"""

    def test_singleton_pattern(self):
        """测试单例模式"""
        service1 = LogConfigService()
        service2 = LogConfigService()
        assert service1 is service2

    def test_get_log_level_default(self):
        """测试获取默认日志级别"""
        service = LogConfigService()
        level = service.get_log_level("app")
        assert level == "INFO"

    def test_set_log_level_valid(self):
        """测试设置有效的日志级别"""
        service = LogConfigService()

        result = service.set_log_level("test_logger", "DEBUG")
        assert result is True
        assert service.get_log_level("test_logger") == "DEBUG"

        result = service.set_log_level("test_logger", "WARNING")
        assert result is True
        assert service.get_log_level("test_logger") == "WARNING"

    def test_set_log_level_invalid(self):
        """测试设置无效的日志级别时使用默认值 INFO"""
        service = LogConfigService()
        result = service.set_log_level("test_logger", "INVALID_LEVEL")
        assert result is True
        assert service.get_log_level("test_logger") == "INFO"

    def test_log_level_enum(self):
        """测试日志级别枚举"""
        assert LogLevel.from_string("debug") == LogLevel.DEBUG
        assert LogLevel.from_string("INFO") == LogLevel.INFO
        assert LogLevel.from_string("warning") == LogLevel.WARNING
        assert LogLevel.from_string("ERROR") == LogLevel.ERROR
        assert LogLevel.from_string("CRITICAL") == LogLevel.CRITICAL
        assert LogLevel.from_string("invalid") == LogLevel.INFO  # 默认值

    def test_get_all_levels(self):
        """测试获取所有已配置的日志级别"""
        service = LogConfigService()
        service.set_log_level("logger1", "DEBUG")
        service.set_log_level("logger2", "ERROR")

        levels = service.get_all_levels()
        assert "logger1" in levels
        assert "logger2" in levels
        assert levels["logger1"] == "DEBUG"
        assert levels["logger2"] == "ERROR"

    def test_set_global_level(self):
        """测试设置全局日志级别"""
        service = LogConfigService()

        result = service.set_global_level("WARNING")
        assert result is True
        assert service.get_log_level("") == "WARNING"

    def test_get_config(self):
        """测试获取当前日志配置"""
        service = LogConfigService()
        service.set_log_level("app", "ERROR")

        config = service.get_config()
        assert "log_level" in config
        assert "log_to_file" in config
        assert "log_to_console" in config

    def test_set_file_logging(self):
        """测试文件日志开关"""
        service = LogConfigService()

        service.set_file_logging(False)
        assert service.is_file_logging_enabled() is False

        service.set_file_logging(True)
        assert service.is_file_logging_enabled() is True

    def test_actual_logger_update(self):
        """测试实际 Logger 是否被更新"""
        service = LogConfigService()
        test_logger_name = "test_actual_logger"

        service.set_log_level(test_logger_name, "DEBUG")
        target_logger = logging.getLogger(test_logger_name)
        assert target_logger.level == logging.DEBUG

        service.set_log_level(test_logger_name, "CRITICAL")
        assert target_logger.level == logging.CRITICAL


class TestModuleLevelService:
    """测试模块级单例"""

    def test_module_service_is_singleton(self):
        """测试模块级服务是单例"""
        assert log_config_service is not None
        assert isinstance(log_config_service, LogConfigService)
