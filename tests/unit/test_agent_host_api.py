from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from app.api.v1.agent_host import (
    AgentHostSessionStore,
    AgentHostEnvelope,
    HostHandshakeRequest,
    agent_host_handshake,
    get_agent_host_actions,
    post_agent_host_event,
    update_agent_host_policy,
    PolicyUpdateRequest,
    enqueue_state_actions,
    sync_agent_host_skills,
    revoke_agent_host_skill,
    control_agent_host_session,
    SkillSyncRequest,
    SessionControlRequest,
)
from app.agent.state import StateDelta, StateGraphBuilder
import app.agent.workflow_registry as workflow_registry
from app.agent.workflow_registry import (
    WorkflowDefinition,
    register_recoverable_workflow_factory,
    resume_workflow_from_local_result,
    run_workflow,
)


@pytest.mark.asyncio
async def test_agent_host_handshake_returns_bound_session() -> None:
    response = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-1",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["workspace", "validation", "workspace"],
        ),
        {"sub": "user-1"},
    )

    assert response.session_id
    assert response.workspace_id == "workspace-1"
    assert response.protocol_version == 1
    assert response.capabilities == ["validation", "workspace"]
    assert response.policy_version == 1
    assert response.pending_actions == []


@pytest.mark.asyncio
async def test_agent_host_handshake_rejects_unknown_capability() -> None:
    with pytest.raises(HTTPException) as error:
        await agent_host_handshake(
            HostHandshakeRequest(
                workspace_id="workspace-1",
                extension_version="0.1.0",
                protocol_versions=[1],
                capabilities=["unknown"],
            ),
            {"sub": "user-1"},
        )

    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_agent_host_handshake_requires_supported_protocol() -> None:
    with pytest.raises(HTTPException) as error:
        await agent_host_handshake(
            HostHandshakeRequest(
                workspace_id="workspace-1",
                extension_version="0.1.0",
                protocol_versions=[2],
                capabilities=["workspace"],
            ),
            {"sub": "user-1"},
        )

    assert error.value.status_code == 426


@pytest.mark.asyncio
async def test_agent_host_session_scopes_events_and_policy_updates() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-2",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["workspace"],
        ),
        {"sub": "user-2"},
    )
    session_id = handshake.session_id
    event = AgentHostEnvelope(
        message_id="event-1",
        schema_version=1,
        session_id=session_id,
        kind="progress_event",
        payload={"message": "running"},
    )

    accepted = await post_agent_host_event(session_id, event, {"sub": "user-2"})
    duplicate = await post_agent_host_event(session_id, event, {"sub": "user-2"})
    assert accepted.duplicate is False
    assert duplicate.duplicate is True

    updated = await update_agent_host_policy(
        session_id,
        PolicyUpdateRequest(expected_policy_version=1, policy={"auto_approve": True}),
        {"sub": "user-2"},
    )
    assert updated.policy_version == 2
    actions = await get_agent_host_actions(session_id, {"sub": "user-2"})
    assert actions.actions[0]["kind"] == "policy_update"
    assert (await get_agent_host_actions(session_id, {"sub": "user-2"})).actions == []

    with pytest.raises(HTTPException) as error:
        await get_agent_host_actions(session_id, {"sub": "another-user"})
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_enqueue_state_actions_binds_session_context_and_deduplicates() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-3",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["validation"],
        ),
        {"sub": "user-3"},
    )
    state = {
        "session_id": handshake.session_id,
        "task_id": "task-3",
        "revision": 7,
        "pending_actions": [{
            "type": "local_validation",
            "event_id": "pending-1",
            "scopes": ["local_runtime"],
        }],
    }

    assert enqueue_state_actions(handshake.session_id, state) == 1
    assert enqueue_state_actions(handshake.session_id, state) == 0
    queued = (await get_agent_host_actions(handshake.session_id, {"sub": "user-3"})).actions
    assert queued[0]["session_id"] == handshake.session_id
    assert queued[0]["task_id"] == "task-3"
    assert queued[0]["revision"] == 7
    assert queued[0]["payload"]["workspace_id"] == "workspace-3"


@pytest.mark.asyncio
async def test_enqueue_state_actions_maps_execution_capabilities() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-capabilities",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["file", "terminal", "validation"],
        ),
        {"sub": "user-capabilities"},
    )
    state = {
        "session_id": handshake.session_id,
        "task_id": "task-capabilities",
        "pending_actions": [
            {"type": "file_sync", "action_id": "file-action"},
            {"type": "install_dependencies", "action_id": "install-action"},
            {"type": "local_validation", "action_id": "validation-action"},
        ],
    }

    assert enqueue_state_actions(handshake.session_id, state) == 3
    queued = (await get_agent_host_actions(handshake.session_id, {"sub": "user-capabilities"})).actions
    assert [action["capability"] for action in queued] == ["file", "terminal", "validation"]


def test_agent_host_session_store_round_trips_expiry_and_queue(tmp_path) -> None:
    store = AgentHostSessionStore(tmp_path)
    session = {
        "user_id": "user-4",
        "workspace_id": "workspace-4",
        "expires_at": datetime.now(timezone.utc),
        "policy_version": 1,
        "policy": {},
        "pending_actions": [],
        "events": {},
    }
    store.save("session-4", session)
    restored = store.load("session-4")
    assert restored["user_id"] == "user-4"
    assert restored["expires_at"].tzinfo is not None


@pytest.mark.asyncio
async def test_agent_host_syncs_skills_and_session_control() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-controls",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["skill_runtime"],
        ),
        {"sub": "user-controls"},
    )
    session_id = handshake.session_id
    skills = {"review": {"content": "Review changed files", "version": 1}}

    synced = await sync_agent_host_skills(session_id, SkillSyncRequest(skills=skills), {"sub": "user-controls"})
    assert synced["skills"] == skills
    revoked = await revoke_agent_host_skill(session_id, "review", {"sub": "user-controls"})
    assert revoked["skills"] == {}
    controlled = await control_agent_host_session(
        session_id, SessionControlRequest(action="pause"), {"sub": "user-controls"}
    )
    assert controlled == {"status": "paused"}
    actions = (await get_agent_host_actions(session_id, {"sub": "user-controls"})).actions
    assert [action["kind"] for action in actions[-3:]] == ["tool_action", "skill_revoke", "session_control"]


@pytest.mark.asyncio
async def test_run_workflow_publishes_pending_actions_to_connected_host() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-5",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["validation"],
        ),
        {"sub": "user-5"},
    )

    async def create_action(_state):
        return StateDelta(
            expected_revision=0,
            pending_actions=[{"type": "local_validation", "action_id": "workflow-action"}],
        )

    definition = WorkflowDefinition(
        name="host-test",
        entry_node="create_action",
        graph=StateGraphBuilder().add_node("create_action", create_action).compile(),
        legacy_endpoint="test",
    )
    await run_workflow(definition, session_id=handshake.session_id, task_id="task-5")

    actions = (await get_agent_host_actions(handshake.session_id, {"sub": "user-5"})).actions
    assert actions[0]["payload"]["action_id"] == "workflow-action"


@pytest.mark.asyncio
async def test_tool_result_resumes_workflow_and_reaches_completed() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-6",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["validation"],
        ),
        {"sub": "user-6"},
    )

    async def create_action(_state):
        return StateDelta(
            expected_revision=0,
            status="waiting_local_validation",
            pending_actions=[{
                "type": "local_validation",
                "action_id": "workflow-action-6",
                "scope": "local_e2e",
            }],
            metadata={"required_validation_scopes": ["local_e2e"]},
        )

    definition = WorkflowDefinition(
        name="host-resume-test",
        entry_node="create_action",
        graph=StateGraphBuilder().add_node("create_action", create_action).compile(),
        legacy_endpoint="test",
    )
    await run_workflow(definition, session_id=handshake.session_id, task_id="task-6")
    action = (await get_agent_host_actions(handshake.session_id, {"sub": "user-6"})).actions[0]

    response = await post_agent_host_event(
        handshake.session_id,
        AgentHostEnvelope(
            message_id=f"{action['message_id']}:result",
            schema_version=1,
            session_id=handshake.session_id,
            task_id="task-6",
            revision=1,
            kind="tool_result",
            capability="validation",
            policy_version=1,
            payload={
                "validation_scope": "local_e2e",
                "status": "passed",
                "summary": {"tests_passed": 1},
            },
        ),
        {"sub": "user-6"},
    )

    assert response.state_status == "completed"
    assert (await get_agent_host_actions(handshake.session_id, {"sub": "user-6"})).actions == []


@pytest.mark.asyncio
async def test_tool_result_resumes_from_checkpoint_after_registry_reset() -> None:
    session_id = "session-checkpoint"
    task_id = "task-checkpoint"

    async def create_action(_state):
        return StateDelta(
            expected_revision=0,
            status="waiting_local_validation",
            pending_actions=[{"type": "local_validation", "action_id": "checkpoint-action", "scope": "local_runtime"}],
            metadata={"required_validation_scopes": ["local_runtime"]},
        )

    definition = WorkflowDefinition(
        name="checkpoint-resume-test",
        entry_node="create_action",
        graph=StateGraphBuilder().add_node("create_action", create_action).compile(),
        legacy_endpoint="test",
    )
    await run_workflow(definition, session_id=session_id, task_id=task_id)
    workflow_registry._active_workflows.pop((session_id, task_id))

    state = await resume_workflow_from_local_result(
        session_id=session_id,
        task_id=task_id,
        result={
            "session_id": session_id,
            "task_id": task_id,
            "revision": 1,
            "schema_version": 1,
            "source": "local",
            "validation_scope": "local_runtime",
            "status": "passed",
        },
    )

    assert state.status == "completed"
    assert state.pending_actions == []


@pytest.mark.asyncio
async def test_tool_result_continues_from_persisted_next_graph_node() -> None:
    session_id = "session-graph-cursor"
    task_id = "task-graph-cursor"

    async def create_action(_state):
        return StateDelta(
            expected_revision=0,
            status="waiting_local_validation",
            pending_actions=[{"type": "local_validation", "scope": "local_runtime"}],
            metadata={"required_validation_scopes": ["local_runtime"]},
        )

    async def finish(state):
        assert state.status == "completed"
        return StateDelta(expected_revision=state.revision, metadata={"continued": True})

    graph = (
        StateGraphBuilder()
        .add_node("create_action", create_action)
        .add_node("finish", finish)
        .add_edge("create_action", "finish")
        .compile()
    )
    definition = WorkflowDefinition("graph-cursor-test", "create_action", graph, "test")
    state = await run_workflow(definition, session_id=session_id, task_id=task_id)
    assert state.metadata["_next_node"] == "finish"

    state = await resume_workflow_from_local_result(
        session_id=session_id,
        task_id=task_id,
        result={
            "session_id": session_id,
            "task_id": task_id,
            "revision": 1,
            "source": "local",
            "validation_scope": "local_runtime",
            "status": "passed",
        },
    )

    assert state.metadata["continued"] is True
    assert "_next_node" not in state.metadata


@pytest.mark.asyncio
async def test_tool_result_rebuilds_workflow_from_registered_factory() -> None:
    session_id = "session-factory"
    task_id = "task-factory"

    async def create_action(_state):
        return StateDelta(
            expected_revision=0,
            status="waiting_local_validation",
            pending_actions=[{"type": "local_validation", "scope": "local_runtime"}],
            metadata={"required_validation_scopes": ["local_runtime"]},
        )

    async def finish(state):
        return StateDelta(expected_revision=state.revision, metadata={"factory_continued": True})

    def factory():
        graph = (
            StateGraphBuilder()
            .add_node("create_action", create_action)
            .add_node("finish", finish)
            .add_edge("create_action", "finish")
            .compile()
        )
        return WorkflowDefinition("factory-resume-test", "create_action", graph, "test")

    definition = factory()
    register_recoverable_workflow_factory(definition.name, factory)
    await run_workflow(definition, session_id=session_id, task_id=task_id)
    workflow_registry._active_workflows.pop((session_id, task_id))

    state = await resume_workflow_from_local_result(
        session_id=session_id,
        task_id=task_id,
        result={
            "session_id": session_id,
            "task_id": task_id,
            "revision": 1,
            "source": "local",
            "validation_scope": "local_runtime",
            "status": "passed",
        },
    )

    assert state.metadata["factory_continued"] is True
