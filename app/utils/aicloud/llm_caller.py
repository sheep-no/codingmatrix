"""
多供应商模型调用系统 - 统一调用入口

提供统一的 `call_llm()` 函数，自动路由到对应供应商适配器。
"""

import asyncio
import logging
from typing import AsyncIterator, Optional, Union

from app.core.config import settings
from app.utils.aicloud.providers import ModelProvider, ProviderConfig
from app.utils.aicloud.provider_router import ProviderRouter
from app.utils.aicloud.adapters.base import BaseProviderAdapter
from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
from app.utils.aicloud.adapters.dashscope import DashScopeAdapter
from app.utils.aicloud.adapters.zhipu import ZhipuAdapter
from app.utils.aicloud.adapters.openai import OpenAIAdapter

logger = logging.getLogger(__name__)

# 适配器工厂
ADAPTER_FACTORIES = {
    ModelProvider.SILICONFLOW: lambda cfg: SiliconFlowAdapter(cfg),
    ModelProvider.DASHSCOPE: lambda cfg: DashScopeAdapter(cfg),
    ModelProvider.ZHIPU: lambda cfg: ZhipuAdapter(cfg),
    ModelProvider.OPENAI: lambda cfg: OpenAIAdapter(cfg),
}


def get_adapter(provider: ModelProvider, config: Optional[ProviderConfig] = None) -> BaseProviderAdapter:
    """获取供应商适配器实例"""
    if provider not in ADAPTER_FACTORIES:
        raise ValueError(f"Unknown provider: {provider}")
    
    if config is None:
        config = settings.get_provider_registry().get(provider)
        if config is None:
            raise RuntimeError(f"Provider {provider.value} is not configured")
    
    return ADAPTER_FACTORIES[provider](config)


async def call_llm(
    model: str,
    prompt: str,
    system_prompt: str = "",
    stream: bool = False,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    thinking_budget: int = 4096,
    timeout: float = 360.0,
    cancel_event: Optional[asyncio.Event] = None,
) -> Union[dict, AsyncIterator[str]]:
    """
    统一模型调用函数（带故障转移）
    
    Args:
        model: 模型名称
        prompt: 用户提示
        system_prompt: 系统提示
        stream: 是否流式输出
        temperature: 温度参数
        max_tokens: 最大输出 token
        thinking_budget: 思考 token 预算
        timeout: 超时时间（秒）
        cancel_event: 取消事件
    
    Returns:
        非流式: OpenAI 兼容响应字典
        流式: AsyncIterator[str]
    """
    router = ProviderRouter.get_instance(settings.get_provider_registry())
    primary_provider = router.route(model)
    
    # 尝试主供应商
    try:
        adapter = get_adapter(primary_provider)
        adapter.timeout = timeout
        return await adapter.call_llm(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            cancel_event=cancel_event,
        )
    except Exception as e:
        logger.warning(f"Primary provider {primary_provider.value} failed: {e}")
        
        # 故障转移（流式模式不重试）
        if stream:
            raise
        
        fallback_providers = router.get_fallback_providers(primary_provider)
        last_error = e
        
        for fallback in fallback_providers:
            try:
                logger.info(f"Trying fallback provider: {fallback.value}")
                adapter = get_adapter(fallback)
                adapter.timeout = timeout
                return await adapter.call_llm(
                    model=model,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    stream=False,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    thinking_budget=thinking_budget,
                    cancel_event=cancel_event,
                )
            except Exception as fallback_error:
                logger.warning(f"Fallback provider {fallback.value} failed: {fallback_error}")
                last_error = fallback_error
                continue
        
        raise RuntimeError(f"All providers failed. Last error: {last_error}") from last_error
