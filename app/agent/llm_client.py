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
import json
import logging
from typing import Optional, Dict, Any, Callable, Awaitable, AsyncIterator, Union

import httpx
from app.utils import call_llm
from app.agent.dynamic_model_router import get_dynamic_router, LayeredModelRouter

logger = logging.getLogger(__name__)

# 流式 chunk 回调签名: (content_delta, reasoning_delta) -> None
StreamChunkCallback = Callable[[str, str], Awaitable[None]]

MAX_CONCURRENT_LLM_CALLS = 6
MAX_CONCURRENT_PER_MODEL = 2  # 同一模型最多 2 个并发请求，避免 503 过载
_global_semaphore: Optional[asyncio.Semaphore] = None
_model_semaphores: Dict[str, asyncio.Semaphore] = {}


def get_global_semaphore() -> asyncio.Semaphore:
    global _global_semaphore
    if _global_semaphore is None:
        _global_semaphore = asyncio.Semaphore(MAX_CONCURRENT_LLM_CALLS)
    return _global_semaphore


def get_model_semaphore(model_name: str) -> asyncio.Semaphore:
    """获取按模型的并发信号量，同一模型最多 MAX_CONCURRENT_PER_MODEL 个并发请求"""
    if model_name not in _model_semaphores:
        _model_semaphores[model_name] = asyncio.Semaphore(MAX_CONCURRENT_PER_MODEL)
    return _model_semaphores[model_name]


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
        cancel_event: Optional[asyncio.Event] = None,
    ):
        self.model_name = model_name
        self.task_type = task_type
        self.api_key_token = api_key_token
        self.provider_id = provider_id
        self._cost_tracker = cost_tracker
        self._complexity = complexity
        self._semaphore = semaphore if semaphore is not None else get_global_semaphore()
        self._model_semaphore = get_model_semaphore(model_name)  # 按模型并发限制
        self._cancel_event = cancel_event
        self._model_config = LayeredModelRouter.get_model_config(
            model_name, task_type=task_type, api_key_token=api_key_token
        )
        self._disable_fallback = self._check_disable_fallback()

    def _check_disable_fallback(self) -> bool:
        """检查用户降级链偏好是否为 disabled"""
        if not self.api_key_token:
            return False
        try:
            from app.services.apikey_manager import get_apikey_manager
            manager = get_apikey_manager()
            pref = manager.get_fallback_preference_by_token(self.api_key_token)
            if pref and pref.get("fallback_preference") == "disabled":
                return True
        except Exception as e:
            logger.debug(f"检查降级链偏好失败（非致命）: {e}")
        return False

    async def call(self, prompt: str, system_prompt: str = "", stream: bool = False, thinking_budget: Optional[int] = None) -> str:
        """调用 LLM

        Args:
            prompt: 用户 prompt
            system_prompt: 系统 prompt
            stream: 是否流式（仅当配合 on_chunk 才有意义，否则按非流式处理）
            thinking_budget: 覆盖模型默认的 thinking budget（None=使用默认，0=禁用思考）

        Returns:
            LLM 输出文本

        Raises:
            LLMClientError: 不可恢复错误（401/403）
        """
        return await self._call_internal(prompt, system_prompt, stream=stream, on_chunk=None, thinking_budget=thinking_budget)

    async def call_stream(
        self,
        prompt: str,
        system_prompt: str = "",
        on_chunk: Optional[StreamChunkCallback] = None,
        thinking_budget: Optional[int] = None,
    ) -> str:
        """流式调用 LLM，逐 token 回调

        当 LLM 返回 SSE 流时，每个 chunk 都会调用 on_chunk(content_delta, reasoning_delta)。
        reasoning_delta 是 DeepSeek-R1 等推理模型的思考内容（reasoning_content 字段），
        content_delta 是正常回复内容（content 字段）。

        Args:
            prompt: 用户 prompt
            system_prompt: 系统 prompt
            on_chunk: 异步回调函数 (content_delta: str, reasoning_delta: str) -> None
            thinking_budget: 覆盖模型默认的 thinking budget（None=使用默认，0=禁用思考）

        Returns:
            LLM 完整输出文本（content 字段，不含 reasoning）
        """
        if on_chunk is None:
            raise ValueError("call_stream 必须传入 on_chunk 回调")

        start_time = time.time()
        await (await get_dynamic_router()).start_call(self.model_name)

        try:
            full_content, full_reasoning, response = await self._consume_stream(
                prompt, system_prompt, on_chunk, thinking_budget=thinking_budget
            )
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(
                self.model_name, success=True, latency_ms=latency_ms
            )

            self._record_usage(response, start_time)
            return full_content

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(
                self.model_name, success=False, latency_ms=latency_ms, error="timeout"
            )
            logger.error(f"LLM 流式调用超时 ({self._model_config.get('timeout', 300)}s): {self.model_name}")
            raise LLMClientError(
                f"LLM 流式调用超时 ({self._model_config.get('timeout', 300)}s): {self.model_name}"
            )

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = str(e) or f"{type(e).__name__}(无消息)"
            await (await get_dynamic_router()).record_call(
                self.model_name, success=False, latency_ms=latency_ms, error=error_msg
            )
            logger.error(f"LLM 流式调用失败: {self.model_name} - [{type(e).__name__}] {e}")

            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                raise LLMClientError(
                    f"认证失败 (HTTP {e.response.status_code})，请检查 API Key 配置"
                ) from e

            raise LLMClientError(f"LLM 流式调用失败: {self.model_name} - {e}") from e

    async def _consume_stream(
        self,
        prompt: str,
        system_prompt: str,
        on_chunk: StreamChunkCallback,
        thinking_budget: Optional[int] = None,
    ) -> tuple[str, str, Dict[str, Any]]:
        """消费 LLM 流式响应，返回 (full_content, full_reasoning, last_response_meta)

        适配器在 stream=True 时返回 AsyncIterator[str]，每行是 OpenAI 兼容格式的 JSON chunk 字符串。
        """
        effective_thinking_budget = thinking_budget if thinking_budget is not None else self._model_config["thinking_budget"]

        async def _do_call_stream():
            return await call_llm(
                model=self.model_name,
                prompt=prompt,
                system_prompt=system_prompt,
                stream=True,
                max_tokens=self._model_config["max_tokens"],
                thinking_budget=effective_thinking_budget,
                temperature=self._model_config["temperature"],
                api_key_token=self.api_key_token,
                provider_id=self.provider_id,
                disable_fallback=self._disable_fallback,
                cancel_event=self._cancel_event,
                _skip_semaphore=True,
            )

        call_timeout = self._model_config.get("timeout", 300)

        if self._semaphore:
            if self._cancel_event and self._cancel_event.is_set():
                raise asyncio.CancelledError("请求已取消")
            # 同时获取全局信号量和按模型信号量
            await self._semaphore.acquire()
            await self._model_semaphore.acquire()
            try:
                stream_iter = await asyncio.wait_for(_do_call_stream(), timeout=call_timeout)
            finally:
                self._model_semaphore.release()
                self._semaphore.release()
        else:
            stream_iter = await asyncio.wait_for(_do_call_stream(), timeout=call_timeout)

        # stream_iter 可能是 AsyncIterator[str] 或 coroutine
        if asyncio.iscoroutine(stream_iter):
            stream_iter = await stream_iter

        full_content = ""
        full_reasoning = ""
        last_meta: Dict[str, Any] = {}

        async for chunk_str in stream_iter:
            if not chunk_str:
                continue
            chunk_str = chunk_str.strip()
            if not chunk_str or chunk_str == "[DONE]":
                continue
            if chunk_str.startswith("data: "):
                chunk_str = chunk_str[6:]

            try:
                chunk = json.loads(chunk_str)
            except json.JSONDecodeError:
                logger.debug(f"流式 chunk 无法解析: {chunk_str[:100]}")
                continue

            choices = chunk.get("choices") or []
            if not choices:
                # 可能是 usage-only 末尾 chunk
                if chunk.get("usage"):
                    last_meta = chunk
                continue

            delta = choices[0].get("delta", {}) or {}
            content_delta = delta.get("content", "") or ""
            reasoning_delta = delta.get("reasoning_content", "") or ""

            if content_delta:
                full_content += content_delta
            if reasoning_delta:
                full_reasoning += reasoning_delta

            if content_delta or reasoning_delta:
                try:
                    await on_chunk(content_delta, reasoning_delta)
                except Exception as e:
                    logger.debug(f"on_chunk 回调失败（非致命）: {e}")

            # 捕获 usage（最后一个 chunk 通常带 usage）
            if chunk.get("usage"):
                last_meta = chunk

        # 合成兼容的 response dict 以复用 cost tracking
        synthetic_response: Dict[str, Any] = {
            "choices": [{"message": {"content": full_content}}],
            "usage": last_meta.get("usage", {}),
        }
        return full_content, full_reasoning, synthetic_response

    def _record_usage(self, response: Dict[str, Any], start_time: float) -> None:
        """记录成本追踪"""
        usage = response.get("usage", {}) if response else {}
        if usage and self._cost_tracker:
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            cost_per_1m_input = self._model_config.get("cost_per_1m_input", 0.0)
            cost_per_1m_output = self._model_config.get("cost_per_1m_output", 0.0)
            cost_usd = (
                prompt_tokens * cost_per_1m_input + completion_tokens * cost_per_1m_output
            ) / 1_000_000
            self._cost_tracker.add_usage(
                self.model_name, prompt_tokens, completion_tokens, cost_usd
            )

    async def _call_internal(
        self,
        prompt: str,
        system_prompt: str = "",
        stream: bool = False,
        on_chunk: Optional[StreamChunkCallback] = None,
        thinking_budget: Optional[int] = None,
    ) -> str:
        """非流式调用 LLM（call() 走此路径）

        保持向后兼容：stream 参数被接受但忽略（流式必须用 call_stream）。
        """
        start_time = time.time()
        await (await get_dynamic_router()).start_call(self.model_name)

        effective_thinking_budget = thinking_budget if thinking_budget is not None else self._model_config["thinking_budget"]

        try:
            async def _do_call():
                return await call_llm(
                    model=self.model_name,
                    prompt=prompt,
                    system_prompt=system_prompt,
                    stream=stream,
                    max_tokens=self._model_config["max_tokens"],
                    thinking_budget=effective_thinking_budget,
                    temperature=self._model_config["temperature"],
                    api_key_token=self.api_key_token,
                    provider_id=self.provider_id,
                    disable_fallback=self._disable_fallback,
                    cancel_event=self._cancel_event,
                    _skip_semaphore=True,
                )

            call_timeout = self._model_config.get("timeout", 300)

            if self._semaphore:
                if self._cancel_event and self._cancel_event.is_set():
                    raise asyncio.CancelledError("请求已取消")
                # 同时获取全局信号量和按模型信号量
                await self._semaphore.acquire()
                await self._model_semaphore.acquire()
                try:
                    response = await asyncio.wait_for(_do_call(), timeout=call_timeout)
                finally:
                    self._model_semaphore.release()
                    self._semaphore.release()
            else:
                response = await asyncio.wait_for(_do_call(), timeout=call_timeout)

            choices = response.get("choices", [])
            content = choices[0].get("message", {}).get("content", "") if choices else ""
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(
                self.model_name, success=True, latency_ms=latency_ms
            )

            self._record_usage(response, start_time)
            return content

        except asyncio.TimeoutError:
            latency_ms = (time.time() - start_time) * 1000
            await (await get_dynamic_router()).record_call(
                self.model_name, success=False, latency_ms=latency_ms, error="timeout"
            )
            logger.error(f"LLM 调用超时 ({call_timeout}s): {self.model_name}")
            raise LLMClientError(f"LLM 调用超时 ({call_timeout}s): {self.model_name}")

        except Exception as e:
            latency_ms = (time.time() - start_time) * 1000
            error_msg = str(e) or f"{type(e).__name__}(无消息)"
            await (await get_dynamic_router()).record_call(
                self.model_name, success=False, latency_ms=latency_ms, error=error_msg
            )
            logger.error(f"LLM 调用失败: {self.model_name} - [{type(e).__name__}] {e}")

            if isinstance(e, httpx.HTTPStatusError) and e.response.status_code in (401, 403):
                raise LLMClientError(
                    f"认证失败 (HTTP {e.response.status_code})，请检查 API Key 配置"
                ) from e

            raise LLMClientError(f"LLM 调用失败: {self.model_name} - {e}") from e

    @property
    def model_config(self) -> Dict:
        return self._model_config

    @property
    def max_tokens(self) -> int:
        return self._model_config.get("max_tokens", 4096)

    @property
    def thinking_budget(self) -> int:
        return self._model_config.get("thinking_budget", 0)
