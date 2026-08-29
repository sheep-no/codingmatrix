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
)
from app.agent.state import StateDelta, StateGraphBuilder
from app.agent.workflow_registry import WorkflowDefinition, run_workflow


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
