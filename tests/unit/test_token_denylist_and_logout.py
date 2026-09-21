"""Token 吊销黑名单与 /logout 的回归测试（AUT3）。

覆盖：黑名单写入/查询、verify_token/verify_token_ws 拒绝已吊销 token、
/logout 同时吊销 access 与 refresh 并清 Cookie、/refresh 拒绝已吊销 refresh。
Redis 以内存 fake 注入，避免测试依赖真实实例。
"""
import pytest
from fastapi import HTTPException
from jose import jwt

from app.api.v1 import auth as auth_module
from app.core.config import settings
from app.utils import token_denylist
from app.utils.security import (
    create_access_token,
    create_refresh_token,
    verify_token,
    verify_token_ws,
)


class _FakeRedis:
    def __init__(self):
        self.store = {}

    async def setex(self, key, ttl, value):
        self.store[key] = (value, ttl)
        return True

    async def exists(self, key):
        return 1 if key in self.store else 0


class _Req:
    def __init__(self, headers=None, cookies=None):
        self.headers = headers or {}
        self.cookies = cookies or {}
        self.client = None


@pytest.fixture(autouse=True)
def _fake_denylist():
    fake = _FakeRedis()
    token_denylist.set_denylist_client(fake)
    yield fake
    token_denylist.set_denylist_client(None)


@pytest.mark.asyncio
async def test_revoke_token_ignores_zero_ttl(_fake_denylist):
    assert await token_denylist.revoke_token("some-token", 0) is False
    assert await token_denylist.is_token_revoked("some-token") is False


@pytest.mark.asyncio
async def test_verify_token_rejects_revoked_access_token(_fake_denylist):
    from fastapi.security import HTTPAuthorizationCredentials

    token = create_access_token(sub="5", permission_level="normal")
    assert await token_denylist.revoke_token(token, 60) is True

    with pytest.raises(HTTPException) as exc:
        await verify_token(HTTPAuthorizationCredentials(scheme="Bearer", credentials=token))
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_token_ws_rejects_revoked_token(_fake_denylist):
    token = create_access_token(sub="5", permission_level="normal")
    await token_denylist.revoke_token(token, 60)

    valid, payload, close_code, reason = await verify_token_ws(token)
    assert valid is False
    assert payload is None
    assert close_code is not None


@pytest.mark.asyncio
async def test_logout_revokes_access_and_refresh_and_clears_cookies(_fake_denylist):
    access = create_access_token(sub="9", permission_level="normal")
    refresh = create_refresh_token(sub="9")
    payload = jwt.decode(access, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])

    request = _Req(
        headers={"authorization": f"Bearer {access}"},
        cookies={"refresh_token": refresh},
    )
    response = await auth_module.logout(request=request, token=payload, csrf="token")

    assert await token_denylist.is_token_revoked(access) is True
    assert await token_denylist.is_token_revoked(refresh) is True

    set_cookies = response.headers.getlist("set-cookie")
    assert any(cookie.startswith("refresh_token=") for cookie in set_cookies)
    assert any(cookie.startswith("csrf_token=") for cookie in set_cookies)


@pytest.mark.asyncio
async def test_refresh_rejects_revoked_refresh_token(_fake_denylist):
    refresh = create_refresh_token(sub="9")
    await token_denylist.revoke_token(refresh, 60)

    with pytest.raises(HTTPException) as exc:
        await auth_module.refresh_token(
            request=_Req(cookies={"refresh_token": refresh}), db=None, csrf="token"
        )
    assert exc.value.status_code == 401
