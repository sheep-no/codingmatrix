"""
安全服务单元测试

覆盖安全相关的核心服务：
- 密码哈希与验证
- JWT Token 创建与验证
- CSRF Token 管理
- 密码强度验证
"""
import pytest
from unittest.mock import patch, MagicMock
import jwt
from datetime import datetime, timedelta
from fastapi import HTTPException

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.utils.security import (
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    _decode_and_validate_token,
    verify_refresh_token
)
from app.utils.security import validate_password_strength


class TestPasswordHashing:
    def test_hash_password_returns_string(self):
        hashed = hash_password("testpassword123")
        assert isinstance(hashed, str)
        assert len(hashed) > 0

    def test_hash_password_different_each_time(self):
        hashed1 = hash_password("testpassword123")
        hashed2 = hash_password("testpassword123")
        assert hashed1 != hashed2

    def test_verify_password_correct(self):
        hashed = hash_password("testpassword123")
        assert verify_password("testpassword123", hashed) is True

    def test_verify_password_incorrect(self):
        hashed = hash_password("testpassword123")
        assert verify_password("wrongpassword", hashed) is False

    def test_verify_password_empty(self):
        hashed = hash_password("testpassword123")
        assert verify_password("", hashed) is False

    def test_hash_password_special_characters(self):
        special_pw = "p@ssw0rd!#$%^&*()"
        hashed = hash_password(special_pw)
        assert verify_password(special_pw, hashed) is True

    def test_hash_password_unicode(self):
        unicode_pw = "密码123"
        hashed = hash_password(unicode_pw)
        assert verify_password(unicode_pw, hashed) is True


class TestJWTToken:
    def test_create_access_token(self):
        token = create_access_token(sub="1", permission_level="normal")
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

    def test_create_access_token_custom_expiry(self):
        token = create_access_token(
            sub="1",
            permission_level="normal",
            expires_delta=timedelta(hours=2)
        )
        assert isinstance(token, str)

    def test_create_access_token_super_user(self):
        token = create_access_token(sub="1", permission_level="super")
        assert isinstance(token, str)

    def test_decode_and_validate_token_valid(self):
        token = create_access_token(sub="1", permission_level="normal")
        valid, payload, user_id, perm = _decode_and_validate_token(token, verify_expiry=False)
        assert valid is True
        assert payload is not None
        assert payload.get("sub") == "1"

    def test_decode_and_validate_token_expired(self):
        token = create_access_token(
            sub="1",
            permission_level="normal",
            expires_delta=timedelta(seconds=-1)
        )
        valid, payload, user_id, perm = _decode_and_validate_token(token, verify_expiry=True)
        assert valid is False

    def test_decode_and_validate_token_invalid(self):
        valid, payload, user_id, perm = _decode_and_validate_token("invalid.token.here")
        assert valid is False

    def test_create_refresh_token(self):
        token = create_refresh_token(sub="1")
        assert isinstance(token, str)
        assert len(token.split(".")) == 3

    def test_verify_refresh_token_valid(self):
        token = create_refresh_token(sub="1")
        payload = verify_refresh_token(token)
        assert payload is not None

    def test_verify_refresh_token_invalid(self):
        with pytest.raises(HTTPException):
            verify_refresh_token("invalid.token")


class TestCSRF:
    @pytest.mark.asyncio
    async def test_get_csrf_token(self):
        from app.utils.csrf import get_csrf_token
        token = await get_csrf_token()
        assert isinstance(token, str)
        assert len(token) > 0

    @pytest.mark.asyncio
    async def test_csrf_token_unique(self):
        from app.utils.csrf import get_csrf_token
        token1 = await get_csrf_token()
        token2 = await get_csrf_token()
        assert token1 != token2


class TestPasswordStrength:
    def test_strong_password(self):
        valid, msg = validate_password_strength("StrongP@ss123")
        assert valid is True

    def test_weak_password_too_short(self):
        valid, msg = validate_password_strength("Ab1!")
        assert valid is False

    def test_weak_password_no_uppercase(self):
        valid, msg = validate_password_strength("weakpass123!")
        assert valid is False

    def test_weak_password_no_lowercase(self):
        valid, msg = validate_password_strength("STRONGPASS123!")
        assert valid is False

    def test_weak_password_no_digit(self):
        valid, msg = validate_password_strength("StrongPassword!")
        assert valid is False

    def test_weak_password_no_special(self):
        valid, msg = validate_password_strength("StrongPass123")
        assert valid is False
