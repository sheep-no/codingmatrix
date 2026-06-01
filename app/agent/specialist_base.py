import re
import json
import time
import logging
from typing import Optional, Dict, List, Any
from dataclasses import dataclass
import asyncio

from app.utils.aicloud import call_llm
from app.agent.complexity import ComplexityAnalysis
from app.agent.dynamic_model_router import get_dynamic_router, LayeredModelRouter
from app.agent.tracing import traced

logger = logging.getLogger(__name__)

MAX_CONCURRENT_LLM_CALLS = 4


class Specialist:
    """专业角色基类"""

    _semaphore: Optional[asyncio.Semaphore] = None
    _cost_tracker = None  # 成本追踪器，由 orchestrator 设置

    @classmethod
    def set_semaphore(cls, sem: asyncio.Semaphore):
        cls._semaphore = sem

    @classmethod
    def set_cost_tracker(cls, tracker):
        cls._cost_tracker = tracker

    def __init__(self, role_name: str, model_name: str, task_type: str = "generate", api_key_token: Optional[str] = None, provider_id: Optional[str] = None):
        self.role_name = role_name
        self.model_name = model_name
        self.task_type = task_type
        self.model_config = LayeredModelRouter.get_model_config(model_name, task_type=task_type)
        self.api_key_token = api_key_token
        self.provider_id = provider_id

    @traced("specialist.call_llm", attributes={"component": "specialist"})
    async def call_llm(self, prompt: str, system_prompt: str = "") -> str:
        """调用 LLM（带并发限制和动态指标记录，支持多供应商）"""
        start_time = time.time()
        await (await get_dynamic_router()).start_call(self.model_name)

        try:
            async def _do_call():
                return await call_llm(
                    model=self.model_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    stream=False,
                    max_tokens=self.model_config["max_tokens"],
                    thinking_budget=self.model_config["thinking_budget"],
                    temperature=self.model_config["temperature"],
                    api_key_token=self.api_key_token,
                    provider_id=self.provider_id,
                )

            if self._semaphore:
                async with self._semaphore:
                    response = await _do_call()
            else:
                response = await _do_call()

            content = response.get("choices", [{}])[0].get("message", {}).get("content", "")
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(self.model_name, success=True, latency_ms=latency_ms)
            
            # 追踪 token 使用量
            usage = response.get("usage", {})
            if usage and self._cost_tracker:
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                # 估算成本（美元）
                cost_per_1m_input = self.model_config.get("cost_per_1m_input", 0.0)
                cost_per_1m_output = self.model_config.get("cost_per_1m_output", 0.0)
                cost_usd = (prompt_tokens * cost_per_1m_input + completion_tokens * cost_per_1m_output) / 1000000
                self._cost_tracker.add_usage(self.model_name, prompt_tokens, completion_tokens, cost_usd)
            
            return content
        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(self.model_name, success=False, latency_ms=latency_ms, error=str(e))
            logger.error(f"{self.role_name} 调用 LLM 失败: {e}")
            return ""