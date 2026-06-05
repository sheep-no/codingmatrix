"""
统一 LLM 调用层

封装 call_llm，添加并发控制、超时保护、成本追踪、性能记录。
替代各文件中重复实现的 LLM 调用逻辑。

用法：
    from app.agent.llm_client import LLMClient

    client = LLMClient(model_name="Qwen/Qwen3.5-4B", cost_tracker=tracker)
    result = await client.call("你好", system_prompt="你是一个助手")
"""

import time
import asyncio
import logging
from typing import Optional, Dict, Any

import httpx
from app.utils import call_llm
from app.agent.dynamic_model_router import get_dynamic_router, LayeredModelRouter

logger = logging.getLogger(__name__)

MAX_CONCURRENT_LLM_CALLS = 6
_global_semaphore: Optional[asyncio.Semaphore] = None


def get_global_semaphore() -> asyncio.Semaphore:
    global _global_semaphore
    if _global_semaphore is None:
        _global_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
    return _global_semaphore


class LLMClientError(Exception):
    """LLM 调用不可恢复错误"""
    pass


class LLMClient:
    """统一 LLM 客户端

    Args:
        model_name: 模型名称
        task_type: 任务类型（generate/review/test）
        api_key_token: API Key
        provider_id: 提供商 ID
        cost_tracker: 成本追踪器（可选）
        complexity: 复杂度级别（影响超时和重试）
        semaphore: 自定义并发信号量（默认使用全局）
    """

    def __init__(
        self,
        model_name: str,
        task_type: str = "generate",
        api_key_token: Optional[str] = None,
        provider_id: Optional[str] = None,
        cost_tracker=None,
        complexity: str = "medium",
        semaphore: Optional[asyncio.Semaphore] = None,
    ):
        self.model_name = model_name
        self.task_type = task_type
        self.api_key_token = api_key_token
        self.provider_id = provider_id
        self._cost_tracker = cost_tracker
        self._complexity = complexity
        self._semaphore = semaphore if semaphore is not None else get_global_semaphore()
        self._model_config = LayeredModelRouter.get_model_config(
            model_name, task_type=task_type, api_key_token=api_key_token
        )

    async def call(self, prompt: str, system_prompt: str = "", stream: bool = False) -> str:
        """调用 LLM

        Args:
            prompt: 用户 prompt
            system_prompt: 系统 prompt
            stream: 是否流式

        Returns:
            LLM 输出文本

        Raises:
            LLMClientError: 不可恢复错误（401/403）
        """
        start_time = time.time()
        await (await get_dynamic_router()).start_call(self.model_name)

        try:
            async def _do_call():
                return await call_llm(
                    model=self.model_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    stream=stream,
                    max_tokens=self._model_config["max_tokens"],
                    thinking_budget=self._model_config["thinking_budget"],
                    temperature=self._model_config["temperature"],
                    api_key_token=self.api_key_token,
                    provider_id=self.provider_id,
                )

            call_timeout = self._model_config.get("timeout", 300)

            if self._semaphore:
                async with self._semaphore:
                    response = await asyncio.wait_for(_do_call(), timeout=call_timeout)
            else:
                response = await asyncio.wait_for(_do_call(), timeout=call_timeout)

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(
                self.model_name, success=True, latency_ms=latency_ms
            )

            # 成本追踪
            usage = response.get("usage", {})
            if usage and self._cost_tracker:
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                cost_per_1m_input = self._model_config.get("cost_per_1m_input", 0.0)
                cost_per_1m_output = self._model_config.get("cost_per_1m_output", 0.0)
                cost_usd = (prompt_tokens * cost_per_1m_input + completion_tokens * cost_per_1m_output) / 1_000_000
                self._cost_tracker.add_usage(self.model_name, prompt_tokens, completion_tokens, cost_usd)

            return content

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(
                self.model_name, success=False, latency_ms=latency_ms, error="timeout"
            )
            logger.error(f"LLM 调用超时 ({call_timeout}s): {self.model_name}")
            return ""

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(
                self.model_name, success=False, latency_ms=latency_ms, error=str(e)
            )
            logger.error(f"LLM 调用失败: {self.model_name} - {e}")

            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                raise LLMClientError(
                    f"认证失败 (HTTP {e.response.status_code})，请检查 API Key 配置"
                ) from e

            return ""

    @property
    def model_config(self) -> Dict:
        return self._model_config

    @property
    def max_tokens(self) -> int:
        return self._model_config.get("max_tokens", 4096)

    @property
    def thinking_budget(self) -> int:
        return self._model_config.get("thinking_budget", 0)
