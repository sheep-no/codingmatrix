"""
Phase 4 优化功能测试
"""
import pytest
from fastapi.testclient import TestClient
from datetime import datetime


class TestHealthCheck:
    """测试健康检查端点"""
    
    def test_health_check_router_import(self):
        """测试健康检查路由可导入"""
        from app.api.v1.health import router
        assert router is not None
        
        # 检查路由是否正确定义
        routes = [r.path for r in router.routes]
        assert "/api/v1/health" in routes or "/health" in routes
    
    def test_health_check_functions_exist(self):
        """测试健康检查函数存在"""
        from app.api.v1.health import health_check, readiness_check, liveness_check
        assert health_check is not None
        assert readiness_check is not None
        assert liveness_check is not None


class TestRetryMechanism:
    """测试重试机制"""
    
    def test_retry_decorator_import(self):
        """测试重试装饰器可导入"""
        from app.utils.retry import retry_on_failure, retry_api_call, retry_db_operation
        assert retry_on_failure is not None
        assert retry_api_call is not None
        assert retry_db_operation is not None
    
    def test_retry_decorator_parameters(self):
        """测试重试装饰器参数"""
        from app.utils.retry import retry_on_failure
        
        decorator = retry_on_failure(
            max_attempts=3,
            min_wait=1.0,
            max_wait=10.0
        )
        assert decorator is not None


class TestPerformanceMonitor:
    """测试性能监控"""
    
    def test_performance_middleware_import(self):
        """测试性能监控中间件可导入"""
        from app.utils.performance_monitor import (
            PerformanceMonitorMiddleware,
            setup_performance_monitoring,
            track_performance
        )
        assert PerformanceMonitorMiddleware is not None
        assert setup_performance_monitoring is not None
        assert track_performance is not None
    
    def test_performance_middleware_in_app(self):
        """测试应用已添加性能监控中间件"""
        from app.main import app
        
        # 检查中间件是否已注册
        middleware_names = [
            m.cls.__name__ if hasattr(m, 'cls') else str(m)
            for m in app.user_middleware
        ]
        assert any('PerformanceMonitorMiddleware' in str(m) for m in middleware_names)


class TestLoggingRotation:
    """测试日志轮转配置"""
    
    def test_logging_config_exists(self):
        """测试日志配置存在"""
        from app.core.logging_config import LOGGING_CONFIG
        assert LOGGING_CONFIG is not None
        assert "handlers" in LOGGING_CONFIG
    
    def test_timed_rotating_handler_configured(self):
        """测试定时轮转处理器已配置"""
        from app.core.logging_config import LOGGING_CONFIG
        
        handlers = LOGGING_CONFIG["handlers"]
        assert "file_app" in handlers
        assert handlers["file_app"]["class"] == "logging.handlers.TimedRotatingFileHandler"
        assert handlers["file_app"]["when"] == "midnight"
        assert handlers["file_app"]["backupCount"] == 14
    
    def test_security_audit_logger_configured(self):
        """测试安全审计日志配置"""
        from app.core.logging_config import LOGGING_CONFIG
        
        handlers = LOGGING_CONFIG["handlers"]
        assert "security_audit" in handlers
        assert handlers["security_audit"]["backupCount"] == 90
    
    def test_security_audit_tool_import(self):
        """测试安全审计工具可导入"""
        from app.utils.security_audit import (
            log_security_event,
            log_login_success,
            log_login_failed,
            log_permission_change,
            log_token_refresh
        )
        assert log_security_event is not None
        assert log_login_success is not None


class TestImageInpainting:
    """测试图像修复功能"""
    
    def test_inpaint_api_exists(self):
        """测试图像修复 API 存在"""
        from app.api.v1.kolors_api import router
        assert router is not None
        
        # 检查路由是否注册
        routes = [r.path for r in router.routes]
        assert any("/inpaint" in path for path in routes)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
