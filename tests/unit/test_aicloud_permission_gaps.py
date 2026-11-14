"""aicloud 权限检查的边界补测。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.utils import aicloud
from app.utils.aicloud import permission as permission_module


class _Result:
    def __init__(self, user):
        self._user = user

    def scalar_one_or_none(self):
        return self._user


def _db_returning(user):
    db = SimpleNamespace(execute=AsyncMock(return_value=_Result(user)))
    return db


async def test_missing_user_returns_normal():
    db = _db_returning(None)

    assert await permission_module.get_user_permission_level(1, db) == "normal"


async def test_user_without_permission_row_returns_normal():
    db = _db_returning(SimpleNamespace(permission=None))

    assert await permission_module.get_user_permission_level(1, db) == "normal"


async def test_user_permission_without_level_returns_normal():
    db = _db_returning(SimpleNamespace(permission=SimpleNamespace(permission_level=None)))

    assert await permission_module.get_user_permission_level(1, db) == "normal"


async def test_user_permission_returns_level():
    db = _db_returning(SimpleNamespace(permission=SimpleNamespace(permission_level="superadmin")))

    assert await permission_module.get_user_permission_level(1, db) == "superadmin"


async def test_check_aicloud_permission_allows_admin():
    db = _db_returning(SimpleNamespace(permission=SimpleNamespace(permission_level="admin")))

    assert await permission_module.check_aicloud_permission(1, db) is True


async def test_check_aicloud_permission_rejects_normal_user():
    db = _db_returning(SimpleNamespace(permission=SimpleNamespace(permission_level="normal")))

    with pytest.raises(HTTPException) as excinfo:
        await permission_module.check_aicloud_permission(1, db)

    assert excinfo.value.status_code == 403
    assert "admin permission" in excinfo.value.detail


async def test_require_permission_rejects_unauthenticated():
    dependency = permission_module.require_aicloud_permission()

    with pytest.raises(HTTPException) as excinfo:
        await dependency(user_id=None, db=None)

    assert excinfo.value.status_code == 401


async def test_require_permission_returns_user_when_allowed(monkeypatch):
    checker = AsyncMock(return_value=True)
    monkeypatch.setattr(permission_module, "check_aicloud_permission", checker)
    db = object()

    assert await permission_module.require_aicloud_permission()(user_id=5, db=db) == 5
    checker.assert_awaited_once_with(5, db)


async def test_require_permission_propagates_http_error(monkeypatch):
    checker = AsyncMock(side_effect=HTTPException(status_code=403, detail="nope"))
    monkeypatch.setattr(permission_module, "check_aicloud_permission", checker)

    with pytest.raises(HTTPException) as excinfo:
        await permission_module.require_aicloud_permission()(user_id=5, db=object())

    assert excinfo.value.status_code == 403
