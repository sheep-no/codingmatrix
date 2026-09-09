"""Client delivery compatibility for current and legacy project layouts."""

import pytest

from app.api.v1.ai_agent import helpers
from app.api.v1.ai_agent.generate_endpoints import get_project_files, read_project_file


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
