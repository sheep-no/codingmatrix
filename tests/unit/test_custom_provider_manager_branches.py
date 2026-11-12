"""CustomProviderManager 全分支回归。"""

import time

import pytest

from app.services import custom_provider_manager as cpm
from app.services.custom_provider_manager import (
    CustomProvider,
    CustomProviderManager,
    ModelInfo,
    Protocol,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text="body", raise_exc=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self._raise_exc = raise_exc

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self._raise_exc:
            raise self._raise_exc


class FakeAsyncClient:
    def __init__(self, get_response=None, post_response=None, **kwargs):
        self.get_response = get_response
        self.post_response = post_response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def get(self, url, headers=None):
        self.calls.append(("get", url, headers))
        return self.get_response

    async def post(self, url, headers=None, json=None):
        self.calls.append(("post", url, headers, json))
        return self.post_response


@pytest.fixture
def manager():
    return CustomProviderManager()


@pytest.fixture
def provider(manager):
    return manager.add_provider("Test", "https://api.example.com", "openai", "sk-1")


def _patch_httpx(monkeypatch, client):
    monkeypatch.setattr(cpm.httpx, "AsyncClient", lambda **kwargs: client)


class TestProtocolAndModels:
    def test_protocol_values(self):
        assert Protocol.OPENAI == "openai"
        assert Protocol.ANTHROPIC == "anthropic"

    def test_model_info_defaults(self):
        info = ModelInfo(id="m")
        assert info.name == ""
        assert info.max_tokens == 4096
        assert info.context_length == 32768
        assert info.supports_vision is False

    def test_custom_provider_defaults(self):
        provider = CustomProvider(
            id="i", name="n", base_url="u", protocol=Protocol.OPENAI, api_key="k"
        )
        assert provider.enabled is True
        assert provider.models == []
        assert provider.last_sync == 0.0


class TestAddProvider:
    def test_rejects_unsafe_url(self, manager):
        with pytest.raises(ValueError):
            manager.add_provider("n", "http://127.0.0.1:1234", "openai", "k")

    def test_adds_v1_for_openai(self, manager):
        provider = manager.add_provider("n", "https://api.example.com/", "openai", "k")
        assert provider.base_url == "https://api.example.com/v1"
        assert provider.id.startswith("custom_")

    def test_keeps_existing_v1(self, manager):
        provider = manager.add_provider("n", "https://api.example.com/v1", "openai", "k")
        assert provider.base_url.endswith("/v1")

    def test_anthropic_no_v1_suffix(self, manager):
        provider = manager.add_provider("n", "https://api.example.com", "anthropic", "k")
        assert provider.base_url == "https://api.example.com"

    def test_duplicate_names_get_distinct_ids(self, manager):
        first = manager.add_provider("n", "https://a.example.com", "openai", "k")
        second = manager.add_provider("n", "https://b.example.com", "openai", "k")
        assert first.id != second.id

    def test_invalid_protocol(self, manager):
        with pytest.raises(ValueError):
            manager.add_provider("n", "https://api.example.com", "bad", "k")


class TestCRUD:
    def test_get_and_list_hides_key(self, manager, provider):
        assert manager.get_provider(provider.id) is provider
        listed = manager.list_providers()[0]
        assert listed.api_key == ""
        assert listed.id == provider.id
        assert manager.get_provider("missing") is None

    def test_delete(self, manager, provider):
        assert manager.delete_provider(provider.id) is True
        assert manager.delete_provider(provider.id) is False

    def test_update_enabled(self, manager, provider):
        assert manager.update_enabled(provider.id, False) is True
        assert provider.enabled is False
        assert manager.update_enabled("missing", True) is False


class TestSyncModels:
    @pytest.mark.asyncio
    async def test_missing_provider(self, manager):
        with pytest.raises(ValueError):
            await manager.sync_models("missing")

    @pytest.mark.asyncio
    async def test_cached_models_returned(self, manager, provider):
        provider.models = [ModelInfo(id="cached")]
        provider.last_sync = time.time()
        assert (await manager.sync_models(provider.id))[0].id == "cached"

    @pytest.mark.asyncio
    async def test_anthropic_uses_known_models(self, manager):
        provider = manager.add_provider("n", "https://api.example.com", "anthropic", "k")
        models = await manager.sync_models(provider.id)
        assert models[0].id.startswith("claude-")
        assert provider.last_sync > 0

    @pytest.mark.asyncio
    async def test_openai_parse_models(self, manager, provider, monkeypatch):
        payload = {
            "data": [
                {"id": "", "name": "skip"},
                {
                    "id": "gpt-vision",
                    "name": "Vision",
                    "description": "d",
                    "context_length": 8000,
                    "max_tokens": 100,
                },
                {"id": "plain", "metadata": {"context_length": 16000, "max_tokens": 50}},
                {"id": "meta", "meta": {"context_length": 32000}},
            ]
        }
        client = FakeAsyncClient(get_response=FakeResponse(payload=payload))
        _patch_httpx(monkeypatch, client)
        models = await manager.sync_models(provider.id)
        assert [m.id for m in models] == ["gpt-vision", "plain", "meta"]
        assert models[0].supports_vision is True
        assert models[0].context_length == 8000
        assert models[1].context_length == 16000
        assert models[1].max_tokens == 50
        assert models[2].context_length == 32000

    @pytest.mark.asyncio
    async def test_openai_defaults(self, manager, provider, monkeypatch):
        client = FakeAsyncClient(get_response=FakeResponse(payload={"data": [{"id": "m"}]}))
        _patch_httpx(monkeypatch, client)
        model = (await manager.sync_models(provider.id))[0]
        assert model.context_length == 32768
        assert model.max_tokens == 4096
        assert model.name == "m"

    @pytest.mark.asyncio
    async def test_openai_missing_data_key(self, manager, provider, monkeypatch):
        client = FakeAsyncClient(get_response=FakeResponse(payload={}))
        _patch_httpx(monkeypatch, client)
        assert await manager.sync_models(provider.id) == []

    @pytest.mark.asyncio
    async def test_openai_http_error_is_wrapped(self, manager, provider, monkeypatch):
        client = FakeAsyncClient(
            get_response=FakeResponse(raise_exc=RuntimeError("http down"))
        )
        _patch_httpx(monkeypatch, client)
        messages = []
        monkeypatch.setattr(cpm.logger, "error", messages.append)
        with pytest.raises(RuntimeError):
            await manager.sync_models(provider.id)
        assert "拉取模型列表失败" in messages[0]

    @pytest.mark.asyncio
    async def test_fetch_openai_metadata_context_wins(self, manager, provider, monkeypatch):
        payload = {
            "data": [
                {
                    "id": "m",
                    "metadata": {"max_context_tokens": 9999},
                }
            ]
        }
        client = FakeAsyncClient(get_response=FakeResponse(payload=payload))
        _patch_httpx(monkeypatch, client)
        model = (await manager.sync_models(provider.id))[0]
        assert model.max_tokens == 9999


class TestConnection:
    @pytest.mark.asyncio
    async def test_missing_provider(self, manager):
        assert await manager.test_connection("missing") == (False, "供应商不存在")

    @pytest.mark.asyncio
    async def test_exception_wrapped(self, manager, provider, monkeypatch):
        async def _boom(provider_config):
            raise RuntimeError("x")

        monkeypatch.setattr(manager, "_test_openai", _boom)
        assert await manager.test_connection(provider.id) == (False, "连接失败: x")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status,expected",
        [(200, (True, "连接成功")), (401, (False, "API Key 无效")), (403, (False, "权限不足"))],
    )
    async def test_openai_statuses(self, manager, provider, monkeypatch, status, expected):
        client = FakeAsyncClient(post_response=FakeResponse(status_code=status))
        _patch_httpx(monkeypatch, client)
        assert await manager.test_connection(provider.id) == expected

    @pytest.mark.asyncio
    async def test_openai_other_status_truncates(self, manager, provider, monkeypatch):
        client = FakeAsyncClient(
            post_response=FakeResponse(status_code=500, text="x" * 200)
        )
        _patch_httpx(monkeypatch, client)
        success, message = await manager.test_connection(provider.id)
        assert success is False
        assert message.startswith("HTTP 500:")
        assert len(message) == len("HTTP 500: ") + 100

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "status,expected",
        [(200, (True, "连接成功")), (401, (False, "API Key 无效")), (403, (False, "权限不足"))],
    )
    async def test_anthropic_statuses(self, manager, monkeypatch, status, expected):
        provider = manager.add_provider("n", "https://api.example.com", "anthropic", "k")
        client = FakeAsyncClient(post_response=FakeResponse(status_code=status))
        _patch_httpx(monkeypatch, client)
        assert await manager.test_connection(provider.id) == expected

    @pytest.mark.asyncio
    async def test_anthropic_other_status(self, manager, monkeypatch):
        provider = manager.add_provider("n", "https://api.example.com", "anthropic", "k")
        client = FakeAsyncClient(post_response=FakeResponse(status_code=502, text="bad"))
        _patch_httpx(monkeypatch, client)
        assert await manager.test_connection(provider.id) == (False, "HTTP 502: bad")


class TestSingleton:
    def test_get_manager_cached(self):
        original = cpm._custom_provider_manager
        try:
            cpm._custom_provider_manager = None
            first = cpm.get_custom_provider_manager()
            assert first is cpm.get_custom_provider_manager()
        finally:
            cpm._custom_provider_manager = original
