import json

import pytest

import app.middleware.input_validator as input_validator
from app.middleware.input_validator import InputValidatorMiddleware


def _scope(path: str, body: bytes) -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
    }


def _receive(body: bytes):
    delivered = False

    async def receive():
        nonlocal delivered
        if delivered:
            return {"type": "http.disconnect"}
        delivered = True
        return {"type": "http.request", "body": body, "more_body": False}

    return receive


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    (
        "/api/v1/agent/orchestrate",
        "/api/v1/agent/orchestrate/stream",
        "/api/v1/agent/modify",
        "/api/v1/ai-agent/orchestrate",
        "/api/v1/ai-agent/orchestrate/stream",
        "/api/v1/ai-agent/modify",
    ),
)
async def test_generation_prompts_may_contain_sql_vocabulary(path):
    body = json.dumps({"requirement": "Create and delete SQLite database records"}).encode()
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    middleware = InputValidatorMiddleware(app)
    await middleware(_scope(path, body), _receive(body), lambda message: None)

    assert called is True


@pytest.mark.asyncio
async def test_regular_json_endpoint_still_rejects_sql_injection_payload():
    body = json.dumps({"name": "' OR 1=1 --"}).encode()
    messages = []

    async def app(scope, receive, send):
        raise AssertionError("blocked request reached downstream app")

    async def send(message):
        messages.append(message)

    middleware = InputValidatorMiddleware(app)
    await middleware(_scope("/api/v1/users", body), _receive(body), send)

    assert messages[0]["status"] == 400
    payload = json.loads(messages[1]["body"])
    assert payload["details"]["detected_issues"] == ["sql_injection"]


def _scope_with(path: str, body: bytes, content_type=None, content_length=True) -> dict:
    headers = []
    if content_type is not None:
        headers.append((b"content-type", content_type.encode()))
    if content_length:
        headers.append((b"content-length", str(len(body)).encode()))
    return {"type": "http", "method": "POST", "path": path, "headers": headers}


async def _run(path, body, content_type=None, content_length=True, receive=None):
    """返回 (是否到达下游, 拦截响应消息列表)。"""
    reached = False
    messages = []

    async def app(scope, inner_receive, send):
        nonlocal reached
        reached = True

    async def send(message):
        messages.append(message)

    middleware = InputValidatorMiddleware(app)
    await middleware(
        _scope_with(path, body, content_type, content_length),
        receive or _receive(body),
        send,
    )
    return reached, messages


@pytest.mark.asyncio
async def test_missing_content_type_still_scans_json_body():
    """仅去掉 Content-Type 不能绕过注入扫描。"""
    body = json.dumps({"name": "' OR 1=1 --"}).encode()

    reached, messages = await _run("/api/v1/users", body, content_type=None)

    assert reached is False
    assert messages[0]["status"] == 400
    assert "sql_injection" in json.loads(messages[1]["body"])["details"]["detected_issues"]


@pytest.mark.asyncio
async def test_missing_content_type_non_json_body_passes_through():
    """无法判定为 JSON 的原始 body 不应被误判为非法 JSON。"""
    body = b"plain text, not json"

    reached, messages = await _run("/api/v1/users", body, content_type=None)

    assert reached is True
    assert messages == []


@pytest.mark.asyncio
async def test_xss_payload_in_json_key_is_rejected():
    body = json.dumps({"<script>alert(1)</script>": "clean"}).encode()

    reached, messages = await _run("/api/v1/chat", body, content_type="application/json")

    assert reached is False
    assert messages[0]["status"] == 400
    assert "xss" in json.loads(messages[1]["body"])["details"]["detected_issues"]


@pytest.mark.asyncio
async def test_malformed_content_length_does_not_crash():
    body = json.dumps({"name": "ok"}).encode()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/users",
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", b"not-a-number"),
        ],
    }
    reached = False
    messages = []

    async def app(scope, inner_receive, send):
        nonlocal reached
        reached = True

    async def send(message):
        messages.append(message)

    middleware = InputValidatorMiddleware(app)
    await middleware(scope, _receive(body), send)

    assert reached is True
    assert messages == []


@pytest.mark.asyncio
async def test_deeply_nested_json_is_rejected_not_server_error():
    depth = 50000
    body = b"[" * depth + b"]" * depth

    reached, messages = await _run("/api/v1/users", body, content_type="application/json")

    assert reached is False
    assert messages[0]["status"] == 400


@pytest.mark.asyncio
async def test_chunked_body_over_limit_stops_reading_early(monkeypatch):
    """无 Content-Length 的分块传输必须在读取过程中中断，不能先全量缓冲。"""
    monkeypatch.setattr(input_validator, "MAX_BODY_SIZE", 100)
    chunks = [b"x" * 40 for _ in range(50)]
    consumed = 0

    async def receive():
        nonlocal consumed
        if consumed < len(chunks):
            chunk = chunks[consumed]
            consumed += 1
            return {"type": "http.request", "body": chunk, "more_body": True}
        return {"type": "http.request", "body": b"", "more_body": False}

    reached, messages = await _run(
        "/api/v1/users",
        b"",
        content_type="application/json",
        content_length=False,
        receive=receive,
    )

    assert reached is False
    assert messages[0]["status"] == 413
    assert consumed < len(chunks), "超限后仍在继续读取 body"
