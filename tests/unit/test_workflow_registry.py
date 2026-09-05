"""Tests for workflow registry and session replay adapters."""

from app.agent.adapters import replay_messages, replay_session, state_to_session_summary
from app.agent.state import MessageEnvelope, State, StateGraphBuilder
import app.agent.workflow_registry as workflow_registry
import pytest
from uuid import uuid4

from app.agent.workflow_registry import (
    WorkflowDefinition,
    WorkflowRegistry,
    build_legacy_workflow,
    get_legacy_result,
    run_workflow,
    cancel_workflows_for_session,
)


def test_registry_names_and_session_summary() -> None:
    graph = StateGraphBuilder().add_node("start", lambda state: None).compile()
    registry = WorkflowRegistry([WorkflowDefinition("generate", "start", graph, "/generate")])
    state = State("s1", "t1", revision=2, status="completed")
    state.messages.append(MessageEnvelope(1, "e1", "s1", "t1", 2, 1, "done", "test"))

    assert registry.names() == ["generate"]
    assert state_to_session_summary(state)["status"] == "completed"
    assert replay_messages(state, after_sequence=0)[0]["event_id"] == "e1"


def test_session_replay_exposes_snapshot_recovery_for_sequence_gap() -> None:
    state = State("s1", "t1", revision=3)
    state.messages.extend([
        MessageEnvelope(1, "e2", "s1", "t1", 2, 2, "progress", "test"),
        MessageEnvelope(1, "e4", "s1", "t1", 3, 4, "done", "test"),
    ])

    replay = replay_session(state, after_sequence=1)

    assert [message["sequence"] for message in replay["messages"]] == [2, 4]
    assert replay["recovery_action"]["type"] == "snapshot_recovery"


@pytest.mark.asyncio
async def test_legacy_workflow_preserves_result_and_maps_state() -> None:
    definition = build_legacy_workflow(
        "generate",
        "/generate",
        lambda state: {
            "success": True,
            "files": [{"path": "main.py"}],
        },
    )

    state = await run_workflow(
        definition,
        session_id="s1",
        task_id="t1",
    )

    assert state.status == "completed"
    assert state.generated_files == [{"path": "main.py"}]
    assert state.metadata["legacy_result"]["success"] is True


@pytest.mark.asyncio
async def test_legacy_workflow_supports_async_stream_handler() -> None:
    async def generate(_state):
        return {"success": False, "errors": ["validation failed"]}

    definition = build_legacy_workflow(
        "orchestrate_stream",
        "/orchestrate/stream",
        generate,
    )
    state = await run_workflow(definition, session_id="s1", task_id="t1")

    assert state.status == "failed"
    assert state.errors[0]["message"] == "validation failed"
    assert state.metadata["legacy_result"]["success"] is False


@pytest.mark.asyncio
async def test_workflow_selects_core_handler_when_feature_flag_is_enabled() -> None:
    definition = build_legacy_workflow(
        "generate",
        "/generate",
        lambda _state: {"success": True, "engine": "legacy"},
        core_handler=lambda _state: {"success": True, "engine": "core"},
    )

    state = await run_workflow(
        definition,
        session_id="core-session",
        task_id="core-task",
        metadata={"engine": "core"},
    )

    assert state.metadata["legacy_result"]["engine"] == "core"
    assert state.metadata["engine"] == "core"


@pytest.mark.asyncio
async def test_legacy_workflow_exposes_original_handler_error() -> None:
    async def generate(_state):
        raise RuntimeError("provider is not configured")

    definition = build_legacy_workflow("generate", "/generate", generate)
    state = await run_workflow(definition, session_id="s1", task_id="t1")

    assert state.status == "failed"
    with pytest.raises(RuntimeError, match="provider is not configured"):
        get_legacy_result(state)


@pytest.mark.asyncio
async def test_cancel_workflow_persists_terminal_state_and_clears_actions() -> None:
    definition = WorkflowDefinition(
        "cancel", "wait", StateGraphBuilder().add_node("wait", lambda _state: None).compile(), "/cancel"
    )
    workflow_registry._active_workflows[("cancel-session", "cancel-task")] = (
        definition,
        State(
            "cancel-session",
            "cancel-task",
            status="waiting_local_validation",
            pending_actions=[{"type": "local_validation", "action_id": "cancel-action"}],
        ),
    )

    assert await cancel_workflows_for_session("cancel-session") == 1
    state = workflow_registry._active_workflows[("cancel-session", "cancel-task")][1]

    assert state.status == "cancelled"
    assert state.pending_actions == []
    assert state.errors[-1]["code"] == "orchestration.cancelled"


@pytest.mark.asyncio
async def test_checkpoint_recovery_has_registered_factory_for_production_workflows() -> None:
    session_id = f"recover-session-{uuid4().hex}"
    task_id = f"recover-task-{uuid4().hex}"
    definition = build_legacy_workflow(
        "orchestrate",
        "/orchestrate",
        lambda _state: {"success": True},
    )
    state = await run_workflow(
        definition,
        session_id=session_id,
        task_id=task_id,
        metadata={
            "requirement": "build an app",
            "output_dir": "projects/recover",
            "required_validation_scopes": ["local_runtime"],
        },
    )
    workflow_registry._active_workflows.pop((session_id, task_id), None)

    resumed = await workflow_registry.resume_workflow_from_local_result(
        session_id=session_id,
        task_id=task_id,
        result={
            "task_id": task_id,
            "session_id": session_id,
            "revision": state.revision,
            "scope": "local_runtime",
            "status": "passed",
            "event_id": "recover-result",
            "schema_version": 1,
            "source": "local",
        },
    )

    assert "orchestrate" in workflow_registry._recoverable_workflow_factories
    assert resumed.status == "completed"
    assert resumed.validation_results[-1]["passed"] is True
