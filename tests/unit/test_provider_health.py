"""
供应商健康检查模块单元测试
"""
import pytest
from unittest.mock import Mock, patch, AsyncMock
from app.services.provider_health import ProviderHealthChecker, get_health_checker


class TestProviderHealthChecker:
    """供应商健康检查器测试"""

    def test_singleton(self):
        """测试单例模式"""
        checker1 = get_health_checker()
        checker2 = get_health_checker()
        assert checker1 is checker2

    def test_supported_providers(self):
        """测试支持的供应商"""
        from app.services.provider_health import PROVIDER_CONFIGS
        assert "siliconflow" in PROVIDER_CONFIGS
        assert "openai" in PROVIDER_CONFIGS
        assert "anthropic" in PROVIDER_CONFIGS
        assert "bailian" in PROVIDER_CONFIGS
        assert "glm" in PROVIDER_CONFIGS
        assert "deepseek" in PROVIDER_CONFIGS

    @pytest.mark.asyncio
    async def test_check_siliconflow_success(self):
        """测试硅基流动健康检查成功"""
        checker = get_health_checker()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {"choices": [{"message": {"content": "2"}}]}
            
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            success, message = await checker.check("siliconflow", "sk-valid-key")
            
            assert success == True
            assert "成功" in message or "success" in message.lower()

    @pytest.mark.asyncio
    async def test_check_siliconflow_invalid_key(self):
        """测试硅基流动无效 Key"""
        checker = get_health_checker()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_response = Mock()
            mock_response.status_code = 401
            
            mock_client_instance = AsyncMock()
            mock_client_instance.post.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            success, message = await checker.check("siliconflow", "sk-invalid-key")
            
            assert success == False

    @pytest.mark.asyncio
    async def test_check_siliconflow_timeout(self):
        """测试硅基流动超时"""
        checker = get_health_checker()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.post.side_effect = Exception("Timeout")
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            success, message = await checker.check("siliconflow", "sk-test-key")
            
            assert success == False
            assert "超时" in message or "timeout" in message.lower()

    @pytest.mark.asyncio
    async def test_check_unsupported_provider(self):
        """测试不支持的供应商"""
        checker = get_health_checker()
        
        success, message = await checker.check("unknown_provider", "sk-test-key")
        
        assert success == False
        assert "不支持" in message or "unknown" in message.lower()

    def test_get_provider_config(self):
        """测试获取供应商配置"""
        from app.services.provider_health import PROVIDER_CONFIGS
        
        config = PROVIDER_CONFIGS.get("siliconflow")
        assert config is not None
        assert "base_url" in config
        assert "model" in config

    def test_get_provider_config_unknown(self):
        """测试获取未知供应商配置"""
        from app.services.provider_health import PROVIDER_CONFIGS
        
        config = PROVIDER_CONFIGS.get("unknown_provider")
        assert config is None

    def test_check_timeout_default(self):
        """测试默认超时设置"""
        from app.services.provider_health import TEST_TIMEOUT
        assert TEST_TIMEOUT == 5


class TestGetHealthChecker:
    """获取健康检查器测试"""

    def test_get_instance(self):
        """测试获取实例"""
        checker = get_health_checker()
        assert isinstance(checker, ProviderHealthChecker)

    def test_returns_singleton(self):
        """测试返回单例"""
        checker1 = get_health_checker()
        checker2 = get_health_checker()
        assert checker1 is checker2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
