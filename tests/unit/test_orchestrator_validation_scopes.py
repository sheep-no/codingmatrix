import pytest
from pydantic import ValidationError

from app.api.v1.ai_agent.schemas import OrchestratorRequest
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
