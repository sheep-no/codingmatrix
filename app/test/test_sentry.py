"""
Sentry 模块测试
"""
import pytest
from unittest.mock import patch, MagicMock


class TestSentryModule:
    """Sentry 模块测试"""

    def test_import_sentry_module(self):
        """测试 Sentry 模块可导入"""
        from app.utils.sentry import (
            init_sentry,
            capture_error,
            capture_message_sync,
            set_user,
            set_tag,
            add_breadcrumb,
            is_sentry_initialized,
        )
        assert callable(init_sentry)
        assert callable(capture_error)
        assert callable(capture_message_sync)
        assert callable(set_user)
        assert callable(set_tag)
        assert callable(add_breadcrumb)
        assert callable(is_sentry_initialized)

    def test_is_sentry_initialized_false_when_not_init(self):
        """测试未初始化时返回 False"""
        from app.utils.sentry import is_sentry_initialized
        assert is_sentry_initialized() == False

    def test_capture_error_without_init(self):
        """测试未初始化时 capture_error 不抛错"""
        from app.utils.sentry import capture_error
        try:
            capture_error(Exception("test error"))
        except Exception:
            pytest.fail("capture_error should not raise when Sentry not initialized")

    def test_capture_message_without_init(self):
        """测试未初始化时 capture_message_sync 不抛错"""
        from app.utils.sentry import capture_message_sync
        try:
            capture_message_sync("test message")
        except Exception:
            pytest.fail("capture_message_sync should not raise when Sentry not initialized")

    def test_set_user_without_init(self):
        """测试未初始化时 set_user 不抛错"""
        from app.utils.sentry import set_user
        try:
            set_user("123", "test@example.com", "testuser")
        except Exception:
            pytest.fail("set_user should not raise when Sentry not initialized")

    def test_set_tag_without_init(self):
        """测试未初始化时 set_tag 不抛错"""
        from app.utils.sentry import set_tag
        try:
            set_tag("environment", "test")
        except Exception:
            pytest.fail("set_tag should not raise when Sentry not initialized")

    def test_add_breadcrumb_without_init(self):
        """测试未初始化时 add_breadcrumb 不抛错"""
        from app.utils.sentry import add_breadcrumb
        try:
            add_breadcrumb("test breadcrumb", "test")
        except Exception:
            pytest.fail("add_breadcrumb should not raise when Sentry not initialized")

    def test_get_sentry_client_returns_none_when_not_init(self):
        """测试未初始化时 get_sentry_client 返回 None"""
        from app.utils.sentry import get_sentry_client
        assert get_sentry_client() is None

    @pytest.mark.asyncio
    async def test_init_sentry_without_dsn(self):
        """测试未提供 DSN 时不初始化"""
        from app.utils.sentry import init_sentry, is_sentry_initialized

        await init_sentry(dsn=None)
        assert is_sentry_initialized() == False

    @pytest.mark.asyncio
    async def test_init_sentry_with_invalid_dsn(self):
        """测试无效 DSN 时不初始化"""
        from app.utils.sentry import init_sentry, is_sentry_initialized

        await init_sentry(dsn="invalid-dsn")
        assert is_sentry_initialized() == False
