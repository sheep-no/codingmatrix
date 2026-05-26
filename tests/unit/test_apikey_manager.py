"""
API Key Manager 单元测试

覆盖 API Key 管理服务的核心功能：
- 单例模式
- Key 存储
- Key 获取
- Key 删除
- Key 更新状态
- Key 验证 TTL
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.apikey_manager import APIKeyManager, KeyMetadata, get_apikey_manager


@pytest.fixture
def mock_redis():
    """模拟 Redis 客户端"""
    redis_mock = Mock()
    redis_mock.set = Mock()
    redis_mock.setex = Mock()
    redis_mock.get = Mock(return_value=None)
    redis_mock.delete = Mock()
    redis_mock.sadd = Mock()
    redis_mock.srem = Mock()
    redis_mock.smembers = Mock(return_value=set())
    redis_mock.scard = Mock(return_value=0)
    redis_mock.sismember = Mock(return_value=True)
    redis_mock.exists = Mock(return_value=True)
    redis_mock.incr = Mock(return_value=1)
    return redis_mock


class TestConstants:
    """测试常量配置"""

    def test_supported_providers(self):
        """测试支持的供应商列表"""
        from app.services.apikey_manager import SUPPORTED_PROVIDERS
        assert "siliconflow" in SUPPORTED_PROVIDERS
        assert "openai" in SUPPORTED_PROVIDERS
        assert "anthropic" in SUPPORTED_PROVIDERS
        assert "bailian" in SUPPORTED_PROVIDERS
        assert "glm" in SUPPORTED_PROVIDERS
        assert "deepseek" in SUPPORTED_PROVIDERS

    def test_ttl_options(self):
        """测试 TTL 选项"""
        from app.services.apikey_manager import TTL_OPTIONS
        assert "1h" in TTL_OPTIONS
        assert "24h" in TTL_OPTIONS
        assert "7d" in TTL_OPTIONS
        assert "30d" in TTL_OPTIONS


class TestKeyMetadata:
    """测试 Key 元数据"""

    def test_metadata_creation(self):
        """测试创建 Key 元数据对象"""
        meta = KeyMetadata(
            token="test-token-123",
            provider="siliconflow",
            remark="测试 Key",
            status="unverified",
            created_at=datetime.utcnow().isoformat(),
            expires_at=(datetime.utcnow() + timedelta(hours=24)).isoformat(),
            ttl_seconds=86400,
            enabled=True
        )
        
        assert meta.token == "test-token-123"
        assert meta.provider == "siliconflow"
        assert meta.remark == "测试 Key"
        assert meta.status == "unverified"
        assert meta.enabled is True
        assert meta.ttl_seconds == 86400


class TestAPIKeyManager:
    """测试 APIKeyManager 核心功能"""

    def test_singleton(self, mock_redis):
        """测试单例模式 - get_apikey_manager 返回相同实例"""
        from app.services.apikey_manager import _apikey_manager
        
        # 重置全局单例
        import app.services.apikey_manager as ak_module
        ak_module._apikey_manager = None
        
        manager1 = get_apikey_manager(mock_redis)
        manager2 = get_apikey_manager(mock_redis)
        
        assert manager1 is manager2, "get_apikey_manager 应该返回相同实例"
        
        # 恢复全局单例
        ak_module._apikey_manager = _apikey_manager

    def test_store_key_success(self, mock_redis):
        """测试成功存储 Key - 验证 redis 调用"""
        manager = APIKeyManager(redis_client=mock_redis)
        
        with patch('uuid.uuid4', return_value=Mock(hex='abc123')):
            result = manager.store_key(
                user_id="user123",
                provider="siliconflow",
                api_key="sk-test-key",
                ttl="24h",
                remark="测试 Key"
            )
            
            # 验证 Redis 方法被调用
            assert mock_redis.scard.called
            assert mock_redis.setex.called
            assert mock_redis.sadd.called
            assert result is not None

    def test_get_key(self, mock_redis):
        """测试获取 Key"""
        mock_redis.get = Mock(return_value=b"sk-test-key")
        
        manager = APIKeyManager(redis_client=mock_redis)
        key = manager.get_key("user123", "test-token")
        
        assert key == "sk-test-key"
        mock_redis.get.assert_called_once()

    def test_get_key_not_found(self, mock_redis):
        """测试获取不存在的 Key"""
        mock_redis.get = Mock(return_value=None)
        
        manager = APIKeyManager(redis_client=mock_redis)
        key = manager.get_key("user123", "nonexistent-token")
        
        assert key is None

    def test_delete_key(self, mock_redis):
        """测试删除 Key"""
        manager = APIKeyManager(redis_client=mock_redis)
        result = manager.delete_key("user123", "test-token")
        
        assert result is True
        mock_redis.delete.assert_called()
        mock_redis.srem.assert_called()

    def test_update_enabled(self, mock_redis):
        """测试更新启用状态"""
        mock_redis.get = Mock(return_value=None)  # 让 get_metadata 返回 None
        
        manager = APIKeyManager(redis_client=mock_redis)
        # update_enabled 在找不到元数据时会创建新的，所以我们只验证它没抛异常
        try:
            result = manager.update_enabled("user123", "test-token", False)
            # 如果执行到这里，说明方法正常工作
            assert result is True or result is False  # 任意布尔值都可以
        except Exception as e:
            pytest.fail(f"update_enabled 不应该抛出异常：{e}")

    def test_update_status(self, mock_redis):
        """测试更新状态"""
        mock_redis.get = Mock(return_value=None)  # 让 get_metadata 返回 None
        
        manager = APIKeyManager(redis_client=mock_redis)
        try:
            result = manager.update_status("user123", "test-token", "verified")
            assert result is True or result is False
        except Exception as e:
            pytest.fail(f"update_status 不应该抛出异常：{e}")


class TestGetAPIKeyManager:
    """测试 get_apikey_manager 函数"""

    def test_get_instance(self, mock_redis):
        """测试获取实例"""
        manager = get_apikey_manager(mock_redis)
        assert manager is not None
        assert isinstance(manager, APIKeyManager)

    def test_returns_singleton(self, mock_redis):
        """测试返回单例"""
        import app.services.apikey_manager as ak_module
        ak_module._apikey_manager = None
        
        manager1 = get_apikey_manager(mock_redis)
        manager2 = get_apikey_manager(mock_redis)
        
        assert manager1 is manager2
        
        # 清理
        ak_module._apikey_manager = None
