import json

import pytest

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
