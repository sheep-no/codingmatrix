"""
SiliconFlow 供应商适配器

复用现有 call_siliconflow 逻辑。
"""

import asyncio
import logging
import os
from pathlib import Path
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
        # 缓存 reasoning 模型集合（从统一配置加载一次）
        self._reasoning_models: Optional[set] = None
    
    def _is_reasoning_model(self, model: str) -> bool:
        """判断模型是否是 reasoning 模型（从运行时 YAML 配置读取）。"""
        if self._reasoning_models is None:
            config_path = os.path.join(os.path.dirname(__file__), "../../../../data/agent_model_config.yaml")
            self._reasoning_models = set()
            try:
                from app.utils.model_config_io import load_model_config
                config = load_model_config(Path(config_path))
                for model_id, m in config.get("models", {}).items():
                    if m.get("is_reasoning", False):
                        self._reasoning_models.add(m.get("name", ""))
            except Exception:
                pass
            # 兜底
            if not self._reasoning_models:
                self._reasoning_models = {"deepseek-ai/DeepSeek-R1-0528-Qwen3-8B", "deepseek-ai/DeepSeek-R1"}
        return model in self._reasoning_models
    
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
        
        # 判断是否是 reasoning 模型（从统一配置读取）
        is_reasoning = self._is_reasoning_model(model)

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
                    try:
                        async with client.stream(
                            "POST",
                            f"{self.base_url}/chat/completions",
                            headers=headers,
                            json=data
                        ) as response:
                            if response.status_code != 200:
                                error_body = ""
                                async for chunk in response.aiter_bytes():
                                    error_body += chunk.decode(errors="replace")
                                    if len(error_body) > 2048:
                                        break
                                raise Exception(f"HTTP {response.status_code}: {error_body[:500]}")
                            async for line in response.aiter_lines():
                                if cancel_event and cancel_event.is_set():
                                    await response.aclose()
                                    raise asyncio.CancelledError("LLM 调用被取消")
                                if line.startswith("data: "):
                                    chunk = line[6:]
                                    if chunk == "[DONE]":
                                        break
                                    yield f"{chunk}\n"
                    except httpx.RemoteProtocolError as e:
                        raise Exception(f"服务器断开连接: {e}" if str(e) else "服务器断开连接（无响应）") from e
                    except httpx.ReadError as e:
                        raise Exception(f"读取响应失败: {e}" if str(e) else "读取响应失败（连接中断）") from e
                    except httpx.ConnectError as e:
                        raise Exception(f"连接失败: {e}" if str(e) else "连接服务器失败") from e
                    except httpx.TimeoutException as e:
                        raise Exception(f"请求超时: {e}" if str(e) else "请求超时") from e
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        if str(e):
                            raise
                        raise Exception(f"流式请求异常: {type(e).__name__}") from e
            
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
