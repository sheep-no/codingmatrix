"""app.utils.http_client 连接池生命周期补测。"""

import asyncio

import httpx
import pytest

from app.utils import http_client as module


class _FakeClient:
    def __init__(self, closed=False):
        self.closed = closed
        self.aclosed = False

    @property
    def is_closed(self):
        return self.closed

    async def aclose(self):
        self.aclosed = True
        self.closed = True


def _pool(monkeypatch):
    created = []

    class _Client(_FakeClient):
        def __init__(self, **kwargs):
            super().__init__()
            self.kwargs = kwargs
            created.append(self)

    monkeypatch.setattr(module.httpx, "AsyncClient", _Client)
    return module.HTTPClientPool(), created


async def test_get_client_reuses_open_client(monkeypatch):
    pool, created = _pool(monkeypatch)

    first = await pool.get_client()
    second = await pool.get_client()

    assert first is second
    assert len(created) == 1
    assert pool._client is first
    assert created[0].kwargs["follow_redirects"] is True


async def test_get_client_recreates_closed_client(monkeypatch):
    pool, created = _pool(monkeypatch)
    first = await pool.get_client()
    first.closed = True

    second = await pool.get_client()

    assert second is not first
    assert len(created) == 2


async def test_close_acloses_and_clears_client(monkeypatch):
    pool, _ = _pool(monkeypatch)
    client = await pool.get_client()

    await pool.close()

    assert client.aclosed is True
    assert pool._client is None


async def test_close_without_client_is_noop():
    pool = module.HTTPClientPool()

    await pool.close()

    assert pool._client is None


async def test_client_context_manager_yields_shared_client(monkeypatch):
    pool, _ = _pool(monkeypatch)

    async with pool.client() as client:
        assert client is pool._client

    assert pool._client is not None


async def test_async_context_manager_returns_client(monkeypatch):
    pool, _ = _pool(monkeypatch)

    async with pool as client:
        assert client is pool._client

    assert pool._client is client


def test_get_http_client_pool_is_singleton(monkeypatch):
    monkeypatch.setattr(module, "_http_client_pool", None)

    first = module.get_http_client_pool()
    second = module.get_http_client_pool()

    assert first is second
    assert first._max_connections == 20
    assert first._max_keepalive == 10
    assert first._timeout == 30.0


async def test_get_http_client_delegates_to_pool(monkeypatch):
    monkeypatch.setattr(module, "_http_client_pool", None)
    pool, _ = _pool(monkeypatch)
    monkeypatch.setattr(module, "get_http_client_pool", lambda: pool)

    client = await module.get_http_client()

    assert client is pool._client


async def test_close_http_client_closes_pool(monkeypatch):
    monkeypatch.setattr(module, "_http_client_pool", None)
    pool, _ = _pool(monkeypatch)
    monkeypatch.setattr(module, "get_http_client_pool", lambda: pool)
    await module.get_http_client()

    await module.close_http_client()

    assert pool._client is None
