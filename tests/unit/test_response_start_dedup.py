"""回归：slowapi 重复 start 会破坏 GZip 压缩流。

浏览器带 Accept-Encoding: gzip 请求大于 500 字节的静态资源或图片时，
响应会带 Content-Encoding: gzip 但内容是压缩流与明文混合，浏览器报
ERR_CONTENT_DECODING_FAILED。根因是 slowapi 对每个响应分块重发
http.response.start，外层 GZip 见到第二个 start 后退化为明文透传。

测试直接驱动 ASGI 应用并收集原始响应体，避免 HTTP 客户端自动解压。
"""
import asyncio
import gzip
import os

import pytest
from slowapi import Limiter
from slowapi.middleware import SlowAPIASGIMiddleware
from slowapi.util import get_remote_address
from starlette.applications import Starlette
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import FileResponse
from starlette.routing import Route

from app.middleware.response_start_dedup import ResponseStartDedupMiddleware

PAYLOAD = os.urandom(479792)


@pytest.fixture()
def large_file(tmp_path):
    target = tmp_path / "asset.bin"
    target.write_bytes(PAYLOAD)
    return target


def _build_app(path, *, dedup: bool) -> Starlette:
    async def asset(request):
        return FileResponse(path)

    app = Starlette(routes=[Route("/asset", asset)])
    app.state.limiter = Limiter(
        key_func=get_remote_address, default_limits=["1000/minute"]
    )
    app.add_middleware(SlowAPIASGIMiddleware)
    if dedup:
        app.add_middleware(ResponseStartDedupMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=500)
    return app


def _fetch_raw(app) -> tuple[dict, bytes]:
    """驱动 ASGI 应用，返回响应头与原始（未解压）响应体。"""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/asset",
        "raw_path": b"/asset",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"accept-encoding", b"gzip")],
        "client": ("127.0.0.1", 12345),
        "server": ("127.0.0.1", 80),
        "app": app,
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    messages = []

    async def send(message):
        messages.append(message)

    asyncio.run(app(scope, receive, send))
    headers = {}
    for key, value in messages[0].get("headers", []):
        headers[key.decode().lower()] = value.decode()
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    return headers, body


def test_slowapi_with_gzip_corrupts_stream_without_dedup(large_file):
    """证明缺陷存在：缺少去重时压缩流不可解。"""
    headers, body = _fetch_raw(_build_app(large_file, dedup=False))
    assert headers["content-encoding"] == "gzip"
    with pytest.raises(Exception):
        gzip.decompress(body)


def test_dedup_keeps_gzip_stream_valid(large_file):
    headers, body = _fetch_raw(_build_app(large_file, dedup=True))
    assert headers["content-encoding"] == "gzip"
    assert gzip.decompress(body) == PAYLOAD


def test_dedup_ignores_non_http_scope():
    seen = []

    async def app(scope, receive, send):
        seen.append(scope["type"])

    async def send(message):
        seen.append(message)

    asyncio.run(ResponseStartDedupMiddleware(app)({"type": "websocket"}, None, send))
    assert seen == ["websocket"]


def test_main_app_orders_gzip_outside_dedup_outside_slowapi():
    """真实应用必须保持 GZip > Dedup > SlowAPI 的顺序，否则压缩流再次被破坏。"""
    from app.main import app

    order = [middleware.cls for middleware in app.user_middleware]
    gzip_index = order.index(GZipMiddleware)
    dedup_index = order.index(ResponseStartDedupMiddleware)
    slowapi_index = order.index(SlowAPIASGIMiddleware)
    assert gzip_index < dedup_index < slowapi_index
