"""csrf 校验分支与 FastAPI 依赖补测。"""

import base64
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.utils import csrf as module
from app.utils.csrf import CSRFTokenManager, csrf_manager, csrf_protect, get_csrf_token


def _request(cookies):
    return SimpleNamespace(cookies=cookies)


def _signed(manager, payload):
    encoded = base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")
    return f"{encoded}.{manager._signature(payload)}"


@pytest.mark.parametrize("payload", [
    "not-json",
    json.dumps({"exp": "abc"}),
    json.dumps({"no_exp": 1}),
])
async def test_validate_rejects_bad_payload(payload):
    manager = CSRFTokenManager()
    assert await manager.validate_token(_signed(manager, payload)) is False


async def test_validate_accepts_matching_uid_and_anonymous_user():
    token = await csrf_manager.create_token()
    assert await csrf_manager.validate_token(token, "7") is True


async def test_invalidate_token_is_noop():
    assert await csrf_manager.invalidate_token("whatever") is None


async def test_get_csrf_token_delegates(monkeypatch):
    monkeypatch.setattr(csrf_manager, "create_token", AsyncMock(return_value="tok"))
    assert await get_csrf_token() == "tok"


async def test_csrf_protect_missing_header():
    with pytest.raises(HTTPException) as exc:
        await csrf_protect(_request({"csrf_token": "c"}), x_csrf_token=None)
    assert exc.value.status_code == 403
    assert "缺少 CSRF Token" in exc.value.detail


async def test_csrf_protect_missing_cookie():
    with pytest.raises(HTTPException) as exc:
        await csrf_protect(_request({}), x_csrf_token="h")
    assert "Cookie 中缺少" in exc.value.detail


async def test_csrf_protect_mismatch():
    with pytest.raises(HTTPException) as exc:
        await csrf_protect(_request({"csrf_token": "cookie"}), x_csrf_token="header")
    assert exc.value.detail == "CSRF Token 不匹配"


async def test_csrf_protect_invalid_token(monkeypatch):
    monkeypatch.setattr(csrf_manager, "validate_token", AsyncMock(return_value=False))
    with pytest.raises(HTTPException) as exc:
        await csrf_protect(_request({"csrf_token": "same"}), x_csrf_token="same")
    assert "无效或已过期" in exc.value.detail


async def test_csrf_protect_returns_valid_token(monkeypatch):
    validate = AsyncMock(return_value=True)
    monkeypatch.setattr(csrf_manager, "validate_token", validate)
    token = await csrf_manager.create_token()
    assert await csrf_protect(
        _request({"csrf_token": token}), x_csrf_token=token
    ) == token
    validate.assert_awaited_once_with(token)
