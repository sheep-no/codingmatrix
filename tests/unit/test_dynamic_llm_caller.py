"""
call_dynamic_llm 函数单元测试
"""
import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock

from app.utils.aicloud.dynamic_provider import Protocol, DynamicProvider, get_dynamic_provider_manager


class TestCallDynamicLLM:
    """call_dynamic_llm 函数测试"""

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_nonexistent_provider(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        with pytest.raises(RuntimeError, match="动态供应商不存在"):
            await call_dynamic_llm(
                provider_id="nonexistent-id",
                model="gpt-3.5-turbo",
                prompt="Hello",
            )

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_disabled_provider(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Disabled Test", "http://api.test.com", "openai", "sk-disabled-12345")
        provider.enabled = False
        
        with pytest.raises(RuntimeError, match="动态供应商已禁用"):
            await call_dynamic_llm(
                provider_id=provider.id,
                model="gpt-3.5-turbo",
                prompt="Hello",
            )

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_openai_success(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("OpenAI Test", "http://api.test.com/v1", "openai", "sk-openai-123456789")
        
        mock_response_data = {
            "choices": [{"message": {"content": "Hello from OpenAI!"}}],
            "usage": {"total_tokens": 30},
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
                result = await call_dynamic_llm(
                    provider_id=provider.id,
                    model="gpt-3.5-turbo",
                    prompt="Hello",
                    system_prompt="You are a helpful assistant",
                    temperature=0.7,
                    max_tokens=100,
                )
                
                assert result["choices"][0]["message"]["content"] == "Hello from OpenAI!"

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_anthropic_success(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Anthropic Test", "http://api.anthropic.com", "anthropic", "sk-ant-1234567890")
        
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
                result = await call_dynamic_llm(
                    provider_id=provider.id,
                    model="claude-3-haiku-20240307",
                    prompt="Hello",
                    system_prompt="You are helpful",
                )
                
                assert result["choices"][0]["message"]["content"] == "Hello from Claude!"

    @pytest.mark.skip(reason="流式响应 mock 复杂，需要真实环境测试")
    @pytest.mark.asyncio
    async def test_call_dynamic_llm_streaming(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Stream Test", "http://api.test.com/v1", "openai", "sk-stream-123456789")
        
        async def mock_stream():
            yield 'data: {"choices": [{"delta": {"content": "Hello"}}]}\n'
            yield 'data: {"choices": [{"delta": {"content": " World"}}]}\n'
            yield "data: [DONE]\n"
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.aiter_lines = mock_stream
        mock_response.aclose = AsyncMock()
        
        mock_client_instance = AsyncMock()
        mock_client_instance.stream.return_value.__aenter__.return_value = mock_response
        mock_client_instance.stream.return_value.__aexit__ = AsyncMock()
        
        with patch('httpx.AsyncClient') as mock_client:
            mock_client.return_value.__aenter__.return_value = mock_client_instance
            
            stream_gen = await call_dynamic_llm(
                provider_id=provider.id,
                model="gpt-3.5-turbo",
                prompt="Hello",
                stream=True,
            )
            
            chunks = []
            async for chunk in stream_gen:
                chunks.append(chunk)
            
            assert len(chunks) == 2

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_custom_timeout(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Timeout Test", "http://api.test.com", "openai", "sk-timeout-12345")
        
        mock_response_data = {"choices": [{"message": {"content": "OK"}}], "usage": {}}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=lambda func, **kwargs: func()):
                await call_dynamic_llm(
                    provider_id=provider.id,
                    model="gpt-3.5-turbo",
                    prompt="Test",
                    timeout=600.0,
                )

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_with_cancel_event(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Cancel Test", "http://api.test.com", "openai", "sk-cancel-12345")
        
        cancel_event = asyncio.Event()
        cancel_event.set()
        
        with pytest.raises(asyncio.CancelledError, match="LLM 调用被取消"):
            await call_dynamic_llm(
                provider_id=provider.id,
                model="gpt-3.5-turbo",
                prompt="Test",
                cancel_event=cancel_event,
            )

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_http_error(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        from fastapi import HTTPException
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Error Test", "http://api.test.com", "openai", "sk-error-12345")
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_client = AsyncMock()
        mock_client.post.return_value = mock_response
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', return_value=mock_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=lambda func, **kwargs: func()):
                with pytest.raises(HTTPException):
                    await call_dynamic_llm(
                        provider_id=provider.id,
                        model="gpt-3.5-turbo",
                        prompt="Test",
                    )

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_custom_timeout(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Timeout Test", "http://api.test.com", "openai", "sk-timeout-12345")
        
        mock_response_data = {"choices": [{"message": {"content": "OK"}}], "usage": {}}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        # get_http_client is an async function, so we need AsyncMock
        mock_get_client = AsyncMock(return_value=mock_client)
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', mock_get_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                await call_dynamic_llm(
                    provider_id=provider.id,
                    model="gpt-3.5-turbo",
                    prompt="Test",
                    timeout=600.0,
                )

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_with_cancel_event(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Cancel Test", "http://api.test.com", "openai", "sk-cancel-12345")
        
        cancel_event = asyncio.Event()
        cancel_event.set()
        
        with pytest.raises(asyncio.CancelledError, match="LLM 调用被取消"):
            await call_dynamic_llm(
                provider_id=provider.id,
                model="gpt-3.5-turbo",
                prompt="Test",
                cancel_event=cancel_event,
            )

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_http_error(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        from fastapi import HTTPException
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Error Test", "http://api.test.com", "openai", "sk-error-12345")
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        mock_get_client = AsyncMock(return_value=mock_client)
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', mock_get_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                with pytest.raises(HTTPException):
                    await call_dynamic_llm(
                        provider_id=provider.id,
                        model="gpt-3.5-turbo",
                        prompt="Test",
                    )

    @pytest.mark.asyncio
    async def test_call_dynamic_llm_thinking_budget(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        provider = manager.add("Thinking Test", "http://api.test.com", "openai", "sk-thinking-12345")
        
        mock_response_data = {"choices": [{"message": {"content": "Thinking response"}}], "usage": {}}
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_response_data
        
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        
        async def mock_call_with_retry(func, **kwargs):
            return await func()
        
        mock_get_client = AsyncMock(return_value=mock_client)
        
        with patch('app.utils.aicloud.adapters.dynamic.get_http_client', mock_get_client):
            with patch('app.utils.aicloud.adapters.dynamic.call_with_retry', side_effect=mock_call_with_retry):
                result = await call_dynamic_llm(
                    provider_id=provider.id,
                    model="gpt-3.5-turbo",
                    prompt="Test",
                    thinking_budget=8192,
                )
                
                assert "Thinking response" in result["choices"][0]["message"]["content"]


class TestCallDynamicLLMIntegration:
    """call_dynamic_llm 集成测试"""

    @pytest.mark.asyncio
    async def test_call_different_providers(self):
        from app.utils.aicloud.llm_caller import call_dynamic_llm
        
        manager = get_dynamic_provider_manager()
        
        openai_provider = manager.add("OpenAI", "http://openai.test.com", "openai", "sk-openai-123456789")
        anthropic_provider = manager.add("Anthropic", "http://anthropic.test.com", "anthropic", "sk-ant-1234567890")
        
        assert openai_provider.protocol == Protocol.OPENAI
        assert anthropic_provider.protocol == Protocol.ANTHROPIC
        assert openai_provider.enabled == True
        assert anthropic_provider.enabled == True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
