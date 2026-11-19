"""Stable fatal LLM error detection across wrapped exception chains."""

from app.agent.llm_client import LLMClientError
from app.core.llm_errors import (
    FATAL_LLM_ERROR_CODES,
    LLM_AUTH_FAILED,
    PROVIDER_API_KEY_NOT_CONFIGURED,
    USER_API_KEY_NOT_FOUND,
    error_code_of,
    fatal_error_message,
    is_fatal_llm_error,
)
from app.utils.aicloud.llm_caller import UserAPIKeyNotFoundError


def test_direct_fatal_error_is_detected() -> None:
    exc = UserAPIKeyNotFoundError()

    assert error_code_of(exc) == USER_API_KEY_NOT_FOUND
    assert is_fatal_llm_error(exc) is True
    assert "API Key" in fatal_error_message(exc)


def test_fatal_error_survives_runtime_and_client_wrappers() -> None:
    source = UserAPIKeyNotFoundError()
    client_error = LLMClientError(str(source), code=USER_API_KEY_NOT_FOUND)
    client_error.__cause__ = source
    wrapped = RuntimeError("ReAct LLM call failed")
    wrapped.__cause__ = client_error

    assert error_code_of(wrapped) == USER_API_KEY_NOT_FOUND
    assert is_fatal_llm_error(wrapped) is True


def test_missing_code_is_not_fatal() -> None:
    exc = RuntimeError("ordinary failure")

    assert error_code_of(exc) is None
    assert is_fatal_llm_error(exc) is False
    assert fatal_error_message(exc) == "ordinary failure"


def test_cyclic_cause_chain_terminates() -> None:
    first = RuntimeError("first")
    second = RuntimeError("second")
    first.__cause__ = second
    second.__cause__ = first

    assert error_code_of(first) is None
    assert is_fatal_llm_error(first) is False


def test_fatal_codes_include_provider_configuration() -> None:
    assert PROVIDER_API_KEY_NOT_CONFIGURED in FATAL_LLM_ERROR_CODES


def test_provider_auth_failure_is_fatal() -> None:
    exc = LLMClientError("认证失败", code="LLM_AUTH_FAILED")

    assert LLM_AUTH_FAILED in FATAL_LLM_ERROR_CODES
    assert is_fatal_llm_error(exc) is True
    assert "API Key" in fatal_error_message(exc)
