"""
多供应商适配器 - Anthropic

Anthropic Claude API 格式与 OpenAI 不同，需要特殊处理。
"""

import asyncio
import logging
from typing import AsyncIterator, Optional, Union

import httpx
from httpx import Timeout
from fastapi import HTTPException

from app.utils.aicloud.adapters.base import BaseProviderAdapter
from app.utils.aicloud.providers import ModelProvider, ProviderConfig
from app.utils.aicloud.http_client import get_http_client, call_with_retry, _max_concurrent_calls

logger = logging.getLogger(__name__)


class AnthropicAdapter(BaseProviderAdapter):
    """Anthropic (Claude) 供应商适配器"""
    
    provider = ModelProvider.ANTHROPIC
    
    BASE_URL = "https://api.anthropic.com/v1"
    API_VERSION = "2023-06-01"
    
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
    ) -> Union[dict, AsyncIterator[str]]:
        if not self.api_key:
            raise RuntimeError("Anthropic API Key 未配置")
        
        base_url = self.base_url or self.BASE_URL
        headers = self._get_headers()
        
        timeout = Timeout(self.timeout, connect=10.0)
        
        # Anthropic 使用 messages API，格式与 OpenAI 不同
        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
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
                        f"{base_url}/messages",
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
                                # Anthropic SSE 格式不同
                                yield f"{chunk}\n"
            
            return generate()
        else:
            async with _max_concurrent_calls:
                client = await get_http_client()
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError("LLM 调用被取消")
                
                async def request_func():
                    return await client.post(
                        f"{base_url}/messages",
                        headers=headers,
                        json=data
                    )
                
                resp = await call_with_retry(request_func, max_retries=3)
                
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                
                # 转换为 OpenAI 兼容格式
                anthropic_response = resp.json()
                return {
                    "choices": [{
                        "message": {
                            "content": anthropic_response["content"][0]["text"]
                        }
                    }],
                    "usage": anthropic_response.get("usage", {}),
                }
    
    async def call_embedding(
        self,
        model: str,
        input_text: str,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> dict:
        raise NotImplementedError("Anthropic 不支持 embedding API")
    
    def _get_headers(self) -> dict:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.API_VERSION,
            "content-type": "application/json",
        }
