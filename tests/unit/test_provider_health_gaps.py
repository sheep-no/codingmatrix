"""provider_health 各供应商分派与状态码分支补测。"""

from unittest.mock import AsyncMock, Mock, patch

import httpx
import pytest

from app.services import provider_health as module
from app.services.provider_health import ProviderHealthChecker


def _patch_client(*, status_code=200, exc=None, text="body"):
    client = patch("httpx.AsyncClient")
    mock_client = client.start()
    if exc is not None:
        instance = AsyncMock()
        instance.post.side_effect = exc
    else:
        response = Mock()
        response.status_code = status_code
        response.text = text
        instance = AsyncMock()
        instance.post.return_value = response
    mock_client.return_value.__aenter__.return_value = instance
    return client


@pytest.mark.parametrize(
    "provider",
    ["siliconflow", "openai", "bailian", "glm", "deepseek"],
)
async def test_openai_compatible_dispatch_success(provider):
    client = _patch_client(status_code=200)
    try:
        success, message, definitive = await ProviderHealthChecker().check_detailed(provider, "key")
    finally:
        client.stop()

    assert (success, message, definitive) == (True, "连接成功", True)


@pytest.mark.parametrize("status_code,message", [(401, "API Key 无效"), (403, "权限不足")])
async def test_openai_compatible_auth_failures_are_definitive(status_code, message):
    client = _patch_client(status_code=status_code)
    try:
        success, text, definitive = await ProviderHealthChecker().check_detailed("openai", "key")
    finally:
        client.stop()

    assert (success, text, definitive) == (False, message, True)


async def test_openai_compatible_other_status_truncates_body():
    client = _patch_client(status_code=500, text="x" * 200)
    try:
        success, text, definitive = await ProviderHealthChecker().check_detailed("bailian", "key")
    finally:
        client.stop()

    assert success is False
    assert definitive is False
    assert text.startswith("HTTP 500: ")
    assert len(text) == len("HTTP 500: ") + 100


async def test_openai_compatible_timeout_is_not_definitive():
    client = _patch_client(exc=httpx.TimeoutException("slow"))
    try:
        success, text, definitive = await ProviderHealthChecker().check_detailed("glm", "key")
    finally:
        client.stop()

    assert (success, text, definitive) == (False, "请求超时", False)


async def test_openai_compatible_connection_error_is_reported():
    client = _patch_client(exc=RuntimeError("refused"))
    try:
        success, text, definitive = await ProviderHealthChecker().check_detailed("deepseek", "key")
    finally:
        client.stop()

    assert (success, text, definitive) == (False, "连接失败：refused", False)


async def test_anthropic_success_and_failures():
    client = _patch_client(status_code=200)
    try:
        assert await ProviderHealthChecker().check_detailed("anthropic", "key") == (
            True, "连接成功", True,
        )
    finally:
        client.stop()

    for status_code, expected in ((401, "API Key 无效"), (403, "权限不足")):
        client = _patch_client(status_code=status_code)
        try:
            assert await ProviderHealthChecker().check_detailed("anthropic", "key") == (
                False, expected, True,
            )
        finally:
            client.stop()


async def test_anthropic_other_status_and_timeout():
    client = _patch_client(status_code=503, text="unavailable")
    try:
        assert await ProviderHealthChecker().check_detailed("anthropic", "key") == (
            False, "HTTP 503: unavailable", False,
        )
    finally:
        client.stop()

    client = _patch_client(exc=httpx.TimeoutException("slow"))
    try:
        assert await ProviderHealthChecker().check_detailed("anthropic", "key") == (
            False, "请求超时", False,
        )
    finally:
        client.stop()

    client = _patch_client(exc=RuntimeError("boom"))
    try:
        assert await ProviderHealthChecker().check_detailed("anthropic", "key") == (
            False, "连接失败：boom", False,
        )
    finally:
        client.stop()


def test_get_health_checker_creates_and_reuses_singleton(monkeypatch):
    monkeypatch.setattr(module, "_health_checker", None)

    first = module.get_health_checker()
    second = module.get_health_checker()

    assert first is second
    assert isinstance(first, ProviderHealthChecker)


async def test_unknown_but_configured_provider_uses_compatible_default(monkeypatch):
    monkeypatch.setitem(
        module.PROVIDER_CONFIGS,
        "custom",
        {"base_url": "https://custom.test/v1", "model": "m"},
    )
    client = _patch_client(status_code=200)
    try:
        assert await ProviderHealthChecker().check_detailed("custom", "key") == (
            True, "连接成功", True,
        )
    finally:
        client.stop()
