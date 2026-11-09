"""Client delivery compatibility for current and legacy project layouts."""

import pytest

from app.api.v1.ai_agent import helpers
from app.api.v1.ai_agent.generate_endpoints import (
    delete_project_file,
    get_project_files,
    read_project_file,
)
from fastapi import HTTPException


@pytest.mark.parametrize("project", ["42/desktop-session", "orchestrator/project_42", "project_42"])
def test_project_layouts_are_readable(tmp_path, monkeypatch, project):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    directory = tmp_path / project
    directory.mkdir(parents=True)
    assert helpers._validate_project_path(project, "42") == directory


@pytest.mark.asyncio
async def test_new_project_file_list_and_preview(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    source = tmp_path / "42" / "desktop-session" / "src" / "main.dart"
    source.parent.mkdir(parents=True)
    source.write_text("void main() {}", encoding="utf-8")
    listing = await get_project_files("42/desktop-session", token={"sub": "42"})
    assert listing["files"][0]["path"] == "src/main.dart"
    preview = await read_project_file("42/desktop-session", "src/main.dart", token={"sub": "42"})
    assert preview["content"] == "void main() {}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "relative",
    ["../desktop-session-evil/secret.txt", "../outside/secret.txt"],
)
async def test_read_project_file_rejects_prefix_sibling_escape(tmp_path, monkeypatch, relative):
    """前缀兄弟目录（desktop-session-evil）不能被当成项目内部文件。"""
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    (tmp_path / "42" / "desktop-session").mkdir(parents=True)
    sibling = tmp_path / "42" / "desktop-session-evil"
    sibling.mkdir(parents=True)
    (sibling / "secret.txt").write_text("secret", encoding="utf-8")
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "secret.txt").write_text("secret", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        await read_project_file(
            "42/desktop-session", relative, token={"sub": "42"}
        )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_read_project_file_treats_backslash_as_literal_name(tmp_path, monkeypatch):
    """Linux 上反斜杠是普通字符，越界样式的字面名只能命中 404，不能读到外部文件。"""
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    (tmp_path / "42" / "desktop-session").mkdir(parents=True)
    with pytest.raises(HTTPException) as exc:
        await read_project_file(
            "42/desktop-session",
            "..\\desktop-session-evil\\secret.txt",
            token={"sub": "42"},
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_file_rejects_prefix_sibling_escape(tmp_path, monkeypatch):
    """删除端点同样不能越过项目根到前缀兄弟目录。"""
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    (tmp_path / "42" / "desktop-session").mkdir(parents=True)
    sibling = tmp_path / "42" / "desktop-session-evil"
    sibling.mkdir(parents=True)
    target = sibling / "secret.txt"
    target.write_text("secret", encoding="utf-8")

    with pytest.raises(HTTPException) as exc:
        await delete_project_file(
            "42/desktop-session", "../desktop-session-evil/secret.txt", token={"sub": "42"}
        )
    assert exc.value.status_code == 403
    assert target.exists(), "越界请求不得删除项目外部文件"
