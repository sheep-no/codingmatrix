from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import agent_host
from app.api.v1.ai_agent.orchestrate_endpoints import (
    _bind_local_validation_session,
    _legacy_requirement_with_allowed_files,
)
from app.api.v1.ai_agent.schemas import ModifyRequest, OrchestratorRequest
from app.agent.architect import Architect
from app.agent.state import StateDelta, StateGraphBuilder
from app.agent.workflow_registry import WorkflowDefinition, run_workflow


def test_orchestrator_request_preserves_local_validation_scopes() -> None:
    request = OrchestratorRequest(
        requirement="创建一个可测试项目",
        required_validation_scopes=["local_runtime", "local_e2e"],
    )

    assert request.required_validation_scopes == ["local_runtime", "local_e2e"]


def test_orchestrator_request_rejects_unknown_validation_scope() -> None:
    with pytest.raises(ValidationError, match="required_validation_scopes"):
        OrchestratorRequest(
            requirement="创建一个可测试项目",
            required_validation_scopes=["cloud_runtime"],
        )


def test_modify_request_validates_and_deduplicates_validation_scopes() -> None:
    request = ModifyRequest(
        requirement="修复问题",
        required_validation_scopes=["local_runtime", "local_runtime"],
    )

    assert request.required_validation_scopes == ["local_runtime"]


def test_modify_request_rejects_unknown_validation_scope() -> None:
    with pytest.raises(ValidationError, match="required_validation_scopes"):
        ModifyRequest(requirement="修复问题", required_validation_scopes=["cloud"])


def test_modify_request_validates_host_session_id() -> None:
    assert ModifyRequest(host_session_id="host-session-1").host_session_id == "host-session-1"

    with pytest.raises(ValidationError, match="host_session_id"):
        ModifyRequest(host_session_id="bad session id")


def test_bind_local_validation_session_is_optional() -> None:
    assert _bind_local_validation_session(ModifyRequest(), "conversation-1", "user-1") == (
        "conversation-1"
    )


def test_bind_local_validation_session_rejects_unknown_host_session() -> None:
    request = ModifyRequest(host_session_id="unknown-host-session")

    with pytest.raises(HTTPException) as exc_info:
        _bind_local_validation_session(request, "conversation-1", "user-1")

    assert exc_info.value.status_code == 403


def test_bind_local_validation_session_rejects_foreign_owner() -> None:
    host_session_id = "host-session-owner"
    agent_host._sessions[host_session_id] = {
        "user_id": "other-user",
        "workspace_id": "workspace",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
        "policy_version": 1,
        "policy": {},
        "pending_actions": [],
        "in_flight_actions": [],
        "events": {},
    }
    try:
        with pytest.raises(HTTPException) as exc_info:
            _bind_local_validation_session(
                ModifyRequest(host_session_id=host_session_id),
                "conversation-1",
                "user-1",
            )
        assert exc_info.value.status_code == 403
    finally:
        agent_host._sessions.pop(host_session_id, None)


def test_orchestrator_request_validates_and_deduplicates_allowed_files() -> None:
    request = OrchestratorRequest(
        requirement="修复项目",
        allowed_files=["pom.xml", "src/main/java/App.java", "pom.xml"],
    )

    assert request.allowed_files == ["pom.xml", "src/main/java/App.java"]

    with pytest.raises(ValidationError, match="allowed_files"):
        OrchestratorRequest(requirement="修复项目", allowed_files=["../outside.py"])


def test_legacy_requirement_preserves_structured_allowed_file_boundary() -> None:
    allowed_files = [
        "app/main.py",
        "app/models.py",
        "app/schemas.py",
        "tests/test_crud.py",
    ]

    requirement = _legacy_requirement_with_allowed_files(
        "Repair the existing FastAPI project.",
        allowed_files,
    )

    assert Architect._extract_strict_file_paths(requirement) == set(allowed_files)


def test_legacy_requirement_preserves_dotfile_in_allowed_files() -> None:
    allowed_files = [".gitignore", "App.vue", "main.js", "package.json"]

    requirement = _legacy_requirement_with_allowed_files(
        "Create a minimal Vue app.",
        allowed_files,
    )

    assert Architect._extract_strict_file_paths(requirement) == set(allowed_files)


def test_legacy_requirement_is_unchanged_without_allowed_files() -> None:
    requirement = "Create a project."

    assert _legacy_requirement_with_allowed_files(requirement, []) == requirement


@pytest.mark.asyncio
async def test_completed_legacy_workflow_queues_local_validation() -> None:
    async def complete(_state):
        return StateDelta(expected_revision=0, status="completed")

    workflow = WorkflowDefinition(
        "local-scope-finalization",
        "complete",
        StateGraphBuilder().add_node("complete", complete).compile(),
        "test",
    )
    state = await run_workflow(
        workflow,
        session_id="local-scope-session",
        task_id="local-scope-task",
        metadata={"required_validation_scopes": ["local_runtime", "local_e2e"]},
    )

    assert state.status == "waiting_local_validation"
    assert state.pending_actions[0]["type"] == "local_validation"
