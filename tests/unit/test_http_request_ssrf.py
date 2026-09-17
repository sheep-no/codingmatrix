"""HTTP 请求节点的 SSRF 与响应头防护回归。

覆盖已建档缺陷：
- HRQ1 DNS 解析失败即放行（执行期应 fail-closed）
- HRQ2 变量替换后的 URL 不再做 SSRF 检查
- HRQ3 follow_redirects=True 可跳转内网
- HRQ4 响应头全量进入上下文（Set-Cookie 等敏感头）
"""

import pytest

from app.utils.workflow.node_types import http_request as http_module
from app.utils.workflow.node_types.http_request import HTTPRequestNode

# 公网 IP 字面量，避免测试依赖真实 DNS
PUBLIC_URL = "http://93.184.216.34/api"


class FakeResponse:
    def __init__(self, status_code=200, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload if payload is not None else {"ok": True}

    def json(self):
        return self._payload

    @property
    def text(self):
        return '{"ok": true}'


class FakeClient:
    instances = []

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        FakeClient.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def request(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, "kwargs": kwargs})
        return self._responses.pop(0)


@pytest.fixture
def fake_client(monkeypatch):
    responses = []

    def factory(*args, **kwargs):
        return FakeClient(responses)

    FakeClient.instances.clear()
    monkeypatch.setattr(http_module.httpx, "AsyncClient", factory)
    return responses


def test_dns_failure_is_rejected_when_strict():
    node = HTTPRequestNode("n1", {"url": "http://no-such-host.invalid/x"})

    assert node._check_ssrf("http://no-such-host.invalid/x", strict=True) is not None
    # 校验阶段 URL 可能是模板，保持宽松
    assert node._check_ssrf("http://{host}/x") is None


@pytest.mark.asyncio
async def test_url_replaced_with_internal_address_is_blocked(monkeypatch):
    node = HTTPRequestNode("n1", {"url": "http://{addr_result}/secret"})
    monkeypatch.setattr(
        http_module.httpx,
        "AsyncClient",
        lambda *a, **k: pytest.fail("不应向被拒绝的地址发起请求"),
    )

    result = await node.execute({"addr_result": "127.0.0.1"})

    assert result.success is False
    assert "安全校验" in result.error


@pytest.mark.asyncio
async def test_redirect_to_internal_address_is_blocked(fake_client):
    fake_client.append(FakeResponse(302, {"location": "http://127.0.0.1/admin"}))
    node = HTTPRequestNode("n1", {"url": PUBLIC_URL})

    result = await node.execute({})

    assert result.success is False
    assert "重定向" in result.error
    # 只发出了首次请求，未跟随到内网
    assert len(FakeClient.instances[0].calls) == 1


@pytest.mark.asyncio
async def test_redirect_to_public_address_is_followed(fake_client):
    fake_client.append(FakeResponse(302, {"location": f"{PUBLIC_URL}/next"}))
    fake_client.append(FakeResponse(200, payload={"done": True}))
    node = HTTPRequestNode("n1", {"url": PUBLIC_URL})

    result = await node.execute({})

    assert result.success is True
    assert len(FakeClient.instances[0].calls) == 2
    assert FakeClient.instances[0].calls[0]["kwargs"]["follow_redirects"] is False


@pytest.mark.asyncio
async def test_sensitive_response_headers_are_not_exposed(fake_client):
    fake_client.append(
        FakeResponse(
            200,
            {
                "content-type": "application/json",
                "Set-Cookie": "session=secret",
                "Authorization": "Bearer secret",
            },
        )
    )
    node = HTTPRequestNode("n1", {"url": PUBLIC_URL})

    result = await node.execute({})

    assert result.success is True
    headers = result.data["headers"]
    assert headers["content-type"] == "application/json"
    assert "Set-Cookie" not in headers
    assert "Authorization" not in headers
