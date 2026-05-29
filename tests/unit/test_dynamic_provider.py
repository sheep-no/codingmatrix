"""
动态供应商管理模块单元测试
"""
import pytest
import time
import uuid
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import httpx

from app.utils.aicloud.dynamic_provider import (
    Protocol, ModelInfo, DynamicProvider,
    DynamicProviderManager,
    MODEL_CACHE_TTL,
    get_dynamic_provider_manager,
    fetch_models_openai,
    fetch_models_anthropic,
)


class TestProtocol:
    """Protocol 枚举测试"""

    def test_openai_value(self):
        assert Protocol.OPENAI.value == "openai"

    def test_anthropic_value(self):
        assert Protocol.ANTHROPIC.value == "anthropic"

    def test_protocol_from_string(self):
        assert Protocol("openai") == Protocol.OPENAI
        assert Protocol("anthropic") == Protocol.ANTHROPIC

    def test_invalid_protocol_raises(self):
        with pytest.raises(ValueError):
            Protocol("invalid")


class TestModelInfo:
    """ModelInfo 数据类测试"""

    def test_default_values(self):
        model = ModelInfo(id="model-1")
        assert model.id == "model-1"
        assert model.name == ""
        assert model.max_tokens == 4096
        assert model.context_length == 4096

    def test_custom_values(self):
        model = ModelInfo(id="model-1", name="Test Model", max_tokens=8192, context_length=16384)
        assert model.name == "Test Model"
        assert model.max_tokens == 8192
        assert model.context_length == 16384


class TestDynamicProvider:
    """DynamicProvider 数据类测试"""

    def test_default_values(self):
        provider = DynamicProvider(
            id="test-1", name="Test", base_url="http://test",
            protocol=Protocol.OPENAI, api_key="sk-test",
        )
        assert provider.enabled == True
        assert provider.models == []
        assert provider.last_sync == 0.0
        assert provider.sync_error == ""
        assert provider.created_at > 0

    def test_custom_values(self):
        now = time.time()
        models = [ModelInfo(id="model-1")]
        provider = DynamicProvider(
            id="test-1", name="Test", base_url="http://test",
            protocol=Protocol.OPENAI, api_key="sk-test",
            enabled=False, created_at=now, models=models,
            last_sync=100.0, sync_error="sync failed",
        )
        assert provider.enabled == False
        assert len(provider.models) == 1
        assert provider.last_sync == 100.0
        assert provider.sync_error == "sync failed"


class TestDynamicProviderManager:
    """DynamicProviderManager 测试"""

    def test_singleton(self):
        m1 = get_dynamic_provider_manager()
        m2 = get_dynamic_provider_manager()
        assert m1 is m2

    def test_add_provider(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test Provider", "http://test.com/v1", "openai", "sk-test-key-12345")
        
        assert provider.id is not None
        assert len(provider.id) == 8
        assert provider.name == "Test Provider"
        assert provider.base_url == "http://test.com/v1"
        assert provider.protocol == Protocol.OPENAI
        assert provider.api_key == "sk-test-key-12345"
        assert provider.enabled == True

    def test_add_provider_trims_trailing_slash(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com/v1/", "openai", "sk-test-key-12345")
        assert provider.base_url == "http://test.com/v1"

    def test_add_provider_anthropic(self):
        manager = DynamicProviderManager()
        provider = manager.add("Anthropic", "http://api.anthropic.com", "anthropic", "sk-ant-key-12345")
        assert provider.protocol == Protocol.ANTHROPIC

    def test_add_provider_invalid_protocol(self):
        manager = DynamicProviderManager()
        with pytest.raises(ValueError):
            manager.add("Test", "http://test.com", "invalid", "sk-test-key-12345")

    def test_get_provider(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        
        retrieved = manager.get(provider.id)
        assert retrieved is not None
        assert retrieved.id == provider.id
        assert retrieved.name == provider.name

    def test_get_nonexistent_provider(self):
        manager = DynamicProviderManager()
        assert manager.get("nonexistent") is None

    def test_list_providers(self):
        manager = DynamicProviderManager()
        manager.add("Test1", "http://test1.com", "openai", "sk-key-1-12345678")
        manager.add("Test2", "http://test2.com", "openai", "sk-key-2-12345678")
        
        providers = manager.list()
        assert len(providers) == 2

    def test_list_providers_hides_api_key(self):
        manager = DynamicProviderManager()
        manager.add("Test", "http://test.com", "openai", "sk-secret-key-1234567")
        
        providers = manager.list()
        assert len(providers) == 1
        assert providers[0].api_key == ""

    def test_delete_provider(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        
        result = manager.delete(provider.id)
        assert result == True
        assert manager.get(provider.id) is None

    def test_delete_nonexistent_provider(self):
        manager = DynamicProviderManager()
        result = manager.delete("nonexistent")
        assert result == False

    def test_toggle_provider(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        assert provider.enabled == True
        
        result = manager.toggle(provider.id)
        assert result == True
        
        updated = manager.get(provider.id)
        assert updated.enabled == False

    def test_toggle_provider_again(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        
        manager.toggle(provider.id)
        manager.toggle(provider.id)
        
        updated = manager.get(provider.id)
        assert updated.enabled == True

    def test_toggle_nonexistent_provider(self):
        manager = DynamicProviderManager()
        result = manager.toggle("nonexistent")
        assert result == False

    def test_get_by_model(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        provider.models = [
            ModelInfo(id="model-1"),
            ModelInfo(id="model-2"),
        ]
        
        found = manager.get_by_model("model-1")
        assert found is not None
        assert found.id == provider.id

    def test_get_by_model_not_found(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        provider.models = [ModelInfo(id="model-1")]
        
        assert manager.get_by_model("nonexistent-model") is None

    def test_get_by_model_disabled_provider(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        provider.models = [ModelInfo(id="model-1")]
        provider.enabled = False
        
        assert manager.get_by_model("model-1") is None

    def test_generated_id_is_unique(self):
        manager = DynamicProviderManager()
        p1 = manager.add("Test1", "http://test1.com", "openai", "sk-key-1-123456789")
        p2 = manager.add("Test2", "http://test2.com", "openai", "sk-key-2-123456789")
        assert p1.id != p2.id


class TestProviderIdFormat:
    """供应商 ID 格式测试"""

    def test_id_length(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        assert len(provider.id) == 8

    def test_id_is_string(self):
        manager = DynamicProviderManager()
        provider = manager.add("Test", "http://test.com", "openai", "sk-test-key-12345")
        assert isinstance(provider.id, str)


class TestFetchModelsOpenAI:
    """fetch_models_openai 测试"""

    @pytest.mark.asyncio
    async def test_fetch_models_success(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-test-123456",
        )
        
        mock_response_data = {
            "data": [
                {"id": "model-1", "name": "Model One", "metadata": {"max_tokens": 8192}},
                {"id": "model-2", "name": "Model Two", "metadata": {"max_tokens": 4096}},
            ]
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            models = await fetch_models_openai(provider)
            
            assert len(models) == 2
            assert models[0].id == "model-1"
            assert models[0].name == "Model One"
            assert models[0].max_tokens == 8192
            assert models[1].id == "model-2"

    @pytest.mark.asyncio
    async def test_fetch_models_empty_response(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-test-123456",
        )
        
        mock_response = Mock()
        mock_response.json.return_value = {"data": []}
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            models = await fetch_models_openai(provider)
            assert models == []

    @pytest.mark.asyncio
    async def test_fetch_models_skip_empty_id(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-test-123456",
        )
        
        mock_response_data = {
            "data": [
                {"id": "", "name": "Empty ID"},
                {"id": "valid-model", "name": "Valid"},
            ]
        }
        
        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            models = await fetch_models_openai(provider)
            assert len(models) == 1
            assert models[0].id == "valid-model"

    @pytest.mark.asyncio
    async def test_fetch_models_default_max_tokens(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-test-123456",
        )
        
        mock_response_data = {
            "data": [{"id": "model-no-metadata"}]
        }
        
        mock_response = Mock()
        mock_response.json.return_value = mock_response_data
        mock_response.raise_for_status = Mock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            models = await fetch_models_openai(provider)
            assert models[0].max_tokens == 4096

    @pytest.mark.asyncio
    async def test_fetch_models_http_error(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-test-123456",
        )
        
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401 Unauthorized", request=Mock(), response=Mock(status_code=401)
        )
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance = AsyncMock()
            mock_client_instance.get.return_value = mock_response
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            with pytest.raises(httpx.HTTPStatusError):
                await fetch_models_openai(provider)


class TestFetchModelsAnthropic:
    """fetch_models_anthropic 测试"""

    @pytest.mark.asyncio
    async def test_returns_known_models(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://anthropic.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        
        models = await fetch_models_anthropic(provider)
        
        assert len(models) > 0
        model_ids = [m.id for m in models]
        assert "claude-sonnet-4-20250514" in model_ids
        assert "claude-opus-4-20250514" in model_ids
        assert "claude-3-5-sonnet-20241022" in model_ids
        assert "claude-3-haiku-20240307" in model_ids

    @pytest.mark.asyncio
    async def test_model_max_tokens(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://anthropic.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        
        models = await fetch_models_anthropic(provider)
        
        for model in models:
            assert model.max_tokens == 8192


class TestModelCacheTTL:
    """模型缓存 TTL 常量测试"""

    def test_cache_ttl_is_300_seconds(self):
        assert MODEL_CACHE_TTL == 300

    def test_cache_ttl_is_5_minutes(self):
        assert MODEL_CACHE_TTL == 5 * 60


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
