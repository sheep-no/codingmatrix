"""请求日志敏感参数脱敏回归测试。

LOG1：RequestLoggingMiddleware 的「请求开始」日志会把完整 query_params 落盘，
URL 里的 token/api_key/password 等凭据随日志轮转长期保存。脱敏后不得再出现明文。
"""
import logging

import pytest

from app.utils.logging import JsonFormatter, RequestLoggingMiddleware, _parse_query


def test_sensitive_query_params_are_masked():
    params = _parse_query(
        b"limit=20&token=abc123&access_token=zzz&api_key=k&password=p"
        b"&email=a@b.com&code=999&user_token=x&q=hello"
    )

    assert params["limit"] == "20"
    assert params["email"] == "a@b.com"
    assert params["q"] == "hello"
    for key in ("token", "access_token", "api_key", "password", "code", "user_token"):
        assert params[key] == "***"


def test_repeated_sensitive_params_are_all_masked():
    params = _parse_query(b"token=a&token=b&limit=1")

    assert params["token"] == ["***", "***"]
    assert params["limit"] == "1"


def test_empty_query_string_returns_none():
    assert _parse_query(b"") is None


async def _ok_app(scope, receive, send):
    await send({"type": "http.response.start", "status": 200, "headers": []})
    await send({"type": "http.response.body", "body": b""})


@pytest.mark.asyncio
async def test_request_start_log_does_not_leak_raw_token():
    middleware = RequestLoggingMiddleware(_ok_app, logger_name="app.request.test")
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/things",
        "query_string": b"token=super-secret-value&limit=5",
        "headers": [],
        "client": ("1.2.3.4", 1234),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    # app 日志器在 setup_logging() 中配置为 propagate=False，caplog 收不到，
    # 因此直接把收集器挂到中间件的日志器上
    records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    collector = _Collector()
    middleware.logger.addHandler(collector)
    middleware.logger.setLevel(logging.INFO)
    try:
        await middleware(scope, receive, send)
    finally:
        middleware.logger.removeHandler(collector)

    start_record = next(
        record
        for record in records
        if record.getMessage() == "请求开始"
    )
    assert start_record.extra_data["query_params"]["token"] == "***"
    assert start_record.extra_data["query_params"]["limit"] == "5"

    formatted = JsonFormatter().format(start_record)
    assert "super-secret-value" not in formatted
    assert '"token": "***"' in formatted
    # request_id 仍写回响应头，脱敏不影响链路追踪
    assert any(
        message.get("type") == "http.response.start"
        and b"x-request-id" in dict(message["headers"])
        for message in sent
    )
