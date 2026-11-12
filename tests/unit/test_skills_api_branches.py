"""自定义 Skill API 全分支回归：上传、查询、更新、删除、文件与迁移。"""

import io
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api.v1 import skills as sk


class _Manager:
    def __init__(self, result=(True, "ok", {"name": "s"})):
        self.result = result
        self.skills = [{"name": "s"}]
        self.skill = {"name": "s", "content": "c"}
        self.migrated = 3
        self.calls = []

    def upload_skill(self, **kwargs):
        self.calls.append(("upload", kwargs))
        return self.result

    def list_skills(self, **kwargs):
        self.calls.append(("list", kwargs))
        return self.skills

    def get_skill(self, name, owner_user_id=None):
        return self.skill if name == "s" else None

    def update_skill(self, **kwargs):
        self.calls.append(("update", kwargs))
        return self.result

    def delete_skill(self, name, owner_user_id=None):
        self.calls.append(("delete", name, owner_user_id))
        return self.result

    def migrate_legacy_skills(self, owner_user_id):
        self.calls.append(("migrate", owner_user_id))
        return self.migrated


class _DB:
    def __init__(self, administrator_id=1):
        self.administrator_id = administrator_id

    async def execute(self, statement):
        return SimpleNamespace(scalar_one_or_none=lambda: self.administrator_id)


@pytest.fixture
def manager(monkeypatch):
    fake = _Manager()
    monkeypatch.setattr(sk, "get_skill_manager", lambda: fake)
    return fake


@pytest.fixture
def broadcast(monkeypatch):
    calls = []
    import app.api.v1.agent_host as host

    monkeypatch.setattr(host, "broadcast_user_skill_update", lambda uid: calls.append(uid))
    return calls


@pytest.mark.asyncio
async def test_upload_skill_success(manager, broadcast):
    request = sk.SkillUploadRequest(name="s", category="tool", content="c")
    result = await sk.upload_skill(request, token={"sub": 7})
    assert result == {"name": "s"}
    assert manager.calls[0][1]["owner_user_id"] == "7"
    assert broadcast == ["7"]


@pytest.mark.asyncio
async def test_upload_skill_failure(manager, broadcast):
    manager.result = (False, "bad name", None)
    with pytest.raises(HTTPException) as exc:
        await sk.upload_skill(
            sk.SkillUploadRequest(name="s", category="tool", content="c"),
            token={"sub": 7},
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "bad name"
    assert broadcast == []


@pytest.mark.asyncio
async def test_list_skills_scopes_by_owner(manager):
    payload = await sk.list_skills(category="tool", author="a", token={"sub": 9})
    assert payload == [{"name": "s"}]
    assert manager.calls[0][1] == {
        "category": "tool",
        "author": "a",
        "owner_user_id": "9",
    }


@pytest.mark.asyncio
async def test_get_categories_payload():
    payload = await sk.get_categories()
    assert payload["categories"] == sk.VALID_CATEGORIES
    assert set(payload["descriptions"]) == set(sk.VALID_CATEGORIES)


@pytest.mark.asyncio
async def test_get_skill_found_and_missing(manager):
    assert (await sk.get_skill("s", token={"sub": 1}))["content"] == "c"
    with pytest.raises(HTTPException) as exc:
        await sk.get_skill("missing", token={"sub": 1})
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_skill_success(manager, broadcast):
    result = await sk.update_skill(
        "s", sk.SkillUpdateRequest(content="new"), token={"sub": 2}
    )
    assert result == {"name": "s"}
    assert broadcast == ["2"]


@pytest.mark.asyncio
async def test_update_skill_not_found(manager, broadcast):
    manager.result = (False, "Skill 's' 不存在", None)
    with pytest.raises(HTTPException) as exc:
        await sk.update_skill("s", sk.SkillUpdateRequest(content="c"), token={"sub": 2})
    assert exc.value.status_code == 404
    assert broadcast == []


@pytest.mark.asyncio
async def test_update_skill_other_error(manager):
    manager.result = (False, "invalid content", None)
    with pytest.raises(HTTPException) as exc:
        await sk.update_skill("s", sk.SkillUpdateRequest(content="c"), token={"sub": 2})
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_skill_success(manager, broadcast):
    manager.result = (True, "已删除")
    payload = await sk.delete_skill("s", token={"sub": 3})
    assert payload == {"message": "已删除"}
    assert broadcast == ["3"]


@pytest.mark.asyncio
async def test_delete_skill_not_found_and_error(manager):
    manager.result = (False, "不存在")
    with pytest.raises(HTTPException) as exc:
        await sk.delete_skill("s", token={"sub": 3})
    assert exc.value.status_code == 404

    manager.result = (False, "权限不足")
    with pytest.raises(HTTPException) as exc:
        await sk.delete_skill("s", token={"sub": 3})
    assert exc.value.status_code == 400


def _upload(name="a.md", payload=b"# title"):
    return UploadFile(file=io.BytesIO(payload), filename=name)


@pytest.mark.asyncio
async def test_upload_file_rejects_non_markdown(manager):
    with pytest.raises(HTTPException) as exc:
        await sk.upload_skill_file(
            file=_upload("a.txt"), name="s", category="tool", token={"sub": 1}
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_file_rejects_bad_encoding(manager):
    with pytest.raises(HTTPException) as exc:
        await sk.upload_skill_file(
            file=_upload(payload=b"\xff\xfe\xfa"), name="s", category="tool", token={"sub": 1}
        )
    assert exc.value.status_code == 400
    assert "UTF-8" in exc.value.detail


@pytest.mark.asyncio
async def test_upload_file_success(manager, broadcast):
    result = await sk.upload_skill_file(
        file=_upload(),
        name="s",
        category="tool",
        description="d",
        token={"sub": 4},
    )
    assert result == {"name": "s"}
    assert manager.calls[0][1]["content"] == "# title"
    assert broadcast == ["4"]


@pytest.mark.asyncio
async def test_upload_file_manager_failure(manager, broadcast):
    manager.result = (False, "bad", None)
    with pytest.raises(HTTPException) as exc:
        await sk.upload_skill_file(
            file=_upload(), name="s", category="tool", token={"sub": 4}
        )
    assert exc.value.status_code == 400
    assert broadcast == []


@pytest.mark.asyncio
async def test_migrate_legacy_requires_admin():
    with pytest.raises(HTTPException) as exc:
        await sk.migrate_legacy_skills(token={"permission_level": "normal"}, db=_DB())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_migrate_legacy_without_admin_records(manager):
    with pytest.raises(HTTPException) as exc:
        await sk.migrate_legacy_skills(
            token={"permission_level": "admin"}, db=_DB(administrator_id=None)
        )
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_migrate_legacy_success(manager):
    payload = await sk.migrate_legacy_skills(
        token={"permission_level": "superadmin"}, db=_DB(administrator_id=42)
    )
    assert payload == {"migrated": 3, "owner_user_id": "42"}
    assert manager.calls[-1] == ("migrate", "42")


@pytest.mark.asyncio
async def test_reload_rejects_non_admin():
    with pytest.raises(HTTPException) as exc:
        await sk.reload_prompts(token={"permission_level": "normal"})
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_reload_success(monkeypatch):
    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    monkeypatch.setattr("subprocess.run", lambda *a, **k: _Result())
    payload = await sk.reload_prompts(token={"permission_level": "admin"})
    assert payload["output"] == "ok"


@pytest.mark.asyncio
async def test_reload_extract_failure(monkeypatch):
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "secret"

    monkeypatch.setattr("subprocess.run", lambda *a, **k: _Result())
    with pytest.raises(HTTPException) as exc:
        await sk.reload_prompts(token={"permission_level": "admin"})
    assert exc.value.status_code == 500
    assert "secret" not in exc.value.detail


@pytest.mark.asyncio
async def test_reload_timeout(monkeypatch):
    import subprocess

    def _run(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="x", timeout=60)

    monkeypatch.setattr(subprocess, "run", _run)
    with pytest.raises(HTTPException) as exc:
        await sk.reload_prompts(token={"permission_level": "admin"})
    assert exc.value.status_code == 500
    assert "超时" in exc.value.detail


@pytest.mark.asyncio
async def test_reload_unexpected_error(monkeypatch):
    import asyncio

    async def _boom(func, *args, **kwargs):
        raise RuntimeError("thread exploded")

    monkeypatch.setattr(asyncio, "to_thread", _boom)
    with pytest.raises(HTTPException) as exc:
        await sk.reload_prompts(token={"permission_level": "admin"})
    assert exc.value.status_code == 500
    assert "更新提示词文档失败" in exc.value.detail
