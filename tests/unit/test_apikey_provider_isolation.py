"""用户提交的供应商模型同步必须按用户隔离（APY2）。

原实现用全局 provider 名 `user_<provider>`，不同用户提交同一供应商的 Key 时
后提交者会覆盖先提交者的 api_key；启动恢复也只按 provider 去重，多用户被折叠成一条。
"""

import pytest

from app.api.v1 import apikey
from app.main import _restore_user_providers


class _FakeProvider:
    def __init__(self, name, base_url, protocol, api_key):
        self.id = f"id-{name}"
        self.name = name
        self.base_url = base_url
        self.protocol = protocol
        self.api_key = api_key
        self.last_sync = None


class _FakeCpManager:
    def __init__(self):
        self.providers = {}
        self.synced = []

    def add_provider(self, name, base_url, protocol, api_key):
        provider = _FakeProvider(name, base_url, protocol, api_key)
        self.providers[provider.id] = provider
        return provider

    async def sync_models(self, provider_id):
        self.synced.append(provider_id)


@pytest.fixture
def cp_manager(monkeypatch):
    fake = _FakeCpManager()
    monkeypatch.setattr(
        "app.services.custom_provider_manager.get_custom_provider_manager",
        lambda: fake,
    )
    return fake


@pytest.mark.asyncio
async def test_different_users_same_provider_are_isolated(cp_manager):
    await apikey._sync_provider_models("openai", "key-alice", "alice")
    await apikey._sync_provider_models("openai", "key-bob", "bob")

    assert len(cp_manager.providers) == 2
    assert {p.name for p in cp_manager.providers.values()} == {
        "user_alice_openai",
        "user_bob_openai",
    }
    assert {p.api_key for p in cp_manager.providers.values()} == {"key-alice", "key-bob"}


@pytest.mark.asyncio
async def test_same_user_resubmit_updates_in_place(cp_manager):
    await apikey._sync_provider_models("openai", "key-old", "alice")
    await apikey._sync_provider_models("openai", "key-new", "alice")

    assert len(cp_manager.providers) == 1
    (provider,) = cp_manager.providers.values()
    assert provider.name == "user_alice_openai"
    assert provider.api_key == "key-new"
    assert len(cp_manager.synced) == 2


@pytest.mark.asyncio
async def test_restore_keeps_each_users_provider(monkeypatch):
    class _FakeApikeyManager:
        def get_all_enabled_keys(self):
            return [
                ("alice", "tok-a", "openai", "key-alice"),
                ("bob", "tok-b", "openai", "key-bob"),
                ("alice", "tok-a2", "deepseek", "key-alice-ds"),
            ]

    calls = []

    async def fake_sync(provider, api_key, user_id):
        calls.append((user_id, provider, api_key))

    monkeypatch.setattr(
        "app.services.apikey_manager.get_apikey_manager",
        lambda: _FakeApikeyManager(),
    )
    monkeypatch.setattr(apikey, "_sync_provider_models", fake_sync)

    await _restore_user_providers()

    assert sorted(calls) == sorted(
        [
            ("alice", "openai", "key-alice"),
            ("bob", "openai", "key-bob"),
            ("alice", "deepseek", "key-alice-ds"),
        ]
    )
