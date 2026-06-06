"""
SiliconFlow 供应商适配器

复用现有 call_siliconflow 逻辑。
"""

import asyncio
import logging
from typing import AsyncIterator, Optional, Union

import httpx
from httpx import Timeout
from fastapi import HTTPException

from app.core.config import settings
from app.utils.aicloud.providers import ModelProvider, ProviderConfig
from app.utils.aicloud.adapters.base import BaseProviderAdapter
from app.utils.aicloud.http_client import get_http_client, call_with_retry, _max_concurrent_calls

logger = logging.getLogger(__name__)


class SiliconFlowAdapter(BaseProviderAdapter):
    """SiliconFlow 供应商适配器"""

    provider = ModelProvider.SILICONFLOW

    def __init__(self, config: Optional[ProviderConfig] = None):
        if config is None:
            config = ProviderConfig(
                provider=ModelProvider.SILICONFLOW,
                api_key=settings.SILICONFLOW_API_KEY,
                base_url=settings.SILICONFLOW_BASE_URL,
            )
        super().__init__(config)
        # 已知不支持 enable_thinking 的模型（首次遇到 400 后动态添加到此集合）
        # 实例级字段，每个 Adapter 独立持有，避免跨请求污染和单测不隔离
        self._unsupported_thinking: set = set()
    
    async def call_llm(
        self,
        model: str,
        prompt: str,
        system_prompt: str = "",
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        thinking_budget: int = 4096,
        cancel_event: Optional[asyncio.Event] = None,
        messages: Optional[list] = None,
    ) -> Union[dict, AsyncIterator[str]]:
        logger.info(f"[SiliconFlowAdapter] Calling model: {model}")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        timeout = Timeout(self.timeout, connect=10.0)
        
        if messages is None:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            
            cleaned_prompt = prompt
            if "【SYSTEM】" in cleaned_prompt:
                import re
                match = re.search(r'【SYSTEM】\s*(.*?)\s*【USER】\s*(.*)', cleaned_prompt, re.DOTALL)
                if match:
                    system_part = match.group(1).strip()
                    user_part = match.group(2).strip()
                    if not system_prompt:
                        messages.insert(0, {"role": "system", "content": system_part})
                    cleaned_prompt = user_part
            messages.append({"role": "user", "content": cleaned_prompt})
        
        # 判断是否是 reasoning 模型
        is_reasoning = "deepseek-ai/DeepSeek-R1" in model

        support_thinking = model not in self._unsupported_thinking
        
        if is_reasoning:
            data = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "max_tokens": max_tokens,
                "thinking_budget": thinking_budget,
                "temperature": temperature
            }
        else:
            data = {
                "model": model,
                "messages": messages,
                "stream": stream,
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if support_thinking:
                data["enable_thinking"] = False  # 禁用深度思考，避免 Qwen3 等模型浪费大量 token
        
        if stream:
            async def generate():
                async with _max_concurrent_calls:
                    client = await get_http_client()
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=data
                    ) as response:
                        async for line in response.aiter_lines():
                            if cancel_event and cancel_event.is_set():
                                await response.aclose()
                                raise asyncio.CancelledError("LLM 调用被取消")
                            if line.startswith("data: "):
                                chunk = line[6:]
                                if chunk == "[DONE]":
                                    break
                                yield f"{chunk}\n"
            
            return generate()
        else:
            async with _max_concurrent_calls:
                client = await get_http_client()
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError("LLM 调用被取消")
                
                async def request_func():
                    return await client.post(
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=data
                    )
                
                try:
                    resp = await call_with_retry(request_func, max_retries=3)
                except Exception as e:
                    # 如果失败且包含 enable_thinking 参数，记录并去掉后重试
                    error_msg = str(e)
                    if "enable_thinking" in error_msg and "enable_thinking" in data:
                        logger.warning(f"[SiliconFlowAdapter] 模型 {model} 不支持 enable_thinking，记录并重试")
                        self._unsupported_thinking.add(model)
                        data_without_thinking = {k: v for k, v in data.items() if k != "enable_thinking"}
                        
                        async def request_func_retry():
                            return await client.post(
                                f"{self.base_url}/chat/completions",
                                headers=headers,
                                json=data_without_thinking
                            )
                        
                        resp = await call_with_retry(request_func_retry, max_retries=3)
                    else:
                        raise
                
                if resp.status_code != 200:
                    # 检查是否是 enable_thinking 参数导致的 400 错误
                    if resp.status_code == 400 and "enable_thinking" in resp.text:
                        logger.warning(f"[SiliconFlowAdapter] 模型 {model} 不支持 enable_thinking，记录并重试")
                        self._unsupported_thinking.add(model)
                        data_without_thinking = {k: v for k, v in data.items() if k != "enable_thinking"}
                        
                        async def request_func_retry():
                            return await client.post(
                                f"{self.base_url}/chat/completions",
                                headers=headers,
                                json=data_without_thinking
                            )
                        
                        resp = await call_with_retry(request_func_retry, max_retries=3)
                        if resp.status_code != 200:
                            raise HTTPException(status_code=resp.status_code, detail=resp.text)
                    else:
                        raise HTTPException(status_code=resp.status_code, detail=resp.text)
                return resp.json()
    
    async def call_embedding(
        self,
        model: str,
        input_text: str,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> dict:
        """调用 embedding 接口"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": model,
            "input": input_text,
        }
        
        async with _max_concurrent_calls:
            client = await get_http_client()
            
            async def request_func():
                return await client.post(
                    f"{self.base_url}/embeddings",
                    headers=headers,
                    json=data
                )
            
            resp = await call_with_retry(request_func, max_retries=3)
            
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
    
    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
