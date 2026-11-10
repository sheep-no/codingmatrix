"""登录失败分支不得通过响应时间暴露账号是否存在。

用户不存在时若直接返回，会跳过 bcrypt 校验；该分支比“密码错误”快一个数量级，
攻击者可据此枚举已注册邮箱。修复后两条分支都执行一次 bcrypt 校验。
"""

import pytest
from fastapi import HTTPException

from app.api.v1 import auth as auth_module


class _FakeRequest:
    def __init__(self, host: str = "127.0.0.1"):
        self.client = type("C", (), {"host": host})()


def _install_common(monkeypatch, user):
    async def _get_user(db, email):
        return user

    async def _noop(*args, **kwargs):
        return None

    monkeypatch.setattr(auth_module, "check_login_rate_limit", lambda identifier: True)
    monkeypatch.setattr(auth_module, "record_login_failure", lambda identifier: None)
    monkeypatch.setattr(auth_module, "get_user_by_email", _get_user)
    monkeypatch.setattr(auth_module, "log_login_failed", _noop)


@pytest.mark.asyncio
async def test_unknown_user_still_verifies_dummy_hash(monkeypatch):
    _install_common(monkeypatch, user=None)
    calls = []
    monkeypatch.setattr(
        auth_module,
        "verify_password",
        lambda password, hashed: calls.append(hashed) or False,
    )

    with pytest.raises(HTTPException) as exc:
        await auth_module.login(
            request=_FakeRequest(),
            body={"email": "ghost@example.com", "password": "Passw0rd!"},
            db=None,
            csrf="token",
        )

    assert exc.value.status_code == 401
    assert len(calls) == 1, "用户不存在分支未执行 bcrypt 校验"
    assert calls[0].startswith("$2b$")


@pytest.mark.asyncio
async def test_wrong_password_uses_real_hash(monkeypatch):
    user = type(
        "U",
        (),
        {
            "id": 2,
            "hashed_password": "$2b$12$realhashrealhashrealhashrealhashrealhashrealhashrealhashre",
            "permission": type("P", (), {"permission_level": "normal"})(),
        },
    )()
    _install_common(monkeypatch, user=user)
    calls = []
    monkeypatch.setattr(
        auth_module,
        "verify_password",
        lambda password, hashed: calls.append(hashed) or False,
    )

    with pytest.raises(HTTPException) as exc:
        await auth_module.login(
            request=_FakeRequest(),
            body={"email": "user@example.com", "password": "Passw0rd!"},
            db=None,
            csrf="token",
        )

    assert exc.value.status_code == 401
    assert calls == [user.hashed_password]
