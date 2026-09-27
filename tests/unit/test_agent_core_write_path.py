"""`agent_core.create_project_file` 写入路径约束回归（AC1）。

生成主工具 file_path 完全由 LLM 决定，历史上直接 `aiofiles.open` 可写任意
路径。新增 `_resolve_project_write_path` 将目标约束在本次 output_dir 或项目根
目录之下；越权路径在 mkdir/写入前即被拒绝。
"""
from pathlib import Path

import pytest

from app.utils.agent_core import _resolve_project_write_path, create_project_file


def test_resolve_accepts_path_under_projects_root():
    resolved = _resolve_project_write_path("./projects/demo/main.py")
    assert resolved == (Path.cwd() / "projects/demo/main.py").resolve()


def test_resolve_accepts_path_under_output_dir(tmp_path):
    resolved = _resolve_project_write_path(str(tmp_path / "app/main.py"), str(tmp_path))
    assert resolved == (tmp_path / "app/main.py").resolve()


@pytest.mark.parametrize("bad", ["../../etc/evil.py", "/etc/evil.py", str(Path.home() / "evil.py")])
def test_resolve_rejects_escape(bad):
    with pytest.raises(PermissionError):
        _resolve_project_write_path(bad)


async def test_create_project_file_writes_under_output_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await create_project_file("projects/demo/main.py", "print(1)", output_dir="./projects/demo")
    assert result["status"] == "success"
    assert Path(result["file_path"]) == (tmp_path / "projects/demo/main.py").resolve()


async def test_create_project_file_rejects_escape(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = await create_project_file("../evil.py", "x", output_dir="./projects/demo")
    assert result["status"] == "error"
    assert not (tmp_path / "evil.py").exists()
