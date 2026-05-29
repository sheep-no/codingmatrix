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
    ) -> Union[dict, AsyncIterator[str]]:
        """
        统一模型调用接口
        
        Args:
            model: 模型名称
            prompt: 用户提示
            system_prompt: 系统提示
            stream: 是否流式输出
            temperature: 温度参数 (0.0-2.0)
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
