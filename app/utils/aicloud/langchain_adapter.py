"""LangChain model bridge with a project-owned normalized response format."""

from __future__ import annotations

import json
from typing import Any, AsyncIterator

from app.utils.aicloud.providers import ModelProvider


class LangChainUnavailable(RuntimeError):
    """Raised when the selected LangChain provider package is unavailable."""


def _load_model(provider: ModelProvider, model: str, api_key: str, base_url: str = "", **kwargs: Any):
    try:
        if provider == ModelProvider.ANTHROPIC:
            from langchain_anthropic import ChatAnthropic

            return ChatAnthropic(model=model, api_key=api_key, base_url=base_url or None, **kwargs)
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(model=model, api_key=api_key, base_url=base_url or None, **kwargs)
    except ImportError as exc:
        raise LangChainUnavailable(
            "LangChain provider package is not installed for the selected model provider"
        ) from exc


def _message_to_dict(message: Any) -> dict[str, Any]:
    blocks = getattr(message, "content_blocks", None) or []
    content = getattr(message, "text", None)
    if content is None:
        raw_content = getattr(message, "content", "")
        content = raw_content if isinstance(raw_content, str) else "".join(
            block.get("text", "") for block in raw_content if isinstance(block, dict)
        )
    usage = getattr(message, "usage_metadata", None) or {}
    return {
        "content": content or "",
        "content_blocks": blocks,
        "tool_calls": getattr(message, "tool_calls", None) or [],
        "usage": usage,
        "response_metadata": getattr(message, "response_metadata", None) or {},
    }


async def invoke(
    provider: ModelProvider,
    model: str,
    messages: list[Any],
    api_key: str,
    base_url: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    chat_model = _load_model(provider, model, api_key, base_url, **kwargs)
    message = await chat_model.ainvoke(messages)
    return _message_to_dict(message)


async def stream(
    provider: ModelProvider,
    model: str,
    messages: list[Any],
    api_key: str,
    base_url: str = "",
    **kwargs: Any,
) -> AsyncIterator[str]:
    chat_model = _load_model(provider, model, api_key, base_url, **kwargs)
    async for chunk in chat_model.astream(messages):
        data = _message_to_dict(chunk)
        text = data["content"]
        if text:
            yield json.dumps({
                "choices": [{"delta": {"content": text}, "finish_reason": None}],
            }, ensure_ascii=False)
        if data["tool_calls"]:
            yield json.dumps({
                "choices": [{"delta": {"tool_calls": data["tool_calls"]}, "finish_reason": None}],
            }, ensure_ascii=False)
        if data["usage"]:
            yield json.dumps({"usage": data["usage"]}, ensure_ascii=False)
