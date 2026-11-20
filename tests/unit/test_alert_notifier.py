"""告警通知转发：渠道选择、阈值过滤、载荷格式与失败隔离。"""
import smtplib

import httpx
import pytest

from app.services import alert_notifier


def _alert(severity="warning", status="firing", summary="empty streams"):
    return {
        "status": status,
        "labels": {
            "alertname": "LlmEmptyStreamSpike",
            "severity": severity,
            "provider": "siliconflow",
            "model": "glm-4-flash",
        },
        "annotations": {"summary": summary},
    }


def _configure(monkeypatch, **overrides):
    defaults = {
        "ALERT_WEBHOOK_URL": "",
        "ALERT_WEBHOOK_TYPE": "generic",
        "ALERT_NOTIFY_MIN_SEVERITY": "warning",
        "ALERT_SMTP_HOST": "",
        "ALERT_SMTP_PORT": 587,
        "ALERT_SMTP_SECURITY": "starttls",
        "ALERT_SMTP_USER": "",
        "ALERT_SMTP_PASSWORD": "",
        "ALERT_SMTP_FROM": "",
        "ALERT_SMTP_TO": "",
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(alert_notifier.settings, name, value)


@pytest.mark.asyncio
async def test_no_channels_configured_returns_none(monkeypatch):
    _configure(monkeypatch)

    assert await alert_notifier.notify_alerts([_alert()]) is None


@pytest.mark.asyncio
async def test_empty_alerts_skips_notification(monkeypatch):
    _configure(monkeypatch, ALERT_WEBHOOK_URL="https://example.com/hook")

    assert await alert_notifier.notify_alerts([]) is None


@pytest.mark.asyncio
async def test_below_threshold_alerts_are_filtered(monkeypatch):
    _configure(monkeypatch, ALERT_WEBHOOK_URL="https://example.com/hook")
    posted = []

    async def fake_post(payload):
        posted.append(payload)
        return httpx.Response(200, json={"errcode": 0})

    monkeypatch.setattr(alert_notifier, "_post_webhook", fake_post)

    assert await alert_notifier.notify_alerts([_alert(severity="info")]) is None
    assert posted == []


@pytest.mark.asyncio
async def test_webhook_payload_is_channel_specific(monkeypatch):
    posted = []

    async def fake_post(payload):
        posted.append(payload)
        return httpx.Response(200, json={"errcode": 0})

    monkeypatch.setattr(alert_notifier, "_post_webhook", fake_post)
    _configure(monkeypatch, ALERT_WEBHOOK_URL="https://example.com/hook")

    for webhook_type in ("feishu", "dingtalk", "wecom", "slack", "generic"):
        monkeypatch.setattr(alert_notifier.settings, "ALERT_WEBHOOK_TYPE", webhook_type)
        result = await alert_notifier.notify_alerts([_alert()])
        assert result == {"webhook": "sent"}

    assert posted[0]["msg_type"] == "text"
    assert posted[1]["msgtype"] == "text"
    assert posted[2]["msgtype"] == "text"
    assert posted[3]["text"].startswith("[FIRING]")
    assert posted[4]["alerts"][0]["labels"]["provider"] == "siliconflow"


@pytest.mark.asyncio
async def test_webhook_failure_is_isolated(monkeypatch):
    async def failing_post(payload):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(alert_notifier, "_post_webhook", failing_post)
    _configure(monkeypatch, ALERT_WEBHOOK_URL="https://example.com/hook")

    assert await alert_notifier.notify_alerts([_alert()]) == {"webhook": "failed"}


@pytest.mark.asyncio
async def test_email_failure_does_not_break_webhook(monkeypatch):
    posted = []

    async def fake_post(payload):
        posted.append(payload)
        return httpx.Response(200, json={"errcode": 0})

    def failing_send(subject, body):
        raise smtplib.SMTPException("smtp down")

    monkeypatch.setattr(alert_notifier, "_post_webhook", fake_post)
    monkeypatch.setattr(alert_notifier, "_send_email_sync", failing_send)
    _configure(
        monkeypatch,
        ALERT_WEBHOOK_URL="https://example.com/hook",
        ALERT_SMTP_HOST="smtp.example.com",
        ALERT_SMTP_FROM="alerts@example.com",
        ALERT_SMTP_TO="oncall@example.com, ops@example.com",
    )

    result = await alert_notifier.notify_alerts([_alert()])

    assert result == {"webhook": "sent", "email": "failed"}
    assert len(posted) == 1


def test_send_email_uses_configured_security(monkeypatch):
    sent = []

    class _Client:
        def __init__(self, host, port, timeout=None):
            self.host = host
            self.port = port
            self.started_tls = False
            self.login_args = None

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            self.started_tls = True

        def login(self, user, password):
            self.login_args = (user, password)

        def send_message(self, message):
            sent.append((self, message))

    monkeypatch.setattr(alert_notifier.smtplib, "SMTP", _Client)
    _configure(
        monkeypatch,
        ALERT_SMTP_HOST="smtp.example.com",
        ALERT_SMTP_PORT=2525,
        ALERT_SMTP_USER="user",
        ALERT_SMTP_PASSWORD="secret",
        ALERT_SMTP_FROM="alerts@example.com",
        ALERT_SMTP_TO="oncall@example.com",
    )

    alert_notifier._send_email_sync("subject", "body")

    client, message = sent[0]
    assert client.started_tls is True
    assert client.login_args == ("user", "secret")
    assert message["Subject"] == "subject"
    assert message["To"] == "oncall@example.com"


def test_send_email_ssl_and_no_auth(monkeypatch):
    created = []

    class _SSLClient:
        def __init__(self, host, port, timeout=None):
            created.append((host, port))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def send_message(self, message):
            return None

    monkeypatch.setattr(alert_notifier.smtplib, "SMTP_SSL", _SSLClient)
    _configure(
        monkeypatch,
        ALERT_SMTP_HOST="smtp.example.com",
        ALERT_SMTP_PORT=465,
        ALERT_SMTP_SECURITY="ssl",
        ALERT_SMTP_FROM="alerts@example.com",
        ALERT_SMTP_TO="oncall@example.com",
    )

    alert_notifier._send_email_sync("subject", "body")

    assert created == [("smtp.example.com", 465)]


def test_send_email_requires_recipients(monkeypatch):
    _configure(monkeypatch, ALERT_SMTP_HOST="smtp.example.com")

    with pytest.raises(ValueError):
        alert_notifier._send_email_sync("subject", "body")


def test_severity_rank_defaults_to_warning():
    assert alert_notifier._severity_rank(None) == 1
    assert alert_notifier._severity_rank("unknown") == 1
    assert alert_notifier._severity_rank("critical") == 2


def test_format_alert_truncates_text():
    alert = _alert(summary="x" * 5000)

    assert len(alert_notifier._format_text([alert])) == alert_notifier.MAX_TEXT_LENGTH


@pytest.mark.asyncio
async def test_post_webhook_sends_json_and_raises_on_error(monkeypatch):
    requests = []

    class _Response:
        def __init__(self, status_code):
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError(
                    "bad",
                    request=httpx.Request("POST", "https://example.com/hook"),
                    response=httpx.Response(self.status_code),
                )

        def json(self):
            return {"errcode": 0}

    class _Client:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            requests.append((url, json))
            return _Response(500)

    monkeypatch.setattr(alert_notifier.httpx, "AsyncClient", _Client)
    _configure(monkeypatch, ALERT_WEBHOOK_URL="https://example.com/hook")

    with pytest.raises(httpx.HTTPStatusError):
        await alert_notifier._post_webhook({"text": "hello"})

    assert requests == [("https://example.com/hook", {"text": "hello"})]


@pytest.mark.asyncio
async def test_email_oserror_is_reported_as_failure(monkeypatch):
    def failing_send(subject, body):
        raise OSError("connection refused")

    monkeypatch.setattr(alert_notifier, "_send_email_sync", failing_send)
    _configure(
        monkeypatch,
        ALERT_SMTP_HOST="smtp.example.com",
        ALERT_SMTP_FROM="alerts@example.com",
        ALERT_SMTP_TO="oncall@example.com",
    )

    assert await alert_notifier.notify_alerts([_alert()]) == {"email": "failed"}


@pytest.mark.asyncio
async def test_post_webhook_returns_response_on_success(monkeypatch):
    class _Client:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None):
            request = httpx.Request("POST", url)
            return httpx.Response(200, json={"ok": True}, request=request)

    monkeypatch.setattr(alert_notifier.httpx, "AsyncClient", _Client)
    _configure(monkeypatch, ALERT_WEBHOOK_URL="https://example.com/hook")

    response = await alert_notifier._post_webhook({"text": "hello"})

    assert response.json() == {"ok": True}


def test_format_alert_without_summary_or_details():
    alert = {"status": "resolved", "labels": {"alertname": "Custom"}, "annotations": {}}

    assert alert_notifier._format_text([alert]) == "[RESOLVED] Custom"


@pytest.mark.parametrize(
    ("webhook_type", "body", "expected"),
    (
        ("feishu", {"code": 19001, "msg": "invalid token"}, "code=19001 invalid token"),
        ("dingtalk", {"errcode": 310000, "errmsg": "limit"}, "errcode=310000 limit"),
        ("wecom", {"errcode": 0, "errmsg": "ok"}, None),
        ("generic", {"errcode": 1}, None),
        ("feishu", {"code": "0"}, None),
    ),
)
def test_webhook_rejection_detects_business_errors(webhook_type, body, expected):
    response = httpx.Response(200, json=body)

    assert alert_notifier._webhook_rejection(response, webhook_type) == expected


def test_webhook_rejection_ignores_non_json_and_non_dict():
    assert (
        alert_notifier._webhook_rejection(httpx.Response(200, text="ok"), "feishu")
        is None
    )
    assert (
        alert_notifier._webhook_rejection(httpx.Response(200, json=["ok"]), "dingtalk")
        is None
    )


@pytest.mark.asyncio
async def test_webhook_business_error_marks_failure(monkeypatch):
    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"errcode": 310000, "errmsg": "invalid token"}

    async def fake_post(payload):
        return _Response()

    monkeypatch.setattr(alert_notifier, "_post_webhook", fake_post)
    _configure(
        monkeypatch,
        ALERT_WEBHOOK_URL="https://example.com/hook",
        ALERT_WEBHOOK_TYPE="dingtalk",
    )

    assert await alert_notifier.notify_alerts([_alert()]) == {"webhook": "failed"}
