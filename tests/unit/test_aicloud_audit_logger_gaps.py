"""补齐 aicloud 审计日志的记录与查询分支。"""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import delete

from app.models.aicloud import AicloudAuditLog
from app.utils.aicloud.audit_logger import (
    cleanup_old_audit_logs,
    get_recent_operations,
    log_file_read,
    log_file_write,
    log_network_request,
    log_operation,
    query_audit_logs,
)


@pytest.fixture(autouse=True)
async def clean_audit_logs(test_db):
    await test_db.execute(delete(AicloudAuditLog))
    await test_db.commit()


@pytest.mark.usefixtures("test_user")
class TestLogHelpers:
    async def test_file_read_with_error(self, test_db):
        log = await log_file_read(
            test_db, 1, "/tmp/a.txt", success=False, error="denied"
        )

        assert log.operation == "file_read"
        assert log.status == "failed"
        assert json.loads(log.details) == {"action": "read", "error": "denied"}

    async def test_file_read_success_without_error(self, test_db):
        log = await log_file_read(test_db, 1, "/tmp/a.txt", success=True)

        assert log.status == "success"
        assert json.loads(log.details) == {"action": "read"}

    async def test_file_write_with_bytes(self, test_db):
        log = await log_file_write(
            test_db, 1, "/tmp/b.txt", success=True, bytes_written=42
        )

        assert log.operation == "file_write"
        assert log.status == "success"
        assert json.loads(log.details) == {"action": "write", "bytes_written": 42}

    async def test_file_write_without_optional_fields(self, test_db):
        log = await log_file_write(test_db, 1, "/tmp/c.txt", success=True)

        assert json.loads(log.details) == {"action": "write"}

    async def test_file_write_with_error(self, test_db):
        log = await log_file_write(
            test_db, 1, "/tmp/c.txt", success=False, bytes_written=0, error="disk full"
        )

        assert log.status == "failed"
        assert json.loads(log.details) == {
            "action": "write",
            "bytes_written": 0,
            "error": "disk full",
        }

    async def test_network_request_success(self, test_db):
        log = await log_network_request(
            test_db, 1, "https://example.com", "GET", status_code=204
        )

        assert log.operation == "network_request"
        assert log.status == "success"
        assert log.url == "https://example.com"
        assert json.loads(log.details) == {"method": "GET", "status_code": 204}

    async def test_network_request_failure_with_error(self, test_db):
        log = await log_network_request(
            test_db, 1, "https://example.com", "POST", status_code=500, error="boom"
        )

        assert log.status == "failed"
        assert json.loads(log.details) == {
            "method": "POST",
            "status_code": 500,
            "error": "boom",
        }

    async def test_network_request_without_status(self, test_db):
        log = await log_network_request(test_db, 1, "https://example.com", "GET")

        assert log.status == "failed"
        assert json.loads(log.details) == {"method": "GET"}


@pytest.mark.usefixtures("test_user")
class TestQueryAuditLogs:
    async def _seed(self, db):
        now = datetime.now(timezone.utc)
        entries = [
            AicloudAuditLog(
                user_id=1,
                operation="file_read",
                status="success",
                created_at=now - timedelta(days=5),
            ),
            AicloudAuditLog(
                user_id=1,
                operation="file_write",
                status="success",
                created_at=now - timedelta(days=1),
            ),
            AicloudAuditLog(
                user_id=2,
                operation="file_read",
                status="failed",
                created_at=now,
            ),
        ]
        db.add_all(entries)
        await db.commit()
        return now

    async def test_no_filters_returns_all_ordered_desc(self, test_db):
        await self._seed(test_db)

        logs = await query_audit_logs(test_db)

        assert len(logs) == 3
        assert logs[0].created_at >= logs[-1].created_at

    async def test_all_filters_applied(self, test_db):
        now = await self._seed(test_db)

        logs = await query_audit_logs(
            test_db,
            user_id=1,
            operation="file_read",
            start_date=now - timedelta(days=10),
            end_date=now - timedelta(days=2),
            limit=10,
        )

        assert len(logs) == 1
        assert logs[0].operation == "file_read"
        assert logs[0].user_id == 1

    async def test_limit_applied(self, test_db):
        await self._seed(test_db)

        assert len(await query_audit_logs(test_db, limit=2)) == 2

    async def test_recent_operations_uses_day_window(self, test_db):
        await self._seed(test_db)

        logs = await get_recent_operations(test_db, 1, days=2)

        assert [log.operation for log in logs] == ["file_write"]
        assert all(log.user_id == 1 for log in logs)


@pytest.mark.usefixtures("test_user")
class TestCleanupOldAuditLogs:
    async def test_only_old_successful_logs_removed(self, test_db):
        now = datetime.now(timezone.utc)
        test_db.add_all(
            [
                AicloudAuditLog(
                    user_id=1,
                    operation="file_read",
                    status="success",
                    created_at=now - timedelta(days=200),
                ),
                AicloudAuditLog(
                    user_id=1,
                    operation="file_read",
                    status="failed",
                    created_at=now - timedelta(days=200),
                ),
                AicloudAuditLog(
                    user_id=1,
                    operation="file_read",
                    status="success",
                    created_at=now,
                ),
            ]
        )
        await test_db.commit()

        removed = await cleanup_old_audit_logs(test_db, days=90)

        assert removed == 1
        remaining = await query_audit_logs(test_db)
        assert len(remaining) == 2
