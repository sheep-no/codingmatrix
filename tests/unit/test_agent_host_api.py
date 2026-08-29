import pytest
from fastapi import HTTPException

from app.api.v1.agent_host import HostHandshakeRequest, agent_host_handshake


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
