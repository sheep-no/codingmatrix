import pytest
from fastapi import HTTPException

from app.api.v1.agent_host import (
    AgentHostEnvelope,
    HostHandshakeRequest,
    agent_host_handshake,
    get_agent_host_actions,
    post_agent_host_event,
    update_agent_host_policy,
    PolicyUpdateRequest,
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
