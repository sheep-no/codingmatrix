"""BaseStackAdapter 剩余分支补测。"""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.code_synthesis_contracts import ProjectModel
from app.agent.stack_adapters import base as base_module
from app.agent.stack_adapters.adapters import ExpressStackAdapter
from app.agent.stack_adapters.base import StackArtifactRequest, _normalize_artifact_path


def test_artifact_dependencies_must_be_unique():
    with pytest.raises(ValidationError, match="dependencies must be unique"):
        StackArtifactRequest(
            path="src/api.ts",
            role="api",
            depends_on=("src/domain.ts", "src/domain.ts"),
        )


def test_artifact_path_must_be_normalized_relative_path():
    with pytest.raises(ValueError, match="normalized relative path"):
        _normalize_artifact_path("/absolute/path.ts")


def test_contract_scope_reports_owned_extensions():
    adapter = ExpressStackAdapter()

    stack_id, extensions, roles = adapter.contract_scope()

    assert stack_id == "express"
    assert ".ts" in extensions
    assert roles == frozenset()


@pytest.mark.asyncio
async def test_scaffold_runs_registered_command(tmp_path: Path, monkeypatch):
    adapter = ExpressStackAdapter()
    project = ProjectModel(language="typescript", framework="express")
    captured = {}

    async def fake_execute(workspace, request):
        captured["workspace"] = workspace
        captured["request"] = request
        return "plan-sentinel"

    monkeypatch.setattr(base_module, "execute_official_scaffold", fake_execute)
    staging_dir = tmp_path / "service"

    result = await adapter.scaffold(project, staging_dir)

    assert result.supported is True
    assert result.plan == "plan-sentinel"
    assert result.request is not None
    assert captured["workspace"] == tmp_path.resolve()
    assert captured["request"].target_dir == "service"


@pytest.mark.asyncio
async def test_scaffold_rejects_missing_staging_parent(tmp_path: Path, monkeypatch):
    adapter = ExpressStackAdapter()
    project = ProjectModel(language="typescript", framework="express")

    async def fake_execute(workspace, request):
        raise AssertionError("must not execute without a staging parent")

    monkeypatch.setattr(base_module, "execute_official_scaffold", fake_execute)
    staging_dir = tmp_path / "missing" / "service"

    with pytest.raises(ValueError, match="existing directory"):
        await adapter.scaffold(project, staging_dir)
