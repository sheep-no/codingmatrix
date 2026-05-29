"""
多供应商模型调用系统 - 统一调用入口

提供统一的 `call_llm()` 函数，自动路由到对应供应商适配器。
支持用户自定义 API Key（通过 user_model_overrides 传入 token）。
支持动态供应商（自定义 base_url + 协议类型）。
"""

import asyncio
import logging
from typing import AsyncIterator, Optional, Union, Dict

from app.core.config import settings
from app.utils.aicloud.providers import ModelProvider, ProviderConfig
from app.utils.aicloud.provider_router import ProviderRouter
from app.utils.aicloud.adapters.base import BaseProviderAdapter
from app.utils.aicloud.adapters.siliconflow import SiliconFlowAdapter
from app.utils.aicloud.adapters.dashscope import DashScopeAdapter
from app.utils.aicloud.adapters.zhipu import ZhipuAdapter
from app.utils.aicloud.adapters.openai import OpenAIAdapter
from app.utils.aicloud.adapters.deepseek import DeepSeekAdapter
from app.utils.aicloud.adapters.anthropic import AnthropicAdapter
from app.utils.aicloud.adapters.dynamic import DynamicAdapter
from app.utils.aicloud.dynamic_provider import DynamicProvider

logger = logging.getLogger(__name__)

# 适配器工厂
ADAPTER_FACTORIES = {
    ModelProvider.SILICONFLOW: lambda cfg: SiliconFlowAdapter(cfg),
    ModelProvider.DASHSCOPE: lambda cfg: DashScopeAdapter(cfg),
    ModelProvider.ZHIPU: lambda cfg: ZhipuAdapter(cfg),
    ModelProvider.DEEPSEEK: lambda cfg: DeepSeekAdapter(cfg),
    ModelProvider.OPENAI: lambda cfg: OpenAIAdapter(cfg),
    ModelProvider.ANTHROPIC: lambda cfg: AnthropicAdapter(cfg),
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
    api_key_token: Optional[str] = None,
    provider_id: Optional[str] = None,
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
        api_key_token: 用户 API Key Token（用于从 Redis 获取用户自定义 Key）
        provider_id: 动态供应商 ID（直接指定动态供应商调用）
    
    Returns:
        非流式: OpenAI 兼容响应字典
        流式: AsyncIterator[str]
    """
    adapter = None
    
    # 优先级 1: 直接指定动态供应商
    if provider_id:
        from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
        manager = get_dynamic_provider_manager()
        provider = manager.get(provider_id)
        if provider and provider.enabled:
            adapter = DynamicAdapter(provider)
            adapter.timeout = timeout
            logger.debug(f"使用动态供应商 {provider.name} 调用模型: {model}")
        else:
            logger.warning(f"动态供应商 {provider_id} 不存在或已禁用，降级到其他路由")
    
    # 优先级 2: 用户 API Key Token（内置供应商）
    if adapter is None and api_key_token:
        api_key = _get_user_api_key_from_token(api_key_token)
        if api_key:
            provider = _detect_provider_from_model(model)
            if provider:
                try:
                    config = ProviderConfig(
                        provider=provider,
                        api_key=api_key,
                        base_url=_get_provider_base_url(provider),
                    )
                    adapter = get_adapter(provider, config)
                    adapter.timeout = timeout
                    logger.debug(f"使用用户自定义 Key 调用模型: {model}")
                except Exception as e:
                    logger.warning(f"创建用户自定义适配器失败：{e}，降级到系统默认 Key")
    
    # 优先级 3: 检查动态供应商中是否有该模型
    if adapter is None:
        from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
        manager = get_dynamic_provider_manager()
        dp = manager.get_by_model(model)
        if dp:
            adapter = DynamicAdapter(dp)
            adapter.timeout = timeout
            logger.debug(f"通过动态供应商 {dp.name} 调用模型: {model}")
    
    # 优先级 4: 系统默认路由
    if adapter is None:
        router = ProviderRouter.get_instance(settings.get_provider_registry())
        primary_provider = router.route(model)
        
        try:
            adapter = get_adapter(primary_provider)
            adapter.timeout = timeout
        except Exception as e:
            logger.warning(f"Primary provider {primary_provider.value} failed: {e}")
            
            if stream:
                raise
            
            fallback_providers = router.get_fallback_providers(primary_provider)
            last_error = e
            
            for fallback in fallback_providers:
                try:
                    logger.info(f"Trying fallback provider: {fallback.value}")
                    adapter = get_adapter(fallback)
                    adapter.timeout = timeout
                    break
                except Exception as fallback_error:
                    logger.warning(f"Fallback provider {fallback.value} failed: {fallback_error}")
                    last_error = fallback_error
                    continue
            
            if adapter is None:
                raise RuntimeError(f"All providers failed. Last error: {last_error}") from last_error
    
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


def _get_user_api_key_from_token(token: str) -> Optional[str]:
    """
    从 token 获取用户 API Key（从 Redis）
    
    Args:
        token: 用户 token
        
    Returns:
        API Key 或 None
    """
    # 如果 token 不是 UUID 格式，说明不是用户自定义 Key
    if not token or len(token) < 30:
        return None
    
    try:
        from app.services.apikey_manager import get_apikey_manager
        # 临时使用默认用户 ID（实际应从 session 中获取）
        user_id = "default_user"
        apikey_manager = get_apikey_manager()
        return apikey_manager.get_key(user_id, token)
    except Exception as e:
        logger.warning(f"从 Redis 获取用户 Key 失败：{e}")
        return None


def _detect_provider_from_model(model: str) -> Optional[ModelProvider]:
    """
    根据模型名称检测供应商
    
    Args:
        model: 模型名称
        
    Returns:
        ModelProvider 或 None
    """
    model_lower = model.lower()
    
    if "qwen" in model_lower or "dashscope" in model_lower:
        return ModelProvider.DASHSCOPE
    elif "glm" in model_lower or "zhipu" in model_lower:
        return ModelProvider.ZHIPU
    elif "deepseek" in model_lower:
        return ModelProvider.DEEPSEEK
    elif "claude" in model_lower:
        return ModelProvider.ANTHROPIC
    elif "gpt" in model_lower or "openai" in model_lower:
        return ModelProvider.OPENAI
    else:
        # 默认使用 SiliconFlow
        return ModelProvider.SILICONFLOW


def _get_provider_base_url(provider: ModelProvider) -> str:
    """获取供应商 Base URL"""
    urls = {
        ModelProvider.SILICONFLOW: "https://api.siliconflow.cn/v1",
        ModelProvider.DASHSCOPE: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        ModelProvider.ZHIPU: "https://open.bigmodel.cn/api/paas/v4",
        ModelProvider.DEEPSEEK: "https://api.deepseek.com/v1",
        ModelProvider.OPENAI: "https://api.openai.com/v1",
        ModelProvider.ANTHROPIC: "https://api.anthropic.com",
    }
    return urls.get(provider, "https://api.siliconflow.cn/v1")


async def call_dynamic_llm(
    provider_id: str,
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
    通过动态供应商调用 LLM
    
    Args:
        provider_id: 动态供应商 ID
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
    from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
    
    manager = get_dynamic_provider_manager()
    provider = manager.get(provider_id)
    
    if not provider:
        raise RuntimeError(f"动态供应商不存在: {provider_id}")
    
    if not provider.enabled:
        raise RuntimeError(f"动态供应商已禁用: {provider.name}")
    
    adapter = DynamicAdapter(provider)
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
