"""Branch coverage for app/api/v1/ai_agent/generate_endpoints.py."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.ai_agent import generate_endpoints as endpoints
from app.schema.codeRequest import GenerateRequest


class _Request:
    def __init__(self, disconnected=False, exc=None):
        self._disconnected = disconnected
        self._exc = exc
        self.calls = 0

    async def is_disconnected(self):
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        return self._disconnected


def _result(value=None, *, rowcount=0):
    return SimpleNamespace(
        scalar=lambda: value,
        scalar_one_or_none=lambda: value,
        rowcount=rowcount,
    )


def _db(*results):
    remaining = list(results)

    async def _execute(*_a, **_k):
        return remaining.pop(0) if remaining else _result(None)

    return SimpleNamespace(
        execute=AsyncMock(side_effect=_execute),
        add=MagicMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
        rollback=AsyncMock(),
    )


GENERATED = {
    "validation": {"runnable": True},
    "total_files_created": 3,
    "steps": [{"name": "gen"}],
    "success": True,
}


def _patch_generate(monkeypatch, result=None):
    monkeypatch.setattr(endpoints, "_build_agent_config", lambda req: object())
    monkeypatch.setattr(
        endpoints, "ProjectGeneratorAgent",
        lambda config=None: SimpleNamespace(
            generate_project=AsyncMock(return_value=dict(result or GENERATED))
        ),
    )
    monkeypatch.setattr(endpoints, "run_workflow", AsyncMock(return_value="state"))
    monkeypatch.setattr(
        endpoints, "get_legacy_result", lambda state: dict(result or GENERATED)
    )


def _generate_request(**overrides):
    values = {"requirement": "build a tool", "session_id": "project_1"}
    values.update(overrides)
    return GenerateRequest(**values)


@pytest.mark.asyncio
async def test_generate_success(monkeypatch):
    _patch_generate(monkeypatch)
    response = await endpoints.generate_project(
        _generate_request(), {"sub": "42"}, _Request(), object()
    )
    assert response.success is True
    assert response.total_files_created == 3


@pytest.mark.asyncio
async def test_generate_disconnect_sets_cancel_event(monkeypatch):
    _patch_generate(monkeypatch)

    async def _run(*_a, **_k):
        # Let the disconnect watcher observe the closed client.
        await asyncio.sleep(0.01)
        return "state"

    monkeypatch.setattr(endpoints, "run_workflow", _run)
    response = await endpoints.generate_project(
        _generate_request(), {"sub": "42"}, _Request(disconnected=True), object()
    )
    assert response.success is True


@pytest.mark.asyncio
async def test_generate_watcher_swallows_errors(monkeypatch):
    _patch_generate(monkeypatch)

    async def _run(*_a, **_k):
        await asyncio.sleep(0.01)
        return "state"

    monkeypatch.setattr(endpoints, "run_workflow", _run)
    response = await endpoints.generate_project(
        _generate_request(), {"sub": "42"},
        _Request(exc=RuntimeError("socket gone")), object(),
    )
    assert response.success is True


@pytest.mark.asyncio
async def test_generate_workflow_handler_and_watcher_loop(monkeypatch):
    agent = SimpleNamespace(
        generate_project=AsyncMock(return_value=dict(GENERATED))
    )
    monkeypatch.setattr(endpoints, "_build_agent_config", lambda req: object())
    monkeypatch.setattr(endpoints, "ProjectGeneratorAgent", lambda config=None: agent)

    captured = {}

    def _build(_name, _endpoint, handler):
        captured["handler"] = handler
        return SimpleNamespace(handler=handler)

    monkeypatch.setattr(endpoints, "build_legacy_workflow", _build)

    async def _run_workflow(workflow, **_kwargs):
        # Exercise the legacy handler and the empty progress callback.
        await workflow.handler(None)
        await asyncio.sleep(0)
        return "state"

    monkeypatch.setattr(endpoints, "run_workflow", _run_workflow)
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: dict(GENERATED))

    class _Flapping:
        def __init__(self):
            self.calls = 0

        async def is_disconnected(self):
            self.calls += 1
            return self.calls > 1

    real_sleep = asyncio.sleep

    async def _fast_sleep(delay, *a, **k):
        if delay == 1.0:
            return None
        return await real_sleep(delay)

    monkeypatch.setattr(endpoints.asyncio, "sleep", _fast_sleep)
    response = await endpoints.generate_project(
        _generate_request(), {"sub": "42"}, _Flapping(), object()
    )
    assert response.success is True
    agent.generate_project.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_validation_failure_returns_400(monkeypatch):
    failing = dict(GENERATED, validation={"runnable": False})
    _patch_generate(monkeypatch, result=failing)
    with pytest.raises(HTTPException) as error:
        await endpoints.generate_project(
            _generate_request(), {"sub": "42"}, _Request(), object()
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_generate_unexpected_failure_returns_500(monkeypatch):
    _patch_generate(monkeypatch)
    monkeypatch.setattr(
        endpoints, "run_workflow", AsyncMock(side_effect=RuntimeError("boom"))
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.generate_project(
            _generate_request(), {"sub": "42"}, _Request(), object()
        )
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_download_success_and_failure(monkeypatch, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: project)
    monkeypatch.setattr(endpoints, "tempfile", SimpleNamespace(mkdtemp=lambda: str(tmp_path)))

    def _zip_ok(source, target):
        target.write_bytes(b"zip")
        return True

    monkeypatch.setattr(endpoints, "_create_zip_archive_safe", _zip_ok)
    response = await endpoints.download_project("1/proj", {"sub": "1"})
    assert response.filename == "proj.zip"

    def _zip_fail(source, target):
        return False

    monkeypatch.setattr(endpoints, "_create_zip_archive_safe", _zip_fail)
    with pytest.raises(HTTPException) as error:
        await endpoints.download_project("1/proj", {"sub": "1"})
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_get_project_files_sorts_priority(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: project)

    async def _files(_dir):
        for path in ("zeta.py", "README.md", "package.json"):
            yield {"path": path, "name": path}

    monkeypatch.setattr(endpoints, "_collect_files", _files)
    result = await endpoints.get_project_files("1/proj", {"sub": "1"})
    assert [f["path"] for f in result["files"]] == [
        "README.md", "package.json", "zeta.py",
    ]
    assert result["total"] == 3


@pytest.mark.asyncio
async def test_read_project_file_paths(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("print(1)", encoding="utf-8")
    (project / "bin.dat").write_bytes(b"\xff\xfe\x00")
    (project / "sub").mkdir()
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: project)

    ok = await endpoints.read_project_file("1/proj", "a.py", {"sub": "1"})
    assert ok["mime_type"] == "text/x-python"

    binary = await endpoints.read_project_file("1/proj", "bin.dat", {"sub": "1"})
    assert binary["content"] == "[二进制文件，无法显示]"

    with pytest.raises(HTTPException) as error:
        await endpoints.read_project_file("1/proj", "../escape.py", {"sub": "1"})
    assert error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        await endpoints.read_project_file("1/proj", "missing.py", {"sub": "1"})
    assert error.value.status_code == 404

    with pytest.raises(HTTPException) as error:
        await endpoints.read_project_file("1/proj", "sub", {"sub": "1"})
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_read_project_file_read_error(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    target = project / "a.py"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: project)

    from pathlib import Path

    original = Path.read_text

    def _explode(self, *a, **k):
        if self == target.resolve() or self == target:
            raise OSError("read failed")
        return original(self, *a, **k)

    monkeypatch.setattr(Path, "read_text", _explode)
    with pytest.raises(HTTPException) as error:
        await endpoints.read_project_file("1/proj", "a.py", {"sub": "1"})
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_project_file_paths(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "a.py").write_text("x", encoding="utf-8")
    (project / "sub").mkdir()
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: project)

    result = await endpoints.delete_project_file("1/proj", "a.py", {"sub": "1"})
    assert result["status"] == "deleted"
    assert not (project / "a.py").exists()

    with pytest.raises(HTTPException) as error:
        await endpoints.delete_project_file("1/proj", "../x", {"sub": "1"})
    assert error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        await endpoints.delete_project_file("1/proj", "missing.py", {"sub": "1"})
    assert error.value.status_code == 404

    with pytest.raises(HTTPException) as error:
        await endpoints.delete_project_file("1/proj", "sub", {"sub": "1"})
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_delete_project_file_unlink_failure(tmp_path, monkeypatch):
    project = tmp_path / "proj"
    project.mkdir()
    target = project / "a.py"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: project)

    from pathlib import Path

    def _explode(self, *a, **k):
        raise OSError("denied")

    monkeypatch.setattr(Path, "unlink", _explode)
    with pytest.raises(HTTPException) as error:
        await endpoints.delete_project_file("1/proj", "a.py", {"sub": "1"})
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_import_files_guards_and_success(monkeypatch):
    with pytest.raises(HTTPException) as error:
        await endpoints.import_project_files(
            SimpleNamespace(files=[], project_name=None), {"sub": ""}
        )
    assert error.value.status_code == 401

    request = SimpleNamespace(
        files=[SimpleNamespace(path="a.py", content="x")], project_name="demo"
    )
    monkeypatch.setattr(
        endpoints, "materialize_imported_project",
        lambda user, files, project_name=None: {"project_path": "1/demo", "files": ["a.py"]},
    )
    assert await endpoints.import_project_files(request, {"sub": "1"}) == {
        "project_path": "1/demo", "files": ["a.py"],
    }

    def _bad(*_a, **_k):
        raise ValueError("too many")

    monkeypatch.setattr(endpoints, "materialize_imported_project", _bad)
    with pytest.raises(HTTPException) as error:
        await endpoints.import_project_files(request, {"sub": "1"})
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_save_project_guards_and_success(monkeypatch):
    monkeypatch.setattr(endpoints, "MAX_SAVED_PROJECTS_PER_USER", 2)
    with pytest.raises(HTTPException) as error:
        await endpoints.save_project(
            SimpleNamespace(project_data="{}", name="n"), {"sub": ""}, _db()
        )
    assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        await endpoints.save_project(
            SimpleNamespace(project_data="not json", name="n"), {"sub": "1"}, _db()
        )
    assert error.value.status_code == 400

    with pytest.raises(HTTPException) as error:
        await endpoints.save_project(
            SimpleNamespace(project_data="{}", name="n"), {"sub": "1"},
            _db(_result(2)),
        )
    assert error.value.status_code == 400

    db = _db(_result(0))

    async def _refresh(obj):
        obj.id = 7
        obj.created_at = datetime.now(timezone.utc)

    db.refresh = AsyncMock(side_effect=_refresh)
    response = await endpoints.save_project(
        SimpleNamespace(
            project_data="{}", name="n", description="d", project_path="1/p",
        ),
        {"sub": "1"}, db,
    )
    assert response.id == 7


@pytest.mark.asyncio
async def test_save_project_unexpected_error():
    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    db = SimpleNamespace(
        execute=_boom, add=MagicMock(), commit=AsyncMock(), refresh=AsyncMock(),
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.save_project(
            SimpleNamespace(project_data="{}", name="n"), {"sub": "1"}, db
        )
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_list_saved_projects_guards_and_success():
    with pytest.raises(HTTPException) as error:
        await endpoints.list_saved_projects({"sub": None}, _db(), 0, 50)
    assert error.value.status_code == 401

    row = SimpleNamespace(
        id=1, name="n", description=None, project_path=None,
        created_at=None, updated_at=None,
    )
    list_result = MagicMock()
    list_result.scalars.return_value.all.return_value = [row]
    result = await endpoints.list_saved_projects(
        {"sub": "1"}, _db(_result(1), list_result), 0, 50
    )
    assert result.total == 1
    assert result.projects[0]["id"] == 1

    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    with pytest.raises(HTTPException) as error:
        await endpoints.list_saved_projects(
            {"sub": "1"}, SimpleNamespace(execute=_boom), 0, 50
        )
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_load_saved_project_guards_and_paths():
    with pytest.raises(HTTPException) as error:
        await endpoints.load_saved_project(1, {"sub": None}, _db())
    assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        await endpoints.load_saved_project(1, {"sub": "1"}, _db(_result(None)))
    assert error.value.status_code == 404

    project = SimpleNamespace(
        id=1, name="n", description=None, project_path=None,
        project_data="{}", created_at=datetime.now(timezone.utc), updated_at=None,
    )
    loaded = await endpoints.load_saved_project(1, {"sub": "1"}, _db(_result(project)))
    assert loaded.id == 1

    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    with pytest.raises(HTTPException) as error:
        await endpoints.load_saved_project(
            1, {"sub": "1"}, SimpleNamespace(execute=_boom)
        )
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_delete_saved_project_guards_and_paths():
    with pytest.raises(HTTPException) as error:
        await endpoints.delete_saved_project(1, {"sub": None}, _db())
    assert error.value.status_code == 401

    with pytest.raises(HTTPException) as error:
        await endpoints.delete_saved_project(1, {"sub": "1"}, _db(_result(None, rowcount=0)))
    assert error.value.status_code == 404

    deleted = await endpoints.delete_saved_project(
        1, {"sub": "1"}, _db(_result(None, rowcount=1))
    )
    assert deleted == {"status": "deleted", "project_id": 1}

    async def _boom(*_a, **_k):
        raise RuntimeError("db down")

    with pytest.raises(HTTPException) as error:
        await endpoints.delete_saved_project(
            1, {"sub": "1"}, SimpleNamespace(execute=_boom, commit=AsyncMock())
        )
    assert error.value.status_code == 500
