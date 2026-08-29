from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.utils.security import verify_token

router = APIRouter()

SUPPORTED_PROTOCOL_VERSION = 1
CAPABILITIES = {"workspace", "file", "terminal", "diagnostics", "validation", "skill_runtime"}
_sessions: dict[str, dict[str, Any]] = {}


class HostHandshakeRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=256)
    extension_version: str = Field(min_length=1, max_length=64)
    protocol_versions: list[int] = Field(min_length=1, max_length=8)
    capabilities: list[str] = Field(min_length=1, max_length=16)


class HostHandshakeResponse(BaseModel):
    session_id: str
    workspace_id: str
    extension_version: str
    protocol_version: Literal[1]
    capabilities: list[str]
    policy_version: int
    policy: dict[str, Any]
    pending_actions: list[dict[str, Any]]
    expires_at: str


@router.post("/agent/host/handshake", response_model=HostHandshakeResponse)
async def agent_host_handshake(
    request: HostHandshakeRequest,
    token: dict = Depends(verify_token),
) -> HostHandshakeResponse:
    capabilities = sorted(set(request.capabilities))
    unsupported = [item for item in capabilities if item not in CAPABILITIES]
    if unsupported:
        raise HTTPException(status_code=422, detail=f"unsupported capabilities: {', '.join(unsupported)}")
    if SUPPORTED_PROTOCOL_VERSION not in request.protocol_versions:
        raise HTTPException(status_code=426, detail="supported protocol version 1 is required")

    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    session_id = str(uuid4())
    _sessions[session_id] = {
        "user_id": str(token.get("sub", "")),
        "workspace_id": request.workspace_id,
        "expires_at": expires_at,
    }
    policy = {
        "local_execution_enabled": True,
        "validation_operations": {},
        "auto_approve": False,
        "require_confirmation_on_failure": True,
    }
    return HostHandshakeResponse(
        session_id=session_id,
        workspace_id=request.workspace_id,
        extension_version=request.extension_version,
        protocol_version=SUPPORTED_PROTOCOL_VERSION,
        capabilities=capabilities,
        policy_version=1,
        policy=policy,
        pending_actions=[],
        expires_at=expires_at.isoformat(),
    )
