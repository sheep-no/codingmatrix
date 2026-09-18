"""
多供应商模型调用系统 - 供应商适配器基类

定义统一的模型调用接口。
"""

import abc
import asyncio
import json
import logging
from typing import AsyncIterator, Optional, Union

from app.utils.aicloud.providers import ModelProvider, ProviderConfig

logger = logging.getLogger(__name__)


def anthropic_sse_to_openai_chunk(payload: dict) -> Optional[str]:
    """把 Anthropic 流式事件转换为 OpenAI 兼容的 chunk JSON。

    Anthropic 的文本载荷在 content_block_delta.delta.text，下游统一按
    choices[0].delta.content 解析。非文本事件返回 None。
    """
    event_type = payload.get("type")
    if event_type == "content_block_delta":
        delta = payload.get("delta") or {}
        if delta.get("type") == "text_delta":
            text = delta.get("text", "")
            if text:
                return json.dumps({"choices": [{"delta": {"content": text}}]})
    elif event_type == "message_delta":
        stop_reason = (payload.get("delta") or {}).get("stop_reason")
        if stop_reason:
            return json.dumps(
                {"choices": [{"delta": {}, "finish_reason": stop_reason}]}
            )
    return None


class BaseProviderAdapter(abc.ABC):
    """供应商适配器基类"""
    
    provider: ModelProvider
    # 是否支持 Qwen 系的 enable_thinking/thinking_budget 顶层开关。
    # OpenAI/DeepSeek/Zhipu 官方接口拒收这两个非标准字段，默认不注入。
    SUPPORTS_THINKING_TOGGLE = False
    
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
        messages: Optional[list] = None,
    ) -> Union[dict, AsyncIterator[str]]:
        """
        统一模型调用接口

        子类必须实现此方法，并在入口处自行校验 api_key 是否为空。

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
        
        # enable_thinking/thinking_budget 是 Qwen（SiliconFlow/DashScope）特有字段，
        # 官方 OpenAI/DeepSeek/Zhipu 接口会拒收，按供应商注入。
        if self.SUPPORTS_THINKING_TOGGLE:
            if self._is_reasoning_model(model):
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
