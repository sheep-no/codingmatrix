"""v2 用户管理不得让管理员绕过超级管理员门禁。

仅校验 is_admin 时，管理员可以创建 superadmin 账号、把任意账号提升为
superadmin，或删除/重置超管账号，从而拿到平台全部高危权限。
"""

import pytest
from fastapi import HTTPException

from app.api.v2 import user_manage
from app.schema.manageUser import UserCreateRequest, UserUpdateRequest


class _Permission:
    def __init__(self, level):
        self.permission_level = level


class _User:
    def __init__(self, uid, level):
        self.id = uid
        self.username = f"user{uid}"
        self.email = f"user{uid}@example.com"
        self.permission = _Permission(level) if level else None


class _Result:
    def __init__(self, user):
        self._user = user

    def scalar(self):
        return self._user


class _FakeDb:
    """提供目标用户，并记录是否发生了写操作。"""

    def __init__(self, user):
        self.user = user
        self.writes = []

    async def execute(self, statement):
        self.writes.append(statement)
        return _Result(self.user)

    async def commit(self):
        return None

    async def refresh(self, instance):
        return None

    async def delete(self, instance):
        self.writes.append(instance)

    def add(self, instance):
        self.writes.append(instance)

    async def flush(self):
        return None


class _ExplodingDb:
    """任何数据库访问都视为权限校验漏放行。"""

    def __init__(self):
        self.touched = False

    async def execute(self, statement):
        self.touched = True
        raise AssertionError("权限校验未拦截，已访问数据库")


def test_scope_guard_blocks_admin_for_superadmin_target():
    with pytest.raises(HTTPException) as error:
        user_manage._ensure_superadmin_scope("admin", "superadmin")

    assert error.value.status_code == 403


@pytest.mark.parametrize("actor,target", [
    ("superadmin", "superadmin"),
    ("admin", "admin"),
    ("admin", "normal"),
])
def test_scope_guard_allows_other_combinations(actor, target):
    user_manage._ensure_superadmin_scope(actor, target)


@pytest.mark.asyncio
async def test_admin_cannot_create_superadmin():
    db = _ExplodingDb()
    body = UserCreateRequest(
        username="evil", email="evil@example.com",
        password="secret123", permission_level="superadmin",
    )

    with pytest.raises(HTTPException) as error:
        await user_manage.create_user(
            body=body, db=db, token={"sub": "1", "permission_level": "admin"}
        )

    assert error.value.status_code == 403
    assert db.touched is False


@pytest.mark.asyncio
async def test_superadmin_still_can_create_superadmin():
    db = _ExplodingDb()
    body = UserCreateRequest(
        username="peer", email="peer@example.com",
        password="Secret123!", permission_level="superadmin",
    )

    # 越过权限门禁后才会访问数据库，说明超管未被误伤
    with pytest.raises(AssertionError):
        await user_manage.create_user(
            body=body, db=db, token={"sub": "1", "permission_level": "superadmin"}
        )

    assert db.touched is True


@pytest.mark.asyncio
async def test_admin_cannot_promote_user_to_superadmin():
    db = _FakeDb(_User(7, "normal"))
    body = UserUpdateRequest(permission_level="superadmin")

    with pytest.raises(HTTPException) as error:
        await user_manage.update_user(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "admin"},
        )

    assert error.value.status_code == 403
    assert len(db.writes) == 1  # 仅发生读取，无写入


@pytest.mark.asyncio
async def test_admin_cannot_modify_existing_superadmin():
    db = _FakeDb(_User(7, "superadmin"))
    body = UserUpdateRequest(username="renamed")

    with pytest.raises(HTTPException) as error:
        await user_manage.update_user(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "admin"},
        )

    assert error.value.status_code == 403
    assert len(db.writes) == 1


@pytest.mark.asyncio
async def test_admin_cannot_delete_superadmin():
    db = _FakeDb(_User(7, "superadmin"))

    with pytest.raises(HTTPException) as error:
        await user_manage.delete_user(
            user_id=7, db=db, token={"sub": "1", "permission_level": "admin"}
        )

    assert error.value.status_code == 403
    assert len(db.writes) == 1


@pytest.mark.asyncio
async def test_admin_cannot_reset_superadmin_password():
    db = _FakeDb(_User(7, "superadmin"))
    body = type("Body", (), {"new_password": "hijacked123"})()

    with pytest.raises(HTTPException) as error:
        await user_manage.reset_password(
            user_id=7, body=body, db=db,
            token={"sub": "1", "permission_level": "admin"},
        )

    assert error.value.status_code == 403
    assert len(db.writes) == 1
