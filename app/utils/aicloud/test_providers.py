"""
多供应商模型调用系统 - 单元测试

测试供应商配置、路由和适配器。
"""

import pytest
import asyncio

from app.utils.aicloud.providers import ModelProvider, ProviderConfig, ProviderRegistry
from app.utils.aicloud.provider_router import ProviderRouter, MODEL_PROVIDER_MAP


class TestModelProvider:
    """测试 ModelProvider 枚举"""
    
    def test_enum_values(self):
        assert ModelProvider.SILICONFLOW.value == "siliconflow"
        assert ModelProvider.DASHSCOPE.value == "dashscope"
        assert ModelProvider.ZHIPU.value == "zhipu"
        assert ModelProvider.DEEPSEEK.value == "deepseek"
        assert ModelProvider.OPENAI.value == "openai"
        assert ModelProvider.ANTHROPIC.value == "anthropic"
        assert ModelProvider.OLLAMA.value == "ollama"


class TestProviderConfig:
    """测试 ProviderConfig 数据类"""
    
    def test_valid_siliconflow_config(self):
        config = ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key="test-key",
            base_url="https://api.siliconflow.cn/v1",
        )
        assert config.is_valid() is True
    
    def test_invalid_config_missing_key(self):
        config = ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="",
            base_url="https://api.openai.com/v1",
        )
        assert config.is_valid() is False
    
    def test_invalid_config_missing_url(self):
        config = ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="test-key",
            base_url="",
        )
        assert config.is_valid() is False
    
    def test_disabled_config(self):
        config = ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key="test-key",
            base_url="https://api.siliconflow.cn/v1",
            enabled=False,
        )
        assert config.is_valid() is False
    
    def test_ollama_without_key(self):
        config = ProviderConfig(
            provider=ModelProvider.OLLAMA,
            api_key="",
            base_url="http://localhost:11434",
        )
        assert config.is_valid() is True


class TestProviderRegistry:
    """测试 ProviderRegistry"""
    
    def test_register_valid_config(self):
        registry = ProviderRegistry()
        config = ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key="test-key",
            base_url="https://api.siliconflow.cn/v1",
        )
        registry.register(config)
        
        assert registry.is_provider_available(ModelProvider.SILICONFLOW)
        assert registry.get(ModelProvider.SILICONFLOW) == config
    
    def test_register_invalid_config(self):
        registry = ProviderRegistry()
        config = ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="",
            base_url="https://api.openai.com/v1",
        )
        registry.register(config)
        
        assert registry.is_provider_available(ModelProvider.OPENAI) is False
    
    def test_get_available_providers(self):
        registry = ProviderRegistry()
        
        registry.register(ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key="key1",
            base_url="https://example.com/v1",
        ))
        registry.register(ProviderConfig(
            provider=ModelProvider.OPENAI,
            api_key="",  # Invalid
            base_url="https://api.openai.com/v1",
        ))
        
        available = registry.get_available_providers()
        assert ModelProvider.SILICONFLOW in available
        assert ModelProvider.OPENAI not in available


class TestProviderRouter:
    """测试 ProviderRouter"""
    
    def setup_method(self):
        """每个测试前清除单例"""
        ProviderRouter.clear_cache()
    
    def test_route_known_model(self):
        """测试已知模型路由"""
        router = ProviderRouter.get_instance()
        
        assert router.route("Qwen/Qwen3.5-4B") == ModelProvider.SILICONFLOW
        assert router.route("THUDM/GLM-4.1V-9B-Thinking") == ModelProvider.SILICONFLOW
        assert router.route("deepseek-ai/DeepSeek-OCR") == ModelProvider.SILICONFLOW
        assert router.route("qwen-plus") == ModelProvider.DASHSCOPE
        assert router.route("glm-4") == ModelProvider.ZHIPU
        assert router.route("deepseek-chat") == ModelProvider.DEEPSEEK
    
    def test_route_unknown_model_defaults_to_siliconflow(self):
        """测试未知模型默认路由到 SiliconFlow"""
        router = ProviderRouter.get_instance()
        assert router.route("unknown/model") == ModelProvider.SILICONFLOW
    
    def test_get_fallback_providers(self):
        """测试故障转移列表"""
        router = ProviderRouter.get_instance()
        fallbacks = router.get_fallback_providers(ModelProvider.SILICONFLOW)
        
        assert ModelProvider.DASHSCOPE in fallbacks
        assert ModelProvider.ZHIPU in fallbacks
    
    def test_get_fallback_ollama_empty(self):
        """测试 Ollama 无故障转移"""
        router = ProviderRouter.get_instance()
        fallbacks = router.get_fallback_providers(ModelProvider.OLLAMA)
        assert fallbacks == []
    
    def test_singleton_pattern(self):
        """测试单例模式"""
        router1 = ProviderRouter.get_instance()
        router2 = ProviderRouter.get_instance()
        assert router1 is router2
    
    def test_clear_cache(self):
        """测试清除缓存"""
        router1 = ProviderRouter.get_instance()
        ProviderRouter.clear_cache()
        router2 = ProviderRouter.get_instance()
        assert router1 is not router2


class TestModelProviderMap:
    """测试模型供应商映射表"""
    
    def test_all_builtin_models_mapped(self):
        """测试所有内置模型都有映射"""
        builtin_models = [
            "deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
            "deepseek-ai/DeepSeek-OCR",
            "Qwen/Qwen3.5-4B",
            "Qwen/Qwen3-8B",
            "Qwen/Qwen2.5-7B-Instruct",
            "THUDM/GLM-4.1V-9B-Thinking",
            "THUDM/GLM-4-9B-0414",
            "THUDM/GLM-Z1-9B-0414",
            "Kwai-Kolors/Kolors",
            "netease-youdao/bce-embedding-base_v1",
        ]
        
        for model in builtin_models:
            assert model in MODEL_PROVIDER_MAP, f"Model {model} not in provider map"
