"""Stable LLM error codes shared by callers, schedulers, and API layers."""

from __future__ import annotations

from typing import Any

USER_API_KEY_NOT_FOUND = "USER_API_KEY_NOT_FOUND"
PROVIDER_API_KEY_NOT_CONFIGURED = "PROVIDER_API_KEY_NOT_CONFIGURED"

FATAL_LLM_ERROR_CODES = frozenset({
    USER_API_KEY_NOT_FOUND,
    PROVIDER_API_KEY_NOT_CONFIGURED,
})

FATAL_LLM_ERROR_MESSAGES = {
    USER_API_KEY_NOT_FOUND: "用户 API Key 未找到或已过期，请重新配置",
    PROVIDER_API_KEY_NOT_CONFIGURED: "供应商 API Key 未配置，请在 Settings → API Key 管理中添加",
}


def error_code_of(exc: BaseException | None) -> str | None:
    """Return the nearest stable error code in an exception cause chain."""
    seen: set[int] = set()
    current: Any = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "code", None)
        if isinstance(code, str) and code:
            return code
        current = current.__cause__ or current.__context__
    return None


def is_fatal_llm_error(exc: BaseException | None) -> bool:
    """True when the failure cannot be repaired by retrying the same call."""
    return error_code_of(exc) in FATAL_LLM_ERROR_CODES


def fatal_error_message(exc: BaseException | None) -> str:
    """Human-readable message for a known fatal LLM configuration error."""
    code = error_code_of(exc)
    if code in FATAL_LLM_ERROR_MESSAGES:
        return FATAL_LLM_ERROR_MESSAGES[code]
    return str(exc) or "LLM 配置错误"
