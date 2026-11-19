"""Shared LLM call errors and HTTP response normalization."""

from __future__ import annotations

from typing import Any, Optional

from app.core.llm_errors import LLM_AUTH_FAILED, LLM_RATE_LIMITED

LLM_PROVIDER_ERROR = "LLM_PROVIDER_ERROR"


def code_for_status(status_code: int) -> str:
    if status_code in (401, 403):
        return LLM_AUTH_FAILED
    if status_code == 429:
        return LLM_RATE_LIMITED
    return LLM_PROVIDER_ERROR


def retry_after_from_headers(headers: Any) -> Optional[float]:
    getter = getattr(headers, "get", None)
    if getter is None:
        return None
    raw = getter("Retry-After") or getter("retry-after")
    if raw is None:
        return None
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


class LLMCallError(Exception):
    """Unified provider failure carrying an HTTP status and stable code."""

    def __init__(
        self,
        message: str,
        status_code: int = 500,
        code: str = "LLM_CALL_ERROR",
        retry_after: Optional[float] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.retry_after = retry_after


def error_from_response(response: Any, body: Optional[str] = None) -> LLMCallError:
    status_code = int(getattr(response, "status_code", 500) or 500)
    text = body if body is not None else (getattr(response, "text", "") or "")
    message = f"HTTP {status_code}: {text[:500]}" if text else f"HTTP {status_code}"
    return LLMCallError(
        message,
        status_code=status_code,
        code=code_for_status(status_code),
        retry_after=retry_after_from_headers(getattr(response, "headers", None)),
    )


def normalize_llm_error(exc: BaseException) -> Optional[LLMCallError]:
    """Convert provider/transport failures into one public error type."""
    if isinstance(exc, LLMCallError):
        return exc
    response = getattr(exc, "response", None)
    status_code = getattr(exc, "status_code", None)
    if status_code is None and response is not None:
        status_code = getattr(response, "status_code", None)
    if status_code is None:
        return None
    retry_after = getattr(exc, "retry_after", None)
    if retry_after is None and response is not None:
        retry_after = retry_after_from_headers(getattr(response, "headers", None))
    try:
        status = int(status_code)
    except (TypeError, ValueError):
        return None
    return LLMCallError(
        str(exc) or f"HTTP {status}",
        status_code=status,
        code=code_for_status(status),
        retry_after=retry_after,
    )
