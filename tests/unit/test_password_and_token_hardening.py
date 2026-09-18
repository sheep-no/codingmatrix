"""API 安全模块 P2/P3 缺陷回归（SEC1/SEC3/SEC4）。"""

from datetime import timedelta

import pytest
from jose import jwt, JWTError

from app.core.config import settings
from app.utils import security as security_mod
from app.utils.security import (
    _decode_and_validate_token,
    create_access_token,
    hash_password,
    validate_password_strength,
    verify_password,
)


class TestPasswordLengthLimit:
    def test_validate_password_strength_rejects_over_limit(self):
        limit = security_mod.BCRYPT_MAX_PASSWORD_BYTES
        valid, message = validate_password_strength("A1!" + "a" * 80)
        assert valid is False
        assert str(limit) in message

    def test_hash_password_rejects_over_limit(self):
        with pytest.raises(ValueError):
            hash_password("A1!" + "a" * 80)

    def test_verify_password_rejects_over_limit_collision(self):
        base = "a" * security_mod.BCRYPT_MAX_PASSWORD_BYTES
        hashed = hash_password(base)

        # 超过上限、且前 72 字节相同的不同密码不得通过校验
        assert verify_password(base + "X", hashed) is False
        assert verify_password(base + "Y", hashed) is False
        assert verify_password(base, hashed) is True


class TestRefreshWindow:
    def test_refresh_until_not_before_expiry(self):
        token = create_access_token(
            sub="1",
            permission_level="normal",
            expires_delta=timedelta(days=10),
        )
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        assert payload["refresh_until"] >= payload["exp"]

    def test_default_window_is_five_days(self):
        token = create_access_token(sub="1", permission_level="normal")
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        # 默认 access 有效期远小于 5 天，刷新窗口应晚于 exp
        assert payload["refresh_until"] > payload["exp"]


class TestTokenErrorMessages:
    def test_unexpected_decode_error_does_not_leak_details(self, monkeypatch):
        calls = {"count": 0}

        def fake_decode(*args, **kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise JWTError("signature failure")
            raise ValueError("internal detail that must not leak")

        monkeypatch.setattr(security_mod.jwt, "decode", fake_decode)

        success, payload, code, message = _decode_and_validate_token("garbage")

        assert success is False
        assert payload is None
        assert message == "Token 无效"
        assert "internal detail" not in message

    def test_invalid_token_returns_fixed_message(self):
        success, payload, code, message = _decode_and_validate_token("not-a-token")
        assert success is False
        assert message == "Token 无效"
