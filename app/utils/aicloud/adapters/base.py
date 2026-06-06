"""
多供应商模型调用系统 - 供应商适配器基类

定义统一的模型调用接口。
"""

import abc
import asyncio
import logging
from typing import AsyncIterator, Optional, Union

from app.utils.aicloud.providers import ModelProvider, ProviderConfig

logger = logging.getLogger(__name__)


class BaseProviderAdapter(abc.ABC):
    """供应商适配器基类"""
    
    provider: ModelProvider
    
    def __init__(self, config: ProviderConfig):
        self.config = config
        self.api_key = config.api_key
        self.base_url = config.base_url
        self.timeout = config.timeout
        self.max_retries = config.max_retries

    def _validate_api_key(self) -> None:
        """校验 api_key 非空：空 Key 会在 HTTP 请求时发 "Bearer " → 401
        子类在 call_llm 入口处调用。DynamicAdapter 内部已自带校验（抛 RuntimeError），
        因此本方法不在基类 call_llm 包装里强制调用。
        """
        if not self.api_key:
            from fastapi import HTTPException
            raise HTTPException(
                status_code=401,
                detail=f"{self.provider.value} 供应商的 API Key 未配置，请在 Settings → API Key 管理中添加"
            )
    
    @abc.abstractmethod
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
        """
        统一模型调用接口

        子类必须实现此方法。基类在子类的 call_llm 入口处会校验 api_key，
        子类实现应在方法首行调用 self._validate_api_key()。

        Args:
            model: 模型名称
            prompt: 用户提示
            system_prompt: 系统提示
            stream: 是否流式输出
            temperature: 温度 (0.0-2.0)
            max_tokens: 最大输出 token 数
            thinking_budget: 思考 token 预算（仅 reasoning 模型）
            cancel_event: 取消事件

        Returns:
            非流式: {"choices": [{"message": {"content": "..."}}], "usage": {...}}
            流式: AsyncIterator[str]
        """
        pass
    
    @abc.abstractmethod
    async def call_embedding(
        self,
        model: str,
        input_text: str,
        cancel_event: Optional[asyncio.Event] = None,
    ) -> dict:
        """
        Embedding 调用接口（可选实现）
        """
        pass
    
    def _build_messages(self, prompt: str, system_prompt: str = "") -> list[dict]:
        """构建 OpenAI 兼容的 messages 列表"""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages
    
    def _parse_response_content(self, response: dict) -> str:
        """从响应中提取内容（OpenAI 兼容格式）"""
        if "choices" in response:
            return response["choices"][0]["message"]["content"]
        elif "content" in response:
            return response["content"]
        raise ValueError(f"Unexpected response format: {response.keys()}")
    
    def _build_request_body(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        temperature: float = 0.7,
        max_tokens: int = 4096,
        thinking_budget: int = 4096,
    ) -> dict:
        """构建请求体（OpenAI 兼容格式）"""
        body = {
            "model": model,
            "messages": messages,
            "stream": stream,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        # 判断是否为推理模型
        if self._is_reasoning_model(model):
            # 推理模型：添加 thinking budget
            if thinking_budget > 0:
                body["extra_body"] = {"thinking_budget": thinking_budget}
        else:
            # 非推理模型：禁用深度思考（避免 Qwen3 等模型浪费大量 token 在思考上）
            body["enable_thinking"] = False
        
        return body
    
    def _is_reasoning_model(self, model: str) -> bool:
        """判断是否为 reasoning 模型"""
        reasoning_keywords = ["r1", "reasoner", "thinking", "deepthink"]
        return any(kw in model.lower() for kw in reasoning_keywords)

    @abc.abstractmethod
    def _get_headers(self) -> dict:
        """获取请求头"""
        pass
