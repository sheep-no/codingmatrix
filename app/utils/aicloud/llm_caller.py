"""
多供应商模型调用系统 - 统一调用入口

提供统一的 `call_llm()` 函数，自动路由到对应供应商适配器。
支持用户自定义 API Key（通过 user_model_overrides 传入 token）。
支持动态供应商（自定义 base_url + 协议类型）。
"""

import asyncio
from contextvars import ContextVar, Token
from dataclasses import dataclass
import json
import logging
import time
from typing import AsyncIterator, Optional, Union, Dict, Any

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


@dataclass
class LLMCallMetrics:
    """Request-scoped aggregate for logical model calls."""

    model_call_count: int = 0
    token_count: int = 0


_llm_call_metrics: ContextVar[Optional[LLMCallMetrics]] = ContextVar(
    "llm_call_metrics", default=None
)


def begin_llm_call_metrics() -> Token:
    """Start an isolated metrics scope for one API request."""
    return _llm_call_metrics.set(LLMCallMetrics())


def finish_llm_call_metrics(token: Token) -> Dict[str, int]:
    """Snapshot and close the active request metrics scope."""
    metrics = _llm_call_metrics.get() or LLMCallMetrics()
    _llm_call_metrics.reset(token)
    return {
        "model_call_count": metrics.model_call_count,
        "token_count": metrics.token_count,
    }


def _record_llm_response_metrics(result: Any) -> None:
    metrics = _llm_call_metrics.get()
    if metrics is None or not isinstance(result, dict):
        return
    usage = result.get("usage") or {}
    metrics.token_count += int(usage.get("total_tokens") or 0)


def _record_llm_call() -> None:
    metrics = _llm_call_metrics.get()
    if metrics is not None:
        metrics.model_call_count += 1


def _stream_usage_tokens(chunk: Any) -> int:
    if not isinstance(chunk, str):
        return 0
    payload = chunk.strip()
    if payload.startswith("data: "):
        payload = payload[6:]
    try:
        parsed = json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        return 0
    usage = parsed.get("usage") or {}
    return int(usage.get("total_tokens") or 0)


def _record_llm_stream_metrics(chunk: Any) -> None:
    """Record one standalone stream chunk for compatibility callers.

    Stream wrappers use the per-stream maximum below so cumulative provider
    usage fields are counted once. This helper retains the historical behavior
    for direct unit-test and integration callers that provide one chunk.
    """
    tokens = _stream_usage_tokens(chunk)
    metrics = _llm_call_metrics.get()
    if metrics is not None:
        metrics.token_count += tokens

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

# 429 重试配置
_RETRY_MAX_ATTEMPTS = 3
_MODEL_COOLDOWN_MIN = 15.0
_MODEL_COOLDOWN_MAX = 60.0
_model_cooldown_until: Dict[str, float] = {}


def reset_model_cooldowns() -> None:
    """Clear per-model 429 cooldowns (tests)."""
    _model_cooldown_until.clear()


def _is_rate_limit_error(exc: Exception) -> bool:
    if getattr(exc, "status_code", None) == 429:
        return True
    if getattr(getattr(exc, "response", None), "status_code", None) == 429:
        return True
    text = str(exc).lower()
    return "429" in text or "rate limit" in text or "too many requests" in text


def _retry_after_seconds(exc: Exception) -> float:
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None) if response is not None else None
    header = None
    if headers is not None and hasattr(headers, "get"):
        header = headers.get("Retry-After") or headers.get("retry-after")
    if header is not None:
        raw = str(header).strip()
        try:
            return min(max(float(raw), _MODEL_COOLDOWN_MIN), _MODEL_COOLDOWN_MAX)
        except ValueError:
            pass
    return _MODEL_COOLDOWN_MIN


def _set_model_cooldown(model: str, seconds: float) -> None:
    if not model:
        return
    delay = min(max(float(seconds), _MODEL_COOLDOWN_MIN), _MODEL_COOLDOWN_MAX)
    _model_cooldown_until[model] = time.monotonic() + delay


async def _await_model_cooldown(model: str) -> None:
    if not model:
        return
    remaining = _model_cooldown_until.get(model, 0.0) - time.monotonic()
    if remaining > 0:
        logger.warning("rate_limited model=%s wait=%.1fs", model, remaining)
        await asyncio.sleep(remaining)


async def _retry_on_rate_limit_for_model(
    coro_factory,
    max_attempts: int = _RETRY_MAX_ATTEMPTS,
    model: str = "",
):
    last_error = None
    for attempt in range(max_attempts):
        try:
            return await coro_factory()
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < max_attempts - 1:
                delay = _retry_after_seconds(e)
                _set_model_cooldown(model, delay)
                logger.warning(
                    "rate_limited model=%s wait=%.1fs attempt=%s/%s",
                    model or "unknown",
                    delay,
                    attempt + 1,
                    max_attempts,
                )
                await asyncio.sleep(delay)
                last_error = e
                continue
            raise
    raise last_error


class _LLMSemaphoreLease:
    """Tracks global+model semaphore ownership so 429 cooldown can release the slots."""

    __slots__ = ("global_sem", "model_sem", "global_acquired", "model_acquired")

    def __init__(self) -> None:
        self.global_sem = None
        self.model_sem = None
        self.global_acquired = False
        self.model_acquired = False

    async def acquire(self, model: str, skip: bool) -> None:
        if skip:
            return
        if self.global_sem is None and self.model_sem is None:
            try:
                from app.agent.llm_client import get_model_semaphore, get_global_semaphore
                self.global_sem = get_global_semaphore()
                self.model_sem = get_model_semaphore(model)
            except Exception:
                return
        try:
            if self.global_sem and not self.global_acquired:
                await self.global_sem.acquire()
                self.global_acquired = True
            if self.model_sem and not self.model_acquired:
                await self.model_sem.acquire()
                self.model_acquired = True
        except BaseException:
            self.release()
            raise
        logger.info(
            f"[信号量] 已获取 {model} 信号量 "
            f"(global={self.global_sem._value if self.global_sem else 'N/A'}, "
            f"model={self.model_sem._value if self.model_sem else 'N/A'})"
        )

    def release(self) -> None:
        if self.model_acquired and self.model_sem:
            self.model_sem.release()
            self.model_acquired = False
        if self.global_acquired and self.global_sem:
            self.global_sem.release()
            self.global_acquired = False

    def transfer(self):
        global_sem = self.global_sem if self.global_acquired else None
        model_sem = self.model_sem if self.model_acquired else None
        self.global_acquired = False
        self.model_acquired = False
        return global_sem, model_sem


class _PrefixedAsyncIterator:
    """Yield a peeked first chunk, then the remainder of an async iterator."""

    def __init__(self, first: str, rest):
        self._first = first
        self._sent_first = False
        self._rest = rest

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        if not self._sent_first:
            self._sent_first = True
            return self._first
        return await self._rest.__anext__()

    async def aclose(self) -> None:
        close = getattr(self._rest, "aclose", None)
        if close is not None:
            await close()


async def _invoke_adapter_with_retry(
    coro_factory,
    model: str,
    stream: bool = False,
    skip_semaphore: bool = False,
    max_attempts: int = _RETRY_MAX_ATTEMPTS,
):
    """Call the adapter; on 429 release semaphores, cool down, then re-acquire."""
    lease = _LLMSemaphoreLease()
    last_error = None
    for attempt in range(max_attempts):
        await _await_model_cooldown(model)
        await lease.acquire(model, skip_semaphore)
        try:
            result = await coro_factory()
            if stream and hasattr(result, "__aiter__"):
                iterator = result.__aiter__()
                try:
                    first_chunk = await iterator.__anext__()
                except StopAsyncIteration:
                    global_sem, model_sem = lease.transfer()
                    return _SemaphoreWrappedAsyncIterator(result, global_sem, model_sem)
                except Exception:
                    close = getattr(iterator, "aclose", None)
                    if close is not None:
                        try:
                            await close()
                        except Exception:
                            pass
                    raise
                global_sem, model_sem = lease.transfer()
                return _SemaphoreWrappedAsyncIterator(
                    _PrefixedAsyncIterator(first_chunk, iterator),
                    global_sem,
                    model_sem,
                )
            logger.info(f"[信号量] 释放 {model} 信号量 (非流式)")
            lease.release()
            return result
        except asyncio.CancelledError:
            lease.release()
            raise
        except Exception as e:
            if _is_rate_limit_error(e) and attempt < max_attempts - 1:
                delay = _retry_after_seconds(e)
                _set_model_cooldown(model, delay)
                logger.warning(
                    "rate_limited model=%s wait=%.1fs attempt=%s/%s",
                    model or "unknown",
                    delay,
                    attempt + 1,
                    max_attempts,
                )
                lease.release()
                last_error = e
                continue
            lease.release()
            raise
    raise last_error


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


class _SemaphoreWrappedAsyncIterator:
    """包装 AsyncIterator，在迭代期间持有信号量，迭代结束后释放"""

    def __init__(self, inner: AsyncIterator[str], global_sem, model_sem):
        self._inner = inner
        self._global_sem = global_sem
        self._model_sem = model_sem
        self._closed = False
        self._released = False
        self._max_stream_tokens = 0

    def __aiter__(self):
        return self

    async def __anext__(self) -> str:
        try:
            chunk = await self._inner.__anext__()
            self._max_stream_tokens = max(
                self._max_stream_tokens,
                _stream_usage_tokens(chunk),
            )
            return chunk
        except BaseException:
            try:
                await self.aclose()
            except Exception as close_error:
                logger.warning("关闭 LLM 流失败: %s", close_error)
            raise

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            close = getattr(self._inner, "aclose", None)
            if close is not None:
                await close()
        finally:
            metrics = _llm_call_metrics.get()
            if metrics is not None:
                metrics.token_count += self._max_stream_tokens
            self._release()

    def _release(self) -> None:
        if self._released:
            return
        self._released = True
        logger.info("[信号量] 流式迭代关闭，释放信号量")
        if self._model_sem:
            self._model_sem.release()
        if self._global_sem:
            self._global_sem.release()


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
    synthesis_protocol: Optional[str] = None,
    capability_degraded: bool = False,
    _skip_semaphore: bool = False,
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
    _record_llm_call()
    adapter = None
    
    # 优先级 1: 直接指定动态供应商
    if provider_id:
        from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
        manager = get_dynamic_provider_manager()
        provider = manager.get(provider_id)
        if provider and provider.enabled:
            try:
                from app.utils.aicloud.langchain_adapter import LangChainUnavailable
                from app.utils.aicloud.langchain_adapter import invoke as lc_invoke
                from app.utils.aicloud.langchain_adapter import stream as lc_stream
                from app.utils.aicloud.providers import ModelProvider

                lc_provider = (ModelProvider.ANTHROPIC
                               if provider.protocol.value == "anthropic"
                               else ModelProvider.OPENAI)
                lc_messages = messages or [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ]
                lc_messages = [m for m in lc_messages if m.get("content")]
                if stream:
                    result = lc_stream(
                        lc_provider, model, lc_messages, provider.api_key,
                        provider.base_url, timeout=timeout, max_retries=2,
                    )
                else:
                    result = await lc_invoke(
                        lc_provider, model, lc_messages, provider.api_key,
                        provider.base_url, timeout=timeout, max_retries=2,
                    )
                logger.debug(f"使用 LangChain 动态供应商调用模型: {model}")
                return result
            except LangChainUnavailable:
                logger.info("LangChain provider package unavailable; using native adapter")
            except ImportError:
                logger.info("LangChain bridge unavailable; using native adapter")
            adapter = DynamicAdapter(provider)
            adapter.timeout = timeout
            logger.debug(f"使用原生动态供应商调用模型: {model}")
        else:
            logger.warning(f"动态供应商 {provider_id} 不存在或已禁用，降级到其他路由")
    
    # 优先级 2: 用户 API Key Token（内置供应商）
    user_config = None
    if adapter is None and api_key_token:
        api_key = _get_user_api_key_from_token(api_key_token)
        if api_key:
            # 复用 ProviderRouter.route() 查 MODEL_PROVIDER_MAP 完整表
            router = ProviderRouter.get_instance(settings.get_provider_registry())
            provider = router.route(model)
            if provider:
                try:
                    user_config = ProviderConfig(
                        provider=provider,
                        api_key=api_key,
                        base_url=_get_provider_base_url(provider),
                    )
                    adapter = await get_adapter(provider, user_config)
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

            fallback_providers = router.get_fallback_providers(primary_provider, model)
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

    logger.info(
        "LLM请求审计: provider=%s model=%s thinking_budget=%d max_tokens=%d stream=%s",
        adapter.provider.value,
        model,
        thinking_budget,
        max_tokens,
        stream,
    )

    try:
        result = await _invoke_adapter_with_retry(lambda: adapter.call_llm(
            model=model,
            prompt=prompt,
            system_prompt=system_prompt,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
            cancel_event=cancel_event,
            messages=messages,
        ), model=model, stream=stream, skip_semaphore=_skip_semaphore)
        if stream and hasattr(result, '__aiter__'):
            logger.info(f"[信号量] 流式模式，信号量将在迭代期间持有 {model}")
            return result
        _record_llm_response_metrics(result)
        return result
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.warning(
            "LLM请求失败: provider=%s model=%s thinking_budget=%d error_type=%s status=%s",
            adapter.provider.value,
            model,
            thinking_budget,
            type(e).__name__,
            getattr(e, "status_code", None),
        )
        # 流式调用失败时尝试 fallback（仅在流式未开始前的失败）
        if stream and not disable_fallback:
            logger.warning(f"Stream call failed before streaming started, attempting fallback: {e}")
            router = ProviderRouter.get_instance(settings.get_provider_registry())
            primary_provider = router.route(model)
            fallback_providers = router.get_fallback_providers(primary_provider, model)
            global_sem = None
            model_sem = None

            for fallback in fallback_providers:
                fallback_global_acquired = False
                fallback_model_acquired = False
                try:
                    # 优先使用用户 Key（如果用户配置了），否则使用平台默认
                    fallback_adapter = await get_adapter(fallback, user_config)
                    fallback_adapter.timeout = timeout
                    logger.info(f"Stream fallback to {fallback.value}")

                    # 为 fallback 也获取信号量
                    if global_sem is None:
                        try:
                            from app.agent.llm_client import get_model_semaphore, get_global_semaphore
                            global_sem = get_global_semaphore()
                            model_sem = get_model_semaphore(model)
                        except Exception:
                            pass
                    if global_sem:
                        await global_sem.acquire()
                        fallback_global_acquired = True
                    if model_sem:
                        await model_sem.acquire()
                        fallback_model_acquired = True

                    fallback_result = await fallback_adapter.call_llm(
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
                    if stream and hasattr(fallback_result, '__aiter__'):
                        return _SemaphoreWrappedAsyncIterator(fallback_result, global_sem, model_sem)
                    if model_sem:
                        model_sem.release()
                    if global_sem:
                        global_sem.release()
                    return fallback_result
                except asyncio.CancelledError:
                    if fallback_model_acquired:
                        model_sem.release()
                    if fallback_global_acquired:
                        global_sem.release()
                    raise
                except Exception as fallback_error:
                    logger.warning(f"Stream fallback {fallback.value} also failed: {fallback_error}")
                    if fallback_model_acquired:
                        model_sem.release()
                    if fallback_global_acquired:
                        global_sem.release()
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
    if len(token) < 30:
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
