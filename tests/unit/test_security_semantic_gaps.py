"""Coverage gaps for security helpers and PPT semantic renderer."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jose import jwt
from starlette import status

from app.core.config import settings
from app.utils import security
from app.utils.pptx.semantic_renderer import select_chart_type


def test_password_strength_rejects_common_password():
    assert security.validate_password_strength("P@ssw0rd") == (
        False,
        "密码过于简单，请使用更复杂的密码",
    )


def test_verify_password_rejects_non_bcrypt_hash():
    assert security.verify_password("anything", "plain-text") is False
    assert security.verify_password("anything", "") is False


def test_create_access_token_includes_extra_claims():
    token = security.create_access_token(
        "1", "superadmin", extra_claims={"tenant": "acme"}
    )
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert payload["tenant"] == "acme"


@pytest.mark.asyncio
async def test_verify_token_rejects_revoked_token(monkeypatch):
    async def revoked(token):
        return True

    monkeypatch.setitem(
        __import__("sys").modules,
        "app.utils.token_denylist",
        SimpleNamespace(is_token_revoked=revoked),
    )
    with pytest.raises(HTTPException) as exc:
        await _verify_with(
            monkeypatch,
            (True, {"type": "access", "sub": "1"}, None, None),
        )
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED
    assert "已失效" in exc.value.detail


@pytest.mark.asyncio
async def test_verify_token_ws_propagates_invalid_result(monkeypatch):
    monkeypatch.setattr(
        security,
        "_decode_and_validate_token",
        lambda token: (False, None, security.WS_TOKEN_EXPIRED, "expired"),
    )
    result = await security.verify_token_ws("token")
    assert result == (False, None, security.WS_TOKEN_EXPIRED, "expired")


@pytest.mark.asyncio
async def test_verify_token_ws_rejects_revoked_token(monkeypatch):
    async def revoked(token):
        return True

    monkeypatch.setitem(
        __import__("sys").modules,
        "app.utils.token_denylist",
        SimpleNamespace(is_token_revoked=revoked),
    )
    monkeypatch.setattr(
        security,
        "_decode_and_validate_token",
        lambda token: (True, {"sub": "1"}, None, None),
    )
    result = await security.verify_token_ws("token")
    assert result == (False, None, security.WS_TOKEN_EXPIRED, "Token 已失效，请重新登录")


@pytest.mark.asyncio
async def test_verify_token_ws_accepts_valid_token(monkeypatch):
    async def active(token):
        return False

    monkeypatch.setitem(
        __import__("sys").modules,
        "app.utils.token_denylist",
        SimpleNamespace(is_token_revoked=active),
    )
    monkeypatch.setattr(
        security,
        "_decode_and_validate_token",
        lambda token: (True, {"sub": "1"}, None, None),
    )
    result = await security.verify_token_ws("token")
    assert result == (True, {"sub": "1"}, None, None)


# ---------------------------------------------------------------------------
# _decode_and_validate_token
# ---------------------------------------------------------------------------

def test_decode_rejects_token_without_refresh_until():
    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        "type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    valid, data, code, message = security._decode_and_validate_token(token)

    assert valid is False
    assert data is None
    assert code == security.WS_TOKEN_REFRESH_EXPIRED
    assert "刷新期限" in message


def test_decode_returns_expired_when_expired_within_refresh_window(monkeypatch):
    now = datetime.now(timezone.utc)
    expired = {
        "sub": "1",
        "exp": now - timedelta(minutes=5),
        "type": "access",
        "refresh_until": int((now + timedelta(days=1)).timestamp()),
    }
    token = jwt.encode(expired, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    valid, data, code, message = security._decode_and_validate_token(token)

    assert valid is False
    assert code == security.WS_TOKEN_EXPIRED
    assert "已过期" in message


def test_decode_rejects_expired_token_without_refresh_until():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "1",
            "exp": now - timedelta(minutes=1),
            "type": "access",
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    valid, _, code, message = security._decode_and_validate_token(token)

    assert valid is False
    assert code == security.WS_TOKEN_REFRESH_EXPIRED


def test_decode_accepts_valid_token_with_refresh_window():
    now = datetime.now(timezone.utc)
    token = jwt.encode(
        {
            "sub": "1",
            "exp": now + timedelta(minutes=5),
            "type": "access",
            "refresh_until": int((now + timedelta(days=1)).timestamp()),
        },
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

    valid, payload, code, message = security._decode_and_validate_token(token)

    assert valid is True
    assert payload["sub"] == "1"
    assert code is None
    assert message is None


def test_decode_requires_refresh_window_for_valid_token():
    payload = {
        "sub": "1",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        "type": "access",
    }
    token = jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    valid, _, code, _ = security._decode_and_validate_token(token)

    assert valid is False
    assert code == security.WS_TOKEN_REFRESH_EXPIRED


# ---------------------------------------------------------------------------
# verify_token
# ---------------------------------------------------------------------------

async def _verify_with(monkeypatch, result):
    monkeypatch.setattr(security, "_decode_and_validate_token", lambda token: result)
    credentials = SimpleNamespace(credentials="token")
    return await security.verify_token(credentials)


@pytest.mark.asyncio
async def test_verify_token_maps_expired_to_401(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _verify_with(
            monkeypatch,
            (False, None, security.WS_TOKEN_EXPIRED, "expired"),
        )
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_verify_token_maps_refresh_expired_to_403(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _verify_with(
            monkeypatch,
            (False, None, security.WS_TOKEN_REFRESH_EXPIRED, "refresh expired"),
        )
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_verify_token_maps_other_error_to_401(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _verify_with(monkeypatch, (False, None, 4999, "unknown"))
    assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_verify_token_rejects_non_access_token(monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await _verify_with(monkeypatch, (True, {"type": "refresh"}, None, None))
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    assert "token 类型" in exc.value.detail


@pytest.mark.asyncio
async def test_verify_token_accepts_access_token(monkeypatch):
    async def not_revoked(token):
        return False

    monkeypatch.setitem(
        __import__("sys").modules,
        "app.utils.token_denylist",
        SimpleNamespace(is_token_revoked=not_revoked),
    )
    payload = {"type": "access", "sub": "1"}
    result = await _verify_with(monkeypatch, (True, payload, None, None))
    assert result == payload


def test_require_superadmin_rejects_normal_user():
    with pytest.raises(HTTPException) as exc:
        security.require_superadmin({"permission_level": "normal"})
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_require_superadmin_returns_superadmin_payload():
    payload = {"permission_level": "superadmin", "sub": "1"}
    assert security.require_superadmin(payload) is payload


# ---------------------------------------------------------------------------
# verify_refresh_token
# ---------------------------------------------------------------------------

def test_verify_refresh_token_rejects_expired():
    refresh_key = f"{settings.SECRET_KEY}_refresh_v1"
    token = jwt.encode(
        {
            "sub": "1",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=1),
            "type": "refresh",
        },
        refresh_key,
        algorithm=settings.ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        security.verify_refresh_token(token)

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
    assert "Refresh Token 已过期" in exc.value.detail


# ---------------------------------------------------------------------------
# semantic renderer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("relationship", "expected"),
    [
        ("correlation", "scatter"),
        ("distribution", "scatter"),
        ("comparison", "bar"),
        ("unknown", "bar"),
    ],
)
def test_select_chart_type_relationship_branches(relationship, expected):
    assert select_chart_type({"relationship": relationship}) == expected
