"""
多供应商适配器 - DeepSeek 官方

DeepSeek API 兼容 OpenAI 格式。
"""

import asyncio
from typing import AsyncIterator, Optional, Union

import httpx
from httpx import Timeout
from fastapi import HTTPException

from app.utils.aicloud.adapters.base import BaseProviderAdapter
from app.utils.aicloud.providers import ModelProvider, ProviderConfig
from app.utils.aicloud.http_client import get_http_client, call_with_retry, _max_concurrent_calls


class DeepSeekAdapter(BaseProviderAdapter):
    """DeepSeek 官方供应商适配器"""
    
    provider = ModelProvider.DEEPSEEK
    
    BASE_URL = "https://api.deepseek.com/v1"
    
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
            raise RuntimeError("DeepSeek API Key 未配置")
        
        base_url = self.base_url or self.BASE_URL
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        timeout = Timeout(self.timeout, connect=10.0)
        if messages is None:
            messages = self._build_messages(prompt, system_prompt)
        
        data = self._build_request_body(
            model=model,
            messages=messages,
            stream=stream,
            temperature=temperature,
            max_tokens=max_tokens,
            thinking_budget=thinking_budget,
        )
        
        if stream:
            async def generate():
                async with _max_concurrent_calls:
                    client = await get_http_client()
                    async with client.stream(
                        "POST",
                        f"{base_url}/chat/completions",
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
                        f"{base_url}/chat/completions",
                        headers=headers,
                        json=data
                    )
                
                resp = await call_with_retry(request_func, max_retries=3)
                
                if resp.status_code != 200:
                    raise HTTPException(status_code=resp.status_code, detail=resp.text)
                return resp.json()
    
    async def call_embedding(
        self,
        model: str,
        input_text: str,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> dict:
        if not self.api_key:
            raise RuntimeError("DeepSeek API Key 未配置")
        
        base_url = self.base_url or self.BASE_URL
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
                    f"{base_url}/embeddings",
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
