"""动态供应商 API 全分支回归：权限、校验、同步与连接测试。"""

import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import providers as pv
from app.utils.aicloud.dynamic_provider import (
    ModelInfo,
    get_dynamic_provider_manager,
)
from app.utils.rate_limiter import init_rate_limit
from app.utils.security import verify_token


@pytest.fixture(autouse=True)
def reset_manager():
    import app.utils.aicloud.dynamic_provider as dp_module

    original = dp_module._manager
    dp_module._manager = None
    yield
    dp_module._manager = original


@pytest.fixture(autouse=True)
def disable_rate_limit():
    original = pv.limiter.enabled
    pv.limiter.enabled = False
    yield
    pv.limiter.enabled = original


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(pv, "check_outbound_url", lambda url: None)
    monkeypatch.setattr(pv, "get_rsa_key_manager", lambda: _Crypto())
    app = _build_app(monkeypatch)
    return TestClient(app)


def _build_app(monkeypatch=None):
    app = FastAPI()
    init_rate_limit(app)
    app.include_router(pv.router)
    app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "admin",
    }
    return app


class _Crypto:
    def __init__(self, key="sk-valid-key-123456", fail=False):
        self.key = key
        self.fail = fail

    def decrypt(self, value):
        if self.fail:
            raise ValueError("bad ciphertext")
        return self.key


def _add(manager, name="p", base_url="https://api.example.com", protocol="openai"):
    return manager.add(
        name=name,
        base_url=base_url,
        protocol=protocol,
        api_key="sk-valid-key-123456",
        owner_id="u1",
    )


def test_add_provider_requires_admin(client):
    client.app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "user",
    }
    resp = client.post(
        "/api/v1/providers",
        json={
            "name": "p",
            "base_url": "https://api.example.com",
            "protocol": "openai",
            "encrypted_api_key": "x",
        },
    )
    assert resp.status_code == 403


@pytest.mark.parametrize(
    "protocol,base_url,key,fail,status",
    [
        ("grpc", "https://a.com", "sk-valid-key-123456", False, 400),
        ("openai", "http://127.0.0.1", "sk-valid-key-123456", False, 400),
        ("openai", "https://a.com", "short", False, 400),
        ("openai", "https://a.com", "x", True, 400),
    ],
)
def test_add_provider_validation_failures(
    client, protocol, base_url, key, fail, status
):
    client.app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "admin",
    }
    app = _build_app()
    pv.get_rsa_key_manager = lambda: _Crypto(key=key, fail=fail)
    pv.check_outbound_url = (
        (lambda url: "内网地址不允许")
        if base_url.startswith("http://127.0.0.1")
        else (lambda url: None)
    )
    local = TestClient(app)
    resp = local.post(
        "/api/v1/providers",
        json={
            "name": "p",
            "base_url": base_url,
            "protocol": protocol,
            "encrypted_api_key": "cipher",
        },
    )
    assert resp.status_code == status


def test_add_provider_success(client):
    resp = client.post(
        "/api/v1/providers",
        json={
            "name": "OpenAI",
            "base_url": "https://api.example.com/",
            "protocol": "openai",
            "encrypted_api_key": "cipher",
        },
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["name"] == "OpenAI"
    assert "已添加" in payload["message"]


def test_list_and_get_provider(client):
    provider = _add(get_dynamic_provider_manager())
    provider.models = [ModelInfo(id="gpt-4"), ModelInfo(id="gpt-3.5")]
    provider.last_sync = time.time()

    listed = client.get("/api/v1/providers").json()
    assert listed[0]["models"] == ["gpt-4", "gpt-3.5"]

    detail = client.get(f"/api/v1/providers/{provider.id}").json()
    assert detail["protocol"] == "openai"

    assert client.get("/api/v1/providers/missing").status_code == 404


def test_list_providers_default_owner(client):
    client.app.dependency_overrides[verify_token] = lambda: {}
    assert client.get("/api/v1/providers").json() == []


def test_delete_provider_requires_admin_and_handles_missing(client):
    provider = _add(get_dynamic_provider_manager())
    client.app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "user",
    }
    assert client.delete(f"/api/v1/providers/{provider.id}").status_code == 403

    client.app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "admin",
    }
    assert client.delete(f"/api/v1/providers/{provider.id}").status_code == 200
    assert client.delete(f"/api/v1/providers/{provider.id}").status_code == 404


def test_toggle_provider_requires_admin_and_flips_state(client):
    provider = _add(get_dynamic_provider_manager())
    client.app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "user",
    }
    assert client.put(f"/api/v1/providers/{provider.id}/toggle").status_code == 403

    client.app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "admin",
    }
    disabled = client.put(f"/api/v1/providers/{provider.id}/toggle").json()
    assert disabled == {"message": "供应商已禁用", "enabled": False}
    enabled = client.put(f"/api/v1/providers/{provider.id}/toggle").json()
    assert enabled == {"message": "供应商已启用", "enabled": True}
    assert client.put("/api/v1/providers/missing/toggle").status_code == 404


def test_sync_requires_admin_and_missing(client, monkeypatch):
    client.app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "user",
    }
    assert client.post("/api/v1/providers/any/sync").status_code == 403

    client.app.dependency_overrides[verify_token] = lambda: {
        "sub": "u1",
        "permission_level": "admin",
    }
    assert client.post("/api/v1/providers/missing/sync").status_code == 404


def test_sync_returns_cached_without_force(client):
    provider = _add(get_dynamic_provider_manager())
    provider.models = [ModelInfo(id="a")]
    provider.last_sync = time.time()
    payload = client.post(f"/api/v1/providers/{provider.id}/sync").json()
    assert payload["count"] == 1
    assert "缓存" in payload["message"]


def test_sync_fetches_and_force_bypasses_cache(client, monkeypatch):
    provider = _add(get_dynamic_provider_manager())
    provider.models = [ModelInfo(id="old")]
    provider.last_sync = time.time()
    calls = []

    async def _fetch(p):
        calls.append(p.id)
        return [ModelInfo(id="new")]

    monkeypatch.setattr(pv, "fetch_models_openai", _fetch)
    payload = client.post(f"/api/v1/providers/{provider.id}/sync?force=true").json()
    assert payload["count"] == 1
    assert calls == [provider.id]
    assert provider.models[0].id == "new"


def test_sync_anthropic_branch(client, monkeypatch):
    provider = _add(get_dynamic_provider_manager(), protocol="anthropic")
    calls = []

    async def _fetch(p):
        calls.append(p.id)
        return [ModelInfo(id="claude")]

    monkeypatch.setattr(pv, "fetch_models_anthropic", _fetch)
    payload = client.post(f"/api/v1/providers/{provider.id}/sync").json()
    assert payload["count"] == 1
    assert calls == [provider.id]


def test_sync_failure_records_error(client, monkeypatch):
    provider = _add(get_dynamic_provider_manager())
    provider.models = [ModelInfo(id="kept")]

    async def _boom(p):
        raise RuntimeError("upstream down")

    monkeypatch.setattr(pv, "fetch_models_openai", _boom)
    payload = client.post(f"/api/v1/providers/{provider.id}/sync").json()
    assert payload["error"] == "upstream down"
    assert payload["count"] == 1
    assert "同步失败" in payload["message"]
    assert provider.sync_error == "upstream down"


def test_sync_refetches_when_cache_expired(client, monkeypatch):
    provider = _add(get_dynamic_provider_manager())
    provider.models = [ModelInfo(id="old")]
    provider.last_sync = time.time() - pv.MODEL_CACHE_TTL - 1
    calls = []

    async def _fetch(p):
        calls.append(p.id)
        return [ModelInfo(id="fresh")]

    monkeypatch.setattr(pv, "fetch_models_openai", _fetch)
    payload = client.post(f"/api/v1/providers/{provider.id}/sync").json()
    assert payload["count"] == 1
    assert calls == [provider.id]
    assert provider.models[0].id == "fresh"


class _Response:
    def __init__(self, status_code=200, text="body"):
        self.status_code = status_code
        self.text = text


class _AsyncClient:
    response = _Response()
    error = None
    captured = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, headers=None, json=None):
        _AsyncClient.captured.update(url=url, headers=headers, json=json)
        if _AsyncClient.error:
            raise _AsyncClient.error
        return _AsyncClient.response


@pytest.fixture
def fake_http(monkeypatch):
    _AsyncClient.response = _Response()
    _AsyncClient.error = None
    _AsyncClient.captured = {}
    monkeypatch.setattr(pv.httpx, "AsyncClient", _AsyncClient)
    return _AsyncClient


def test_test_connection_missing_provider(client):
    assert client.post("/api/v1/providers/missing/test").status_code == 404


@pytest.mark.parametrize(
    "status,expected",
    [
        (200, "连接成功"),
        (401, "API Key 无效"),
        (403, "权限不足"),
        (429, "请求频率过高"),
        (418, "HTTP 418: body"),
    ],
)
def test_test_connection_status_mapping(client, fake_http, status, expected):
    provider = _add(get_dynamic_provider_manager())
    fake_http.response = _Response(status_code=status, text="body")
    payload = client.post(f"/api/v1/providers/{provider.id}/test").json()
    assert payload["message"] == expected


def test_test_connection_anthropic_payload(client, fake_http):
    provider = _add(get_dynamic_provider_manager(), protocol="anthropic")
    payload = client.post(f"/api/v1/providers/{provider.id}/test").json()
    assert payload["success"] is True
    captured = fake_http.captured
    assert captured["url"].endswith("/messages")
    assert captured["headers"]["anthropic-version"] == "2023-06-01"
    assert captured["json"]["model"].startswith("claude")


def test_test_connection_openai_payload(client, fake_http):
    provider = _add(get_dynamic_provider_manager())
    client.post(f"/api/v1/providers/{provider.id}/test")
    assert fake_http.captured["url"].endswith("/chat/completions")
    assert fake_http.captured["headers"]["Authorization"].startswith("Bearer ")


def test_test_connection_timeout_and_generic_error(client, fake_http):
    provider = _add(get_dynamic_provider_manager())
    fake_http.error = pv.httpx.TimeoutException("slow")
    assert client.post(f"/api/v1/providers/{provider.id}/test").json() == {
        "success": False,
        "message": "请求超时",
    }

    fake_http.error = RuntimeError("boom")
    payload = client.post(f"/api/v1/providers/{provider.id}/test").json()
    assert payload["message"] == "连接失败: boom"


def test_test_connection_blocked_by_outbound_check(client, monkeypatch):
    provider = _add(get_dynamic_provider_manager())
    monkeypatch.setattr(pv, "check_outbound_url", lambda url: "内网地址不允许")
    called = []
    monkeypatch.setattr(pv.httpx, "AsyncClient", lambda *a, **k: called.append(1))
    payload = client.post(f"/api/v1/providers/{provider.id}/test").json()
    assert payload["success"] is False
    assert "内网" in payload["message"]
    assert called == []
