"""
系统监控和日志服务测试
"""
import pytest
from unittest.mock import MagicMock
import asyncio

from app.db.log_server import LogFilter
from app.utils.system_monitor import get_system_stats


@pytest.mark.unit
@pytest.mark.logging
class TestLogService:
    """日志服务测试"""

    @pytest.mark.asyncio
    async def test_stream_logs_generator_type(self):
        """测试日志流生成器类型"""
        from app.db.log_server import LogService

        log_service = LogService()

        gen = log_service.stream_logs_with_filter("app")
        assert hasattr(gen, '__aiter__'), "stream_logs_with_filter should return an async generator"

        gen.aclose()

    @pytest.mark.asyncio
    async def test_stream_logs_returns_async_generator(self):
        """测试日志流返回异步生成器"""
        from app.db.log_server import LogService
        import inspect

        log_service = LogService()

        result = log_service.stream_logs_with_filter("app")
        assert asyncio.iscoroutine(gen if (gen := result) else None) or hasattr(result, '__aiter__')

        try:
            await result.aclose()
        except:
            pass


@pytest.mark.unit
@pytest.mark.logging
class TestLogFilter:
    """日志过滤器测试"""

    def test_log_filter_default(self):
        """测试默认过滤器"""
        log_filter = LogFilter()
        
        assert log_filter.level is None
        assert log_filter.keyword is None

    def test_log_filter_with_values(self):
        """测试带值的过滤器"""
        log_filter = LogFilter(level="ERROR", keyword="websocket")
        
        assert log_filter.level == "ERROR"
        assert log_filter.keyword == "websocket"

    def test_log_filter_to_dict(self):
        """测试转换为字典"""
        log_filter = LogFilter(level="INFO", keyword="test")
        result = log_filter.to_dict()
        
        assert isinstance(result, dict)
        assert "level" in result
        assert "keyword" in result

    def test_log_filter_to_dict_empty(self):
        """测试空过滤器转字典"""
        log_filter = LogFilter()
        result = log_filter.to_dict()
        
        assert result == {"level": None, "keyword": None}


@pytest.mark.unit
@pytest.mark.monitoring
class TestSystemMonitor:
    """系统监控测试"""

    def test_get_system_stats(self):
        """测试获取系统统计信息"""
        stats = get_system_stats()
        
        assert "timestamp" in stats
        assert "cpu" in stats
        assert "memory" in stats
        assert "disk" in stats
        assert "network" in stats
        
        assert "total_percent" in stats["cpu"]
        assert "percent" in stats["memory"]
        assert "percent" in stats["disk"]
        assert "bytes_sent" in stats["network"]
        assert "bytes_recv" in stats["network"]
        
        assert 0 <= stats["cpu"]["total_percent"] <= 100
        assert 0 <= stats["memory"]["percent"] <= 100
        assert stats["memory"]["percent"] >= 0
        assert stats["disk"]["percent"] >= 0
        assert stats["network"]["bytes_sent"] >= 0
        assert stats["network"]["bytes_recv"] >= 0

    def test_system_stats_types(self):
        """测试系统统计信息类型"""
        stats = get_system_stats()
        
        assert isinstance(stats["cpu"]["total_percent"], float)
        assert isinstance(stats["memory"]["percent"], float)
        assert isinstance(stats["memory"]["total_gb"], (int, float))
        assert isinstance(stats["memory"]["used_gb"], (int, float))
        assert isinstance(stats["disk"]["total_gb"], (int, float))
        assert isinstance(stats["disk"]["used_gb"], (int, float))
        assert isinstance(stats["network"]["bytes_sent"], int)
        assert isinstance(stats["network"]["bytes_recv"], int)


@pytest.mark.unit
@pytest.mark.guardian
class TestProcessGuardian:
    """进程守护测试"""

    @pytest.mark.asyncio
    async def test_smart_guardian_initialization(self):
        """测试智能守护初始化"""
        from app.utils.async_enhanced_guard import AsyncSmartGuardian
        
        guardian = AsyncSmartGuardian(check_interval=10)
        
        assert guardian is not None
        assert guardian.check_interval == 10
        
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_smart_guardian_scan_and_learn(self):
        """测试扫描和学习"""
        from app.utils.async_enhanced_guard import AsyncSmartGuardian
        
        guardian = AsyncSmartGuardian(check_interval=10)
        
        await guardian.scan_and_learn(auto_enable_trusted=True)
        
        assert guardian.config_manager is not None
        
        await guardian.shutdown()

    @pytest.mark.asyncio
    async def test_service_config_manager(self):
        """测试服务配置管理器"""
        from app.utils.service_config_manager import ServiceConfigManager
        
        manager = ServiceConfigManager()
        
        assert manager is not None
        assert hasattr(manager, "configs")
        assert hasattr(manager, "get_or_create_config")
        assert hasattr(manager, "save_configs")

    @pytest.mark.asyncio
    async def test_is_port_open(self):
        """测试端口检测"""
        from app.utils.async_enhanced_guard import AsyncSmartGuardian
        
        guardian = AsyncSmartGuardian(check_interval=10)
        
        is_open = await guardian.is_port_open(8000)
        
        assert isinstance(is_open, bool)
        
        await guardian.shutdown()
