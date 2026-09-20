"""PermissionService.create_permission_if_not_exists 并发竞态回归。

db_layer.md DB10：唯一约束已由 app/models/Permission.py 提供，
但服务层先查后插，并发时后到的一方会因 IntegrityError 冒泡成 500。
"""

import importlib

import pytest
from sqlalchemy.exc import IntegrityError

permission_service = importlib.import_module("app.db.permission_service")
PermissionService = permission_service.PermissionService


class _FakeResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _SequenceDb:
    """按调用顺序返回预设查询结果，并记录回滚。"""

    def __init__(self, results):
        self._results = list(results)
        self.rollbacks = 0

    async def execute(self, stmt):
        return _FakeResult(self._results.pop(0))

    async def rollback(self):
        self.rollbacks += 1


async def test_returns_existing_without_insert():
    existing = object()
    db = _SequenceDb([existing])
    service = PermissionService(db)

    assert await service.create_permission_if_not_exists(1, "normal") is existing
    assert db.rollbacks == 0


async def test_falls_back_to_existing_row_on_integrity_error(monkeypatch):
    existing = object()
    # 第一次查询为空，触发插入；插入冲突回滚后重查命中并发方写入的行
    db = _SequenceDb([None, existing])
    service = PermissionService(db)

    async def _conflict(user_id, level):
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(service, "create_permission", _conflict)

    assert await service.create_permission_if_not_exists(1, "normal") is existing
    assert db.rollbacks == 1


async def test_reraises_when_conflict_row_still_missing(monkeypatch):
    db = _SequenceDb([None, None])
    service = PermissionService(db)

    async def _conflict(user_id, level):
        raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

    monkeypatch.setattr(service, "create_permission", _conflict)

    with pytest.raises(IntegrityError):
        await service.create_permission_if_not_exists(1, "normal")
    assert db.rollbacks == 1
