"""auth.py 注册并发冲突与内部错误泄露加固（AUT4/AUT5）。

AUT4: check_email_exists 与 flush 之间存在 TOCTOU，并发注册同一邮箱时唯一约束
触发 IntegrityError 逃逸为 500。修复后回滚并返回 400「邮箱已存在」。
AUT5: get_conversations 异常分支曾 `detail=str(e)` 泄露内部错误。
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError, SQLAlchemyError


class _FakeDB:
    def __init__(self, flush_error=None, execute_error=None):
        self._flush_error = flush_error
        self._execute_error = execute_error
        self.rollbacks = 0

    def add(self, obj):
        pass

    async def flush(self):
        if self._flush_error:
            raise self._flush_error

    async def rollback(self):
        self.rollbacks += 1

    async def execute(self, stmt):
        if self._execute_error:
            raise self._execute_error
        raise AssertionError("unexpected execute")


@pytest.mark.asyncio
async def test_register_concurrent_email_conflict_returns_400():
    from app.api.v1 import auth
    from app.schema.user import UserRegister

    db = _FakeDB(flush_error=IntegrityError("INSERT", {}, Exception("duplicate")))
    body = UserRegister(email="dup@example.com", password="Test1234!", username="dup")

    with patch.object(auth, "check_email_exists", AsyncMock(return_value=False)):
        with pytest.raises(HTTPException) as exc:
            await auth.register(body=body, db=db, csrf="ok")

    assert exc.value.status_code == 400
    assert exc.value.detail == "邮箱已存在"
    assert db.rollbacks == 1


@pytest.mark.asyncio
async def test_get_conversations_error_is_generic():
    from app.api.v1 import auth

    db = _FakeDB(execute_error=SQLAlchemyError("secret dsn leak"))

    with pytest.raises(HTTPException) as exc:
        await auth.get_conversations.__wrapped__(
            limit=1, offset=0, db=db, token={"sub": "7"}
        )

    assert exc.value.status_code == 500
    assert "secret dsn leak" not in str(exc.value.detail)
    assert exc.value.detail == "查询会话列表失败"
