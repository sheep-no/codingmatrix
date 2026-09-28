"""动态供应商 test 端点的出站安全回归（PAPI2 补全）。

PAPI2 原判定覆盖 sync 与 test 两个服务端出站请求点，但此前只在
``fetch_models_openai`` 内补了 ``check_outbound_url``；``test_connection``
端点仍会直接向 ``provider.base_url`` 拼出的 URL 发请求。本测试锁定该端点
在被其他调用方注入非公网 base_url 时不得发起任何出站请求。
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import providers as providers_module
from app.utils.aicloud.dynamic_provider import get_dynamic_provider_manager
from app.utils.rate_limiter import init_rate_limit
from app.utils.security import verify_token


@pytest.fixture(autouse=True)
def reset_manager():
    import app.utils.aicloud.dynamic_provider as dp_module

    original = dp_module._manager
    dp_module._manager = None
    yield
    dp_module._manager = original


def _client_for(token: dict) -> TestClient:
    app = FastAPI()
    init_rate_limit(app)
    app.include_router(providers_module.router)
    app.dependency_overrides[verify_token] = lambda: token
    return TestClient(app)


def test_test_connection_blocks_internal_base_url(monkeypatch):
    """非公网 base_url 拼出的 URL 不得发请求，直接返回失败。"""
    manager = get_dynamic_provider_manager()
    provider = manager.add(
        name="internal",
        base_url="http://127.0.0.1:8000",
        protocol="openai",
        api_key="sk-internal-1234567890",
        owner_id="u1",
    )

    state = {"called": False}

    def _no_network(*args, **kwargs):
        state["called"] = True
        raise AssertionError("不应向非公网地址发起请求")

    monkeypatch.setattr(providers_module.httpx, "AsyncClient", _no_network)

    client = _client_for({"sub": "u1", "permission_level": "admin"})
    resp = client.post(f"/api/v1/providers/{provider.id}/test")

    assert resp.status_code == 200
    data = resp.json()
    assert state["called"] is False
    assert data["success"] is False
    assert "内网" in data["message"]
