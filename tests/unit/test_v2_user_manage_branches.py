from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.v2 import user_manage
from app.schema.manageUser import UserCreateRequest, UserUpdateRequest


class _Result:
    def __init__(self, *, scalar=None, rows=()):
        self._scalar = scalar
        self._rows = list(rows)

    def scalar(self):
        return self._scalar

    def fetchall(self):
        return self._rows


class _DB:
    def __init__(self, results=()):
        self._results = list(results)
        self.statements = []
        self.commits = 0
        self.added = []
        self.deleted = []
        self.flushes = 0
        self.refreshed = []

    async def execute(self, statement):
        self.statements.append(statement)
        if self._results:
            return self._results.pop(0)
        return _Result()

    async def commit(self):
        self.commits += 1

    async def flush(self):
        self.flushes += 1
        for item in self.added:
            if getattr(item, "id", None) is None and hasattr(item, "email"):
                item.id = 99

    async def refresh(self, instance):
        self.refreshed.append(instance)
        if getattr(instance, "created_at", "missing") is None:
            instance.created_at = "2026-01-01"

    def add(self, instance):
        self.added.append(instance)

    async def delete(self, instance):
        self.deleted.append(instance)


def _user(uid=7, level="normal", created="2026-01-01"):
    permission = SimpleNamespace(permission_level=level) if level else None
    return SimpleNamespace(
        id=uid,
        username=f"user{uid}",
        email=f"user{uid}@example.com",
        created_at=created,
        permission=permission,
    )


@pytest.mark.asyncio
async def test_get_users_requires_admin():
    with pytest.raises(HTTPException) as exc:
        await user_manage.get_users(db=_DB(), token={"sub": "1", "permission_level": "normal"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_get_users_serialises_rows_with_filters_and_sorting():
    user_with_perm = _user(1, "admin")
    user_without_perm = _user(2, None)
    db = _DB([
        _Result(scalar=2),
        _Result(rows=[(user_with_perm, user_with_perm.permission), (user_without_perm, None)]),
    ])

    payload = await user_manage.get_users(
        page=2,
        page_size=5,
        keyword="user",
        permission_level="admin",
        sort_by="username",
        sort_order="asc",
        db=db,
        token={"sub": "1", "permission_level": "superadmin"},
    )

    assert payload["total"] == 2
    assert payload["users"][0]["permission_level"] == "admin"
    assert payload["users"][1]["permission_level"] == ""
    assert payload["page"] == 2

    default_db = _DB([_Result(scalar=0), _Result(rows=[])])
    default_payload = await user_manage.get_users(
        page=1,
        page_size=20,
        keyword=None,
        permission_level=None,
        sort_by="created_at",
        sort_order="desc",
        db=default_db,
        token={"sub": "1", "permission_level": "admin"},
    )
    assert default_payload["total"] == 0
    assert default_payload["users"] == []


@pytest.mark.asyncio
async def test_create_user_rejects_weak_password_and_duplicate_email():
    body = SimpleNamespace(
        username="newbie", email="new@example.com", password="123", permission_level="normal"
    )
    with pytest.raises(HTTPException) as exc:
        await user_manage.create_user(
            body=body, db=_DB(), token={"sub": "1", "permission_level": "admin"}
        )
    assert exc.value.status_code == 400

    body = UserCreateRequest(
        username="newbie", email="new@example.com",
        password="Secret123!", permission_level="normal",
    )
    db = _DB([_Result(scalar=_user())])
    with pytest.raises(HTTPException) as exc:
        await user_manage.create_user(
            body=body, db=db, token={"sub": "1", "permission_level": "admin"}
        )
    assert exc.value.status_code == 400
    assert "邮箱已存在" in exc.value.detail


@pytest.mark.asyncio
async def test_create_user_requires_admin():
    body = UserCreateRequest(
        username="newbie", email="new@example.com",
        password="Secret123", permission_level="normal",
    )
    with pytest.raises(HTTPException) as exc:
        await user_manage.create_user(
            body=body, db=_DB(), token={"sub": "1", "permission_level": "normal"}
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_create_user_persists_user_and_permission():
    body = UserCreateRequest(
        username="newbie", email="new@example.com",
        password="Secret123!", permission_level="normal",
    )
    db = _DB([_Result(scalar=None)])

    payload = await user_manage.create_user(
        body=body, db=db, token={"sub": "1", "permission_level": "admin"}
    )

    assert payload["id"] == 99
    assert payload["permission_level"] == "normal"
    assert db.commits == 1
    assert len(db.added) == 2


@pytest.mark.asyncio
async def test_update_user_requires_admin_and_blocks_self():
    with pytest.raises(HTTPException) as exc:
        await user_manage.update_user(
            user_id=7, body=UserUpdateRequest(), db=_DB(),
            token={"sub": "1", "permission_level": "normal"},
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await user_manage.update_user(
            user_id=1, body=UserUpdateRequest(), db=_DB(),
            token={"sub": "1", "permission_level": "admin"},
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_user_missing_target_returns_404():
    db = _DB([_Result(scalar=None)])
    with pytest.raises(HTTPException) as exc:
        await user_manage.update_user(
            user_id=7, body=UserUpdateRequest(), db=db,
            token={"sub": "1", "permission_level": "admin"},
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_user_rejects_duplicate_email():
    user = _user()
    db = _DB([_Result(scalar=user), _Result(scalar=_user(8))])
    body = UserUpdateRequest(email="taken@example.com")

    with pytest.raises(HTTPException) as exc:
        await user_manage.update_user(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "superadmin"},
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_update_user_creates_missing_permission_and_invalidates_cache():
    user = _user(level=None)
    db = _DB([_Result(scalar=user), _Result(scalar=None)])
    body = UserUpdateRequest(username="renamed", email="new@example.com", permission_level="admin")

    with patch.object(user_manage, "log_permission_change", AsyncMock()) as log_change, \
            patch.object(user_manage, "invalidate_user_cache", AsyncMock()) as invalidate_user, \
            patch.object(user_manage, "invalidate_cache_by_prefix", AsyncMock()) as invalidate_prefix:
        payload = await user_manage.update_user(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "superadmin"},
        )

    assert db.flushes == 1
    assert log_change.await_count == 1
    invalidate_user.assert_awaited_once_with(7)
    invalidate_prefix.assert_awaited_once_with("profile")
    assert payload["permission_level"] == "normal"


@pytest.mark.asyncio
async def test_update_user_swallows_cache_prefix_failure():
    user = _user(level="admin")
    db = _DB([_Result(scalar=user)])
    body = UserUpdateRequest(username="renamed")

    with patch.object(user_manage, "invalidate_cache_by_prefix", AsyncMock(side_effect=RuntimeError("boom"))), \
            patch.object(user_manage.logger, "warning") as warning:
        payload = await user_manage.update_user(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "admin"},
        )

    assert payload["username"] == "user7"
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_update_user_without_permission_skips_permission_refresh():
    user = _user(level=None)
    user.permission = None
    db = _DB([_Result(scalar=user)])
    body = UserUpdateRequest(username="renamed")

    with patch.object(user_manage, "invalidate_cache_by_prefix", AsyncMock()):
        await user_manage.update_user(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "admin"},
        )

    # 无 Permission 记录时只 refresh 用户本体，不再 refresh 权限对象
    assert db.refreshed == [user]


@pytest.mark.asyncio
async def test_delete_user_guard_and_success_purges_owned_data():
    with pytest.raises(HTTPException) as exc:
        await user_manage.delete_user(
            user_id=7, db=_DB(), token={"sub": "1", "permission_level": "normal"}
        )
    assert exc.value.status_code == 403

    with pytest.raises(HTTPException) as exc:
        await user_manage.delete_user(
            user_id=1, db=_DB(), token={"sub": "1", "permission_level": "admin"}
        )
    assert exc.value.status_code == 400

    user = _user()
    db = _DB([_Result(scalar=user)])
    with patch.object(user_manage, "invalidate_user_cache", AsyncMock()), \
            patch.object(user_manage, "log_sensitive_operation", AsyncMock()), \
            patch.object(user_manage, "invalidate_cache_by_prefix", AsyncMock()):
        payload = await user_manage.delete_user(
            user_id=7, db=db, token={"sub": "1", "permission_level": "admin"}
        )

    assert payload == {"detail": "用户已删除"}
    assert user in db.deleted
    assert db.commits == 1
    # Permission 删除 + 14 张业务表清理
    assert len(db.statements) >= 15


@pytest.mark.asyncio
async def test_delete_user_swallows_cache_prefix_failure():
    user = _user()
    db = _DB([_Result(scalar=user)])
    with patch.object(user_manage, "invalidate_user_cache", AsyncMock()), \
            patch.object(user_manage, "log_sensitive_operation", AsyncMock()), \
            patch.object(user_manage, "invalidate_cache_by_prefix", AsyncMock(side_effect=RuntimeError("x"))), \
            patch.object(user_manage.logger, "warning") as warning:
        await user_manage.delete_user(
            user_id=7, db=db, token={"sub": "1", "permission_level": "admin"}
        )
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_reset_password_guards_target_and_password_strength():
    body = SimpleNamespace(new_password="123")
    with pytest.raises(HTTPException) as exc:
        await user_manage.reset_password(
            user_id=7, body=body, db=_DB(),
            token={"sub": "1", "permission_level": "normal"},
        )
    assert exc.value.status_code == 403

    user = _user()
    db = _DB([_Result(scalar=user)])
    with pytest.raises(HTTPException) as exc:
        await user_manage.reset_password(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "admin"},
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_reset_password_success_swallows_prefix_error():
    user = _user()
    db = _DB([_Result(scalar=user)])
    body = SimpleNamespace(new_password="Secret123!")

    with patch.object(user_manage, "invalidate_user_cache", AsyncMock()), \
            patch.object(user_manage, "log_sensitive_operation", AsyncMock()), \
            patch.object(user_manage, "invalidate_cache_by_prefix", AsyncMock(side_effect=RuntimeError("x"))), \
            patch.object(user_manage.logger, "warning") as warning:
        payload = await user_manage.reset_password(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "admin"},
        )

    assert "密码已重置" in payload["detail"]
    assert db.commits == 1
    warning.assert_called_once()


@pytest.mark.asyncio
async def test_purge_user_owned_data_issues_all_deletes():
    db = _DB()
    await user_manage._purge_user_owned_data(db, 7)
    assert len(db.statements) == 15
