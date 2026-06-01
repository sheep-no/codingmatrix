"""
动态供应商适配器单元测试
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from fastapi import HTTPException

from app.utils.aicloud.dynamic_provider import Protocol, DynamicProvider, ModelInfo
from app.utils.aicloud.adapters.dynamic import DynamicAdapter


class TestDynamicAdapterInit:
    """DynamicAdapter 初始化测试"""

    def test_init_with_openai_provider(self):
        provider = DynamicProvider(
            id="test-openai", name="Test OpenAI", base_url="http://openai.test.com/v1",
            protocol=Protocol.OPENAI, api_key="sk-openai-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        assert adapter._protocol == Protocol.OPENAI
        assert adapter.base_url == "http://openai.test.com/v1"
        assert adapter.api_key == "sk-openai-123456789"

    def test_init_with_anthropic_provider(self):
        provider = DynamicProvider(
            id="test-anthropic", name="Test Anthropic", base_url="http://anthropic.test.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        adapter = DynamicAdapter(provider)
        
        assert adapter._protocol == Protocol.ANTHROPIC
        assert adapter.base_url == "http://anthropic.test.com"

    def test_get_headers_openai(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-openai-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        headers = adapter._get_headers()
        assert headers["Authorization"] == "Bearer sk-openai-123456789"
        assert headers["Content-Type"] == "application/json"

    def test_get_headers_anthropic(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        adapter = DynamicAdapter(provider)
        
        headers = adapter._get_headers()
        assert headers["x-api-key"] == "sk-ant-1234567890"
        assert headers["anthropic-version"] == "2023-06-01"


class TestDynamicAdapterCallLLM:
    """call_llm 方法测试"""

    @pytest.mark.asyncio
    async def test_call_llm_routes_to_openai(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-openai-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        mock_response_data = {
            "choices": [{"message": {"content": "Hello!"}}],
            "usage": {"total_tokens": 20},
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                result = await adapter.call_llm(
                    model="gpt-3.5-turbo",
                    prompt="Hello",
                    system_prompt="You are helpful",
                )
                
                assert result["choices"][0]["message"]["content"] == "Hello!"

    @pytest.mark.asyncio
    async def test_call_llm_routes_to_anthropic(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        adapter = DynamicAdapter(provider)
        
        mock_response_data = {
            "content": [{"type": "text", "text": "Hello from Claude!"}],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                result = await adapter.call_llm(
                    model="claude-3-haiku-20240307",
                    prompt="Hello",
                    system_prompt="You are helpful",
                )
                
                assert result["choices"][0]["message"]["content"] == "Hello from Claude!"

    @pytest.mark.asyncio
    async def test_call_llm_raises_error_without_api_key(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="",
        )
        adapter = DynamicAdapter(provider)
        
        with pytest.raises(RuntimeError, match="API Key 未配置"):
            await adapter.call_llm(model="gpt-3.5-turbo", prompt="Hello")

    @pytest.mark.asyncio
    async def test_call_llm_http_error_openai(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-openai-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        mock_response = Mock()
        mock_response.status_code = 401
        mock_response.text = "Unauthorized"
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                with pytest.raises(HTTPException) as exc_info:
                    await adapter.call_llm(model="gpt-3.5-turbo", prompt="Hello")
                
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_call_llm_anthropic_http_error(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        adapter = DynamicAdapter(provider)
        
        mock_response = Mock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                with pytest.raises(HTTPException) as exc_info:
                    await adapter.call_llm(model="claude-3-haiku-20240307", prompt="Hello")
                
                assert exc_info.value.status_code == 403


class TestDynamicAdapterOpenAI:
    """_call_openai 方法测试"""

    @pytest.mark.asyncio
    async def test_openai_non_streaming(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://api.test.com/v1",
            protocol=Protocol.OPENAI, api_key="sk-openai-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        mock_response_data = {
            "choices": [{"message": {"content": "Response"}}],
            "usage": {"total_tokens": 50},
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                result = await adapter._call_openai(
                    model="gpt-3.5-turbo", prompt="Test", system_prompt="Test",
                    stream=False, temperature=0.7, max_tokens=100, thinking_budget=100,
                    cancel_event=None,
                )
                
                assert result["choices"][0]["message"]["content"] == "Response"

    @pytest.mark.skip(reason="流式响应 mock 复杂，需要真实环境测试")
    @pytest.mark.asyncio
    async def test_openai_streaming(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://api.test.com/v1",
            protocol=Protocol.OPENAI, api_key="sk-openai-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        async def mock_aiter_lines():
            yield 'data: {"choices": [{"delta": {"content": "Hello"}}]}\n'
            yield 'data: {"choices": [{"delta": {"content": " World"}}]}\n'
            yield "data: [DONE]\n"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.aclose = AsyncMock()
        
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)
        
        mock_client_instance = AsyncMock()
        mock_client_instance.stream.return_value = mock_stream_cm
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client_instance.get = AsyncMock()
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            stream_gen = await adapter._call_openai(
                model="gpt-3.5-turbo", prompt="Test", system_prompt="",
                stream=True, temperature=0.7, max_tokens=100, thinking_budget=100,
                cancel_event=None,
            )
            
            chunks = []
            async for chunk in stream_gen:
                chunks.append(chunk)
            
            assert len(chunks) == 2
            assert 'Hello' in chunks[0]
            assert 'World' in chunks[1]

    @pytest.mark.asyncio
    async def test_openai_cancel_event(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://api.test.com/v1",
            protocol=Protocol.OPENAI, api_key="sk-openai-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        cancel_event = asyncio.Event()
        cancel_event.set()
        
        with pytest.raises(asyncio.CancelledError, match="LLM 调用被取消"):
            await adapter._call_openai(
                model="gpt-3.5-turbo", prompt="Test", system_prompt="",
                stream=False, temperature=0.7, max_tokens=100, thinking_budget=100,
                cancel_event=cancel_event,
            )


class TestDynamicAdapterAnthropic:
    """_call_anthropic 方法测试"""

    @pytest.mark.asyncio
    async def test_anthropic_non_streaming(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://api.anthropic.test.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        adapter = DynamicAdapter(provider)
        
        mock_response_data = {
            "content": [{"type": "text", "text": "Claude response"}],
            "usage": {"input_tokens": 10, "output_tokens": 20},
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                result = await adapter._call_anthropic(
                    model="claude-3-haiku-20240307", prompt="Hi", system_prompt="",
                    stream=False, temperature=0.7, max_tokens=100, thinking_budget=100,
                    cancel_event=None,
                )
                
                assert result["choices"][0]["message"]["content"] == "Claude response"

    @pytest.mark.asyncio
    async def test_anthropic_with_system_prompt(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://api.anthropic.test.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        adapter = DynamicAdapter(provider)
        
        mock_response_data = {
            "content": [{"type": "text", "text": "OK"}],
            "usage": {},
        }
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                await adapter._call_anthropic(
                    model="claude-3-haiku-20240307", prompt="Test", system_prompt="You are helpful",
                    stream=False, temperature=0.7, max_tokens=100, thinking_budget=100,
                    cancel_event=None,
                )
                
                call_args = mock_client.post.call_args
                assert call_args[1]["json"]["system"] == "You are helpful"

    @pytest.mark.asyncio
    async def test_anthropic_cancel_event(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://api.anthropic.test.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        adapter = DynamicAdapter(provider)
        
        cancel_event = asyncio.Event()
        cancel_event.set()
        
        with pytest.raises(asyncio.CancelledError, match="LLM 调用被取消"):
            await adapter._call_anthropic(
                model="claude-3-haiku-20240307", prompt="Test", system_prompt="",
                stream=False, temperature=0.7, max_tokens=100, thinking_budget=100,
                cancel_event=cancel_event,
            )

    @pytest.mark.skip(reason="流式响应 mock 复杂，需要真实环境测试")
    @pytest.mark.asyncio
    async def test_anthropic_streaming(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://api.anthropic.test.com",
            protocol=Protocol.ANTHROPIC, api_key="sk-ant-1234567890",
        )
        adapter = DynamicAdapter(provider)
        
        async def mock_aiter_lines():
            yield 'data: {"type": "content_block_delta", "delta": {"text": "Hello"}}\n'
            yield 'data: {"type": "content_block_delta", "delta": {"text": " World"}}\n'
            yield "data: [DONE]\n"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.aiter_lines = mock_aiter_lines
        mock_response.aclose = AsyncMock()
        
        mock_stream_cm = AsyncMock()
        mock_stream_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_cm.__aexit__ = AsyncMock(return_value=False)
        
        mock_client_instance = AsyncMock()
        mock_client_instance.stream.return_value = mock_stream_cm
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            stream_gen = await adapter._call_anthropic(
                model="claude-3-haiku-20240307", prompt="Test", system_prompt="",
                stream=True, temperature=0.7, max_tokens=100, thinking_budget=100,
                cancel_event=None,
            )
            
            chunks = []
            async for chunk in stream_gen:
                chunks.append(chunk)
            
            assert len(chunks) == 2


class TestDynamicAdapterEmbedding:
    """call_embedding 方法测试"""

    @pytest.mark.asyncio
    async def test_embedding_raises_not_implemented(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-test-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        with pytest.raises(NotImplementedError, match="动态供应商不支持 embedding"):
            await adapter.call_embedding(model="embedding-model", input_text="test")


class TestDynamicAdapterTimeout:
    """超时配置测试"""

    def test_adapter_default_timeout(self):
        provider = DynamicProvider(
            id="test", name="Test", base_url="http://test.com",
            protocol=Protocol.OPENAI, api_key="sk-openai-123456789",
        )
        adapter = DynamicAdapter(provider)
        
        assert hasattr(adapter, 'timeout')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
