"""Branch coverage for app/api/v1/auth.py."""

import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.api.v1 import auth
from app.schema.history import ConversationHistoryRequest, HistoryRequest
from app.schema.user import UserRegister


class _DB:
    def __init__(self, scalar=None, rows=None, execute_error=None, flush_error=None):
        self.scalar_value = scalar
        self.rows = rows or []
        self.execute_error = execute_error
        self.flush_error = flush_error
        self.added = []
        self.commits = 0
        self.rollbacks = 0
        self.refreshes = 0

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = 42

    async def flush(self):
        if self.flush_error:
            raise self.flush_error

    async def commit(self):
        self.commits += 1

    async def rollback(self):
        self.rollbacks += 1

    async def refresh(self, obj):
        self.refreshes += 1

    async def execute(self, stmt):
        if self.execute_error:
            raise self.execute_error
        return SimpleNamespace(
            scalar=lambda: self.scalar_value,
            scalar_one_or_none=lambda: self.scalar_value,
            all=lambda: self.rows,
        )


class _Req:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client = SimpleNamespace(host="1.2.3.4")


class TestHelpers:
    def test_history_payload_valid_metadata(self):
        record = SimpleNamespace(
            id=1,
            conversation_id=2,
            prompt="p",
            response="r",
            thinking=None,
            title="t",
            created_at=datetime.now(),
            metadata_json='{"a": 1}',
        )
        assert auth._history_payload(record)["metadata"] == {"a": 1}

    def test_history_payload_invalid_metadata(self):
        record = SimpleNamespace(
            id=1,
            conversation_id=2,
            prompt="p",
            response="r",
            thinking=None,
            title="t",
            created_at=datetime.now(),
            metadata_json="not json",
        )
        assert auth._history_payload(record)["metadata"] == {}

    def test_history_payload_empty_metadata(self):
        record = SimpleNamespace(
            id=1,
            conversation_id=2,
            prompt="p",
            response="r",
            thinking=None,
            title="t",
            created_at=datetime.now(),
            metadata_json=None,
        )
        assert auth._history_payload(record)["metadata"] == {}

    def test_remaining_ttl_no_exp(self):
        assert auth._remaining_ttl({}) == 0

    def test_remaining_ttl_future(self):
        exp = datetime.now(timezone.utc).timestamp() + 100
        assert 0 < auth._remaining_ttl({"exp": exp}) <= 100

    def test_remaining_ttl_expired(self):
        assert auth._remaining_ttl({"exp": 0}) == 0

    def test_refresh_token_ttl_invalid_token(self, monkeypatch):
        monkeypatch.setattr(auth.jwt, "decode", MagicMock(side_effect=auth.JWTError("bad")))
        assert auth._refresh_token_ttl("t") == 7 * 24 * 60 * 60

    def test_refresh_token_ttl_valid(self, monkeypatch):
        exp = datetime.now(timezone.utc).timestamp() + 100
        monkeypatch.setattr(auth.jwt, "decode", MagicMock(return_value={"exp": exp}))
        assert 0 < auth._refresh_token_ttl("t") <= 100

    def test_refresh_token_ttl_missing_exp_falls_back(self, monkeypatch):
        monkeypatch.setattr(auth.jwt, "decode", MagicMock(return_value={}))
        assert auth._refresh_token_ttl("t") == 7 * 24 * 60 * 60


@pytest.mark.asyncio
async def test_public_key_endpoint(monkeypatch):
    monkeypatch.setattr(auth, "get_public_key_for_client", AsyncMock(return_value="pem"))
    result = await auth.get_public_key()
    assert result["public_key"] == "pem"


@pytest.mark.asyncio
async def test_csrf_token_endpoint(monkeypatch):
    monkeypatch.setattr(auth, "get_csrf_token", AsyncMock(return_value="csrf"))
    response = await auth.get_csrf_token_endpoint()
    assert response.status_code == 200
    assert any("csrf_token" in cookie for cookie in response.headers.getlist("set-cookie"))


def _patch_login(monkeypatch, **overrides):
    defaults = {
        "get_client_ip": lambda request: "1.2.3.4",
        "check_login_rate_limit": lambda identifier: True,
        "record_login_failure": MagicMock(),
        "record_login_success": MagicMock(),
        "log_login_failed": AsyncMock(),
        "log_login_success": AsyncMock(),
        "verify_password": lambda raw, hashed: raw == "secret",
        "create_access_token": lambda **kw: "access",
        "create_refresh_token": lambda **kw: "refresh",
        "get_csrf_token": AsyncMock(return_value="csrf"),
        "get_user_by_email": AsyncMock(return_value=None),
        "decrypt_sensitive_data": AsyncMock(return_value={"email": "a@b.c", "password": "secret"}),
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(auth, name, value)
    return defaults


def _user(permission=None, hashed="secret", uid=1):
    return SimpleNamespace(
        id=uid,
        username="u",
        hashed_password=hashed,
        permission=permission,
    )


@pytest.mark.asyncio
async def test_login_encrypted_mode_success(monkeypatch):
    _patch_login(
        monkeypatch,
        get_user_by_email=AsyncMock(
            return_value=_user(permission=SimpleNamespace(permission_level="normal"))
        ),
    )

    response = await auth.login(
        request=_Req(),
        body={"encrypted_data": "d", "encrypted_key": "k"},
        db=_DB(),
        csrf="csrf",
    )

    assert response.status_code == 200
    assert json.loads(response.body)["encryption_enabled"] is True


@pytest.mark.asyncio
async def test_login_encrypted_mode_decrypt_failure(monkeypatch):
    _patch_login(
        monkeypatch, decrypt_sensitive_data=AsyncMock(side_effect=ValueError("bad"))
    )
    with pytest.raises(HTTPException) as exc:
        await auth.login(
            request=_Req(),
            body={"encrypted_data": "d", "encrypted_key": "k"},
            db=_DB(),
            csrf="csrf",
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "数据解密失败"


@pytest.mark.asyncio
async def test_login_missing_fields(monkeypatch):
    _patch_login(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await auth.login(request=_Req(), body={}, db=_DB(), csrf="csrf")
    assert exc.value.detail == "登录数据格式错误"


@pytest.mark.asyncio
async def test_login_non_string_credentials(monkeypatch):
    _patch_login(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await auth.login(
            request=_Req(), body={"email": 1, "password": "x"}, db=_DB(), csrf="csrf"
        )
    assert exc.value.detail == "登录数据格式错误"


@pytest.mark.asyncio
async def test_login_empty_email(monkeypatch):
    _patch_login(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await auth.login(
            request=_Req(), body={"email": "   ", "password": "x"}, db=_DB(), csrf="csrf"
        )
    assert exc.value.detail == "登录数据格式错误"


@pytest.mark.asyncio
async def test_login_email_too_long(monkeypatch):
    _patch_login(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await auth.login(
            request=_Req(),
            body={"email": "a" * 255 + "@b.c", "password": "x"},
            db=_DB(),
            csrf="csrf",
        )
    assert exc.value.detail == "登录数据格式错误"


@pytest.mark.asyncio
async def test_login_password_too_long(monkeypatch):
    _patch_login(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await auth.login(
            request=_Req(),
            body={"email": "a@b.c", "password": "x" * 100},
            db=_DB(),
            csrf="csrf",
        )
    assert exc.value.detail == "登录数据格式错误"


@pytest.mark.asyncio
async def test_login_rate_limited(monkeypatch):
    _patch_login(monkeypatch, check_login_rate_limit=lambda identifier: False)
    with pytest.raises(HTTPException) as exc:
        await auth.login(
            request=_Req(),
            body={"email": "a@b.c", "password": "secret"},
            db=_DB(),
            csrf="csrf",
        )
    assert exc.value.status_code == 429


@pytest.mark.asyncio
async def test_login_user_not_found(monkeypatch):
    patched = _patch_login(monkeypatch)
    with pytest.raises(HTTPException) as exc:
        await auth.login(
            request=_Req(),
            body={"email": "a@b.c", "password": "secret"},
            db=_DB(),
            csrf="csrf",
        )
    assert exc.value.status_code == 401
    patched["record_login_failure"].assert_called_once()


@pytest.mark.asyncio
async def test_login_wrong_password(monkeypatch):
    patched = _patch_login(
        monkeypatch,
        get_user_by_email=AsyncMock(return_value=_user(permission=SimpleNamespace(permission_level="admin"))),
    )
    patched["verify_password"] = lambda raw, hashed: False
    monkeypatch.setattr(auth, "verify_password", patched["verify_password"])

    with pytest.raises(HTTPException) as exc:
        await auth.login(
            request=_Req(),
            body={"email": "a@b.c", "password": "secret"},
            db=_DB(),
            csrf="csrf",
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_login_creates_missing_permission(monkeypatch):
    _patch_login(monkeypatch, get_user_by_email=AsyncMock(return_value=_user()))
    service = SimpleNamespace(
        create_permission_if_not_exists=AsyncMock(
            return_value=SimpleNamespace(permission_level="normal")
        )
    )
    monkeypatch.setattr(auth, "PermissionService", MagicMock(return_value=service))

    response = await auth.login(
        request=_Req(),
        body={"email": "a@b.c", "password": "secret"},
        db=_DB(),
        csrf="csrf",
    )
    assert response.status_code == 200
    service.create_permission_if_not_exists.assert_awaited_once()


@pytest.mark.parametrize("level,role", [("superadmin", "superadmin"), ("admin", "admin"), ("normal", "user")])
@pytest.mark.asyncio
async def test_login_role_mapping(monkeypatch, level, role):
    _patch_login(
        monkeypatch,
        get_user_by_email=AsyncMock(
            return_value=_user(permission=SimpleNamespace(permission_level=level))
        ),
    )
    captured = {}

    def _create(**kwargs):
        captured.update(kwargs)
        return "access"

    monkeypatch.setattr(auth, "create_access_token", _create)

    await auth.login(
        request=_Req(),
        body={"email": "a@b.c", "password": "secret"},
        db=_DB(),
        csrf="csrf",
    )
    assert captured["role"] == role


@pytest.mark.asyncio
async def test_register_password_too_weak(monkeypatch):
    monkeypatch.setattr(auth, "validate_password_strength", lambda p: (False, "weak"))
    with pytest.raises(HTTPException) as exc:
        await auth.register(
            body=UserRegister(email="a@b.c", password="Test1234!", username="u"),
            db=_DB(),
            csrf="csrf",
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_register_existing_email(monkeypatch):
    monkeypatch.setattr(auth, "validate_password_strength", lambda p: (True, ""))
    monkeypatch.setattr(auth, "check_email_exists", AsyncMock(return_value=True))
    with pytest.raises(HTTPException) as exc:
        await auth.register(
            body=UserRegister(email="a@b.c", password="Test1234!", username="u"),
            db=_DB(),
            csrf="csrf",
        )
    assert exc.value.detail == "邮箱已存在"


@pytest.mark.asyncio
async def test_register_success(monkeypatch):
    monkeypatch.setattr(auth, "validate_password_strength", lambda p: (True, ""))
    monkeypatch.setattr(auth, "check_email_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(auth, "hash_password", lambda p: "hashed")
    monkeypatch.setattr(auth, "create_access_token", lambda **kw: "token")
    service = SimpleNamespace(
        create_permission=AsyncMock(
            return_value=SimpleNamespace(permission_level="normal")
        )
    )
    monkeypatch.setattr(auth, "PermissionService", MagicMock(return_value=service))
    db = _DB()

    result = await auth.register(
        body=UserRegister(email="a@b.c", password="Test1234!", username="u"),
        db=db,
        csrf="csrf",
    )
    assert result["access_token"] == "token"
    assert db.commits == 1


@pytest.mark.asyncio
async def test_get_history_success(monkeypatch):
    record = SimpleNamespace(
        id=1,
        conversation_id=2,
        prompt="p",
        response="r",
        thinking=None,
        title="t",
        created_at=datetime.now(),
        metadata_json=None,
    )
    monkeypatch.setattr(auth, "search_history_to_db", AsyncMock(return_value=[record]))
    monkeypatch.setattr(
        auth, "get_distinct_conversation_count", AsyncMock(return_value=1)
    )

    result = await auth.get_history.__wrapped__(
        request=HistoryRequest(), db=_DB(), token={"sub": "1"}
    )
    assert result["total"] == 1
    assert result["items"][0]["id"] == 1


@pytest.mark.asyncio
async def test_get_history_error(monkeypatch):
    monkeypatch.setattr(
        auth, "search_history_to_db", AsyncMock(side_effect=SQLAlchemyError("boom"))
    )
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        await auth.get_history.__wrapped__(
            request=HistoryRequest(), db=db, token={"sub": "1"}
        )
    assert exc.value.status_code == 500
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_get_conversation_detail_success(monkeypatch):
    record = SimpleNamespace(
        id=1,
        conversation_id=2,
        prompt="p",
        response="r",
        thinking=None,
        title="t",
        created_at=datetime.now(),
        metadata_json=None,
    )
    monkeypatch.setattr(auth, "get_conversation_history", AsyncMock(return_value=[record]))

    result = await auth.get_conversation_detail(
        request=ConversationHistoryRequest(conversation_id=2),
        db=_DB(),
        token={"sub": "1"},
    )
    assert result["conversation_id"] == 2


@pytest.mark.asyncio
async def test_get_conversation_detail_error(monkeypatch):
    monkeypatch.setattr(
        auth, "get_conversation_history", AsyncMock(side_effect=ValueError("boom"))
    )
    db = _DB()
    with pytest.raises(HTTPException) as exc:
        await auth.get_conversation_detail(
            request=ConversationHistoryRequest(conversation_id=2),
            db=db,
            token={"sub": "1"},
        )
    assert exc.value.status_code == 500
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_refresh_missing_cookie():
    with pytest.raises(HTTPException) as exc:
        await auth.refresh_token(request=_Req(), db=_DB(), csrf="csrf")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_refresh_missing_sub(monkeypatch):
    from app.utils import token_denylist

    monkeypatch.setattr(token_denylist, "is_token_revoked", AsyncMock(return_value=False))
    monkeypatch.setattr(auth, "verify_refresh_token", lambda token: {})

    with pytest.raises(HTTPException) as exc:
        await auth.refresh_token(
            request=_Req(cookies={"refresh_token": "t"}), db=_DB(), csrf="csrf"
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_refresh_success_no_permission(monkeypatch):
    from app.utils import token_denylist

    monkeypatch.setattr(token_denylist, "is_token_revoked", AsyncMock(return_value=False))
    monkeypatch.setattr(auth, "verify_refresh_token", lambda token: {"sub": "3"})
    service = SimpleNamespace(get_permission=AsyncMock(return_value=None))
    monkeypatch.setattr(auth, "PermissionService", MagicMock(return_value=service))
    monkeypatch.setattr(auth, "create_access_token", lambda **kw: "new")
    monkeypatch.setattr(auth, "get_csrf_token", AsyncMock(return_value="csrf"))
    monkeypatch.setattr(auth, "log_token_refresh", AsyncMock())

    response = await auth.refresh_token(
        request=_Req(cookies={"refresh_token": "t"}), db=_DB(), csrf="csrf"
    )
    assert response.status_code == 200
    assert json.loads(response.body)["username"] == "unknown"


@pytest.mark.asyncio
@pytest.mark.parametrize("level", ["superadmin", "admin"])
async def test_refresh_role_mapping(monkeypatch, level):
    from app.utils import token_denylist

    monkeypatch.setattr(token_denylist, "is_token_revoked", AsyncMock(return_value=False))
    monkeypatch.setattr(auth, "verify_refresh_token", lambda token: {"sub": "3"})
    permission = SimpleNamespace(
        permission_level=level, user=SimpleNamespace(username="u")
    )
    service = SimpleNamespace(get_permission=AsyncMock(return_value=permission))
    monkeypatch.setattr(auth, "PermissionService", MagicMock(return_value=service))
    captured = {}

    def _create(**kwargs):
        captured.update(kwargs)
        return "new"

    monkeypatch.setattr(auth, "create_access_token", _create)
    monkeypatch.setattr(auth, "get_csrf_token", AsyncMock(return_value="csrf"))
    monkeypatch.setattr(auth, "log_token_refresh", AsyncMock())

    await auth.refresh_token(
        request=_Req(cookies={"refresh_token": "t"}), db=_DB(), csrf="csrf"
    )
    assert captured["role"] == level


@pytest.mark.asyncio
async def test_refresh_generic_error(monkeypatch):
    from app.utils import token_denylist

    monkeypatch.setattr(token_denylist, "is_token_revoked", AsyncMock(return_value=False))
    monkeypatch.setattr(auth, "verify_refresh_token", MagicMock(side_effect=RuntimeError("x")))

    with pytest.raises(HTTPException) as exc:
        await auth.refresh_token(
            request=_Req(cookies={"refresh_token": "t"}), db=_DB(), csrf="csrf"
        )
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_logout_without_tokens(monkeypatch):
    from app.utils import token_denylist

    monkeypatch.setattr(token_denylist, "revoke_token", AsyncMock())
    response = await auth.logout(request=_Req(), token={"sub": "1"}, csrf="csrf")
    assert response.status_code == 200
    assert json.loads(response.body)["revoked_tokens"] == 0


@pytest.mark.asyncio
async def test_user_profile_success_without_permission(monkeypatch):
    user = SimpleNamespace(
        id=1,
        username="u",
        email="e",
        permission=None,
        created_at=datetime.now(),
        updated_at=None,
    )
    db = _DB(scalar=user)
    result = await auth.get_user_profile.__wrapped__(db=db, token={"sub": "1"})
    assert result["permission_level"] == "normal"
    assert result["updated_at"] is None


@pytest.mark.asyncio
async def test_user_profile_not_found():
    with pytest.raises(HTTPException) as exc:
        await auth.get_user_profile.__wrapped__(db=_DB(scalar=None), token={"sub": "1"})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_user_profile_generic_error():
    with pytest.raises(HTTPException) as exc:
        await auth.get_user_profile.__wrapped__(
            db=_DB(execute_error=SQLAlchemyError("boom")), token={"sub": "1"}
        )
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_conversations_success(monkeypatch):
    conv = SimpleNamespace(
        conversation_id=1,
        title="t",
        prompt="x" * 200,
        created_at=datetime.now(),
    )
    empty_prompt = SimpleNamespace(
        conversation_id=2, title=None, prompt=None, created_at=datetime.now()
    )
    db = _DB(scalar=2, rows=[(conv, 3), (empty_prompt, 1)])

    result = await auth.get_conversations.__wrapped__(limit=10, offset=0, db=db, token={"sub": "1"})
    assert result["total"] == 2
    assert result["items"][0]["prompt"] == "x" * 100
    assert result["items"][1]["prompt"] == ""


@pytest.mark.asyncio
async def test_conversations_total_none(monkeypatch):
    db = _DB(scalar=None, rows=[])
    result = await auth.get_conversations.__wrapped__(limit=10, offset=0, db=db, token={"sub": "1"})
    assert result["total"] == 0


@pytest.mark.asyncio
async def test_register_integrity_error_returns_400(monkeypatch):
    monkeypatch.setattr(auth, "validate_password_strength", lambda p: (True, ""))
    monkeypatch.setattr(auth, "check_email_exists", AsyncMock(return_value=False))
    monkeypatch.setattr(auth, "hash_password", lambda p: "hashed")
    db = _DB(flush_error=IntegrityError("INSERT", {}, Exception("dup")))

    with pytest.raises(HTTPException) as exc:
        await auth.register(
            body=UserRegister(email="a@b.c", password="Test1234!", username="u"),
            db=db,
            csrf="csrf",
        )
    assert exc.value.status_code == 400
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_refresh_rejects_revoked_token(monkeypatch):
    from app.utils import token_denylist

    monkeypatch.setattr(token_denylist, "is_token_revoked", AsyncMock(return_value=True))
    with pytest.raises(HTTPException) as exc:
        await auth.refresh_token(
            request=_Req(cookies={"refresh_token": "t"}), db=_DB(), csrf="csrf"
        )
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_logout_revokes_present_tokens(monkeypatch):
    from app.utils import token_denylist

    monkeypatch.setattr(token_denylist, "revoke_token", AsyncMock(return_value=True))
    monkeypatch.setattr(auth, "_remaining_ttl", lambda token: 60)
    monkeypatch.setattr(auth, "_refresh_token_ttl", lambda token: 60)

    response = await auth.logout(
        request=_Req(
            headers={"authorization": "Bearer abc"},
            cookies={"refresh_token": "refresh"},
        ),
        token={"sub": "1"},
        csrf="csrf",
    )
    assert json.loads(response.body)["revoked_tokens"] == 2


@pytest.mark.asyncio
async def test_conversations_error_is_generic():
    db = _DB(execute_error=SQLAlchemyError("secret"))
    with pytest.raises(HTTPException) as exc:
        await auth.get_conversations.__wrapped__(limit=10, offset=0, db=db, token={"sub": "1"})
    assert exc.value.status_code == 500
    assert "secret" not in exc.value.detail
