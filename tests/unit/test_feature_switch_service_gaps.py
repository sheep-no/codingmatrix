"""FeatureSwitchService 与中间件的边界补测。"""

import asyncio
import json

import pytest

from app.middleware.feature_switch import FeatureSwitchMiddleware
from app.services import feature_switch as feature_switch_module
from app.services.feature_switch import FeatureSwitchService, feature_switch_service


class _Recorder:
    def __init__(self):
        self.called = False

    async def __call__(self, scope, receive, send):
        self.called = True


def test_singleton_reuses_instance():
    assert FeatureSwitchService() is FeatureSwitchService()
    assert FeatureSwitchService() is feature_switch_service


async def test_is_feature_enabled_accepts_truthy_values(monkeypatch):
    values = iter(["TRUE", "1", "yes", "on"])

    async def fake_get_config(_key, _default):
        return next(values)

    monkeypatch.setattr(
        feature_switch_module.resource_config_service, "get_config", fake_get_config
    )

    for _ in range(4):
        assert await feature_switch_service.is_feature_enabled("docker") is True


async def test_is_feature_enabled_rejects_other_values(monkeypatch):
    async def fake_get_config(_key, _default):
        return "false"

    monkeypatch.setattr(
        feature_switch_module.resource_config_service, "get_config", fake_get_config
    )

    assert await feature_switch_service.is_feature_enabled("docker") is False


async def test_is_feature_enabled_rejects_unknown_feature():
    assert await feature_switch_service.is_feature_enabled("unknown") is False


async def test_set_feature_enabled_updates_config(monkeypatch):
    captured = {}

    async def fake_set_config(key, value, user_id):
        captured.update(key=key, value=value, user_id=user_id)
        return True

    monkeypatch.setattr(
        feature_switch_module.resource_config_service, "set_config", fake_set_config
    )

    assert await feature_switch_service.set_feature_enabled("workflow", True, user_id=9) is True
    assert captured == {"key": "feature_workflow_enabled", "value": "true", "user_id": 9}

    assert await feature_switch_service.set_feature_enabled("workflow", False) is True
    assert captured["value"] == "false"


async def test_set_feature_enabled_unknown_feature_returns_false():
    assert await feature_switch_service.set_feature_enabled("nope", True) is False


async def test_set_feature_enabled_propagates_failure(monkeypatch):
    async def fake_set_config(*_args, **_kwargs):
        return False

    monkeypatch.setattr(
        feature_switch_module.resource_config_service, "set_config", fake_set_config
    )

    assert await feature_switch_service.set_feature_enabled("docker", True) is False


async def test_get_all_feature_status_covers_every_feature(monkeypatch):
    async def fake_is_feature_enabled(feature):
        return feature != "workflow"

    monkeypatch.setattr(
        feature_switch_service, "is_feature_enabled", fake_is_feature_enabled
    )

    status = await feature_switch_service.get_all_feature_status()

    assert status == {
        "docker": True,
        "aicloud": True,
        "project": True,
        "workflow": False,
    }


async def test_check_access_returns_true_when_enabled(monkeypatch):
    async def fake_is_feature_enabled(_feature):
        return True

    monkeypatch.setattr(
        feature_switch_service, "is_feature_enabled", fake_is_feature_enabled
    )

    assert await feature_switch_service.check_access("aicloud") == (True, None)


async def test_check_access_uses_known_and_unknown_names(monkeypatch):
    async def fake_is_feature_enabled(_feature):
        return False

    monkeypatch.setattr(
        feature_switch_service, "is_feature_enabled", fake_is_feature_enabled
    )

    assert await feature_switch_service.check_access("aicloud") == (
        False,
        "AI Cloud 功能已关闭，请联系管理员",
    )
    assert await feature_switch_service.check_access("mystery") == (
        False,
        "mystery已关闭，请联系管理员",
    )


def test_middleware_passes_non_http_scope():
    downstream = _Recorder()
    sent = []

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    asyncio.run(
        FeatureSwitchMiddleware(downstream)(
            {"type": "websocket", "path": "/api/v1/agent"}, receive, send
        )
    )

    assert downstream.called is True
    assert sent == []


def test_middleware_uses_raw_feature_name_when_unmapped(monkeypatch):
    async def fake_is_feature_enabled(_feature):
        return False

    monkeypatch.setattr(
        feature_switch_service, "is_feature_enabled", fake_is_feature_enabled
    )
    monkeypatch.setattr(
        FeatureSwitchMiddleware,
        "PATH_FEATURE_MAP",
        {"/custom": "custom"},
        raising=True,
    )
    sent = []

    async def send(message):
        sent.append(message)

    asyncio.run(
        FeatureSwitchMiddleware(_Recorder())({"type": "http", "path": "/custom"}, None, send)
    )

    body = json.loads(next(m for m in sent if m["type"] == "http.response.body")["body"])
    assert body["detail"] == "custom已关闭，请联系管理员开启"
