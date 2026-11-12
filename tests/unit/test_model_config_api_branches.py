"""统一模型配置 API 全分支回归。"""

from dataclasses import replace

import pytest
from fastapi import HTTPException

from app.api.v2 import model_config_api as mc
from app.services.model_config_manager import AgentConfig, ModelConfig, ProviderConfig


def _model(model_id="m1", provider="p1", model_type="chat", enabled=True):
    return ModelConfig(
        id=model_id,
        name=f"api-{model_id}",
        display_name=f"Model {model_id}",
        provider=provider,
        model_type=model_type,
        enabled=enabled,
        tags=["t"],
    )


def _provider(provider_id="p1"):
    return ProviderConfig(id=provider_id, name=f"P {provider_id}", api_key="k", base_url="u")


class _Manager:
    def __init__(self, models=None, providers=None):
        self.models = {m.id: m for m in (models or [])}
        self.providers = {p.id: p for p in (providers or [])}
        self.agent = AgentConfig()
        self.add_model_result = True
        self.update_model_result = True
        self.delete_model_result = True
        self.toggle_model_result = True
        self.add_provider_result = True
        self.delete_provider_result = True
        self.update_role_result = True
        self.update_fallback_result = True
        self.calls = []

    def get_model(self, model_id):
        return self.models.get(model_id)

    def get_models_by_type(self, model_type):
        return [m for m in self.models.values() if m.model_type == model_type]

    def get_all_models(self, enabled_only=False):
        values = list(self.models.values())
        return [m for m in values if m.enabled] if enabled_only else values

    def add_model(self, model):
        if self.add_model_result:
            self.models[model.id] = model
        return self.add_model_result

    def update_model(self, model_id, updates):
        self.calls.append(("update_model", model_id, updates))
        if self.update_model_result:
            self.models[model_id] = replace(self.models[model_id], **updates)
        return self.update_model_result

    def delete_model(self, model_id):
        if not self.delete_model_result:
            return False
        return self.models.pop(model_id, None) is not None

    def toggle_model(self, model_id):
        if self.toggle_model_result:
            self.models[model_id] = replace(
                self.models[model_id], enabled=not self.models[model_id].enabled
            )
        return self.toggle_model_result

    def get_provider(self, provider_id):
        return self.providers.get(provider_id)

    def get_all_providers(self):
        return list(self.providers.values())

    def add_provider(self, provider):
        if self.add_provider_result:
            self.providers[provider.id] = provider
        return self.add_provider_result

    def delete_provider(self, provider_id):
        if self.delete_provider_result:
            self.providers.pop(provider_id, None)
        return self.delete_provider_result

    def get_agent_config(self):
        return self.agent

    def update_agent_role(self, role, model_id):
        if self.update_role_result:
            self.agent.roles[role] = model_id
        return self.update_role_result

    def update_fallback_chain(self, chain):
        if self.update_fallback_result:
            self.agent.fallback_chain = chain
        return self.update_fallback_result


@pytest.fixture
def manager(monkeypatch):
    fake = _Manager(models=[_model()], providers=[_provider()])
    monkeypatch.setattr(mc, "get_model_config_manager", lambda: fake)
    return fake


@pytest.mark.asyncio
async def test_list_models_all(manager):
    payload = await mc.list_models(current_user={"sub": 1})
    assert payload["total"] == 1
    assert payload["models"][0]["type"] == "chat"


@pytest.mark.asyncio
async def test_list_models_by_type_and_enabled(manager):
    manager.models["m2"] = _model("m2", model_type="embedding", enabled=False)
    payload = await mc.list_models(model_type="embedding", current_user={"sub": 1})
    assert [m["id"] for m in payload["models"]] == ["m2"]
    enabled = await mc.list_models(enabled_only=True, current_user={"sub": 1})
    assert [m["id"] for m in enabled["models"]] == ["m1"]


@pytest.mark.asyncio
async def test_add_model_success(manager):
    request = mc.AddModelRequest(
        id="m3", name="api", display_name="Display", provider="p1", tags=["x"]
    )
    payload = await mc.add_model(request, current_user={"sub": 7})
    assert payload["success"] is True
    assert manager.models["m3"].tags == ["x"]


@pytest.mark.asyncio
async def test_add_model_rejects_duplicate_and_missing_provider(manager):
    duplicate = mc.AddModelRequest(id="m1", name="n", display_name="d", provider="p1")
    with pytest.raises(HTTPException) as exc:
        await mc.add_model(duplicate, current_user={"sub": 1})
    assert exc.value.status_code == 400

    missing = mc.AddModelRequest(id="m9", name="n", display_name="d", provider="nope")
    with pytest.raises(HTTPException) as exc:
        await mc.add_model(missing, current_user={"sub": 1})
    assert exc.value.status_code == 400
    assert "供应商" in exc.value.detail


@pytest.mark.asyncio
async def test_add_model_save_failure(manager):
    manager.add_model_result = False
    request = mc.AddModelRequest(id="m3", name="n", display_name="d", provider="p1")
    with pytest.raises(HTTPException) as exc:
        await mc.add_model(request, current_user={"sub": 1})
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_update_model_success_and_missing(manager):
    payload = await mc.update_model(
        "m1",
        mc.UpdateModelRequest(display_name="New", temperature=0.1),
        current_user={"sub": 1},
    )
    assert payload["success"] is True
    updates = manager.calls[-1][2]
    assert updates == {"display_name": "New", "temperature": 0.1}

    with pytest.raises(HTTPException) as exc:
        await mc.update_model("nope", mc.UpdateModelRequest(), current_user={"sub": 1})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_model_failure(manager):
    manager.update_model_result = False
    with pytest.raises(HTTPException) as exc:
        await mc.update_model("m1", mc.UpdateModelRequest(name="x"), current_user={"sub": 1})
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_model_success_and_missing(manager):
    payload = await mc.delete_model("m1", current_user={"sub": 1})
    assert payload["success"] is True
    with pytest.raises(HTTPException) as exc:
        await mc.delete_model("m1", current_user={"sub": 1})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_toggle_model_enable_and_disable(manager):
    payload = await mc.toggle_model("m1", current_user={"sub": 1})
    assert payload["enabled"] is False
    assert "禁用" in payload["message"]

    payload = await mc.toggle_model("m1", current_user={"sub": 1})
    assert payload["enabled"] is True
    assert "启用" in payload["message"]


@pytest.mark.asyncio
async def test_toggle_model_missing_and_failure(manager):
    with pytest.raises(HTTPException) as exc:
        await mc.toggle_model("nope", current_user={"sub": 1})
    assert exc.value.status_code == 404

    manager.toggle_model_result = False
    with pytest.raises(HTTPException) as exc:
        await mc.toggle_model("m1", current_user={"sub": 1})
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_list_providers(manager):
    payload = await mc.list_providers(current_user={"sub": 1})
    assert payload["total"] == 1
    assert payload["providers"][0]["has_api_key"] is True
    assert "api_key" not in payload["providers"][0]


@pytest.mark.asyncio
async def test_add_provider_success_and_duplicate(manager):
    payload = await mc.add_provider(
        mc.AddProviderRequest(id="p2", name="Two"), current_user={"sub": 1}
    )
    assert payload["success"] is True
    with pytest.raises(HTTPException) as exc:
        await mc.add_provider(
            mc.AddProviderRequest(id="p2", name="Two"), current_user={"sub": 1}
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_add_provider_save_failure(manager):
    manager.add_provider_result = False
    with pytest.raises(HTTPException) as exc:
        await mc.add_provider(
            mc.AddProviderRequest(id="p3", name="Three"), current_user={"sub": 1}
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_provider_success(manager):
    manager.models.clear()
    payload = await mc.delete_provider("p1", current_user={"sub": 1})
    assert payload["success"] is True


@pytest.mark.asyncio
async def test_delete_provider_missing_or_referenced(manager):
    with pytest.raises(HTTPException) as exc:
        await mc.delete_provider("nope", current_user={"sub": 1})
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc:
        await mc.delete_provider("p1", current_user={"sub": 1})
    assert exc.value.status_code == 400
    assert "m1" in exc.value.detail


@pytest.mark.asyncio
async def test_delete_provider_failure(manager):
    manager.models.clear()
    manager.delete_provider_result = False
    with pytest.raises(HTTPException) as exc:
        await mc.delete_provider("p1", current_user={"sub": 1})
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_get_agent_config(manager):
    payload = await mc.get_agent_config(current_user={"sub": 1})
    assert payload["roles"]["architect"]
    assert payload["fallback_chain"]


@pytest.mark.asyncio
async def test_update_agent_role_success_and_invalid(manager):
    payload = await mc.update_agent_role(
        mc.UpdateRoleRequest(role="architect", model_id="m1"), current_user={"sub": 1}
    )
    assert payload["success"] is True

    manager.update_role_result = False
    with pytest.raises(HTTPException) as exc:
        await mc.update_agent_role(
            mc.UpdateRoleRequest(role="unknown", model_id="m1"), current_user={"sub": 1}
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_agent_role_missing_model(manager):
    with pytest.raises(HTTPException) as exc:
        await mc.update_agent_role(
            mc.UpdateRoleRequest(role="architect", model_id="nope"),
            current_user={"sub": 1},
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_fallback_chain_success(manager):
    payload = await mc.update_fallback_chain(
        mc.UpdateFallbackRequest(chain=["m1"]), current_user={"sub": 1}
    )
    assert payload["success"] is True
    assert manager.agent.fallback_chain == ["m1"]


@pytest.mark.asyncio
async def test_update_fallback_chain_missing_or_failure(manager):
    with pytest.raises(HTTPException) as exc:
        await mc.update_fallback_chain(
            mc.UpdateFallbackRequest(chain=["nope"]), current_user={"sub": 1}
        )
    assert exc.value.status_code == 404

    manager.update_fallback_result = False
    with pytest.raises(HTTPException) as exc:
        await mc.update_fallback_chain(
            mc.UpdateFallbackRequest(chain=["m1"]), current_user={"sub": 1}
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_reload_config(monkeypatch):
    calls = []
    monkeypatch.setattr(mc, "reload_model_config", lambda: calls.append(True))
    payload = await mc.reload_config(current_user={"sub": 1})
    assert payload["success"] is True
    assert calls == [True]


def test_to_dict_helpers(manager):
    model = manager.models["m1"]
    payload = mc._model_to_dict(model)
    assert payload["type"] == "chat"
    assert payload["tags"] == ["t"]

    provider = manager.providers["p1"]
    assert mc._provider_to_dict(provider) == {
        "id": "p1",
        "name": "P p1",
        "base_url": "u",
        "enabled": True,
        "has_api_key": True,
    }
