"""功能开关中间件回归：路径段边界匹配与功能名单一来源。"""

import asyncio
import json

import pytest

from app.middleware.feature_switch import FeatureSwitchMiddleware
from app.services.feature_switch import feature_switch_service


class _Recorder:
    """记录下游是否被调用，并返回 200。"""

    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"downstream"})


def _run(middleware, path):
    sent = []

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        sent.append(message)

    scope = {"type": "http", "path": path, "method": "GET", "headers": []}
    asyncio.run(middleware(scope, receive, send))
    return sent


def _status(sent):
    return next(m["status"] for m in sent if m["type"] == "http.response.start")


def _body(sent):
    chunk = next(m for m in sent if m["type"] == "http.response.body")
    return json.loads(chunk["body"].decode())


@pytest.fixture
def enabled(monkeypatch):
    calls = []
    async def is_feature_enabled(feature):
        calls.append(feature)
        return True

    monkeypatch.setattr(feature_switch_service, "is_feature_enabled", is_feature_enabled)
    return calls


@pytest.fixture
def disabled(monkeypatch):
    calls = []

    async def is_feature_enabled(feature):
        calls.append(feature)
        return False

    monkeypatch.setattr(feature_switch_service, "is_feature_enabled", is_feature_enabled)
    return calls


@pytest.mark.parametrize(
    "path,feature",
    [
        ("/api/v1/agent", "project"),
        ("/api/v1/agent/apikey", "project"),
        ("/api/v1/aicloud/chat/stream", "aicloud"),
        ("/api/v1/workflow/execute", "workflow"),
        ("/api/v1/docker/containers", "docker"),
    ],
)
def test_disabled_feature_returns_503(path, feature, disabled):
    downstream = _Recorder()
    sent = _run(FeatureSwitchMiddleware(downstream), path)

    assert _status(sent) == 503
    body = _body(sent)
    assert body["code"] == "FEATURE_DISABLED"
    assert body["feature"] == feature
    assert downstream.called is False
    assert disabled == [feature]


def test_disabled_feature_detail_uses_service_feature_name(disabled):
    sent = _run(FeatureSwitchMiddleware(_Recorder()), "/api/v1/agent/apikey")

    assert _body(sent)["detail"] == (
        f"{feature_switch_service.FEATURE_NAMES['project']}已关闭，请联系管理员开启"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/agentfoo",
        "/api/v1/agent-evil",
        "/api/v1/aicloudx",
        "/api/v1/workflows",
        "/api/v1/dockerfile",
    ],
)
def test_lookalike_prefix_paths_are_not_gated(path, disabled):
    downstream = _Recorder()
    sent = _run(FeatureSwitchMiddleware(downstream), path)

    assert _status(sent) == 200
    assert downstream.called is True
    # 无归属路径不应触发功能开关查询（不做无谓的配置读取）
    assert disabled == []


@pytest.mark.parametrize("path", ["/api/v1/health", "/health", "/", "/api/docs"])
def test_unmapped_paths_skip_feature_lookup(path, disabled):
    downstream = _Recorder()
    sent = _run(FeatureSwitchMiddleware(downstream), path)

    assert _status(sent) == 200
    assert disabled == []


def test_enabled_feature_passes_through(enabled):
    downstream = _Recorder()
    sent = _run(FeatureSwitchMiddleware(downstream), "/api/v1/workflow/history")

    assert _status(sent) == 200
    assert downstream.called is True
    assert enabled == ["workflow"]


def test_match_feature_uses_path_segment_boundary():
    assert FeatureSwitchMiddleware._match_feature("/api/v1/agent") == "project"
    assert FeatureSwitchMiddleware._match_feature("/api/v1/agent/") == "project"
    assert FeatureSwitchMiddleware._match_feature("/api/v1/agentfoo") == ""
    assert FeatureSwitchMiddleware._match_feature("/api/v2/agent") == ""
