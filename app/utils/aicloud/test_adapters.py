"""
多供应商适配器 - 单元测试

测试供应商适配器的消息构建、参数映射和响应解析。
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from app.utils.aicloud.providers import ModelProvider, ProviderConfig
from app.utils.aicloud.adapters.base import BaseProviderAdapter


class TestBaseProviderAdapter:
    """测试 BaseProviderAdapter 通用方法"""
    
    def test_build_messages_with_system_prompt(self):
        """测试带 system prompt 的消息构建"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        messages = adapter._build_messages("你好", "你是助手")
        
        assert len(messages) == 2
        assert messages[0] == {"role": "system", "content": "你是助手"}
        assert messages[1] == {"role": "user", "content": "你好"}
    
    def test_build_messages_without_system_prompt(self):
        """测试不带 system prompt 的消息构建"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        messages = adapter._build_messages("你好")
        
        assert len(messages) == 1
        assert messages[0] == {"role": "user", "content": "你好"}
    
    def test_parse_response_content_standard(self):
        """测试标准响应解析"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        response = {
            "choices": [{"message": {"content": "Hello World"}}],
            "usage": {"total_tokens": 100}
        }
        
        content = adapter._parse_response_content(response)
        assert content == "Hello World"
    
    def test_parse_response_content_direct(self):
        """测试直接 content 格式解析"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        response = {"content": "Hello"}
        
        content = adapter._parse_response_content(response)
        assert content == "Hello"
    
    def test_parse_response_content_invalid(self):
        """测试无效响应格式"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        response = {"error": "something wrong"}
        
        with pytest.raises(ValueError, match="Unexpected response format"):
            adapter._parse_response_content(response)
    
    def test_build_request_body_standard(self):
        """测试标准请求体构建"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        messages = [{"role": "user", "content": "test"}]
        
        body = adapter._build_request_body(
            model="Qwen/Qwen3.5-4B",
            messages=messages,
            stream=False,
            temperature=0.7,
            max_tokens=4096,
            thinking_budget=4096,
        )
        
        assert body["model"] == "Qwen/Qwen3.5-4B"
        assert body["messages"] == messages
        assert body["stream"] is False
        assert body["temperature"] == 0.7
        assert body["max_tokens"] == 4096
        assert "extra_body" not in body  # 非 reasoning 模型
    
    def test_build_request_body_reasoning(self):
        """测试 reasoning 模型请求体构建"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        messages = [{"role": "user", "content": "test"}]
        
        body = adapter._build_request_body(
            model="deepseek-ai/DeepSeek-R1",
            messages=messages,
            stream=False,
            temperature=0.7,
            max_tokens=4096,
            thinking_budget=4096,
        )
        
        assert "extra_body" in body
        assert body["extra_body"]["thinking_budget"] == 4096
    
    def test_is_reasoning_model(self):
        """测试 reasoning 模型判断"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        
        assert adapter._is_reasoning_model("deepseek-ai/DeepSeek-R1") is True
        assert adapter._is_reasoning_model("deepseek-reasoner") is True
        assert adapter._is_reasoning_model("THUDM/GLM-Z1-9B-0414-thinking") is True
        assert adapter._is_reasoning_model("Qwen/Qwen3.5-4B") is False
        assert adapter._is_reasoning_model("gpt-4o") is False


class TestSiliconFlowAdapter:
    """测试 SiliconFlowAdapter"""
    
    def test_default_config(self):
        """测试默认配置加载"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter()
        assert adapter.provider == ModelProvider.SILICONFLOW
        assert adapter.base_url == "https://api.siliconflow.cn/v1"
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key="custom-key",
            base_url="https://custom.url/v1",
        )
        
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        adapter = SiliconFlowAdapter(config)
        
        assert adapter.api_key == "custom-key"
        assert adapter.base_url == "https://custom.url/v1"
    
    def test_get_headers(self):
        """测试请求头构建"""
        from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
        
        adapter = SiliconFlowAdapter(ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key="test-key",
            base_url="https://example.com/v1",
        ))
        
        headers = adapter._get_headers()
        assert headers["Authorization"] == "Bearer test-key"
        assert headers["Content-Type"] == "application/json"


class TestAnthropicAdapter:
    """测试 AnthropicAdapter"""
    
    def test_get_headers(self):
        """测试 Anthropic 请求头"""
        from app.utils.aicloud.adapters.anthropic import AnthropicAdapter
        
        adapter = AnthropicAdapter(ProviderConfig(
            provider=ModelProvider.ANTHROPIC,
            api_key="test-key",
            base_url="https://api.anthropic.com/v1",
        ))
        
        headers = adapter._get_headers()
        assert headers["x-api-key"] == "test-key"
        assert headers["anthropic-version"] == "2023-06-01"
    
    def test_call_embedding_not_implemented(self):
        """测试 Anthropic 不支持 embedding"""
        from app.utils.aicloud.adapters.anthropic import AnthropicAdapter
        
        adapter = AnthropicAdapter(ProviderConfig(
            provider=ModelProvider.ANTHROPIC,
            api_key="test-key",
            base_url="https://api.anthropic.com/v1",
        ))
        
        with pytest.raises(NotImplementedError):
            import asyncio
            asyncio.get_event_loop().run_until_complete(
                adapter.call_embedding("model", "text")
            )
