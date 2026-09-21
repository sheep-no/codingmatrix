"""CSP 策略回归：应用页面不再放行 eval，文档页保持可用的放开策略。"""

import pytest

from app.middleware.security_headers import (
    SecurityHeadersMiddleware,
    _build_security_headers,
    _csp_for_path,
)


def _directive(csp: str, name: str) -> str:
    for part in csp.split(";"):
        part = part.strip()
        if part.startswith(f"{name} "):
            return part
    raise AssertionError(f"未找到 {name} 指令: {csp}")


def test_app_csp_drops_unsafe_eval():
    csp = _csp_for_path("/")

    script_src = _directive(csp, "script-src")
    assert "'unsafe-eval'" not in script_src
    assert script_src == "script-src 'self' 'unsafe-inline'"
    assert "'unsafe-eval'" not in csp
    # 画中画窗口依赖内联脚本，收紧要等 nonce 方案落地
    assert _directive(csp, "style-src") == "style-src 'self' 'unsafe-inline'"
    assert _directive(csp, "object-src") == "object-src 'none'"


@pytest.mark.parametrize(
    "path",
    [
        "/api/docs",
        "/api/docs/oauth2-redirect",
        "/api/redoc",
        "/api/redoc/",
        "/api/openapi.json",
    ],
)
def test_docs_csp_keeps_swagger_ui_requirements(path):
    csp = _csp_for_path(path)

    script_src = _directive(csp, "script-src")
    assert "'unsafe-inline'" in script_src
    assert "'unsafe-eval'" in script_src
    assert "https://cdn.jsdelivr.net" in script_src
    # 文档页不额外收紧 object-src，保持一致
    assert "object-src" not in csp


@pytest.mark.parametrize(
    "path",
    ["/api/docsomething", "/api/redocx", "/api/openapi.json.bak", "/api/openapis"],
)
def test_docs_branch_does_not_apply_to_lookalike_paths(path):
    # 前缀相同但并非文档页的路径不应命中放宽策略（段边界匹配）
    csp = _csp_for_path(path)

    assert "'unsafe-eval'" not in csp
    assert "cdn.jsdelivr.net" not in csp
    assert _directive(csp, "object-src") == "object-src 'none'"


def test_security_headers_middleware_emits_tightened_csp():
    import asyncio

    sent = []

    async def asgi_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    middleware = SecurityHeadersMiddleware(asgi_app)
    scope = {"type": "http", "path": "/", "method": "GET", "headers": []}

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))

    start = next(m for m in sent if m["type"] == "http.response.start")
    headers = {k.decode(): v.decode() for k, v in start["headers"]}
    assert headers["content-security-policy"] == _csp_for_path("/")
    assert len(sent) == 2


def test_build_security_headers_skips_coep_for_docs_only():
    def coep(path):
        keys = [k.decode() for k, _ in _build_security_headers(path)]
        return "cross-origin-embedder-policy" in keys

    assert coep("/") is True
    assert coep("/api/docs") is False
    assert coep("/api/redoc") is False
    assert coep("/api/docsomething") is True
