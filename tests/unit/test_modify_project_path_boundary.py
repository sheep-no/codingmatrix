"""Agent 项目路径必须留在 PROJECTS_BASE_DIR 内且归属当前用户。

修复前：``/modify`` 直接把客户端传来的 ``project_path``/``output_dir`` 交给
``_resolve_project_dir``，绝对路径与其它用户目录都会被接受，导致读取或改写
任意目录；``/orchestrate`` 的 ``output_dir`` 与流式端点的 ``project_path``
同样缺少归属校验。这里从端点入口验证拒绝行为。
"""

import pytest
from fastapi import HTTPException

from app.api.v1.ai_agent import helpers
from app.api.v1.ai_agent import orchestrate_endpoints as endpoints
from app.api.v1.ai_agent.schemas import ModifyRequest, OrchestratorRequest


def _prepare_projects(tmp_path, monkeypatch):
    monkeypatch.setattr(helpers, "PROJECTS_BASE_DIR", str(tmp_path))
    (tmp_path / "1" / "owned").mkdir(parents=True)
    (tmp_path / "2" / "foreign").mkdir(parents=True)
    (tmp_path / "user_uploads" / "1" / "zip-owned").mkdir(parents=True)
    return tmp_path


def test_modify_request_rejects_parent_traversal():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ModifyRequest(project_path="../outside")
    with pytest.raises(ValidationError):
        ModifyRequest(output_dir="../outside")


@pytest.mark.asyncio
async def test_modify_rejects_path_outside_projects_base(tmp_path, monkeypatch):
    _prepare_projects(tmp_path, monkeypatch)
    outside = tmp_path.parent / "outside-project"
    outside.mkdir(exist_ok=True)

    request = ModifyRequest(requirement="edit", output_dir=str(outside))
    with pytest.raises(HTTPException) as error:
        await endpoints.modify_project(request, {"sub": "1"}, db=None)

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_modify_rejects_other_user_project(tmp_path, monkeypatch):
    _prepare_projects(tmp_path, monkeypatch)

    request = ModifyRequest(requirement="edit", project_path="2/foreign")
    with pytest.raises(HTTPException) as error:
        await endpoints.modify_project(request, {"sub": "1"}, db=None)

    assert error.value.status_code == 403
    assert "其他用户" in error.value.detail


@pytest.mark.asyncio
async def test_modify_accepts_owned_upload_directory(tmp_path, monkeypatch):
    _prepare_projects(tmp_path, monkeypatch)
    seen = {}

    async def fake_analyze(request, project_dir, user_id):
        seen["dir"] = project_dir
        return {"code": 0, "type": "analysis"}

    monkeypatch.setattr(endpoints, "_is_analyze_intent", lambda req: True)
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    monkeypatch.setattr(endpoints, "_handle_analyze_request", fake_analyze)

    request = ModifyRequest(requirement="分析", project_path="user_uploads/1/zip-owned")
    result = await endpoints.modify_project(request, {"sub": "1"}, db=None)

    assert result["code"] == 0
    assert seen["dir"] == (tmp_path / "user_uploads" / "1" / "zip-owned").resolve()


@pytest.mark.asyncio
async def test_orchestrate_rejects_absolute_output_dir(tmp_path, monkeypatch):
    _prepare_projects(tmp_path, monkeypatch)

    request = OrchestratorRequest(
        requirement="build", output_dir=str(tmp_path.parent / "outside"), enable_skills=False
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project(request, {"sub": "1"}, None)

    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_stream_rejects_other_user_project_path(tmp_path, monkeypatch):
    _prepare_projects(tmp_path, monkeypatch)

    class ConnectedRequest:
        async def is_disconnected(self):
            return False

    request = OrchestratorRequest(
        requirement="continue", project_path="2/foreign", enable_skills=False
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            request, ConnectedRequest(), token={"sub": "1"}, db=None
        )

    assert error.value.status_code == 403


def test_validate_project_target_rejects_base_directory(tmp_path, monkeypatch):
    _prepare_projects(tmp_path, monkeypatch)

    with pytest.raises(HTTPException) as error:
        helpers._validate_project_target(".", "1")

    assert error.value.status_code == 403
