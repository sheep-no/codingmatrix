import json
import logging
import os
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.models import ProjectSession
from app.agent.host_action_dispatch import register_state_action_dispatcher
from app.utils.security import verify_token

router = APIRouter()

SUPPORTED_PROTOCOL_VERSION = 1
CAPABILITIES = {"workspace", "file", "terminal", "diagnostics", "validation", "skill_runtime"}
HOST_EVENT_KINDS = {"approval_request", "progress_event", "diagnostic_event", "tool_result"}
_sessions: dict[str, dict[str, Any]] = {}
logger = logging.getLogger(__name__)

LOCAL_VALIDATION_SCOPES = {"local_runtime", "local_e2e"}


class AgentHostSessionStore:
    """Small atomic JSON store for session queues and event acknowledgements."""

    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or Path(os.getenv("AGENT_HOST_SESSION_DIR", "data/agent_host_sessions"))
        self.directory.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        if not session_id or Path(session_id).name != session_id:
            raise ValueError("invalid session id")
        return self.directory / f"{session_id}.json"

    def load(self, session_id: str) -> dict[str, Any] | None:
        path = self._path(session_id)
        if not path.exists():
            return None
        with path.open(encoding="utf-8") as handle:
            value = json.load(handle)
        value["expires_at"] = datetime.fromisoformat(value["expires_at"])
        return value

    def save(self, session_id: str, session: dict[str, Any]) -> None:
        target = self._path(session_id)
        payload = {**session, "expires_at": session["expires_at"].isoformat()}
        fd, temporary_name = tempfile.mkstemp(prefix=f".{session_id}.", suffix=".tmp", dir=self.directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        except Exception:
            Path(temporary_name).unlink(missing_ok=True)
            raise


_session_store = AgentHostSessionStore()
_last_prune_at: float = 0.0
_PRUNE_INTERVAL_SECONDS = 60.0


def _prune_expired_sessions(now: datetime | None = None) -> int:
    """Drop expired sessions from memory and disk.

    Every handshake writes a 30-minute session to both `_sessions` and the
    session store. Without a sweep they accumulate forever, growing memory and
    leaving JSON files behind.
    """

    global _last_prune_at
    reference = now or datetime.now(timezone.utc)
    now_monotonic = time.monotonic()
    if now is None and now_monotonic - _last_prune_at < _PRUNE_INTERVAL_SECONDS:
        return 0
    _last_prune_at = now_monotonic
    removed = 0
    for session_id, session in list(_sessions.items()):
        expires_at = session.get("expires_at")
        if expires_at is not None and reference >= expires_at:
            _sessions.pop(session_id, None)
            removed += 1

    for path in _session_store.directory.glob("*.json"):
        try:
            stored = _session_store.load(path.stem)
        except (OSError, ValueError):
            continue
        expires_at = stored.get("expires_at") if stored else None
        if expires_at is not None and reference >= expires_at:
            try:
                path.unlink()
            except OSError:
                pass
    return removed


def _dump_model(model: BaseModel) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def enqueue_state_actions(session_id: str, state: Any) -> int:
    """Adapt State.pending_actions into versioned Host actions for a session."""
    host_session_id = _host_session_id_for(session_id) or session_id
    session = _sessions.get(host_session_id)
    if session is None:
        session = _session_store.load(host_session_id)
    if session is None:
        raise KeyError(f"agent host session not found: {session_id}")
    if datetime.now(timezone.utc) >= session["expires_at"]:
        _sessions.pop(host_session_id, None)
        raise KeyError(f"agent host session expired: {session_id}")
    _sessions[host_session_id] = session
    state_data = state.to_dict() if hasattr(state, "to_dict") else dict(state)
    if state_data.get("session_id") not in (None, session_id):
        raise ValueError("state session does not match agent host session")
    stored_workflow_session = session.get("workflow_session_id")
    if stored_workflow_session not in (None, session_id):
        raise ValueError("state session does not match agent host session")
    task_id = str(state_data.get("task_id", ""))
    revision = int(state_data.get("revision", 0))
    workspace_id = str(session["workspace_id"])
    pending_actions = state_data.get("pending_actions", [])
    needs_commands = any(
        isinstance(action, dict)
        and action.get("type") in {"local_validation", "install_dependencies", "dependency_install"}
        for action in pending_actions
    )
    commands = _validation_commands(state_data) if needs_commands else None
    existing = {
        action.get("payload", {}).get("action_id")
        for action in [
            *session.get("pending_actions", []),
            *session.get("in_flight_actions", []),
        ]
    }
    added = 0
    for pending in pending_actions:
        if not isinstance(pending, dict):
            continue
        event_id = str(pending.get("event_id") or uuid4())
        base_id = str(pending.get("action_id") or event_id)
        for scope, spec in _pending_execution_plans(pending, commands):
            action_id = base_id if scope is None else f"{base_id}:{scope}"
            message_id = event_id if scope is None else f"{event_id}:{scope}"
            if action_id in existing:
                continue
            capability = _pending_action_capability(pending)
            payload = {
                **pending,
                "schema_version": SUPPORTED_PROTOCOL_VERSION,
                "event_id": message_id,
                "action_id": action_id,
                "session_id": host_session_id,
                "task_id": task_id,
                "revision": revision,
                "workspace_id": workspace_id,
            }
            if spec is not None:
                payload.update({
                    "validation_scope": scope or "local_runtime",
                    "operation": _validation_operation(spec.action, scope),
                    "command": list(spec.command),
                    "working_directory": ".",
                    "timeout_seconds": spec.timeout_seconds,
                    "requested_by": "cloud",
                })
            session["pending_actions"].append({
                "message_id": message_id,
                "schema_version": SUPPORTED_PROTOCOL_VERSION,
                "session_id": host_session_id,
                "task_id": task_id,
                "revision": revision,
                "kind": "tool_action",
                "capability": capability,
                "policy_version": session["policy_version"],
                "payload": payload,
            })
            existing.add(action_id)
            added += 1
    if added:
        _session_store.save(host_session_id, session)
    return added


def bind_workflow_session(workflow_session_id: str, host_session_id: str, user_id: str) -> None:
    """Remember which Host session executes a workflow conversation's actions."""
    if not workflow_session_id or not host_session_id:
        raise KeyError("workflow and host session ids are required")
    session = _sessions.get(host_session_id)
    if session is None:
        session = _session_store.load(host_session_id)
    if session is None:
        raise KeyError(f"agent host session not found: {host_session_id}")
    if datetime.now(timezone.utc) >= session["expires_at"]:
        _sessions.pop(host_session_id, None)
        raise KeyError(f"agent host session expired: {host_session_id}")
    if str(session.get("user_id", "")) != str(user_id):
        raise PermissionError("agent host session belongs to another user")
    # A re-handshake replaces the delivery target; the old session must stop
    # claiming this conversation so new actions are not queued twice.
    for other_id, other in _sessions.items():
        if other_id != host_session_id and other.get("workflow_session_id") == workflow_session_id:
            other.pop("workflow_session_id", None)
            _session_store.save(other_id, other)
    for path in _session_store.directory.glob("*.json"):
        if path.stem == host_session_id:
            continue
        try:
            other = _session_store.load(path.stem)
        except (OSError, ValueError):
            continue
        if other and other.get("workflow_session_id") == workflow_session_id:
            other.pop("workflow_session_id", None)
            _session_store.save(path.stem, other)
    session["workflow_session_id"] = workflow_session_id
    _sessions[host_session_id] = session
    _session_store.save(host_session_id, session)


def _host_session_id_for(workflow_session_id: str) -> str | None:
    if workflow_session_id in _sessions:
        return workflow_session_id
    now = datetime.now(timezone.utc)
    for host_session_id, session in _sessions.items():
        if (
            session.get("workflow_session_id") == workflow_session_id
            and now < session["expires_at"]
        ):
            return host_session_id
    for path in _session_store.directory.glob("*.json"):
        try:
            session = _session_store.load(path.stem)
        except (OSError, ValueError):
            continue
        if (
            session
            and session.get("workflow_session_id") == workflow_session_id
            and now < session["expires_at"]
        ):
            _sessions[path.stem] = session
            return path.stem
    return None


def _pending_scopes(action: dict[str, Any]) -> list[str]:
    raw = action.get("scopes", action.get("scope", []))
    if isinstance(raw, str):
        raw = [raw]
    return [scope for scope in raw if scope in LOCAL_VALIDATION_SCOPES]


def _validation_commands(state_data: dict[str, Any]) -> dict[str, Any] | None:
    """Detect toolchain commands for the generated workspace, keyed by scope.

    Returns ``None`` when the workspace is unknown, which keeps legacy payloads
    for state-only callers. An empty mapping means the workspace exists but no
    executable command was detected, so the action must not be sent.
    """
    metadata = state_data.get("metadata") or {}
    workspace = _workspace_directory(metadata)
    if workspace is None:
        logger.warning("agent host action skipped: workspace directory is unknown")
        return None
    try:
        from app.agent.toolchain import ToolchainAction, detect_toolchain

        plan = detect_toolchain(workspace)
    except (OSError, ValueError):
        logger.exception("agent host action skipped: toolchain detection failed")
        return None
    preferences = {
        "install": (ToolchainAction.INSTALL,),
        "local_runtime": (
            ToolchainAction.TEST,
            ToolchainAction.BUILD,
            ToolchainAction.TYPECHECK,
            ToolchainAction.LINT,
            ToolchainAction.INSTALL,
        ),
        "local_e2e": (
            ToolchainAction.SMOKE,
            ToolchainAction.TEST,
            ToolchainAction.BUILD,
        ),
    }
    return {
        scope: next(
            (spec for action in actions if (spec := plan.for_action(action)) is not None),
            None,
        )
        for scope, actions in preferences.items()
    }


def _workspace_directory(metadata: dict[str, Any]) -> Path | None:
    from app.api.v1.ai_agent.project_config import PROJECTS_BASE_DIR

    for key in ("project_path", "output_dir"):
        value = metadata.get(key)
        if not isinstance(value, str) or not value:
            continue
        path = Path(value)
        if path.is_absolute():
            candidate = path.resolve()
        else:
            relative = value.removeprefix("./")
            if relative.startswith("projects/"):
                relative = relative.removeprefix("projects/")
            candidate = Path(PROJECTS_BASE_DIR) / relative
        if candidate.is_dir():
            return candidate
    return None


def _pending_execution_plans(
    action: dict[str, Any],
    commands: dict[str, Any] | None,
):
    """Yield (scope, command) pairs; at most one command per validation scope."""
    if action.get("type") == "local_validation":
        scopes = _pending_scopes(action)
        if not scopes:
            # A local validation request without a scope is not executable;
            # keep the legacy payload for compatibility with older producers.
            yield None, None
            return
        if commands is None:
            # No workspace metadata (state-only callers): retain the legacy
            # payload so the action still reaches the Host queue.
            yield None, None
            return
        # Emit one scope at a time: a second action would carry the old
        # revision and be rejected once the first result advances the state.
        plan = next(
            ((scope, spec) for scope in scopes if (spec := commands.get(scope)) is not None),
            None,
        )
        if plan is None:
            # An executable action without a command fails plugin parsing and
            # aborts the whole poll, so it stays pending on the cloud side.
            logger.warning("agent host action skipped: no command for %s", action.get("type"))
            return
        yield plan
        return
    if action.get("type") in {"install_dependencies", "dependency_install"}:
        spec = commands.get("install") if commands else None
        if spec is None:
            if commands is None:
                yield None, None
                return
            logger.warning("agent host action skipped: no dependency command detected")
            return
        yield None, spec
        return
    # Non-executable actions keep their existing payload contract.
    yield None, None


def _validation_operation(action: Any, scope: str | None) -> str:
    from app.agent.toolchain import ToolchainAction

    if action is ToolchainAction.TEST:
        return "e2e_test" if scope == "local_e2e" else "unit_test"
    if action is ToolchainAction.BUILD:
        return "build"
    if action is ToolchainAction.INSTALL:
        return "dependency_install"
    if action in {ToolchainAction.LINT, ToolchainAction.FORMAT}:
        return "syntax_check"
    if action is ToolchainAction.TYPECHECK:
        return "build"
    if action in {ToolchainAction.SMOKE, ToolchainAction.HEALTH, ToolchainAction.START}:
        return "service_check"
    return "unit_test"


# Register the Host dispatcher so the agent layer can forward pending actions
# without importing this Web module.
register_state_action_dispatcher(enqueue_state_actions)


def _pending_action_capability(action: dict[str, Any]) -> str:
    """Map State actions to the Host capability that owns their execution."""
    capability = action.get("capability")
    if capability in {"file", "terminal", "validation", "diagnostics", "workspace"}:
        return capability
    action_type = action.get("type")
    if action_type == "file_sync":
        return "file"
    if action_type in {"install_dependencies", "dependency_install"}:
        return "terminal"
    return "validation"


def broadcast_user_skill_update(user_id: str) -> int:
    """Queue the latest private Skill snapshot for every active session of a user."""
    from app.services.custom_skill_manager import get_skill_manager

    manager = get_skill_manager()
    skills = {}
    for skill in manager.list_skills(owner_user_id=str(user_id)):
        detail = manager.get_skill(skill["name"], owner_user_id=str(user_id))
        if detail:
            skills[f"user:{skill['name']}"] = detail
    updated = 0
    for session_id, session in _sessions.items():
        if session.get("user_id") != str(user_id):
            continue
        _queue_session_action(session_id, session, {
            "kind": "tool_action",
            "capability": "skill_runtime",
            "payload": {"operation": "sync_user", "skills": skills},
        })
        _session_store.save(session_id, session)
        updated += 1
    return updated


def get_latest_session_skills(user_id: str) -> dict[str, dict[str, Any]]:
    """Return the newest non-expired workspace snapshot owned by a user."""
    now = datetime.now(timezone.utc)
    sessions = [
        session for session in _sessions.values()
        if session.get("user_id") == str(user_id) and now < session.get("expires_at", now)
    ]
    return dict(sessions[-1].get("skills", {})) if sessions else {}


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
    user_skills: dict[str, dict[str, Any]] = Field(default_factory=dict)


class AgentHostEnvelope(BaseModel):
    message_id: str = Field(min_length=1, max_length=256)
    schema_version: Literal[1]
    session_id: str = Field(min_length=1, max_length=256)
    task_id: str | None = None
    revision: int | None = Field(default=None, ge=0)
    kind: Literal["tool_action", "approval_request", "approval_decision", "progress_event", "diagnostic_event", "tool_result", "policy_update", "skill_revoke", "session_control"]
    capability: str | None = None
    policy_version: int | None = Field(default=None, ge=0)
    payload: dict[str, Any]


class AgentHostActionsResponse(BaseModel):
    actions: list[dict[str, Any]]


class AgentHostActionAckRequest(BaseModel):
    action_id: str = Field(min_length=1, max_length=256)


class AgentHostEventResponse(BaseModel):
    accepted: bool
    duplicate: bool = False
    state_status: str | None = None


class PolicyUpdateRequest(BaseModel):
    expected_policy_version: int = Field(ge=0)
    policy: dict[str, Any]


class PolicyUpdateResponse(BaseModel):
    policy_version: int
    policy: dict[str, Any]


class SkillSyncRequest(BaseModel):
    skills: dict[str, dict[str, Any]]


class AgentHostSessionSummary(BaseModel):
    session_id: str
    workspace_id: str
    control_status: str
    skills: dict[str, dict[str, Any]]
    expires_at: str


class SessionControlRequest(BaseModel):
    action: Literal["pause", "resume", "cancel"]


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

    _prune_expired_sessions()

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
        "in_flight_actions": [],
        "events": {},
        "skills": {},
        "control_status": "active",
    }
    _session_store.save(session_id, _sessions[session_id])
    from app.services.custom_skill_manager import get_skill_manager
    user_id = str(token.get("sub", ""))
    user_skills = {
        f"user:{skill['name']}": {**skill, "content": get_skill_manager().get_skill(skill["name"], owner_user_id=user_id)["content"]}
        for skill in get_skill_manager().list_skills(owner_user_id=user_id)
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
        user_skills=user_skills,
    )


def _get_session(session_id: str, token: dict) -> dict[str, Any]:
    session = _sessions.get(session_id)
    restored = session is None
    session = session or _session_store.load(session_id)
    if session is None or session["user_id"] != str(token.get("sub", "")):
        raise HTTPException(status_code=404, detail="agent host session not found")
    if datetime.now(timezone.utc) >= session["expires_at"]:
        _sessions.pop(session_id, None)
        raise HTTPException(status_code=410, detail="agent host session expired")
    session.setdefault("skills", {})
    session.setdefault("control_status", "active")
    session.setdefault("in_flight_actions", [])
    if restored and session["in_flight_actions"]:
        session["pending_actions"] = [
            *session.get("pending_actions", []),
            *session.pop("in_flight_actions"),
        ]
    _sessions[session_id] = session
    return session


@router.get("/agent/host/sessions", response_model=list[AgentHostSessionSummary])
async def list_agent_host_sessions(token: dict = Depends(verify_token)) -> list[AgentHostSessionSummary]:
    user_id = str(token.get("sub", ""))
    summaries = []
    session_ids = set(_sessions)
    session_ids.update(path.stem for path in _session_store.directory.glob("*.json"))
    for session_id in session_ids:
        session = _sessions.get(session_id) or _session_store.load(session_id)
        if session is None:
            continue
        if session.get("user_id") != user_id:
            continue
        if datetime.now(timezone.utc) >= session["expires_at"]:
            continue
        _sessions[session_id] = session
        summaries.append(AgentHostSessionSummary(
            session_id=session_id,
            workspace_id=session["workspace_id"],
            control_status=session.get("control_status", "active"),
            skills=session.get("skills", {}),
            expires_at=session["expires_at"].isoformat(),
        ))
    return summaries


@router.get("/agent/host/sessions/{session_id}/actions", response_model=AgentHostActionsResponse)
async def get_agent_host_actions(session_id: str, token: dict = Depends(verify_token)) -> AgentHostActionsResponse:
    session = _get_session(session_id, token)
    actions = list(session["pending_actions"])
    session.setdefault("in_flight_actions", [])
    session["pending_actions"] = []
    session["in_flight_actions"].extend(actions)
    _session_store.save(session_id, session)
    return AgentHostActionsResponse(actions=actions)


@router.post("/agent/host/sessions/{session_id}/actions/ack")
async def acknowledge_agent_host_action(
    session_id: str,
    request: AgentHostActionAckRequest,
    token: dict = Depends(verify_token),
) -> dict[str, Any]:
    session = _get_session(session_id, token)
    session.setdefault("in_flight_actions", [])
    before = len(session["in_flight_actions"])
    session["in_flight_actions"] = [
        action for action in session["in_flight_actions"]
        if action.get("payload", {}).get("action_id") != request.action_id
        and action.get("message_id") != request.action_id
    ]
    _session_store.save(session_id, session)
    return {"acknowledged": len(session["in_flight_actions"]) < before, "action_id": request.action_id}


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
    state_status = None
    if event.kind == "tool_result":
        from app.agent.workflow_registry import resume_workflow_from_local_result

        if not event.task_id or event.revision is None:
            raise HTTPException(status_code=422, detail="tool_result requires task_id and revision")
        # Actions live on the Host session, while workflow checkpoints are keyed
        # by the stable conversation id bound during orchestration.
        workflow_session_id = str(session.get("workflow_session_id") or session_id)
        result = {
            **event.payload,
            "event_id": event.message_id,
            "schema_version": event.schema_version,
            "session_id": workflow_session_id,
            "task_id": event.task_id,
            "revision": event.revision,
            "source": "local",
        }
        try:
            state = await resume_workflow_from_local_result(
                session_id=workflow_session_id,
                task_id=event.task_id,
                result=result,
            )
        except KeyError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        except (TypeError, ValueError, RuntimeError) as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        state_status = state.status
    session["events"][event.message_id] = _dump_model(event)
    if event.kind == "tool_result" and event.message_id.endswith(":result"):
        source_message_id = event.message_id.removesuffix(":result")
        session["pending_actions"] = [
            action for action in session["pending_actions"]
            if action.get("message_id") != source_message_id
        ]
        session["in_flight_actions"] = [
            action for action in session.get("in_flight_actions", [])
            if action.get("message_id") != source_message_id
        ]
    _session_store.save(session_id, session)
    return AgentHostEventResponse(accepted=True, state_status=state_status)


@router.post("/agent/host/sessions/{session_id}/heartbeat")
async def agent_host_heartbeat(
    session_id: str,
    token: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    session = _get_session(session_id, token)
    user_id = token.get("sub")
    if not isinstance(user_id, str) or not user_id.isdigit():
        raise HTTPException(status_code=403, detail="无效的用户身份，请重新登录")
    project = await db.scalar(
        select(ProjectSession).where(
            ProjectSession.session_id == session.get("workspace_id"),
            ProjectSession.user_id == int(user_id),
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="关联项目不存在")
    project.last_activity_at = datetime.now(timezone.utc)
    project.lifecycle_status = "active"
    await db.commit()
    return {"session_id": session_id, "project_session_id": project.session_id, "status": "active"}


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
    _session_store.save(session_id, session)
    return PolicyUpdateResponse(policy_version=next_version, policy=request.policy)


def _queue_session_action(session_id: str, session: dict[str, Any], action: dict[str, Any]) -> None:
    envelope = {
        "message_id": str(uuid4()),
        "schema_version": SUPPORTED_PROTOCOL_VERSION,
        "session_id": session_id,
        "kind": action["kind"],
        "policy_version": session["policy_version"],
        "payload": action["payload"],
    }
    if action.get("capability") is not None:
        envelope["capability"] = action["capability"]
    session["pending_actions"].append(envelope)


@router.put("/agent/host/sessions/{session_id}/skills")
async def sync_agent_host_skills(
    session_id: str,
    request: SkillSyncRequest,
    token: dict = Depends(verify_token),
) -> dict[str, Any]:
    session = _get_session(session_id, token)
    session["skills"] = request.skills
    _queue_session_action(session_id, session, {
        "kind": "tool_action",
        "capability": "skill_runtime",
        "payload": {"operation": "sync", "skills": request.skills},
    })
    _session_store.save(session_id, session)
    return {"skills": session["skills"], "policy_version": session["policy_version"]}


@router.delete("/agent/host/sessions/{session_id}/skills/{skill_name}")
async def revoke_agent_host_skill(
    session_id: str,
    skill_name: str,
    token: dict = Depends(verify_token),
) -> dict[str, Any]:
    session = _get_session(session_id, token)
    session["skills"].pop(skill_name, None)
    _queue_session_action(session_id, session, {
        "kind": "skill_revoke",
        "capability": "skill_runtime",
        "payload": {"skill_name": skill_name},
    })
    _session_store.save(session_id, session)
    return {"skills": session["skills"]}


@router.post("/agent/host/sessions/{session_id}/control")
async def control_agent_host_session(
    session_id: str,
    request: SessionControlRequest,
    token: dict = Depends(verify_token),
) -> dict[str, str]:
    session = _get_session(session_id, token)
    if request.action == "cancel":
        session["control_status"] = "cancelled"
    elif request.action == "pause":
        session["control_status"] = "paused"
    else:
        session["control_status"] = "active"
    _queue_session_action(session_id, session, {
        "kind": "session_control",
        "payload": {"action": request.action},
    })
    _session_store.save(session_id, session)
    return {"status": session["control_status"]}
