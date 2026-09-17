"""出站 URL 安全校验与用户可控 base_url 入口的 SSRF 防护。

服务端会向自定义供应商的 base_url 发起请求，未校验时可被用来探测
内网服务或云元数据端点。
"""

import pytest
from fastapi import HTTPException

from app.api.v1 import providers as providers_module
from app.services.custom_provider_manager import CustomProviderManager
from app.utils import url_safety


def _resolves_to(monkeypatch, ip):
    def fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return [(url_safety.socket.AF_INET, 0, 0, "", (ip, 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)


@pytest.mark.parametrize("url,expected_fragment", [
    ("http://127.0.0.1:8000/v1", "不允许访问"),
    ("http://169.254.169.254/latest/meta-data", "不允许访问"),
    ("http://10.0.0.5/v1", "不允许访问"),
    ("http://192.168.1.10/v1", "不允许访问"),
    ("http://[::1]:8000/v1", "不允许访问"),
    ("http://0.0.0.0/v1", "不允许访问"),
    ("http://user:pass@127.0.0.1/v1", "不允许访问"),
    ("file:///etc/passwd", "仅支持 http/https"),
    ("ftp://example.com/v1", "仅支持 http/https"),
    ("gopher://127.0.0.1/", "仅支持 http/https"),
    ("http://", "缺少主机名"),
])
def test_disallowed_urls_are_rejected(url, expected_fragment):
    error = url_safety.check_outbound_url(url)

    assert error is not None
    assert expected_fragment in error


def test_public_ip_is_allowed():
    assert url_safety.check_outbound_url("https://8.8.8.8/v1") is None


def test_domain_resolving_to_private_ip_is_rejected(monkeypatch):
    _resolves_to(monkeypatch, "10.1.2.3")

    error = url_safety.check_outbound_url("https://internal.example.com/v1")

    assert error is not None
    assert "不允许访问" in error


def test_domain_resolving_to_public_ip_is_allowed(monkeypatch):
    _resolves_to(monkeypatch, "93.184.216.34")

    assert url_safety.check_outbound_url("https://api.example.com/v1") is None


def test_unresolvable_domain_is_allowed_to_fail_at_connect_time(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        raise url_safety.socket.gaierror("Name or service not known")

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)

    assert url_safety.check_outbound_url("https://no-such-host.invalid/v1") is None


def _add_provider_request(base_url, protocol="openai"):
    return providers_module.AddProviderRequest(
        name="probe",
        base_url=base_url,
        protocol=protocol,
        encrypted_api_key="irrelevant-when-url-is-rejected",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("base_url", [
    "http://169.254.169.254/latest/meta-data",
    "http://127.0.0.1:11434/v1",
    "http://10.0.0.1/v1",
])
async def test_api_rejects_internal_base_url_before_decrypting_key(base_url):
    with pytest.raises(HTTPException) as error:
        await providers_module.add_provider.__wrapped__(
            request=None,
            body=_add_provider_request(base_url),
            token={"sub": "1", "permission_level": "admin"},
        )

    assert error.value.status_code == 400
    assert "不允许访问" in error.value.detail


def test_custom_provider_manager_rejects_internal_base_url():
    manager = CustomProviderManager()

    with pytest.raises(ValueError, match="不允许访问"):
        manager.add_provider(
            name="probe",
            base_url="http://169.254.169.254",
            protocol="openai",
            api_key="sk-test-key-123456",
        )


def test_custom_provider_manager_accepts_public_base_url(monkeypatch):
    _resolves_to(monkeypatch, "93.184.216.34")
    manager = CustomProviderManager()

    provider = manager.add_provider(
        name="vendor",
        base_url="https://api.vendor.com",
        protocol="openai",
        api_key="sk-test-key-123456",
    )

    assert provider.base_url == "https://api.vendor.com/v1"
