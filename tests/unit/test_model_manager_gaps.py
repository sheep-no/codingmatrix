"""model_manager 过滤、默认模型缺失与 agent-config 分支补测。"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1 import model_manager as module


class _Capability:
    def __init__(self, value):
        self.value = value


def _model(model_id="m1", capabilities=None, is_free=False):
    return SimpleNamespace(
        id=model_id,
        name=model_id,
        model_key=f"key-{model_id}",
        description="desc",
        capabilities=capabilities or [],
        tags=["tag"],
        is_free=is_free,
    )


@pytest.fixture(autouse=True)
def _reset_runtime_default():
    module._runtime_default_model = None
    yield
    module._runtime_default_model = None


def test_get_current_default_model_id_prefers_runtime(monkeypatch):
    module._runtime_default_model = "runtime"
    monkeypatch.setattr(module, "get_default_model", MagicMock(side_effect=AssertionError))
    assert module.get_current_default_model_id() == "runtime"


def test_get_current_default_model_id_falls_back(monkeypatch):
    monkeypatch.setattr(module, "get_default_model", lambda: SimpleNamespace(id="static"))
    assert module.get_current_default_model_id() == "static"


async def test_list_models_filters_free_only(monkeypatch):
    monkeypatch.setattr(module, "MODEL_REGISTRY", {
        "free": _model("free", is_free=True),
        "paid": _model("paid", is_free=False),
    })
    monkeypatch.setattr(module, "get_default_model", lambda: SimpleNamespace(id="free"))

    result = await module.list_models(free_only=True)

    assert [m.id for m in result.models] == ["free"]
    assert result.total == 1
    assert result.default_model == "free"


async def test_list_models_invalid_capability():
    with pytest.raises(HTTPException) as exc:
        await module.list_models(capability="telepathy")
    assert exc.value.status_code == 400


async def test_list_models_filters_by_capability(monkeypatch):
    sentinel = SimpleNamespace(value="text")

    class Cap:
        @staticmethod
        def __call__(value):
            assert value == "text"
            return sentinel

    monkeypatch.setattr(module, "ModelCapability", Cap())
    monkeypatch.setattr(module, "MODEL_REGISTRY", {
        "with": _model("with", capabilities=[sentinel]),
        "without": _model("without", capabilities=[]),
    })
    monkeypatch.setattr(module, "get_default_model", lambda: SimpleNamespace(id="with"))

    result = await module.list_models(capability="text")
    assert [m.id for m in result.models] == ["with"]


async def test_get_default_missing_model(monkeypatch):
    module._runtime_default_model = "ghost"
    monkeypatch.setattr(module, "get_model", lambda model_id: None)

    with pytest.raises(HTTPException) as exc:
        await module.get_default()
    assert exc.value.status_code == 404
    assert "ghost" in exc.value.detail


async def test_get_default_returns_model(monkeypatch):
    module._runtime_default_model = "m1"
    model = _model("m1", capabilities=[SimpleNamespace(value="text")])
    monkeypatch.setattr(module, "get_model", lambda model_id: model)

    result = await module.get_default()

    assert result.id == "m1"
    assert result.is_default is True
    assert result.capabilities == ["text"]


async def test_get_model_info_marks_default(monkeypatch):
    model = _model("m1", capabilities=[])
    monkeypatch.setattr(module, "get_model", lambda model_id: model)
    module._runtime_default_model = "m1"

    result = await module.get_model_info("m1")

    assert result.is_default is True


async def test_list_capabilities_lists_values():
    result = await module.list_capabilities()
    assert result["capabilities"]
    assert "text" in result["capabilities"]


def _patch_agent_config(monkeypatch, config):
    routing = SimpleNamespace(
        load_agent_model_config=lambda: config,
        _load_roles_assignment=lambda: SimpleNamespace(
            architect_model="a",
            frontend_model="f",
            backend_model="b",
            reviewer_model="r",
            fallback_model="fb",
        ),
        MODEL_KEY_TO_ID={"a": "id-a"},
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config", routing.load_agent_model_config
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router._load_roles_assignment", routing._load_roles_assignment
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.MODEL_KEY_TO_ID", routing.MODEL_KEY_TO_ID
    )


async def test_agent_config_falls_back_to_roles_assignment(monkeypatch):
    _patch_agent_config(monkeypatch, {})

    result = await module.get_agent_model_config(token={})

    assert result.roles["architect"] == "id-a"
    assert result.roles["frontend"] == "f"
    assert result.last_updated == "未配置"
    assert result.fallback_chain == []


async def test_agent_config_extracts_v2_assignments(monkeypatch):
    _patch_agent_config(monkeypatch, {
        "version": "2.0",
        "assignments": {
            "MEDIUM": {"architect_model": "a", "other": "x"},
        },
    })

    result = await module.get_agent_model_config(token={})

    assert result.version == "2.0"
    assert result.roles == {"architect": "a"}


async def test_agent_config_uses_large_assignments(monkeypatch):
    _patch_agent_config(monkeypatch, {
        "assignments": {"LARGE": {"backend_model": "b"}},
    })

    result = await module.get_agent_model_config(token={})

    assert result.roles == {"backend": "b"}


async def test_agent_config_returns_full_config(monkeypatch):
    _patch_agent_config(monkeypatch, {
        "roles": {"architect": "id-a"},
        "fallback_chain": ["x"],
        "error_type_models": {"timeout": "y"},
        "settings": {"k": "v"},
        "global_thinking_ratio": 0.8,
        "models": {"id-a": {}},
    })

    result = await module.get_agent_model_config(token={})

    assert result.roles == {"architect": "id-a"}
    assert result.fallback_chain == ["x"]
    assert result.error_type_models == {"timeout": "y"}
    assert result.settings == {"k": "v"}
    assert result.global_thinking_ratio == 0.8
    assert result.models == {"id-a": {}}
