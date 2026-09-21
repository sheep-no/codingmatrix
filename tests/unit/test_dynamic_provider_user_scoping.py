"""动态供应商按用户归属收口的回归测试（PRV1 残留）。

CRUD 端点已按 owner 过滤，但模型路由仍会命中他人 provider 的 api_key。
这里锁定：路由查找读当前请求用户上下文，只在本人的 provider 中命中。
"""
import pytest

from app.utils import logging as logging_module
from app.utils.aicloud import dynamic_provider as dp_module
from app.utils.aicloud import llm_caller
from app.utils.aicloud.dynamic_provider import DynamicProviderManager, ModelInfo
from app.utils.aicloud.provider_router import ProviderRouter
from app.utils.aicloud.providers import ModelProvider
from app.utils.security import create_access_token, verify_token


class _Sentinel(Exception):
    pass


@pytest.fixture(autouse=True)
def _reset_user_context():
    logging_module.set_user_id(None)
    yield
    logging_module.set_user_id(None)


def _manager_with_two_owners():
    manager = DynamicProviderManager()
    p1 = manager.add(
        name="p1", base_url="https://a.example.com", protocol="openai",
        api_key="sk-owner1", owner_id="u1",
    )
    p1.models = [ModelInfo(id="shared-model")]
    p2 = manager.add(
        name="p2", base_url="https://b.example.com", protocol="openai",
        api_key="sk-owner2", owner_id="u2",
    )
    p2.models = [ModelInfo(id="shared-model")]
    return manager, p1, p2


def test_get_by_model_filters_by_owner():
    manager, p1, p2 = _manager_with_two_owners()
    assert manager.get_by_model("shared-model", "u1").id == p1.id
    assert manager.get_by_model("shared-model", "u2").id == p2.id
    assert manager.get_by_model("shared-model", "u3") is None
    # 不传 owner 保持旧的全局语义，供无请求上下文的系统路径使用
    assert manager.get_by_model("shared-model") is not None


def test_get_filters_by_owner():
    manager, p1, _ = _manager_with_two_owners()
    assert manager.get(p1.id, "u1").id == p1.id
    assert manager.get(p1.id, "u2") is None
    assert manager.get(p1.id) is not None


@pytest.mark.asyncio
async def test_verify_token_sets_current_user_context():
    from fastapi.security import HTTPAuthorizationCredentials

    token = create_access_token(sub="123", permission_level="normal")
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    payload = await verify_token(creds)

    assert payload["sub"] == "123"
    assert logging_module.get_user_id() == "123"


@pytest.mark.asyncio
async def test_call_llm_scopes_model_lookup_by_current_user(monkeypatch):
    recorded = {}

    class _StubManager:
        def get_by_model(self, model_id, owner_id=""):
            recorded["get_by_model"] = (model_id, owner_id)
            raise _Sentinel("get_by_model")

    monkeypatch.setattr(dp_module, "get_dynamic_provider_manager", lambda: _StubManager())
    logging_module.set_user_id("42")

    with pytest.raises(_Sentinel):
        await llm_caller.call_llm(model="custom-model", prompt="hi")

    assert recorded["get_by_model"] == ("custom-model", "42")


@pytest.mark.asyncio
async def test_call_llm_scopes_explicit_provider_id_by_current_user(monkeypatch):
    recorded = {}

    class _StubManager:
        def get(self, pid, owner_id=""):
            recorded["get"] = (pid, owner_id)
            raise _Sentinel("get")

    monkeypatch.setattr(dp_module, "get_dynamic_provider_manager", lambda: _StubManager())
    logging_module.set_user_id("7")

    with pytest.raises(_Sentinel):
        await llm_caller.call_llm(model="m", prompt="hi", provider_id="pid-1")

    assert recorded["get"] == ("pid-1", "7")


def test_provider_router_route_respects_owner(monkeypatch):
    manager = DynamicProviderManager()
    provider = manager.add(
        name="p", base_url="https://a.example.com", protocol="anthropic",
        api_key="sk-owner1", owner_id="u1",
    )
    provider.models = [ModelInfo(id="only-u1-model")]
    monkeypatch.setattr(dp_module, "get_dynamic_provider_manager", lambda: manager)

    router = ProviderRouter.get_instance()
    logging_module.set_user_id("u1")
    assert router.route("only-u1-model") == ModelProvider.ANTHROPIC

    logging_module.set_user_id("u2")
    assert router.route("only-u1-model") != ModelProvider.ANTHROPIC
