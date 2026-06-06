"""
统一 LLM 调用层单元测试

覆盖：
- LLMClient 初始化
- LLMClient.call 正常调用、超时、异常、认证失败
- 全局 Semaphore
- 模型配置属性
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent.llm_client import (
    LLMClient,
    LLMClientError,
    MAX_CONCURRENT_LLM_CALLS,
    get_global_semaphore,
)


class TestGlobalSemaphore:
    def test_semaphore_returns_same_instance(self):
        s1 = get_global_semaphore()
        s2 = get_global_semaphore()
        assert s1 is s2

    def test_semaphore_value(self):
        s = get_global_semaphore()
        assert s._value == MAX_CONCURRENT_LLM_CALLS


class TestLLMClientInit:
    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_global_semaphore")
    def test_init_defaults(self, mock_sem, mock_router):
        mock_router.get_model_config.return_value = {
            "max_tokens": 4096,
            "thinking_budget": 0,
            "temperature": 0.7,
            "timeout": 300,
        }
        mock_sem.return_value = MagicMock()
        client = LLMClient(model_name="test-model")
        assert client.model_name == "test-model"
        assert client.task_type == "generate"
        assert client.api_key_token is None
        assert client.provider_id is None

    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_global_semaphore")
    def test_init_with_params(self, mock_sem, mock_router):
        mock_router.get_model_config.return_value = {
            "max_tokens": 8192,
            "thinking_budget": 4096,
            "temperature": 0.3,
            "timeout": 120,
        }
        mock_sem.return_value = MagicMock()
        client = LLMClient(
            model_name="gpt-4",
            task_type="review",
            api_key_token="sk-test",
            provider_id="openai",
            complexity="large",
        )
        assert client.model_name == "gpt-4"
        assert client.task_type == "review"
        assert client.api_key_token == "sk-test"
        assert client.provider_id == "openai"

    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_global_semaphore")
    def test_model_config_property(self, mock_sem, mock_router):
        config = {"max_tokens": 4096, "thinking_budget": 2048, "temperature": 0.5}
        mock_router.get_model_config.return_value = config
        mock_sem.return_value = MagicMock()
        client = LLMClient(model_name="test")
        assert client.model_config == config

    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_global_semaphore")
    def test_max_tokens_property(self, mock_sem, mock_router):
        mock_router.get_model_config.return_value = {"max_tokens": 8192}
        mock_sem.return_value = MagicMock()
        client = LLMClient(model_name="test")
        assert client.max_tokens == 8192

    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_global_semaphore")
    def test_thinking_budget_property(self, mock_sem, mock_router):
        mock_router.get_model_config.return_value = {"thinking_budget": 4096}
        mock_sem.return_value = MagicMock()
        client = LLMClient(model_name="test")
        assert client.thinking_budget == 4096


class TestLLMClientCall:
    @pytest.mark.asyncio
    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_dynamic_router")
    @patch("app.agent.llm_client.call_llm")
    async def test_call_success(self, mock_call_llm, mock_get_router, mock_router_cls):
        mock_router_cls.get_model_config.return_value = {
            "max_tokens": 4096, "thinking_budget": 0,
            "temperature": 0.7, "timeout": 300,
        }
        mock_router = AsyncMock()
        mock_get_router.return_value = mock_router
        mock_call_llm.return_value = {
            "choices": [{"message": {"content": "Hello, world!"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }

        client = LLMClient(model_name="test-model")
        result = await client.call("Hi")
        assert result == "Hello, world!"
        mock_router.start_call.assert_called_once()
        mock_router.record_call.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_dynamic_router")
    @patch("app.agent.llm_client.call_llm")
    async def test_call_timeout(self, mock_call_llm, mock_get_router, mock_router_cls):
        mock_router_cls.get_model_config.return_value = {
            "max_tokens": 4096, "thinking_budget": 0,
            "temperature": 0.7, "timeout": 0.001,
        }
        mock_router = AsyncMock()
        mock_get_router.return_value = mock_router

        async def slow_call(*args, **kwargs):
            await asyncio.sleep(1)
            return {}

        mock_call_llm.side_effect = slow_call

        client = LLMClient(model_name="test-model")
        with pytest.raises(LLMClientError, match="LLM 调用超时"):
            await client.call("Hi")

    @pytest.mark.asyncio
    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_dynamic_router")
    @patch("app.agent.llm_client.call_llm")
    async def test_call_auth_error_raises(self, mock_call_llm, mock_get_router, mock_router_cls):
        mock_router_cls.get_model_config.return_value = {
            "max_tokens": 4096, "thinking_budget": 0,
            "temperature": 0.7, "timeout": 300,
        }
        mock_router = AsyncMock()
        mock_get_router.return_value = mock_router

        import httpx
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_call_llm.side_effect = httpx.HTTPStatusError(
            "Unauthorized", request=MagicMock(), response=mock_response
        )

        client = LLMClient(model_name="test-model")
        with pytest.raises(LLMClientError, match="认证失败"):
            await client.call("Hi")

    @pytest.mark.asyncio
    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_dynamic_router")
    @patch("app.agent.llm_client.call_llm")
    async def test_call_generic_error_raises(self, mock_call_llm, mock_get_router, mock_router_cls):
        mock_router_cls.get_model_config.return_value = {
            "max_tokens": 4096, "thinking_budget": 0,
            "temperature": 0.7, "timeout": 300,
        }
        mock_router = AsyncMock()
        mock_get_router.return_value = mock_router
        mock_call_llm.side_effect = RuntimeError("connection failed")

        client = LLMClient(model_name="test-model")
        with pytest.raises(LLMClientError, match="LLM 调用失败"):
            await client.call("Hi")

    @pytest.mark.asyncio
    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_dynamic_router")
    @patch("app.agent.llm_client.call_llm")
    async def test_call_with_cost_tracker(self, mock_call_llm, mock_get_router, mock_router_cls):
        mock_router_cls.get_model_config.return_value = {
            "max_tokens": 4096, "thinking_budget": 0,
            "temperature": 0.7, "timeout": 300,
            "cost_per_1m_input": 0.5,
            "cost_per_1m_output": 1.0,
        }
        mock_router = AsyncMock()
        mock_get_router.return_value = mock_router
        mock_call_llm.return_value = {
            "choices": [{"message": {"content": "response"}}],
            "usage": {"prompt_tokens": 1000, "completion_tokens": 500},
        }

        mock_tracker = MagicMock()
        client = LLMClient(model_name="test-model", cost_tracker=mock_tracker)
        result = await client.call("Hi")
        assert result == "response"
        mock_tracker.add_usage.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.agent.llm_client.LayeredModelRouter")
    @patch("app.agent.llm_client.get_dynamic_router")
    @patch("app.agent.llm_client.call_llm")
    async def test_call_empty_choices(self, mock_call_llm, mock_get_router, mock_router_cls):
        mock_router_cls.get_model_config.return_value = {
            "max_tokens": 4096, "thinking_budget": 0,
            "temperature": 0.7, "timeout": 300,
        }
        mock_router = AsyncMock()
        mock_get_router.return_value = mock_router
        mock_call_llm.return_value = {"choices": []}

        client = LLMClient(model_name="test-model")
        result = await client.call("Hi")
        assert result == ""


class TestLLMClientError:
    def test_is_exception(self):
        err = LLMClientError("test")
        assert isinstance(err, Exception)
