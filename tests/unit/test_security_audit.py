"""安全审计日志接线回归测试：各便捷函数写入 security logger 的事件载荷。"""
import json
from unittest.mock import patch

import pytest

from app.utils.security_audit import (
    log_login_failed,
    log_login_success,
    log_permission_change,
    log_sensitive_operation,
    log_token_refresh,
)


def _payload(mock_call):
    return json.loads(mock_call.args[0])


class TestSecurityAuditEvents:
    @pytest.mark.asyncio
    async def test_login_success_logged_as_info(self):
        with patch("app.utils.security_audit.security_logger") as logger:
            await log_login_success(7, "10.0.0.1")
        assert logger.info.called
        payload = _payload(logger.info.call_args)
        assert payload["event_type"] == "login_success"
        assert payload["user_id"] == 7
        assert payload["success"] is True

    @pytest.mark.asyncio
    async def test_login_failure_accepts_unknown_user(self):
        with patch("app.utils.security_audit.security_logger") as logger:
            await log_login_failed(None, "user_not_found", "10.0.0.2")
        assert logger.warning.called
        payload = _payload(logger.warning.call_args)
        assert payload["event_type"] == "login_failed"
        assert payload["user_id"] is None
        assert payload["success"] is False
        assert payload["details"]["reason"] == "user_not_found"

    @pytest.mark.asyncio
    async def test_permission_change_logged(self):
        with patch("app.utils.security_audit.security_logger") as logger:
            await log_permission_change(3, "normal", "admin", 1)
        payload = _payload(logger.info.call_args)
        assert payload["event_type"] == "permission_change"
        assert payload["details"] == {
            "old_role": "normal",
            "new_role": "admin",
            "changed_by": 1,
        }

    @pytest.mark.asyncio
    async def test_token_refresh_logged(self):
        with patch("app.utils.security_audit.security_logger") as logger:
            await log_token_refresh(5)
        payload = _payload(logger.info.call_args)
        assert payload["event_type"] == "token_refresh"
        assert payload["details"]["token_type"] == "access"

    @pytest.mark.asyncio
    async def test_sensitive_operation_logged(self):
        with patch("app.utils.security_audit.security_logger") as logger:
            await log_sensitive_operation(5, "delete_user", "user:9")
        payload = _payload(logger.info.call_args)
        assert payload["event_type"] == "sensitive_operation"
        assert payload["details"] == {"operation": "delete_user", "target": "user:9"}
