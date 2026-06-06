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

# 适配器实例缓存
# _adapter_cache: 平台默认 config（无用户 Key），按 provider 缓存
# _user_adapter_cache: 用户自定义 config（带用户 Key），按 (provider, api_key_hash) 缓存
_adapter_cache: Dict[ModelProvider, BaseProviderAdapter] = {}
_user_adapter_cache: Dict[tuple, BaseProviderAdapter] = {}
_USER_ADAPTER_CACHE_MAX = 256
_adapter_cache_lock = asyncio.Lock()


class LLMCallError(Exception):
    """LLM 调用基础异常"""
    def __init__(self, message: str, status_code: int = 500):
        super().__init__(message)
        self.status_code = status_code
        self.message = message


class UserAPIKeyNotFoundError(LLMCallError):
    """用户 API Key 未找到或已过期"""
    def __init__(self, message: str = "用户 API Key 未找到或已过期，请重新配置"):
        super().__init__(message, status_code=401)


class ProviderAPIKeyNotConfiguredError(LLMCallError):
    """供应商 API Key 未配置"""
    def __init__(self, provider: str):
        super().__init__(
            f"{provider} 供应商的 API Key 未配置，请在 Settings → API Key 管理中添加",
            status_code=401,
        )


def _make_user_cache_key(provider: ModelProvider, api_key: str) -> tuple:
    """用户 Adapter 缓存键：避免存明文 Key，使用 SHA-256 前 16 字节"""
    import hashlib
    api_key_hash = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return (provider, api_key_hash)


async def get_adapter(provider: ModelProvider, config: Optional[ProviderConfig] = None) -> BaseProviderAdapter:
    """获取供应商适配器实例（带缓存）"""
    if provider not in ADAPTER_FACTORIES:
        raise ValueError(f"Unknown provider: {provider}")

    if config is None:
        # 使用默认 config（平台 Key），按 provider 缓存
        async with _adapter_cache_lock:
            if provider in _adapter_cache:
                return _adapter_cache[provider]
            cfg = settings.get_provider_registry().get(provider)
            if cfg is None:
                raise RuntimeError(f"Provider {provider.value} is not configured")
            adapter = ADAPTER_FACTORIES[provider](cfg)
            _adapter_cache[provider] = adapter
            return adapter

    # 自定义 config（用户 API Key），按 (provider, api_key_hash) 缓存
    cache_key = _make_user_cache_key(provider, config.api_key)
    async with _adapter_cache_lock:
        if cache_key in _user_adapter_cache:
            return _user_adapter_cache[cache_key]

        adapter = ADAPTER_FACTORIES[provider](config)

        # LRU 淘汰：超过上限时清掉一半
        if len(_user_adapter_cache) >= _USER_ADAPTER_CACHE_MAX:
            half = _USER_ADAPTER_CACHE_MAX // 2
            for _ in range(half):
                _user_adapter_cache.pop(next(iter(_user_adapter_cache)))

        _user_adapter_cache[cache_key] = adapter
        return adapter


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
    messages: Optional[list] = None,
    disable_fallback: bool = False,
) -> Union[dict, AsyncIterator[str]]:
    """
    统一模型调用函数（带故障转移）
    
    Args:
        model: 模型名称
        prompt: 用户提示（当 messages 为 None 时用于构建消息）
        system_prompt: 系统提示
        stream: 是否流式输出
        temperature: 温度参数
        max_tokens: 最大输出 token
        thinking_budget: 思考 token 预算
        timeout: 超时时间（秒）
        cancel_event: 取消事件
        api_key_token: 用户 API Key Token（用于从 Redis 获取用户自定义 Key）
        provider_id: 动态供应商 ID（直接指定动态供应商调用）
        messages: 原始消息列表（多模态场景），传入时忽略 prompt/system_prompt
        disable_fallback: 禁用降级（用户降级链偏好为 disabled 时）
    
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
            # 复用 ProviderRouter.route() 查 MODEL_PROVIDER_MAP 完整表
            router = ProviderRouter.get_instance(settings.get_provider_registry())
            provider = router.route(model)
            if provider:
                try:
                    config = ProviderConfig(
                        provider=provider,
                        api_key=api_key,
                        base_url=_get_provider_base_url(provider),
                    )
                    adapter = await get_adapter(provider, config)
                    adapter.timeout = timeout
                    logger.debug(f"使用用户自定义 Key 调用模型: {model}（供应商：{provider.value}）")
                except Exception as e:
                    logger.warning(f"创建用户自定义适配器失败：{e}")
        else:
            # 用户提供了 api_key_token，但 Redis 中找不到对应 Key
            # 明确报错，避免静默使用空 Key 走"系统默认"（Bearer 空字符串 → 401 死循环）
            raise UserAPIKeyNotFoundError()
    
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
            adapter = await get_adapter(primary_provider)
            adapter.timeout = timeout
        except Exception as e:
            if disable_fallback:
                raise RuntimeError(f"Provider {primary_provider.value} failed and fallback is disabled: {e}") from e

            logger.warning(f"Primary provider {primary_provider.value} failed: {e}")

            fallback_providers = router.get_fallback_providers(primary_provider)
            last_error = e

            for fallback in fallback_providers:
                try:
                    logger.info(f"Trying fallback provider: {fallback.value}")
                    adapter = await get_adapter(fallback)
                    adapter.timeout = timeout
                    break
                except Exception as fallback_error:
                    logger.warning(f"Fallback provider {fallback.value} failed: {fallback_error}")
                    last_error = fallback_error
                    continue
            
            if adapter is None:
                raise RuntimeError(f"All providers failed. Last error: {last_error}") from last_error

    # 校验 adapter 已绑定有效 api_key（避免空 Key 走到 HTTP 层变 Bearer 401）
    if not adapter.api_key:
        raise ProviderAPIKeyNotConfiguredError(adapter.provider.value)

    try:
        return await adapter.call_llm(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            cancel_event=cancel_event,
            messages=messages,
        )
    except Exception as e:
        # 流式调用失败时尝试 fallback（仅在流式未开始前的失败）
        if stream and not disable_fallback:
            logger.warning(f"Stream call failed before streaming started, attempting fallback: {e}")
            router = ProviderRouter.get_instance(settings.get_provider_registry())
            primary_provider = router.route(model)
            fallback_providers = router.get_fallback_providers(primary_provider)
            
            for fallback in fallback_providers:
                try:
                    # 检查模型是否可能在 fallback 供应商可用
                    fallback_model = router.route(model)
                    if fallback_model != fallback:
                        logger.debug(f"模型 {model} 不在 fallback 供应商 {fallback.value}，跳过")
                        continue
                    fallback_adapter = await get_adapter(fallback)
                    fallback_adapter.timeout = timeout
                    logger.info(f"Stream fallback to {fallback.value}")
                    return await fallback_adapter.call_llm(
                        model=model,
                        prompt=prompt,
                        system_prompt=system_prompt,
                        stream=True,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        thinking_budget=thinking_budget,
                        cancel_event=cancel_event,
                        messages=messages,
                    )
                except Exception as fallback_error:
                    logger.warning(f"Stream fallback {fallback.value} also failed: {fallback_error}")
                    continue
        raise


def _get_user_api_key_from_token(token: str) -> Optional[str]:
    """
    从 token 获取用户 API Key（从 Redis）
    
    Args:
        token: 用户 token
        
    Returns:
        API Key 或 None
    """
    if not token or len(token) < 30:
        return None
    
    try:
        from app.services.apikey_manager import get_apikey_manager
        apikey_manager = get_apikey_manager()
        return apikey_manager.get_key_by_token(token)
    except Exception as e:
        logger.warning(f"从 Redis 获取用户 Key 失败：{e}")
        return None


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
