"""Pure parsing and normalization helpers for structured GirlAI turns."""

import json
import logging
import re
from typing import Any, Mapping, Optional

from app.schema.girl_companion import CompanionTurn

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.IGNORECASE | re.DOTALL)


def _response_content(response: Mapping[str, Any]) -> str:
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ValueError("AI 服务返回了无效响应") from error
    if not isinstance(content, str) or not content.strip():
        raise ValueError("AI 服务返回了空响应")
    return content.strip()


def _parse_json_content(content: str) -> Optional[dict[str, Any]]:
    candidate = content.strip()
    fenced = _JSON_FENCE_RE.match(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def parse_companion_turn(
    response: Mapping[str, Any],
    character_name: str = "虚拟姬",
    *,
    model: Optional[str] = None,
) -> CompanionTurn:
    """Parse provider output and return a safe structured turn.

    Plain text remains a valid degraded response so provider formatting errors do
    not break the primary conversation path.
    """
    content = _response_content(response)
    payload = _parse_json_content(content)
    usage = response.get("usage") or {}
    tokens = usage.get("total_tokens") or 0

    if payload is None:
        return CompanionTurn(
            assistant_text=content,
            degraded_capabilities=["structured_output", "emotion", "intent"],
            model_context= {
                "current_model": model,
                "calls": 1,
                "fallback_used": False,
            },
        )

    assistant_text = payload.get("assistant_text") or payload.get("message")
    if not isinstance(assistant_text, str) or not assistant_text.strip():
        logger.warning("GirlAI 结构化响应缺少 assistant_text，回退到原始响应")
        assistant_text = content
        payload["degraded_capabilities"] = list(
            dict.fromkeys([*(payload.get("degraded_capabilities") or []), "assistant_text"])
        )

    model_context = dict(payload.get("model_context") or {})
    model_context.setdefault("current_model", model)
    model_context.setdefault("calls", 1)
    model_context.setdefault("fallback_used", False)
    payload["assistant_text"] = assistant_text.strip()
    payload["model_context"] = model_context
    payload["schema_version"] = payload.get("schema_version", 1)

    try:
        turn = CompanionTurn.model_validate(payload)
    except AttributeError:
        turn = CompanionTurn.parse_obj(payload)
    except Exception as error:
        logger.warning("GirlAI 结构化响应校验失败，使用降级回合: %s", error)
        turn = CompanionTurn(
            assistant_text=assistant_text.strip(),
            degraded_capabilities=["structured_output"],
            model_context=model_context,
        )

    if tokens:
        turn.model_context.calls = max(turn.model_context.calls, 1)
    return turn


__all__ = ["parse_companion_turn"]
