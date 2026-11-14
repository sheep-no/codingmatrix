"""补齐 github_config_service 的凭据读取、保存与加密边界。"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.services import github_config_service as service


def _record(**kwargs):
    defaults = dict(
        user_id=7,
        username="alice",
        encrypted_token="envelope",
        use_github=True,
        verified_at=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestTokenEncryption:
    def test_round_trip(self):
        envelope = service.encrypt_token("ghp_secret", 7)

        assert envelope != "ghp_secret"
        assert service.decrypt_token(_record(encrypted_token=envelope)) == "ghp_secret"


class TestConfigSummaryCredentialState:
    def test_stored(self, monkeypatch):
        monkeypatch.setattr(service, "decrypt_token", lambda record: "token")

        summary = service.config_summary(_record())

        assert summary["credential_state"] == "stored"
        assert summary["has_token"] is True

    def test_empty_decrypt_result_is_missing(self, monkeypatch):
        monkeypatch.setattr(service, "decrypt_token", lambda record: "")

        summary = service.config_summary(_record())

        assert summary["credential_state"] == "missing"

    def test_unreadable(self, monkeypatch):
        def boom(record):
            raise ValueError("bad envelope")

        monkeypatch.setattr(service, "decrypt_token", boom)

        summary = service.config_summary(_record())

        assert summary["credential_state"] == "unreadable"
        assert summary["has_token"] is False


class TestLoadReadableToken:
    @pytest.mark.asyncio
    async def test_missing_token_column(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=_record(encrypted_token=""))

        with pytest.raises(HTTPException) as exc:
            await service.load_readable_token(db, 7)

        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_unreadable_envelope(self, monkeypatch):
        db = AsyncMock()
        db.get = AsyncMock(return_value=_record())

        def boom(record):
            raise ValueError("bad")

        monkeypatch.setattr(service, "decrypt_token", boom)

        with pytest.raises(HTTPException, match="凭据无法读取"):
            await service.load_readable_token(db, 7)

    @pytest.mark.asyncio
    async def test_empty_decrypted_token(self, monkeypatch):
        db = AsyncMock()
        db.get = AsyncMock(return_value=_record())
        monkeypatch.setattr(service, "decrypt_token", lambda record: "")

        with pytest.raises(HTTPException, match="尚未配置"):
            await service.load_readable_token(db, 7)

    @pytest.mark.asyncio
    async def test_success(self, monkeypatch):
        record = _record()
        db = AsyncMock()
        db.get = AsyncMock(return_value=record)
        monkeypatch.setattr(service, "decrypt_token", lambda item: "token")

        loaded, token = await service.load_readable_token(db, 7)

        assert loaded is record
        assert token == "token"


class TestResolveSaveCredentials:
    @pytest.mark.asyncio
    async def test_disabled_without_record(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        assert await service.resolve_save_credentials(db, 7, " bob ", "", False) == ("bob", "", False)

    @pytest.mark.asyncio
    async def test_disabled_falls_back_to_stored_username(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=_record())

        assert await service.resolve_save_credentials(db, 7, "", "", False) == (
            "alice",
            "",
            False,
        )

    @pytest.mark.asyncio
    async def test_none_uses_record_toggle(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=_record())

        username, token, enabled = await service.resolve_save_credentials(
            db, 7, "alice", "tok", None
        )

        assert (username, token, enabled) == ("alice", "tok", True)

    @pytest.mark.asyncio
    async def test_invalid_username(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException, match="用户名格式无效"):
            await service.resolve_save_credentials(db, 7, "-bad", "tok", True)

    @pytest.mark.asyncio
    async def test_token_without_username(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException, match="请填写 GitHub 用户名"):
            await service.resolve_save_credentials(db, 7, "", "tok", True)

    @pytest.mark.asyncio
    async def test_token_with_whitespace(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        with pytest.raises(HTTPException, match="Token 格式无效"):
            await service.resolve_save_credentials(db, 7, "alice", "to k", True)

    @pytest.mark.asyncio
    async def test_valid_token(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        assert await service.resolve_save_credentials(db, 7, "alice", "tok", True) == (
            "alice",
            "tok",
            True,
        )

    @pytest.mark.asyncio
    async def test_falls_back_to_stored_token(self, monkeypatch):
        stored = _record(username="alice")
        db = AsyncMock()
        db.get = AsyncMock(return_value=stored)
        monkeypatch.setattr(
            service, "load_readable_token", AsyncMock(return_value=(stored, "stored"))
        )

        assert await service.resolve_save_credentials(db, 7, "", "", True) == (
            "alice",
            "stored",
            True,
        )

    @pytest.mark.asyncio
    async def test_stored_token_requires_username(self, monkeypatch):
        stored = _record(username="")
        db = AsyncMock()
        db.get = AsyncMock(return_value=stored)
        monkeypatch.setattr(
            service, "load_readable_token", AsyncMock(return_value=(stored, "stored"))
        )

        with pytest.raises(HTTPException, match="请填写 GitHub 用户名"):
            await service.resolve_save_credentials(db, 7, "", "", True)


class TestSaveConfig:
    @pytest.mark.asyncio
    async def test_invalid_username(self):
        with pytest.raises(HTTPException, match="用户名格式无效"):
            await service.save_config(AsyncMock(), 7, "-bad", "", False)

    @pytest.mark.asyncio
    async def test_invalid_token(self):
        with pytest.raises(HTTPException, match="Token 格式无效"):
            await service.save_config(AsyncMock(), 7, "alice", "a b", False)

    @pytest.mark.asyncio
    async def test_creates_disabled_record(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=None)

        result = await service.save_config(db, 7, "alice", "", False)

        db.add.assert_called_once()
        db.commit.assert_awaited_once()
        assert result["success"] is True
        assert result["persisted"] is True

    @pytest.mark.asyncio
    async def test_username_change_requires_new_token(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=_record())

        with pytest.raises(HTTPException, match="变更 GitHub 用户名时请提供新 Token"):
            await service.save_config(db, 7, "bob", "", False)

    @pytest.mark.asyncio
    async def test_token_requires_username(self):
        db = AsyncMock()
        db.get = AsyncMock(return_value=_record(username=""))

        with pytest.raises(HTTPException, match="请填写 GitHub 用户名"):
            await service.save_config(db, 7, "", "tok", False)

    @pytest.mark.asyncio
    async def test_new_token_invalidates_verification(self, monkeypatch):
        record = _record(verified_at=datetime.now(timezone.utc))
        db = AsyncMock()
        db.get = AsyncMock(return_value=record)
        monkeypatch.setattr(service, "encrypt_token", lambda token, user_id: "new-envelope")
        monkeypatch.setattr(service, "config_summary", lambda item: {"has_token": True})

        result = await service.save_config(db, 7, "alice", "tok", True)

        assert record.encrypted_token == "new-envelope"
        assert record.verified_at is None
        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_username_change_without_token_clears_verification(self):
        record = _record(
            encrypted_token="", verified_at=datetime.now(timezone.utc)
        )
        db = AsyncMock()
        db.get = AsyncMock(return_value=record)

        await service.save_config(db, 7, "bob", "", False)

        assert record.username == "bob"
        assert record.verified_at is None

    @pytest.mark.asyncio
    async def test_enable_requires_readable_credentials(self):
        record = _record(encrypted_token="")
        db = AsyncMock()
        db.get = AsyncMock(return_value=record)

        with pytest.raises(HTTPException, match="启用前请配置可读取的 GitHub 凭据"):
            await service.save_config(db, 7, "alice", "", True)

    @pytest.mark.asyncio
    async def test_enable_with_stored_token(self, monkeypatch):
        record = _record()
        db = AsyncMock()
        db.get = AsyncMock(return_value=record)
        monkeypatch.setattr(service, "decrypt_token", lambda item: "stored")

        result = await service.save_config(db, 7, "alice", "", True)

        assert result["has_token"] is True
        assert result["credential_state"] == "stored"
        db.commit.assert_awaited_once()
