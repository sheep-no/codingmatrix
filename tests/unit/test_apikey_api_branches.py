"""API Key 管理接口全分支回归。"""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.api.v1 import apikey


def _request(path="/api/v1/agent/apikey", method="POST") -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": [],
            "query_string": b"",
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def _meta(**overrides):
    data = dict(
        token="tok",
        provider="openai",
        remark="r",
        status="unverified",
        created_at="2026-01-01T00:00:00+00:00",
        expires_at="2026-02-01T00:00:00+00:00",
        ttl_seconds=3600,
        enabled=True,
        fallback_preference="custom",
        custom_fallback_chain=["m"],
    )
    data.update(overrides)
    return SimpleNamespace(**data)


class FakeManager:
    def __init__(self):
        self.calls = []
        self.keys = []
        self.meta = _meta()
        self.store_error = None
        self.delete_result = True
        self.update_result = True
        self.list_error = None

    def store_key(self, **kwargs):
        self.calls.append(("store", kwargs))
        if self.store_error:
            raise self.store_error
        return "tok-new"

    def get_key(self, user_id, token):
        self.calls.append(("get", user_id, token))
        return "a" * 20

    def get_metadata(self, user_id, token):
        self.calls.append(("meta", user_id, token))
        return self.meta

    def delete_key(self, user_id, token):
        self.calls.append(("delete", user_id, token))
        return self.delete_result

    def list_keys(self, user_id):
        if self.list_error:
            raise self.list_error
        return self.keys

    def update_enabled(self, user_id, token, enabled):
        self.calls.append(("enabled", user_id, token, enabled))
        return self.update_result

    def update_context_lengths(self, user_id, token, lengths):
        self.calls.append(("ctx", user_id, token, lengths))
        return self.update_result

    def update_fallback_preference(self, user_id, token, pref, chain):
        self.calls.append(("fallback", user_id, token, pref, chain))
        return self.update_result

    def update_status(self, user_id, token, status):
        self.calls.append(("status", user_id, token, status))
        return True


class FakeKeyManager:
    def __init__(self, api_key="a" * 20, error=None):
        self.api_key = api_key
        self.error = error

    def decrypt(self, encrypted):
        if self.error:
            raise self.error
        return self.api_key


@pytest.fixture
def manager(monkeypatch):
    fake = FakeManager()
    monkeypatch.setattr(apikey, "get_apikey_manager", lambda: fake)
    monkeypatch.setattr(apikey, "get_rsa_key_manager", lambda: FakeKeyManager())
    return fake


@pytest.fixture(autouse=True)
def disable_rate_limit():
    original = apikey.limiter.enabled
    apikey.limiter.enabled = False
    yield
    apikey.limiter.enabled = original


@pytest.fixture
def no_sync(monkeypatch):
    scheduled = []

    async def _sync(provider, api_key, user_id):
        scheduled.append((provider, user_id))

    monkeypatch.setattr(apikey, "_sync_provider_models", _sync)
    return scheduled


class TestPublicKey:
    @pytest.mark.asyncio
    async def test_success(self):
        fake = SimpleNamespace(get_public_key_pem=lambda: "pem")
        apikey.get_rsa_key_manager.__globals__  # keep import used
        import app.api.v1.apikey as module

        original = module.get_rsa_key_manager
        module.get_rsa_key_manager = lambda: fake
        try:
            assert await apikey.get_public_key(_request()) == {"public_key": "pem"}
        finally:
            module.get_rsa_key_manager = original

    @pytest.mark.asyncio
    async def test_failure(self, monkeypatch):
        def _boom():
            raise RuntimeError("no rsa")

        monkeypatch.setattr(apikey, "get_rsa_key_manager", _boom)
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.get_public_key(_request())
        assert exc.value.status_code == 500


class TestSubmitKey:
    @pytest.mark.asyncio
    async def test_unsupported_provider(self, manager):
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="bad", ttl=3600
        )
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.submit_key(_request(), request, "u")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_ttl(self, manager):
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="openai", ttl=0
        )
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.submit_key(_request(), request, "u")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_key_too_short(self, manager, monkeypatch):
        monkeypatch.setattr(apikey, "get_rsa_key_manager", lambda: FakeKeyManager("short"))
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="openai", ttl=3600
        )
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.submit_key(_request(), request, "u")
        assert exc.value.status_code == 400
        assert "格式无效" in exc.value.detail

    @pytest.mark.asyncio
    async def test_success_non_compat(self, manager, no_sync):
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="anthropic", ttl=3600, remark="r"
        )
        response = await apikey.submit_key(_request(), request, "u")
        assert response.success is True
        assert response.token == "tok-new"
        assert response.provider == "openai"
        assert no_sync == []

    @pytest.mark.asyncio
    async def test_success_schedules_sync(self, manager, no_sync):
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="deepseek", ttl=3600
        )
        await apikey.submit_key(_request(), request, "u")
        await asyncio.sleep(0)
        assert no_sync == [("deepseek", "u")]

    @pytest.mark.asyncio
    async def test_store_value_error(self, manager):
        manager.store_error = ValueError("bad")
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="openai", ttl=3600
        )
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.submit_key(_request(), request, "u")
        assert exc.value.status_code == 400
        assert "参数无效" in exc.value.detail

    @pytest.mark.asyncio
    async def test_store_runtime_error(self, manager):
        manager.store_error = RuntimeError("limit")
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="openai", ttl=3600
        )
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.submit_key(_request(), request, "u")
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_store_generic_error(self, manager):
        manager.store_error = KeyError("boom")
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="openai", ttl=3600
        )
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.submit_key(_request(), request, "u")
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_decrypt_http_exception_passthrough(self, manager, monkeypatch):
        monkeypatch.setattr(
            apikey,
            "get_rsa_key_manager",
            lambda: FakeKeyManager(error=apikey.HTTPException(400, "bad")),
        )
        request = apikey.SubmitKeyRequest(
            encrypted_key="enc", provider="openai", ttl=3600
        )
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.submit_key(_request(), request, "u")
        assert exc.value.status_code == 400


class TestTestKey:
    @pytest.mark.asyncio
    async def test_key_missing(self, manager):
        manager.get_key = lambda user_id, token: None
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.test_key(
                _request(), apikey.TestKeyRequest(token="t"), "u"
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_meta_missing(self, manager):
        manager.get_metadata = lambda user_id, token: None
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.test_key(
                _request(), apikey.TestKeyRequest(token="t"), "u"
            )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_success_marks_verified(self, manager, monkeypatch):
        class _Checker:
            async def check_detailed(self, provider, key):
                return True, "ok", True

        monkeypatch.setattr(apikey, "get_health_checker", lambda: _Checker())
        response = await apikey.test_key(
            _request(), apikey.TestKeyRequest(token="t"), "u"
        )
        assert response.success is True
        assert ("status", "u", "t", "verified") in manager.calls

    @pytest.mark.asyncio
    async def test_definitive_failure_marks_invalid(self, manager, monkeypatch):
        class _Checker:
            async def check_detailed(self, provider, key):
                return False, "invalid key", True

        monkeypatch.setattr(apikey, "get_health_checker", lambda: _Checker())
        response = await apikey.test_key(
            _request(), apikey.TestKeyRequest(token="t"), "u"
        )
        assert response.success is False
        assert ("status", "u", "t", "invalid") in manager.calls

    @pytest.mark.asyncio
    async def test_indefinite_failure_keeps_status(self, manager, monkeypatch):
        class _Checker:
            async def check_detailed(self, provider, key):
                return False, "timeout", False

        monkeypatch.setattr(apikey, "get_health_checker", lambda: _Checker())
        await apikey.test_key(_request(), apikey.TestKeyRequest(token="t"), "u")
        assert not any(call[0] == "status" for call in manager.calls)

    @pytest.mark.asyncio
    async def test_generic_error(self, manager, monkeypatch):
        class _Checker:
            async def check_detailed(self, provider, key):
                raise RuntimeError("boom")

        monkeypatch.setattr(apikey, "get_health_checker", lambda: _Checker())
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.test_key(_request(), apikey.TestKeyRequest(token="t"), "u")
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_http_exception_passthrough(self, manager, monkeypatch):
        def _boom():
            raise apikey.HTTPException(418, "teapot")

        monkeypatch.setattr(apikey, "get_health_checker", _boom)
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.test_key(_request(), apikey.TestKeyRequest(token="t"), "u")
        assert exc.value.status_code == 418


class TestDeleteKey:
    @pytest.mark.asyncio
    async def test_success(self, manager):
        assert await apikey.delete_key(_request(), "t", "u") == {"message": "Key 已清除"}

    @pytest.mark.asyncio
    async def test_not_found(self, manager):
        manager.delete_result = False
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.delete_key(_request(), "t", "u")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error(self, manager, monkeypatch):
        def _boom():
            raise RuntimeError("down")

        monkeypatch.setattr(apikey, "get_apikey_manager", _boom)
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.delete_key(_request(), "t", "u")
        assert exc.value.status_code == 500


class TestListKeys:
    @pytest.mark.asyncio
    async def test_success(self, manager):
        manager.keys = [_meta()]
        result = await apikey.list_keys(_request(), "u")
        assert result[0].token == "tok"

    @pytest.mark.asyncio
    async def test_error(self, manager):
        manager.list_error = RuntimeError("down")
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.list_keys(_request(), "u")
        assert exc.value.status_code == 500


class TestUpdateEnabled:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("enabled,word", [(True, "启用"), (False, "禁用")])
    async def test_success(self, manager, enabled, word):
        result = await apikey.update_enabled(_request(), "t", enabled, "u")
        assert result == {"message": f"Key 已{word}"}

    @pytest.mark.asyncio
    async def test_not_found(self, manager):
        manager.update_result = False
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.update_enabled(_request(), "t", True, "u")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error(self, manager, monkeypatch):
        def _boom():
            raise RuntimeError("down")

        monkeypatch.setattr(apikey, "get_apikey_manager", _boom)
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.update_enabled(_request(), "t", True, "u")
        assert exc.value.status_code == 500


class TestUpdateContextLengths:
    @pytest.mark.asyncio
    async def test_success(self, manager):
        request = apikey.UpdateContextLengthsRequest(context_lengths={"m": 1024})
        result = await apikey.update_context_lengths(_request(), "t", request, "u")
        assert result["context_lengths"] == {"m": 1024}
        assert ("ctx", "u", "t", {"m": 1024}) in manager.calls

    @pytest.mark.asyncio
    async def test_not_found(self, manager):
        manager.update_result = False
        request = apikey.UpdateContextLengthsRequest(context_lengths={})
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.update_context_lengths(_request(), "t", request, "u")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error(self, manager, monkeypatch):
        def _boom():
            raise RuntimeError("down")

        monkeypatch.setattr(apikey, "get_apikey_manager", _boom)
        request = apikey.UpdateContextLengthsRequest(context_lengths={})
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.update_context_lengths(_request(), "t", request, "u")
        assert exc.value.status_code == 500


class TestFallbackPreference:
    @pytest.mark.asyncio
    async def test_invalid_preference(self, manager):
        request = apikey.UpdateFallbackPreferenceRequest(fallback_preference="bad")
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.update_fallback_preference(_request(), "t", request, "u")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_custom_success(self, manager):
        request = apikey.UpdateFallbackPreferenceRequest(
            fallback_preference="custom", custom_fallback_chain=["m"]
        )
        result = await apikey.update_fallback_preference(_request(), "t", request, "u")
        assert result["custom_fallback_chain"] == ["m"]
        assert ("fallback", "u", "t", "custom", ["m"]) in manager.calls

    @pytest.mark.asyncio
    async def test_non_custom_success_clears_chain(self, manager):
        request = apikey.UpdateFallbackPreferenceRequest(
            fallback_preference="disabled", custom_fallback_chain=["m"]
        )
        result = await apikey.update_fallback_preference(_request(), "t", request, "u")
        assert result["custom_fallback_chain"] == []
        assert ("fallback", "u", "t", "disabled", None) in manager.calls

    @pytest.mark.asyncio
    async def test_not_found(self, manager):
        manager.update_result = False
        request = apikey.UpdateFallbackPreferenceRequest(fallback_preference="custom")
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.update_fallback_preference(_request(), "t", request, "u")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_generic_error(self, manager, monkeypatch):
        def _boom():
            raise RuntimeError("down")

        monkeypatch.setattr(apikey, "get_apikey_manager", _boom)
        request = apikey.UpdateFallbackPreferenceRequest(fallback_preference="custom")
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.update_fallback_preference(_request(), "t", request, "u")
        assert exc.value.status_code == 500

    @pytest.mark.asyncio
    async def test_get_success(self, manager):
        result = await apikey.get_fallback_preference(_request(), "t", "u")
        assert result == {"fallback_preference": "custom", "custom_fallback_chain": ["m"]}

    @pytest.mark.asyncio
    async def test_get_not_found(self, manager):
        manager.meta = None
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.get_fallback_preference(_request(), "t", "u")
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_get_generic_error(self, manager, monkeypatch):
        def _boom():
            raise RuntimeError("down")

        monkeypatch.setattr(apikey, "get_apikey_manager", _boom)
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.get_fallback_preference(_request(), "t", "u")
        assert exc.value.status_code == 500


class TestBatchImport:
    @pytest.mark.asyncio
    async def test_all_failure_reasons(self, manager, monkeypatch):
        request = apikey.BatchImportRequest(
            keys=[
                {"provider": "bad", "encrypted_key": "enc"},
                {"provider": "openai"},
                {"provider": "openai", "encrypted_key": "enc"},
            ]
        )
        monkeypatch.setattr(apikey, "get_rsa_key_manager", lambda: FakeKeyManager("short"))
        response = await apikey.batch_import(_request(), request, "u")
        assert response.success_count == 0
        assert response.failed_count == 3
        assert all(not r["success"] for r in response.results)
        assert response.results[0]["provider"] == "bad"

    @pytest.mark.asyncio
    async def test_reports_unknown_provider_on_exception(self, manager, monkeypatch):
        request = apikey.BatchImportRequest(keys=[{}])
        response = await apikey.batch_import(_request(), request, "u")
        assert response.results[0]["provider"] == "unknown"

    @pytest.mark.asyncio
    async def test_success_and_sync_once(self, manager, no_sync):
        request = apikey.BatchImportRequest(
            keys=[
                {"provider": "openai", "encrypted_key": "enc", "remark": "r"},
                {"provider": "openai", "encrypted_key": "enc"},
            ]
        )
        response = await apikey.batch_import(_request(), request, "u")
        await asyncio.sleep(0)
        assert response.success_count == 2
        assert no_sync == [("openai", "u")]

    @pytest.mark.asyncio
    async def test_outer_error(self, manager, monkeypatch):
        def _boom():
            raise RuntimeError("down")

        monkeypatch.setattr(apikey, "get_apikey_manager", _boom)
        request = apikey.BatchImportRequest(keys=[])
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.batch_import(_request(), request, "u")
        assert exc.value.status_code == 500


class TestBatchExport:
    @pytest.mark.asyncio
    async def test_json(self, manager):
        manager.keys = [_meta()]
        response = await apikey.batch_export(_request(), "json", "u")
        assert response.format == "json"
        assert json.loads(response.data)[0]["token"] == "tok"

    @pytest.mark.asyncio
    async def test_csv(self, manager):
        manager.keys = [_meta()]
        response = await apikey.batch_export(_request(), "csv", "u")
        assert response.format == "csv"
        assert response.data.startswith("token,provider")

    @pytest.mark.asyncio
    async def test_unsupported_format(self, manager):
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.batch_export(_request(), "xml", "u")
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_generic_error(self, manager):
        manager.list_error = RuntimeError("down")
        with pytest.raises(apikey.HTTPException) as exc:
            await apikey.batch_export(_request(), "json", "u")
        assert exc.value.status_code == 500


class TestSyncProviderModels:
    @pytest.mark.asyncio
    async def test_unknown_provider_returns(self, monkeypatch):
        import app.services.custom_provider_manager as cp

        existing = SimpleNamespace(id="other", name="someone_else")

        class _Manager:
            providers = {"other": existing}

            async def sync_models(self, provider_id):
                raise AssertionError("should not sync")

        monkeypatch.setattr(cp, "get_custom_provider_manager", lambda: _Manager())
        await apikey._sync_provider_models("unknown", "k", "u")
        assert existing.name == "someone_else"

    @pytest.mark.asyncio
    async def test_updates_existing_provider(self, monkeypatch):
        import app.services.custom_provider_manager as cp

        existing = SimpleNamespace(
            id="existing", name="user_u_openai", api_key="old", last_sync=123
        )
        other = SimpleNamespace(id="other", name="other", api_key="x", last_sync=1)

        class _Manager:
            def __init__(self):
                self.providers = {"other": other, "existing": existing}
                self.synced = []

            async def sync_models(self, provider_id):
                self.synced.append(provider_id)
                return []

        fake = _Manager()
        monkeypatch.setattr(cp, "get_custom_provider_manager", lambda: fake)
        await apikey._sync_provider_models("openai", "new-key", "u")
        assert existing.api_key == "new-key"
        assert existing.last_sync == 0
        assert fake.synced == ["existing"]

    @pytest.mark.asyncio
    async def test_creates_new_provider(self, monkeypatch):
        import app.services.custom_provider_manager as cp

        class _Manager:
            def __init__(self):
                self.providers = {}
                self.synced = []

            def add_provider(self, **kwargs):
                provider = SimpleNamespace(id="new-id", **kwargs)
                self.providers[provider.id] = provider
                return provider

            async def sync_models(self, provider_id):
                self.synced.append(provider_id)

        fake = _Manager()
        monkeypatch.setattr(cp, "get_custom_provider_manager", lambda: fake)
        await apikey._sync_provider_models("deepseek", "key", "u")
        assert fake.synced == ["new-id"]
        assert fake.providers["new-id"].name == "user_u_deepseek"

    @pytest.mark.asyncio
    async def test_anthropic_protocol(self, monkeypatch):
        import app.services.custom_provider_manager as cp

        captured = {}

        class _Manager:
            providers = {}

            def add_provider(self, **kwargs):
                captured.update(kwargs)
                return SimpleNamespace(id="id")

            async def sync_models(self, provider_id):
                return []

        monkeypatch.setattr(cp, "get_custom_provider_manager", lambda: _Manager())
        await apikey._sync_provider_models("anthropic", "key", "u")
        assert captured["protocol"] == "anthropic"

    @pytest.mark.asyncio
    async def test_sync_error_is_swallowed(self, monkeypatch):
        import app.services.custom_provider_manager as cp

        class _Manager:
            @property
            def providers(self):
                raise RuntimeError("boom")

        messages = []
        monkeypatch.setattr(cp, "get_custom_provider_manager", lambda: _Manager())
        monkeypatch.setattr(apikey.logger, "warning", messages.append)
        await apikey._sync_provider_models("openai", "k", "u")
        assert "模型同步失败" in messages[0]


def test_request_models_reject_invalid_payloads():
    with pytest.raises(ValidationError):
        apikey.SubmitKeyRequest(provider="openai")
    with pytest.raises(ValidationError):
        apikey.TestKeyRequest()
    assert apikey.TestKeyResponse(success=True, message="ok").models == []
    assert apikey.BatchImportRequest(keys=[]).keys == []


class TestGetCurrentUserId:
    def test_with_sub(self):
        assert apikey.get_current_user_id({"sub": "alice"}) == "alice"

    def test_without_sub(self):
        assert apikey.get_current_user_id({}) == "default_user"


class TestValidatorsDirect:
    def test_context_lengths_too_many(self):
        with pytest.raises(ValueError):
            apikey.UpdateContextLengthsRequest._validate_context_lengths(
                {f"m{i}": 1 for i in range(apikey._MAX_CONTEXT_ENTRIES + 1)}
            )

    def test_context_lengths_invalid_name(self):
        with pytest.raises(ValueError):
            apikey.UpdateContextLengthsRequest._validate_context_lengths({"": 1})

    def test_context_lengths_non_int(self):
        with pytest.raises(ValueError):
            apikey.UpdateContextLengthsRequest._validate_context_lengths({"m": "1"})

    def test_context_lengths_bool(self):
        with pytest.raises(ValueError):
            apikey.UpdateContextLengthsRequest._validate_context_lengths({"m": True})

    def test_context_lengths_out_of_range(self):
        with pytest.raises(ValueError):
            apikey.UpdateContextLengthsRequest._validate_context_lengths({"m": 0})

    def test_fallback_chain_too_many(self):
        with pytest.raises(ValueError):
            apikey.UpdateFallbackPreferenceRequest._validate_custom_chain(
                ["m"] * (apikey._MAX_FALLBACK_ENTRIES + 1)
            )

    def test_fallback_chain_invalid_item(self):
        with pytest.raises(ValueError):
            apikey.UpdateFallbackPreferenceRequest._validate_custom_chain([""])
