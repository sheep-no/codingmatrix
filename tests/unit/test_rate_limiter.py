"""rate_limiter 回归测试。

覆盖已建档缺陷：
- RL1 默认单进程内存计数（配置 Redis 时改用 Redis 存储）
- RL2 忽略反向代理导致全站共享同一配额
- RL4 429 响应未使用项目统一错误格式
- RL5 get_client_ip 零消费且缺少可信代理校验
- RL6 default_limits 未挂载 SlowAPIMiddleware 导致全局限流不生效
"""

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from slowapi import Limiter
from starlette.requests import Request
from slowapi.middleware import SlowAPIASGIMiddleware
from slowapi.errors import RateLimitExceeded

from app.utils import rate_limiter as mod


class _FakeApp:
    def __init__(self, limiter_obj=None):
        self.state = SimpleNamespace(limiter=limiter_obj)
        self.handlers = {}

    def add_exception_handler(self, exc, handler):
        self.handlers[exc] = handler


def _request(host, headers=None, app=None):
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": [
            (key.lower().encode(), value.encode())
            for key, value in (headers or {}).items()
        ],
        "client": (host, 1234) if host is not None else None,
        "server": ("testserver", 80),
        "scheme": "http",
        "state": {},
    }
    if app is not None:
        scope["app"] = app
    return Request(scope)


def test_is_trusted_peer():
    assert mod._is_trusted_peer("127.0.0.1")
    assert mod._is_trusted_peer("10.1.2.3")
    assert mod._is_trusted_peer("192.168.1.5")
    assert mod._is_trusted_peer("::1")
    assert not mod._is_trusted_peer("8.8.8.8")
    assert not mod._is_trusted_peer("testclient")


def test_client_ip_uses_x_real_ip_from_trusted_peer():
    req = _request("127.0.0.1", {"X-Real-IP": "203.0.113.9"})

    assert mod.get_client_ip(req) == "203.0.113.9"


def test_client_ip_uses_last_forwarded_entry_when_trusted():
    req = _request("10.0.0.5", {"X-Forwarded-For": "1.2.3.4, 203.0.113.9"})

    assert mod.get_client_ip(req) == "203.0.113.9"


def test_client_ip_ignores_spoofed_headers_from_untrusted_peer():
    """公网直连时不得采信客户端伪造的代理头，否则可绕过限流。"""
    req = _request(
        "8.8.8.8",
        {"X-Forwarded-For": "1.2.3.4", "X-Real-IP": "9.9.9.9"},
    )

    assert mod.get_client_ip(req) == "8.8.8.8"


def test_client_ip_falls_back_to_peer_without_headers():
    assert mod.get_client_ip(_request("127.0.0.1")) == "127.0.0.1"


def test_client_ip_handles_missing_client():
    assert mod.get_client_ip(_request(None)) == "unknown"


def test_limiter_uses_proxy_aware_key_func():
    assert mod.limiter._key_func is mod.get_client_ip


def test_resolve_storage_uri(monkeypatch):
    monkeypatch.setattr(mod.settings, "REDIS_URL", "")
    assert mod._resolve_storage_uri() is None

    monkeypatch.setattr(mod.settings, "REDIS_URL", "  redis://localhost:6379/0  ")
    assert mod._resolve_storage_uri() == "redis://localhost:6379/0"


def test_rate_limit_handler_returns_project_envelope():
    req = _request("127.0.0.1", app=_FakeApp(None))
    req.state.view_rate_limit = None
    exc = SimpleNamespace(detail="5 per 1 minute")

    response = mod._rate_limit_handler(req, exc)
    body = json.loads(response.body)

    assert response.status_code == 429
    assert body["code"] == "RATE_LIMIT_EXCEEDED"
    assert body["details"]["limit"] == "5 per 1 minute"


def test_init_rate_limit_registers_custom_handler():
    app = _FakeApp()

    mod.init_rate_limit(app)

    assert app.handlers[RateLimitExceeded] is mod._rate_limit_handler
    assert app.state.limiter is mod.limiter


def test_main_app_mounts_slowapi_middleware():
    """RL6：仅注册 state.limiter 不够，必须挂载 Middleware 才让 default_limits 生效。"""
    from app.main import app

    assert app.state.limiter is mod.limiter
    assert any(
        middleware.cls is SlowAPIASGIMiddleware
        for middleware in app.user_middleware
    )


def test_default_limits_enforced_when_middleware_mounted():
    """RL6 行为回归：未装饰的路由在超出 default_limits 后返回项目统一 429 文案。"""
    app = FastAPI()
    app.state.limiter = Limiter(
        key_func=mod.get_client_ip, default_limits=["2/minute"]
    )
    app.add_exception_handler(RateLimitExceeded, mod._rate_limit_handler)

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    app.add_middleware(SlowAPIASGIMiddleware)
    client = TestClient(app)

    assert client.get("/ping").status_code == 200
    assert client.get("/ping").status_code == 200

    limited = client.get("/ping")

    assert limited.status_code == 429
    assert limited.json()["code"] == "RATE_LIMIT_EXCEEDED"
