"""健康检查必须区分「Key 明确无效」与「瞬时不可用」。

apikey.py 原先把任何失败都 update_status("invalid")，一次网络超时就会让
有效 Key 在用户重测前被调用链跳过。
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.services.provider_health import get_health_checker


def _patched_client(status_code: int = 200):
    client = patch("httpx.AsyncClient")
    mock_client = client.start()
    response = Mock()
    response.status_code = status_code
    response.text = "err"
    instance = AsyncMock()
    instance.post.return_value = response
    mock_client.return_value.__aenter__.return_value = instance
    return client


@pytest.mark.asyncio
async def test_success_is_definitive():
    client = _patched_client(200)
    try:
        success, _, definitive = await get_health_checker().check_detailed(
            "siliconflow", "sk-key"
        )
    finally:
        client.stop()

    assert success is True
    assert definitive is True


@pytest.mark.asyncio
async def test_invalid_key_is_definitive():
    client = _patched_client(401)
    try:
        success, _, definitive = await get_health_checker().check_detailed(
            "siliconflow", "sk-key"
        )
    finally:
        client.stop()

    assert success is False
    assert definitive is True


@pytest.mark.asyncio
async def test_rate_limit_is_not_definitive():
    client = _patched_client(429)
    try:
        success, _, definitive = await get_health_checker().check_detailed(
            "siliconflow", "sk-key"
        )
    finally:
        client.stop()

    assert success is False
    assert definitive is False


@pytest.mark.asyncio
async def test_timeout_is_not_definitive():
    client = patch("httpx.AsyncClient")
    mock_client = client.start()
    instance = AsyncMock()
    instance.post.side_effect = Exception("Timeout")
    mock_client.return_value.__aenter__.return_value = instance
    try:
        success, _, definitive = await get_health_checker().check_detailed(
            "siliconflow", "sk-key"
        )
    finally:
        client.stop()

    assert success is False
    assert definitive is False


@pytest.mark.asyncio
async def test_unsupported_provider_is_definitive():
    success, _, definitive = await get_health_checker().check_detailed(
        "unknown_provider", "sk-key"
    )

    assert success is False
    assert definitive is True


@pytest.mark.asyncio
async def test_check_keeps_two_tuple_contract():
    result = await get_health_checker().check("unknown_provider", "sk-key")

    assert isinstance(result, tuple) and len(result) == 2
