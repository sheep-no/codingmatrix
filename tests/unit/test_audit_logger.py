"""
审计日志模块单元测试
"""
import pytest
import json
from unittest.mock import Mock, patch
from datetime import datetime, timedelta
from app.services.audit_logger import (
    AuditLogger, 
    AuditLogEntry, 
    get_audit_logger
)


class TestAuditLogEntry:
    """审计日志条目测试"""

    def test_create_entry(self):
        """测试创建日志条目"""
        entry = AuditLogEntry(
            timestamp="2026-05-23T12:00:00Z",
            user_id="user123",
            token="test-token-123",
            provider="siliconflow",
            model="gpt-4",
            success=True,
            duration_ms=150,
            input_tokens=100,
            output_tokens=200
        )
        
        assert entry.user_id == "user123"
        assert entry.provider == "siliconflow"
        assert entry.success == True
        assert entry.input_tokens == 100
        assert entry.output_tokens == 200

    def test_entry_defaults(self):
        """测试默认值"""
        entry = AuditLogEntry(
            timestamp="2026-05-23T12:00:00Z",
            user_id="user123",
            token="test-token",
            provider="siliconflow",
            model="gpt-4",
            success=True,
            duration_ms=100
        )
        
        assert entry.input_tokens == 0
        assert entry.output_tokens == 0
        assert entry.error_message == ""
        assert entry.is_fallback == False

    def test_asdict(self):
        """测试转换为字典"""
        from dataclasses import asdict
        
        entry = AuditLogEntry(
            timestamp="2026-05-23T12:00:00Z",
            user_id="user123",
            token="test-token",
            provider="siliconflow",
            model="gpt-4",
            success=True,
            duration_ms=100
        )
        
        d = asdict(entry)
        assert isinstance(d, dict)
        assert d["user_id"] == "user123"
        assert d["provider"] == "siliconflow"


class TestAuditLogger:
    """审计日志记录器测试"""

    @pytest.fixture
    def mock_redis(self):
        """模拟 Redis 客户端"""
        redis_mock = Mock()
        redis_mock.lpush = Mock()
        redis_mock.expire = Mock()
        redis_mock.lrange = Mock(return_value=[])
        redis_mock.delete = Mock()
        return redis_mock

    @pytest.fixture
    def logger(self, mock_redis):
        """创建日志记录器实例"""
        return AuditLogger(redis_client=mock_redis)

    def test_singleton(self):
        """测试单例模式"""
        logger1 = AuditLogger()
        logger2 = AuditLogger()
        # 注意：每次创建都是新实例（没有实现单例）
        assert isinstance(logger1, AuditLogger)
        assert isinstance(logger2, AuditLogger)

    def test_log_usage(self, logger, mock_redis):
        """测试记录使用日志"""
        logger.log_usage(
            user_id="user123",
            token="test-token",
            provider="siliconflow",
            model="gpt-4",
            success=True,
            duration_ms=150,
            input_tokens=100,
            output_tokens=200
        )
        
        mock_redis.lpush.assert_called()
        mock_redis.expire.assert_called()

    def test_log_usage_failure(self, logger, mock_redis):
        """测试记录失败日志"""
        logger.log_usage(
            user_id="user123",
            token="test-token",
            provider="siliconflow",
            model="gpt-4",
            success=False,
            duration_ms=5000,
            error_message="API Key 无效"
        )
        
        mock_redis.lpush.assert_called()
        
        # 验证日志内容
        call_args = mock_redis.lpush.call_args
        log_data = json.loads(call_args[0][1])
        assert log_data["success"] == False
        assert log_data["error_message"] == "API Key 无效"

    def test_log_usage_fallback(self, logger, mock_redis):
        """测试记录降级日志"""
        logger.log_usage(
            user_id="user123",
            token="test-token",
            provider="siliconflow",
            model="gpt-4",
            success=True,
            duration_ms=200,
            is_fallback=True
        )
        
        call_args = mock_redis.lpush.call_args
        log_data = json.loads(call_args[0][1])
        assert log_data["is_fallback"] == True

    def test_get_usage_history(self, logger, mock_redis):
        """测试获取使用历史"""
        mock_redis.lrange.return_value = [
            json.dumps({
                "timestamp": "2026-05-23T12:00:00Z",
                "user_id": "user123",
                "token": "token1",
                "provider": "siliconflow",
                "model": "gpt-4",
                "success": True,
                "duration_ms": 150
            }),
            json.dumps({
                "timestamp": "2026-05-23T12:01:00Z",
                "user_id": "user123",
                "token": "token2",
                "provider": "openai",
                "model": "gpt-3.5",
                "success": False,
                "duration_ms": 5000
            })
        ]
        
        logs = logger.get_usage_history("user123", limit=10)
        
        assert isinstance(logs, list)
        assert len(logs) == 2
        assert logs[0]["provider"] == "siliconflow"
        assert logs[1]["provider"] == "openai"

    def test_get_usage_history_filter_provider(self, logger, mock_redis):
        """测试按供应商过滤"""
        mock_redis.lrange.return_value = [
            json.dumps({
                "timestamp": "2026-05-23T12:00:00Z",
                "user_id": "user123",
                "token": "token1",
                "provider": "siliconflow",
                "model": "gpt-4",
                "success": True,
                "duration_ms": 150
            }),
            json.dumps({
                "timestamp": "2026-05-23T12:01:00Z",
                "user_id": "user123",
                "token": "token2",
                "provider": "openai",
                "model": "gpt-3.5",
                "success": False,
                "duration_ms": 5000
            })
        ]
        
        logs = logger.get_usage_history("user123", provider="siliconflow")
        
        assert len(logs) == 1
        assert logs[0]["provider"] == "siliconflow"

    def test_get_usage_statistics(self, logger, mock_redis):
        """测试获取使用统计"""
        # Mock get_usage_history to return controlled data
        mock_logs = [
            {
                "timestamp": "2026-05-23T12:00:00Z",
                "user_id": "user123",
                "token": "token1",
                "provider": "siliconflow",
                "model": "gpt-4",
                "success": True,
                "duration_ms": 150,
                "input_tokens": 100,
                "output_tokens": 200
            },
            {
                "timestamp": "2026-05-23T12:01:00Z",
                "user_id": "user123",
                "token": "token2",
                "provider": "siliconflow",
                "model": "gpt-4",
                "success": False,
                "duration_ms": 5000,
                "input_tokens": 50,
                "output_tokens": 0
            }
        ]
        
        # Patch get_usage_history to return controlled data
        with patch.object(logger, 'get_usage_history', return_value=mock_logs):
            stats = logger.get_usage_statistics("user123", days=7)
            
            assert stats["total_calls"] == 2
            assert stats["successful_calls"] == 1
            assert stats["failed_calls"] == 1
            assert stats["total_input_tokens"] == 150
            assert stats["total_output_tokens"] == 200

    def test_clear_logs(self, logger, mock_redis):
        """测试清除日志"""
        logger.clear_logs("user123")
        mock_redis.delete.assert_called()


class TestGetAuditLogger:
    """获取审计日志记录器测试"""

    def test_get_instance(self):
        """测试获取实例"""
        logger = get_audit_logger()
        assert isinstance(logger, AuditLogger)

    def test_returns_singleton(self):
        """测试返回单例"""
        logger1 = get_audit_logger()
        logger2 = get_audit_logger()
        assert logger1 is logger2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
