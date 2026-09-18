"""AiCodeUtil embedding 回归测试

覆盖已建档缺陷：
- AIU1 get_embedding 未复用模块级共享 HTTP 客户端，每次调用新建 AsyncClient
- AIU3 内存缓存超限时因最旧项未过期而停止淘汰，可无界增长
- AIU5 SILICONFLOW_API_KEY 未配置时无预校验，发出 Bearer None 请求
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

import app.utils.AiCodeUtil as aicu


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        return self._payload


def _mock_client(vector=None):
    vector = vector if vector is not None else [0.1, 0.2, 0.3]
    client = MagicMock()
    client.post = AsyncMock(
        return_value=_FakeResponse({"data": [{"embedding": vector}]})
    )
    return client


@pytest.fixture
def clean_cache():
    aicu._embedding_memory_cache.clear()
    aicu._embedding_memory_expiry.clear()
    yield
    aicu._embedding_memory_cache.clear()
    aicu._embedding_memory_expiry.clear()


async def test_get_embedding_reuses_shared_http_client(clean_cache, monkeypatch):
    """AIU1：embedding 请求走模块级共享客户端，并保留 30s 短超时。"""
    monkeypatch.setattr(aicu.settings, "SILICONFLOW_API_KEY", "sk-test")
    client = _mock_client()

    with (
        patch.object(aicu, "get_http_client", AsyncMock(return_value=client)),
        patch.object(
            aicu.httpx,
            "AsyncClient",
            side_effect=AssertionError("不应每次新建 httpx.AsyncClient"),
        ),
        patch.object(aicu, "_load_embedding_from_disk", return_value=None),
        patch.object(aicu, "_save_embedding_to_disk"),
    ):
        await aicu.get_embedding("hello")

    client.post.assert_awaited_once()
    request_timeout = client.post.await_args.kwargs["timeout"]
    assert request_timeout.read == 30.0
    assert request_timeout.connect == 10.0


async def test_get_embedding_requires_api_key(clean_cache, monkeypatch):
    """AIU5：Key 缺失时快速失败，不发送任何请求。"""
    monkeypatch.setattr(aicu.settings, "SILICONFLOW_API_KEY", "")
    client = _mock_client()

    with (
        patch.object(aicu, "get_http_client", AsyncMock(return_value=client)),
        patch.object(
            aicu.httpx,
            "AsyncClient",
            side_effect=AssertionError("不应发起请求"),
        ),
        patch.object(aicu, "_load_embedding_from_disk", return_value=None),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await aicu.get_embedding("hello")

    assert exc_info.value.status_code == 401
    client.post.assert_not_awaited()


async def test_memory_cache_evicts_when_over_maxsize(clean_cache, monkeypatch):
    """AIU3：写入超过上限的新鲜条目时，缓存规模保持在 MAXSIZE。"""
    monkeypatch.setattr(aicu.settings, "SILICONFLOW_API_KEY", "sk-test")
    client = _mock_client()
    total = aicu._EMBEDDING_CACHE_MAXSIZE + 8

    with (
        patch.object(aicu, "get_http_client", AsyncMock(return_value=client)),
        patch.object(
            aicu.httpx,
            "AsyncClient",
            side_effect=AssertionError("不应每次新建 httpx.AsyncClient"),
        ),
        patch.object(aicu, "_load_embedding_from_disk", return_value=None),
        patch.object(aicu, "_save_embedding_to_disk"),
        patch.object(aicu, "_clean_expired_disk_cache"),
    ):
        first_key = aicu._get_embedding_cache_key("text-0", aicu.DEFAULT_EMBEDDING_MODEL)
        for index in range(total):
            await aicu.get_embedding(f"text-{index}")

    assert len(aicu._embedding_memory_cache) == aicu._EMBEDDING_CACHE_MAXSIZE
    assert first_key not in aicu._embedding_memory_cache
    assert first_key not in aicu._embedding_memory_expiry
