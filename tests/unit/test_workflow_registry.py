"""Tests for workflow registry and session replay adapters."""

from app.agent.adapters import replay_messages, replay_session, state_to_session_summary
from app.agent.state import MessageEnvelope, State, StateGraphBuilder
import pytest

from app.agent.workflow_registry import (
    WorkflowDefinition,
    WorkflowRegistry,
    build_legacy_workflow,
    run_workflow,
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
