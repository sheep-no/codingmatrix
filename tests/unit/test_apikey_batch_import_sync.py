"""批量导入的模型同步行为（APY3）。

单条提交会为 OpenAI 兼容供应商异步同步模型列表，批量导入此前不触发，
导致批量导入的 Key 缺少 context_length/模型元数据。
"""

import asyncio

import pytest
from starlette.requests import Request

from app.api.v1 import apikey


def _request() -> Request:
    return Request({
        "type": "http",
        "method": "POST",
        "path": "/api/v1/apikey/batch-import",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
    })


class _FakeManager:
    def __init__(self):
        self.stored = []

    def store_key(self, **kwargs):
        self.stored.append(kwargs)
        return f"tok-{len(self.stored)}"


@pytest.mark.asyncio
async def test_batch_import_syncs_openai_compat_providers_once(monkeypatch):
    fake_manager = _FakeManager()
    monkeypatch.setattr(apikey, "get_apikey_manager", lambda: fake_manager)
    monkeypatch.setattr(
        apikey,
        "get_rsa_key_manager",
        lambda: type("K", (), {"decrypt": staticmethod(lambda s: "x" * 20)})(),
    )

    scheduled = []

    async def fake_sync(provider, api_key, user_id):
        scheduled.append((provider, user_id))

    monkeypatch.setattr(apikey, "_sync_provider_models", fake_sync)

    request = apikey.BatchImportRequest(keys=[
        {"provider": "openai", "encrypted_key": "enc", "ttl": "24h"},
        {"provider": "openai", "encrypted_key": "enc", "ttl": "7d"},
        {"provider": "anthropic", "encrypted_key": "enc", "ttl": "24h"},
    ])

    response = await apikey.batch_import(_request(), request, "u1")
    await asyncio.sleep(0)

    assert response.success_count == 3
    assert len(fake_manager.stored) == 3
    # openai 兼容供应商同步一次；anthropic 不在兼容列表，不触发
    assert scheduled == [("openai", "u1")]


@pytest.mark.asyncio
async def test_batch_import_custom_ttl_still_accepted(monkeypatch):
    """批量导入的 TTL 与单条同源（resolve_ttl），自定义秒数应被接受。"""
    fake_manager = _FakeManager()
    monkeypatch.setattr(apikey, "get_apikey_manager", lambda: fake_manager)
    monkeypatch.setattr(
        apikey,
        "get_rsa_key_manager",
        lambda: type("K", (), {"decrypt": staticmethod(lambda s: "x" * 20)})(),
    )
    monkeypatch.setattr(apikey, "_sync_provider_models", lambda *a, **k: None)

    request = apikey.BatchImportRequest(keys=[
        {"provider": "deepseek", "encrypted_key": "enc", "ttl": "3600"},
    ])

    response = await apikey.batch_import(_request(), request, "u1")

    assert response.success_count == 1
    assert fake_manager.stored[0]["ttl"] == "3600"
