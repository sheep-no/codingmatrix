from datetime import datetime, timedelta, timezone
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.utils.security import verify_token

router = APIRouter()

SUPPORTED_PROTOCOL_VERSION = 1
CAPABILITIES = {"workspace", "file", "terminal", "diagnostics", "validation", "skill_runtime"}
HOST_EVENT_KINDS = {"approval_request", "progress_event", "diagnostic_event", "tool_result"}
_sessions: dict[str, dict[str, Any]] = {}


def _dump_model(model: BaseModel) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


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


class AgentHostEnvelope(BaseModel):
    message_id: str = Field(min_length=1, max_length=256)
    schema_version: Literal[1]
    session_id: str = Field(min_length=1, max_length=256)
    task_id: str | None = None
    revision: int | None = Field(default=None, ge=0)
    kind: Literal["approval_request", "progress_event", "diagnostic_event", "tool_result"]
    capability: str | None = None
    policy_version: int | None = Field(default=None, ge=0)
    payload: dict[str, Any]


class AgentHostActionsResponse(BaseModel):
    actions: list[dict[str, Any]]


class AgentHostEventResponse(BaseModel):
    accepted: bool
    duplicate: bool = False


class PolicyUpdateRequest(BaseModel):
    expected_policy_version: int = Field(ge=0)
    policy: dict[str, Any]


class PolicyUpdateResponse(BaseModel):
    policy_version: int
    policy: dict[str, Any]


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
    policy = {
        "local_execution_enabled": True,
        "validation_operations": {},
        "auto_approve": False,
        "require_confirmation_on_failure": True,
    }
    _sessions[session_id] = {
        "user_id": str(token.get("sub", "")),
        "workspace_id": request.workspace_id,
        "expires_at": expires_at,
        "policy_version": 1,
        "policy": policy,
        "pending_actions": [],
        "events": {},
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


def _get_session(session_id: str, token: dict) -> dict[str, Any]:
    session = _sessions.get(session_id)
    if session is None or session["user_id"] != str(token.get("sub", "")):
        raise HTTPException(status_code=404, detail="agent host session not found")
    if datetime.now(timezone.utc) >= session["expires_at"]:
        _sessions.pop(session_id, None)
        raise HTTPException(status_code=410, detail="agent host session expired")
    return session


@router.get("/agent/host/sessions/{session_id}/actions", response_model=AgentHostActionsResponse)
async def get_agent_host_actions(session_id: str, token: dict = Depends(verify_token)) -> AgentHostActionsResponse:
    session = _get_session(session_id, token)
    actions = list(session["pending_actions"])
    session["pending_actions"] = [
        action for action in session["pending_actions"]
        if action.get("kind") != "policy_update"
    ]
    return AgentHostActionsResponse(actions=actions)


@router.post("/agent/host/sessions/{session_id}/events", response_model=AgentHostEventResponse)
async def post_agent_host_event(
    session_id: str,
    event: AgentHostEnvelope,
    token: dict = Depends(verify_token),
) -> AgentHostEventResponse:
    session = _get_session(session_id, token)
    if event.session_id != session_id:
        raise HTTPException(status_code=409, detail="event session does not match route")
    if event.kind not in HOST_EVENT_KINDS:
        raise HTTPException(status_code=422, detail="unsupported host event kind")
    if event.message_id in session["events"]:
        return AgentHostEventResponse(accepted=True, duplicate=True)
    session["events"][event.message_id] = _dump_model(event)
    if event.kind == "tool_result" and event.message_id.endswith(":result"):
        source_message_id = event.message_id.removesuffix(":result")
        session["pending_actions"] = [
            action for action in session["pending_actions"]
            if action.get("message_id") != source_message_id
        ]
    return AgentHostEventResponse(accepted=True)


@router.put("/agent/host/sessions/{session_id}/policy", response_model=PolicyUpdateResponse)
async def update_agent_host_policy(
    session_id: str,
    request: PolicyUpdateRequest,
    token: dict = Depends(verify_token),
) -> PolicyUpdateResponse:
    session = _get_session(session_id, token)
    current_version = session["policy_version"]
    if request.expected_policy_version != current_version:
        raise HTTPException(status_code=409, detail="policy version conflict")
    next_version = current_version + 1
    session["policy_version"] = next_version
    session["policy"] = request.policy
    session["pending_actions"].append({
        "message_id": str(uuid4()),
        "schema_version": SUPPORTED_PROTOCOL_VERSION,
        "session_id": session_id,
        "kind": "policy_update",
        "policy_version": next_version,
        "payload": {"policy": request.policy},
    })
    return PolicyUpdateResponse(policy_version=next_version, policy=request.policy)
