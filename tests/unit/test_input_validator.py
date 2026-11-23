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
    ("path", "field"),
    (
        ("/api/v1/chat", "prompt"),
        ("/api/v1/agent/orchestrate", "requirement"),
        ("/api/v1/agent/orchestrate/stream", "requirement"),
        ("/api/v1/agent/generate", "requirement"),
        ("/api/v1/agent/modify", "requirement"),
    ),
)
async def test_prompt_fields_may_contain_code_and_xss_samples(path, field):
    """编程场景的 prompt/requirement 可以包含代码样本，入口只留审计记录。"""
    body = json.dumps({field: "<img src=x onerror=alert(1)>"}).encode()
    called = False

    async def app(scope, receive, send):
        nonlocal called
        called = True

    middleware = InputValidatorMiddleware(app)
    await middleware(_scope(path, body), _receive(body), lambda message: None)

    assert called is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("path", "field"),
    (
        ("/api/v1/chat", "prompt"),
        ("/api/v1/agent/orchestrate", "requirement"),
        ("/api/v1/agent/generate", "requirement"),
    ),
)
async def test_prompt_fields_still_reject_sql_injection(path, field):
    """XSS 字面拦截放宽，SQL 注入检测在提示词字段上仍然生效。"""
    body = json.dumps({field: "' OR 1=1 --"}).encode()
    reached, messages = await _run(path, body)

    assert reached is False
    assert messages[0]["status"] == 400
    assert "sql_injection" in json.loads(messages[1]["body"])["details"]["detected_issues"]


@pytest.mark.asyncio
async def test_prompt_relaxation_logs_audit_record(monkeypatch):
    """放行 XSS 特征时必须留下审计日志，便于事后追溯。

    直接断言 logger 调用：CI 中 app logger 配置了 propagate=False，
    caplog 无法捕获，依赖 caplog 会让测试随日志配置波动。
    """
    import app.middleware.input_validator as module

    warnings = []
    monkeypatch.setattr(
        module.logger,
        "warning",
        lambda message, *args: warnings.append((message, args)),
    )
    body = json.dumps({"prompt": "<script>alert(1)</script>"}).encode()

    reached, _ = await _run("/api/v1/chat", body)

    assert reached is True
    assert warnings
    message, args = warnings[0]
    assert "提示词 XSS 特征已放行" in message
    assert "/api/v1/chat" in args
    assert ["prompt"] in args


@pytest.mark.asyncio
async def test_prompt_relaxation_emits_security_audit_event(monkeypatch):
    """放行事件必须进入安全审计通道，而不仅是应用日志。"""
    import app.middleware.input_validator as module

    events = []

    async def fake_log(event_type, user_id, details, ip_address=None, success=True):
        events.append({"event_type": event_type, "details": details})

    monkeypatch.setattr(module, "log_security_event", fake_log)
    body = json.dumps({"prompt": "<script>alert(1)</script>"}).encode()

    reached, _ = await _run("/api/v1/chat", body)

    assert reached is True
    assert events == [{
        "event_type": "prompt_xss_relaxed",
        "details": {
            "path": "/api/v1/chat",
            "detected_issues": ["xss"],
            "fields": ["prompt"],
            "policy": "render_layer_sanitization",
        },
    }]


@pytest.mark.asyncio
async def test_non_prompt_field_on_chat_path_still_rejected():
    """放宽只作用于根级 prompt；同一请求里的其他文本字段仍严格拦截。"""
    body = json.dumps(
        {"prompt": "正常问题", "image_analysis_prompt": "<script>alert(1)</script>"}
    ).encode()
    reached, messages = await _run("/api/v1/chat", body)

    assert reached is False
    assert messages[0]["status"] == 400
    assert "xss" in json.loads(messages[1]["body"])["details"]["detected_issues"]


@pytest.mark.asyncio
async def test_agent_apikey_path_is_not_relaxed():
    """apikey 相关接口必须保持严格拦截，不受 agent 前缀放行影响。"""
    body = json.dumps({"prompt": "<script>alert(1)</script>"}).encode()
    reached, messages = await _run("/api/v1/agent/apikey", body)

    assert reached is False
    assert messages[0]["status"] == 400
    assert "xss" in json.loads(messages[1]["body"])["details"]["detected_issues"]


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

    reached, messages = await _run("/api/v1/users", body, content_type="application/json")

    assert reached is False
    assert messages[0]["status"] == 400
    assert "xss" in json.loads(messages[1]["body"])["details"]["detected_issues"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "prompt",
    (
        "<script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        "解释这段代码：<script>alert(1)</script> 做了什么",
        "```html\n<script>alert(1)</script>\n```",
        "这个按钮的 `onclick=\"alert(1)\"` 属性该怎么改？",
    ),
)
async def test_ai_chat_prompts_may_contain_code_samples(prompt):
    """代码解释/修复是编程助手的高频场景，提示词里的标签与事件属性不应被当作攻击拦截。"""
    body = json.dumps({"prompt": prompt}).encode()

    reached, messages = await _run("/api/v1/chat", body, content_type="application/json")

    assert reached is True, f"正常代码提问被误拦: {prompt} -> {messages}"
    assert messages == []


@pytest.mark.asyncio
async def test_ai_chat_still_enforces_transport_checks():
    """豁免内容扫描后，chat 入口仍必须拒绝不支持的内容类型。"""
    body = b"<xml>payload</xml>"

    reached, messages = await _run("/api/v1/chat", body, content_type="application/xml")

    assert reached is False
    assert messages[0]["status"] == 415


@pytest.mark.asyncio
async def test_validation_error_message_is_actionable():
    body = json.dumps({"comment": "<script>alert(1)</script>"}).encode()

    _, messages = await _run("/api/v1/users", body, content_type="application/json")

    message = json.loads(messages[1]["body"])["message"]
    assert "XSS" in message
    assert "移除" in message


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


def test_upload_quota_is_shared_with_file_upload_endpoint():
    """中间件上传上限必须与上传端点共用同一配置，否则整体上传会被 413 误拦。"""
    from app.api.v1 import file_upload

    assert input_validator.MAX_UPLOAD_BODY_SIZE == file_upload.MAX_FILE_SIZE


def _scope_declared(path: str, content_type: str, declared_length: int) -> dict:
    """声明 Content-Length 但不真正发送 body，用于校验体积阈值判定。"""
    return {
        "type": "http",
        "method": "POST",
        "path": path,
        "headers": [
            (b"content-type", content_type.encode()),
            (b"content-length", str(declared_length).encode()),
        ],
    }


async def _run_declared(scope):
    reached = False
    messages = []

    async def app(scope, receive, send):
        nonlocal reached
        reached = True

    async def send(message):
        messages.append(message)

    middleware = InputValidatorMiddleware(app)
    await middleware(scope, _receive(b""), send)
    return reached, messages


@pytest.mark.asyncio
async def test_multipart_upload_within_quota_passes_middleware():
    """超过 10MB 常规上限但在上传配额内的 multipart 请求应放行（P2-3）。"""
    scope = _scope_declared(
        "/api/v1/files/upload",
        "multipart/form-data; boundary=x",
        50 * 1024 * 1024,
    )

    reached, messages = await _run_declared(scope)

    assert reached is True
    assert messages == []


@pytest.mark.asyncio
async def test_multipart_upload_over_quota_is_rejected():
    over = input_validator.MAX_UPLOAD_BODY_SIZE + 1
    scope = _scope_declared(
        "/api/v1/files/upload",
        "multipart/form-data; boundary=x",
        over,
    )

    reached, messages = await _run_declared(scope)

    assert reached is False
    assert messages[0]["status"] == 413


@pytest.mark.asyncio
async def test_json_body_over_10mb_still_rejected():
    """上传配额只放宽 multipart，常规 JSON 请求仍按 10MB 拒绝。"""
    scope = _scope_declared("/api/v1/users", "application/json", 20 * 1024 * 1024)

    reached, messages = await _run_declared(scope)

    assert reached is False
    assert messages[0]["status"] == 413
    assert messages[1]["body"] and b"10MB" in messages[1]["body"]


@pytest.mark.asyncio
async def test_structured_json_suffix_is_accepted_and_scanned():
    """application/vnd.api+json 属 JSON 系类型，不应被 415 拒绝，且仍需扫描注入。"""
    body = json.dumps({"name": "' OR 1=1 --"}).encode()

    reached, messages = await _run(
        "/api/v1/users", body, content_type="application/vnd.api+json"
    )

    assert reached is False
    assert messages[0]["status"] == 400
    assert "sql_injection" in json.loads(messages[1]["body"])["details"]["detected_issues"]


@pytest.mark.asyncio
async def test_structured_json_suffix_clean_body_passes_before_middleware():
    """合法 body 的 +json 请求直接透传，不再被 415 拦截。"""
    body = json.dumps({"name": "ok"}).encode()

    reached, messages = await _run(
        "/api/v1/users", body, content_type="application/vnd.api+json; charset=utf-8"
    )

    assert reached is True
    assert messages == []


@pytest.mark.asyncio
async def test_jsonp_is_not_treated_as_json():
    """application/jsonp 只以前缀相似，不应被当成 JSON 对非 JSON body 报 400。"""
    reached, messages = await _run(
        "/api/v1/users", b"plain text, not json", content_type="application/jsonp"
    )

    assert reached is False
    assert messages[0]["status"] == 415
