"""中间件层回归：限流死代码清理、retry_after 一致性、request_id 追踪统一。

覆盖 middleware.md 的 RLM4/RLM5 与 performance_monitoring.md 的 PM2。
"""
import json
import re
import time

import pytest
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from httpx import ASGITransport, AsyncClient
from starlette.middleware.base import BaseHTTPMiddleware

from app.middleware.rate_limiter import (
    LoginAttemptTracker,
    RateLimitMiddleware,
    RateLimitTier,
    rate_limiter,
)
from app.utils.logging import RequestLoggingMiddleware, get_request_id
from app.utils.performance_monitor import (
    PerformanceMonitorMiddleware,
    setup_performance_monitoring,
)


def test_dead_rate_limiter_symbols_removed():
    """RLM4：五个零消费符号与重复规则表已删除。"""
    for name in (
        "is_rate_limited",
        "endpoint_limits",
        "get_client_id",
        "get_client_identifiers",
        "check_limit",
    ):
        assert not hasattr(rate_limiter, name)


def test_rate_limiter_prunes_stale_bucket_keys():
    """RLM2：窗口滚动后的旧时间桶键会被清扫，不再无限累积。"""
    rate_limiter._history.clear()
    rate_limiter._last_sweep = 0.0
    stale = time.time() - 100_000
    rate_limiter._history["ip:9.9.9.9:1"] = [stale]
    rate_limiter._history["global:1"] = [stale]

    rate_limiter.check_multi_tier("1.1.1.1", None, "/api/v1/ping")

    assert "ip:9.9.9.9:1" not in rate_limiter._history
    assert "global:1" not in rate_limiter._history


def test_login_tracker_removes_empty_and_expired_keys():
    """RLM2：登录失败记录清空或过期后删除键，避免键无限累积。"""
    tracker = LoginAttemptTracker()
    tracker.record_failed_attempt("bob")
    assert tracker.is_blocked("bob") is False
    tracker.clear_failed_attempts("bob")
    assert "bob" not in tracker.failed_attempts

    tracker.failed_attempts["eve"] = [time.time() - tracker.window_seconds - 1]
    assert tracker.is_blocked("eve") is False
    assert "eve" not in tracker.failed_attempts


@pytest.mark.asyncio
async def test_rate_limit_retry_after_consistent(monkeypatch):
    """RLM5：429 响应体与响应头的 retry_after 必须一致。"""
    monkeypatch.setattr(
        rate_limiter,
        "check_multi_tier",
        lambda *args, **kwargs: (True, RateLimitTier.IP, 10, 60),
    )

    async def dummy_app(scope, receive, send):  # pragma: no cover - 不应被调用
        raise AssertionError("限流命中时不应继续调用下游应用")

    middleware = RateLimitMiddleware(dummy_app)
    messages = []

    async def send(message):
        messages.append(message)

    scope = {
        "type": "http",
        "path": "/api/v1/code/execute",
        "headers": [],
        "client": ("1.2.3.4", 1234),
    }

    await middleware(scope, lambda: None, send)

    start = next(m for m in messages if m["type"] == "http.response.start")
    body = json.loads(next(m for m in messages if m["type"] == "http.response.body")["body"])

    header_retry_after = dict(start["headers"])[b"retry-after"].decode()
    assert start["status"] == 429
    assert body["retry_after"] == int(header_retry_after) == 60


@pytest.mark.asyncio
async def test_response_request_id_matches_log_context():
    """PM2：响应头 X-Request-ID 与日志上下文 request_id 一致。"""
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"context_request_id": get_request_id()}

    app.add_middleware(RequestLoggingMiddleware)
    setup_performance_monitoring(app, slow_threshold=1.0)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ping")

    header_id = response.headers.get("x-request-id")
    assert header_id
    # 必须是 uuid 截断形态（生成器格式），而非旧的 `时间戳-IP-path` 拼接
    assert re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{2,4}", header_id)
    assert "127.0.0.1" not in header_id
    assert response.json()["context_request_id"] == header_id


@pytest.mark.asyncio
async def test_performance_middleware_passes_body_through_unbuffered():
    """PM1：纯 ASGI 实现逐条转发 body 消息，不缓冲/合并流式响应。"""
    assert not issubclass(PerformanceMonitorMiddleware, BaseHTTPMiddleware)

    sent = []

    async def fake_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"a", "more_body": True})
        await send({"type": "http.response.body", "body": b"b", "more_body": False})

    middleware = PerformanceMonitorMiddleware(fake_app)

    async def send(message):
        sent.append(message)

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/stream",
        "headers": [],
        "client": ("1.2.3.4", 1),
    }
    await middleware(scope, lambda: None, send)

    assert [m["type"] for m in sent] == [
        "http.response.start",
        "http.response.body",
        "http.response.body",
    ]
    assert sent[1]["more_body"] is True
    assert sent[2]["more_body"] is False
    headers = dict(sent[0]["headers"])
    assert headers[b"x-process-time"]
    assert headers[b"x-request-id"]


@pytest.mark.asyncio
async def test_streaming_response_headers_are_single_valued():
    """PM1：流式响应仍带单份 X-Process-Time / X-Request-ID。"""
    app = FastAPI()

    @app.get("/stream")
    async def stream():
        async def gen():
            yield b"chunk-1\n"
            yield b"chunk-2\n"

        return StreamingResponse(gen(), media_type="text/plain")

    app.add_middleware(PerformanceMonitorMiddleware)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        async with client.stream("GET", "/stream") as response:
            body = b"".join([chunk async for chunk in response.aiter_bytes()])

    assert body == b"chunk-1\nchunk-2\n"
    assert len(response.headers.get_list("x-request-id")) == 1
    assert len(response.headers.get_list("x-process-time")) == 1
