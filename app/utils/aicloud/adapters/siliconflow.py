"""
SiliconFlow 供应商适配器

复用现有 call_siliconflow 逻辑。
"""

import asyncio
from typing import AsyncIterator, Optional, Union

import httpx
from httpx import Timeout
from fastapi import HTTPException

from app.core.config import settings
from app.utils.aicloud.providers import ModelProvider, ProviderConfig
from app.utils.aicloud.adapters.base import BaseProviderAdapter


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
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        timeout = Timeout(self.timeout, connect=10.0)
        
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
        
        is_reasoning = "deepseek-ai/DeepSeek-R1" in model
        
        if is_reasoning:
            data = {
                "model": model,
                "messages": messages + [{"role": "user", "content": cleaned_prompt}],
                "stream": stream,
                "max_tokens": max_tokens,
                "thinking_budget": thinking_budget,
                "temperature": temperature
            }
        else:
            data = {
                "model": model,
                "messages": messages + [{"role": "user", "content": cleaned_prompt}],
                "stream": stream
            }
        
        if stream:
            async def generate():
                async with httpx.AsyncClient(timeout=timeout) as client:
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
            async with httpx.AsyncClient(timeout=timeout) as client:
                if cancel_event and cancel_event.is_set():
                    raise asyncio.CancelledError("LLM 调用被取消")
                resp = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=data
                )
                if resp.status_code != 200:
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
        
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/embeddings",
                headers=headers,
                json=data
            )
            if resp.status_code != 200:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
            return resp.json()
    
    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
