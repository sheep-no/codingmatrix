"""
中间件服务单元测试

覆盖中间件相关功能：
- 速率限制器
- 加密服务
- 配置管理
"""
import pytest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


class TestRateLimiter:
    def test_check_login_rate_limit_initial(self):
        from app.middleware.rate_limiter import check_login_rate_limit
        result = check_login_rate_limit("test_user_mw2")
        assert result is True

    def test_record_login_success(self):
        from app.middleware.rate_limiter import record_login_success
        record_login_success("success_user_mw2")

    def test_record_login_failure(self):
        from app.middleware.rate_limiter import record_login_failure
        record_login_failure("failure_user_mw2")


class TestEncryption:
    @pytest.mark.asyncio
    async def test_get_public_key(self):
        from app.utils.encryption import get_public_key_for_client
        public_key = await get_public_key_for_client()
        assert isinstance(public_key, str)
        assert len(public_key) > 0

    @pytest.mark.asyncio
    async def test_get_public_key_format(self):
        from app.utils.encryption import get_public_key_for_client
        public_key = await get_public_key_for_client()
        assert "-----BEGIN PUBLIC KEY-----" in public_key or "-----BEGIN RSA PUBLIC KEY-----" in public_key


class TestConfig:
    def test_config_has_required_fields(self):
        from app.core.config import settings
        assert hasattr(settings, 'DATABASE_URL')
        assert hasattr(settings, 'SECRET_KEY')
        assert hasattr(settings, 'ENV')

    def test_config_env_default(self):
        from app.core.config import settings
        assert settings.ENV in ['development', 'production', 'test']
