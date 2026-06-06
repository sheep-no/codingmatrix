"""
动态供应商适配器

根据 base_url 和协议类型（OpenAI兼容 / Anthropic原生）自动路由调用。
"""
import asyncio
import logging
from typing import AsyncIterator, Optional, Union

import httpx
from httpx import Timeout
from fastapi import HTTPException

from app.utils.aicloud.adapters.base import BaseProviderAdapter
from app.utils.aicloud.providers import ModelProvider, ProviderConfig
from app.utils.aicloud.dynamic_provider import Protocol, DynamicProvider
from app.utils.aicloud.http_client import get_http_client, call_with_retry, _max_concurrent_calls

logger = logging.getLogger(__name__)


class DynamicAdapter(BaseProviderAdapter):
    """动态供应商适配器 - 根据协议类型自动选择调用格式"""
    
    provider = ModelProvider.SILICONFLOW  # 基类要求，实际通过 protocol 区分
    
    def __init__(self, provider_obj: DynamicProvider):
        config = ProviderConfig(
            provider=ModelProvider.SILICONFLOW,
            api_key=provider_obj.api_key,
            base_url=provider_obj.base_url,
        )
        super().__init__(config)
        self._protocol = provider_obj.protocol
        self._provider_obj = provider_obj
    
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
        if not self.api_key:
            raise RuntimeError("API Key 未配置")
        
        if self._protocol == Protocol.ANTHROPIC:
            return await self._call_anthropic(
                model, prompt, system_prompt, stream,
                temperature, max_tokens, thinking_budget, cancel_event, messages,
            )
        else:
            return await self._call_openai(
                model, prompt, system_prompt, stream,
                temperature, max_tokens, thinking_budget, cancel_event, messages,
            )
    
    async def _call_openai(
        self, model, prompt, system_prompt, stream,
        temperature, max_tokens, thinking_budget, cancel_event, messages=None,
    ):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        timeout = Timeout(self.timeout, connect=10.0)
        
        if messages is None:
            messages = self._build_messages(prompt, system_prompt)
        data = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if stream:
            async def generate():
                async with _max_concurrent_calls:
                    client = await get_http_client()
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers=headers,
                        json=data,
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
                        headers=headers, json=data,
                    )
                
                resp = await call_with_retry(request_func, max_retries=3)
                
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                return resp.json()
    
    async def _call_anthropic(
        self, model, prompt, system_prompt, stream,
        temperature, max_tokens, thinking_budget, cancel_event, messages=None,
    ):
        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        timeout = Timeout(self.timeout, connect=10.0)
        
        if messages is None:
            messages = [{"role": "user", "content": prompt}]
        
        data = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": stream,
        }
        
        if system_prompt:
            data["system"] = system_prompt
        
        if stream:
            async def generate():
                async with _max_concurrent_calls:
                    client = await get_http_client()
                    async with client.stream(
                        "POST",
                        f"{self.base_url}/messages",
                        headers=headers,
                        json=data,
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
                        f"{self.base_url}/messages",
                        headers=headers, json=data,
                    )
                
                resp = await call_with_retry(request_func, max_retries=3)
                
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                
                anthropic_response = resp.json()
                content_blocks = anthropic_response.get("content", [])
                text_content = ""
                for block in content_blocks:
                    if block.get("type") == "text":
                        text_content += block.get("text", "")
                return {
                    "choices": [{
                        "message": {
                            "content": text_content
                        }
                    }],
                    "usage": anthropic_response.get("usage", {}),
                }
    
    async def call_embedding(self, model, input_text, cancel_event=None):
        raise NotImplementedError("动态供应商不支持 embedding")
    
    def _get_headers(self) -> dict:
        if self._protocol == Protocol.ANTHROPIC:
            return {
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
            }
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
