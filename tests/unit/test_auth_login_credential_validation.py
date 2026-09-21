"""登录端点凭据格式校验回归测试（SD1）。

明文登录分支以 `body: dict` 直收 JSON，绕过 UserLogin schema，此前非字符串
email/password 会在 `email[:3]` 或查询环节抛 TypeError 逃逸为 500。这里锁定
统一校验后的行为：非法类型/超长一律 400，合法形态继续走原有 401 流程。
"""
import types

import pytest
from fastapi import HTTPException

from app.api.v1 import auth as auth_module


class _FakeRequest:
    def __init__(self, host: str = "127.0.0.1"):
        self.client = types.SimpleNamespace(host=host)


async def _call_login(body: dict):
    return await auth_module.login(
        request=_FakeRequest(), body=body, db=None, csrf="test-token"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "body",
    [
        {"email": 123, "password": "Passw0rd!"},
        {"email": "user@example.com", "password": 123},
        {"email": ["user@example.com"], "password": "Passw0rd!"},
        {"email": "user@example.com", "password": {"a": 1}},
        {"email": "", "password": "Passw0rd!"},
        {"email": "   ", "password": "Passw0rd!"},
        {"email": "user@example.com", "password": ""},
        {"email": "user@example.com", "password": "x" * 73},
        {"email": "a" * 250 + "@example.com", "password": "Passw0rd!"},
    ],
)
async def test_login_rejects_invalid_credentials_shape(body):
    with pytest.raises(HTTPException) as exc:
        await _call_login(body)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_login_valid_shape_reaches_unknown_user_flow(monkeypatch):
    async def _no_user(db, email):
        return None

    monkeypatch.setattr(auth_module, "check_login_rate_limit", lambda identifier: True)
    monkeypatch.setattr(auth_module, "record_login_failure", lambda identifier: None)
    monkeypatch.setattr(auth_module, "get_user_by_email", _no_user)

    with pytest.raises(HTTPException) as exc:
        await _call_login({"email": "  user@example.com  ", "password": "Passw0rd!"})
    assert exc.value.status_code == 401
