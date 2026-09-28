"""`/modify` 项目路径解析与快照目录定位的文件系统操作须离开事件循环。

重构把 `/modify` 里绝对/相对路径解析、`/snapshots` 等三处重复的候选目录检查
抽成同步辅助函数，由端点经 `asyncio.to_thread` 调用。这里既校验抽取后的解析
语义，也断言端点调用发生在工作线程。
"""

import asyncio
import threading
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.api.v1.ai_agent import orchestrate_endpoints as oe
from app.api.v1.ai_agent.schemas import ModifyRequest


def _resolve_project_dir_relative_setup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "projects" / "1" / "demo").mkdir(parents=True)
    (tmp_path / "workspace_only").mkdir()


def test_resolve_project_dir_absolute(tmp_path):
    existing = tmp_path / "proj"
    existing.mkdir()

    path, error = oe._resolve_project_dir(str(existing))
    assert error is None and path == existing

    assert oe._resolve_project_dir(str(tmp_path / "missing")) == (None, "missing")

    not_dir = tmp_path / "file.txt"
    not_dir.write_text("x", encoding="utf-8")
    assert oe._resolve_project_dir(str(not_dir)) == (None, "not_dir")


def test_resolve_project_dir_relative(tmp_path, monkeypatch):
    _resolve_project_dir_relative_setup(tmp_path, monkeypatch)

    # 相对 projects 目录：projects/1/demo
    path, error = oe._resolve_project_dir("1/demo")
    assert error is None and path.name == "demo" and path.parent.name == "1"

    # 相对工作区根目录：只存在于根目录的目录
    path, error = oe._resolve_project_dir("workspace_only")
    assert error is None and path.name == "workspace_only"

    assert oe._resolve_project_dir("nope/nowhere") == (None, "missing")


def test_locate_snapshot_project_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "orchestrator" / "s1").mkdir(parents=True)
    (tmp_path / "user_uploads" / "s2").mkdir(parents=True)

    orchestrator_dir = oe._locate_snapshot_project_dir("s1")
    assert orchestrator_dir is not None and orchestrator_dir.parts[0] == "orchestrator"

    upload_dir = oe._locate_snapshot_project_dir("s2")
    assert upload_dir is not None and upload_dir.parts[0] == "user_uploads"

    assert oe._locate_snapshot_project_dir("missing") is None


@pytest.mark.asyncio
async def test_modify_endpoint_resolves_dir_off_event_loop(tmp_path, monkeypatch):
    main_thread = threading.get_ident()
    seen = []
    real_resolve = Path.resolve

    def spy(self, *args, **kwargs):
        seen.append(threading.get_ident())
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", spy)

    request = ModifyRequest(project_path=str(tmp_path / "missing"))
    with pytest.raises(HTTPException) as excinfo:
        await oe.modify_project(request=request, token={"sub": "1"}, db=None)

    assert excinfo.value.status_code == 404
    assert seen and all(t != main_thread for t in seen), "路径解析仍在事件循环线程"
