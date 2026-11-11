from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.api.v1.agent_host import (
    AgentHostSessionStore,
    AgentHostEnvelope,
    HostHandshakeRequest,
    agent_host_handshake,
    bind_workflow_session,
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
    list_agent_host_sessions,
    AgentHostActionAckRequest,
    acknowledge_agent_host_action,
    agent_host_heartbeat,
    _prune_expired_sessions,
)
from app.agent.host_action_dispatch import dispatch_state_actions
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.models import ProjectSession
from app.models.base import Base
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
    assert (await get_agent_host_actions(handshake.session_id, {"sub": "user-3"})).actions == []
    ack = await acknowledge_agent_host_action(
        handshake.session_id,
        AgentHostActionAckRequest(action_id="pending-1"),
        {"sub": "user-3"},
    )
    assert ack["acknowledged"] is True


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


@pytest.mark.asyncio
async def test_enqueue_state_actions_translates_validation_commands(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "projects" / "user-commands" / "demo"
    workspace.mkdir(parents=True)
    (workspace / "package.json").write_text(
        '{"scripts": {"test": "node --test", "build": "tsc -p ."}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR",
        str(tmp_path / "projects"),
    )
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-commands",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["validation"],
        ),
        {"sub": "user-commands"},
    )
    state = {
        "session_id": handshake.session_id,
        "task_id": "task-commands",
        "revision": 3,
        "metadata": {"output_dir": "user-commands/demo"},
        "pending_actions": [{
            "type": "local_validation",
            "action_id": "action-commands",
            "scopes": ["local_runtime"],
        }],
    }

    assert enqueue_state_actions(handshake.session_id, state) == 1

    action = (await get_agent_host_actions(handshake.session_id, {"sub": "user-commands"})).actions[0]
    payload = action["payload"]
    assert payload["event_id"] == action["message_id"]
    assert payload["session_id"] == handshake.session_id
    assert payload["workspace_id"] == "workspace-commands"
    assert payload["validation_scope"] == "local_runtime"
    assert payload["operation"] == "unit_test"
    assert payload["command"] == ["npm", "run", "test"]
    assert payload["working_directory"] == "."
    assert payload["timeout_seconds"] > 0
    assert payload["requested_by"] == "cloud"


@pytest.mark.asyncio
async def test_bound_workflow_session_routes_actions_to_host_queue() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-bound",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["validation"],
        ),
        {"sub": "user-bound"},
    )
    conversation_id = "vscode-agent-bound-conversation"
    bind_workflow_session(conversation_id, handshake.session_id, "user-bound")
    state = {
        "session_id": conversation_id,
        "task_id": "task-bound",
        "pending_actions": [{
            "type": "local_validation",
            "action_id": "action-bound",
            "scope": "local_runtime",
        }],
    }

    assert enqueue_state_actions(conversation_id, state) == 1

    actions = (await get_agent_host_actions(handshake.session_id, {"sub": "user-bound"})).actions
    assert actions[0]["session_id"] == handshake.session_id
    assert actions[0]["payload"]["action_id"] == "action-bound"


@pytest.mark.asyncio
async def test_enqueue_state_actions_skips_validation_without_detected_command(
    monkeypatch,
    tmp_path,
) -> None:
    workspace = tmp_path / "projects" / "user-empty" / "demo"
    workspace.mkdir(parents=True)
    monkeypatch.setattr(
        "app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR",
        str(tmp_path / "projects"),
    )
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-empty",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["validation"],
        ),
        {"sub": "user-empty"},
    )
    state = {
        "session_id": handshake.session_id,
        "task_id": "task-empty",
        "metadata": {"output_dir": "projects/user-empty/demo"},
        "pending_actions": [{
            "type": "local_validation",
            "action_id": "action-empty",
            "scopes": ["local_runtime"],
        }],
    }

    assert enqueue_state_actions(handshake.session_id, state) == 0
    assert (
        await get_agent_host_actions(handshake.session_id, {"sub": "user-empty"})
    ).actions == []


@pytest.mark.asyncio
async def test_enqueue_state_actions_translates_dependency_install(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "projects" / "user-install" / "demo"
    workspace.mkdir(parents=True)
    (workspace / "requirements.txt").write_text("fastapi\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR",
        str(tmp_path / "projects"),
    )
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-install",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["terminal"],
        ),
        {"sub": "user-install"},
    )
    state = {
        "session_id": handshake.session_id,
        "task_id": "task-install",
        "metadata": {"project_path": "user-install/demo"},
        "pending_actions": [{"type": "install_dependencies", "action_id": "action-install"}],
    }

    assert enqueue_state_actions(handshake.session_id, state) == 1

    payload = (
        await get_agent_host_actions(handshake.session_id, {"sub": "user-install"})
    ).actions[0]["payload"]
    assert payload["operation"] == "dependency_install"
    assert payload["command"] == ["python3", "-m", "pip", "install", "-r", "requirements.txt"]
    assert payload["timeout_seconds"] == 600


def test_bind_workflow_session_rejects_foreign_host_session() -> None:
    with pytest.raises(KeyError):
        bind_workflow_session("conversation", "missing-host-session", "user")


def test_dispatch_state_actions_ignores_session_mismatch() -> None:
    class State:
        def to_dict(self):
            return {"session_id": "other", "pending_actions": []}

    session_id = "vscode-agent-mismatch"
    from app.api.v1 import agent_host

    agent_host._sessions[session_id] = {
        "user_id": "user",
        "workspace_id": "workspace",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
        "policy_version": 1,
        "policy": {},
        "pending_actions": [],
        "in_flight_actions": [],
        "events": {},
    }
    try:
        dispatch_state_actions(session_id, State())
    finally:
        agent_host._sessions.pop(session_id, None)


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
async def test_agent_host_session_list_loads_persisted_sessions(monkeypatch, tmp_path) -> None:
    store = AgentHostSessionStore(tmp_path)
    session_id = "persisted-session"
    store.save(session_id, {
        "user_id": "user-persisted",
        "workspace_id": "workspace-persisted",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
        "policy_version": 1,
        "policy": {},
        "pending_actions": [],
        "events": {},
    })
    monkeypatch.setattr("app.api.v1.agent_host._session_store", store)
    monkeypatch.setattr("app.api.v1.agent_host._sessions", {})

    summaries = await list_agent_host_sessions({"sub": "user-persisted"})

    assert [summary.session_id for summary in summaries] == [session_id]


@pytest.mark.asyncio
async def test_agent_host_requeues_in_flight_actions_after_restart(monkeypatch, tmp_path) -> None:
    store = AgentHostSessionStore(tmp_path)
    session_id = "restart-session"
    store.save(session_id, {
        "user_id": "user-restart",
        "workspace_id": "workspace-restart",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
        "policy_version": 1,
        "policy": {},
        "pending_actions": [],
        "in_flight_actions": [{
            "message_id": "action-message",
            "payload": {"action_id": "action-retry"},
        }],
        "events": {},
    })
    monkeypatch.setattr("app.api.v1.agent_host._session_store", store)
    monkeypatch.setattr("app.api.v1.agent_host._sessions", {})

    actions = await get_agent_host_actions(session_id, {"sub": "user-restart"})

    assert [item["payload"]["action_id"] for item in actions.actions] == ["action-retry"]


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
async def test_tool_result_resumes_bound_workflow_session() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-bound-resume",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["validation"],
        ),
        {"sub": "user-bound-resume"},
    )
    conversation_id = "vscode-agent-bound-resume"
    bind_workflow_session(conversation_id, handshake.session_id, "user-bound-resume")

    async def create_action(_state):
        return StateDelta(
            expected_revision=0,
            status="waiting_local_validation",
            pending_actions=[{
                "type": "local_validation",
                "action_id": "workflow-action-bound",
                "scope": "local_runtime",
            }],
            metadata={"required_validation_scopes": ["local_runtime"]},
        )

    definition = WorkflowDefinition(
        name="bound-resume-test",
        entry_node="create_action",
        graph=StateGraphBuilder().add_node("create_action", create_action).compile(),
        legacy_endpoint="test",
    )
    await run_workflow(definition, session_id=conversation_id, task_id="task-bound-resume")
    action = (
        await get_agent_host_actions(handshake.session_id, {"sub": "user-bound-resume"})
    ).actions[0]
    assert action["payload"]["session_id"] == handshake.session_id

    response = await post_agent_host_event(
        handshake.session_id,
        AgentHostEnvelope(
            message_id=f"{action['message_id']}:result",
            schema_version=1,
            session_id=handshake.session_id,
            task_id="task-bound-resume",
            revision=1,
            kind="tool_result",
            capability="validation",
            policy_version=1,
            payload={
                "validation_scope": "local_runtime",
                "status": "passed",
                "summary": {"tests_passed": 2},
            },
        ),
        {"sub": "user-bound-resume"},
    )

    assert response.state_status == "completed"


@pytest.mark.asyncio
async def test_multiple_validation_scopes_run_one_round_at_a_time(monkeypatch, tmp_path) -> None:
    workspace = tmp_path / "projects" / "user-scopes" / "demo"
    workspace.mkdir(parents=True)
    (workspace / "package.json").write_text(
        '{"scripts": {"test": "node --test"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR",
        str(tmp_path / "projects"),
    )
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-scopes",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["validation"],
        ),
        {"sub": "user-scopes"},
    )
    conversation_id = "vscode-agent-multi-scope"
    bind_workflow_session(conversation_id, handshake.session_id, "user-scopes")

    async def create_action(_state):
        return StateDelta(
            expected_revision=0,
            status="waiting_local_validation",
            pending_actions=[{
                "type": "local_validation",
                "action_id": "workflow-action-scopes",
                "scopes": ["local_runtime", "local_e2e"],
            }],
            metadata={"required_validation_scopes": ["local_runtime", "local_e2e"]},
        )

    definition = WorkflowDefinition(
        name="multi-scope-test",
        entry_node="create_action",
        graph=StateGraphBuilder().add_node("create_action", create_action).compile(),
        legacy_endpoint="test",
    )
    await run_workflow(
        definition,
        session_id=conversation_id,
        task_id="task-multi-scope",
        metadata={
            "output_dir": "user-scopes/demo",
            "required_validation_scopes": ["local_runtime", "local_e2e"],
        },
    )

    for expected_scope in ("local_runtime", "local_e2e"):
        actions = (
            await get_agent_host_actions(handshake.session_id, {"sub": "user-scopes"})
        ).actions
        assert len(actions) == 1
        action = actions[0]
        assert action["payload"]["validation_scope"] == expected_scope
        response = await post_agent_host_event(
            handshake.session_id,
            AgentHostEnvelope(
                message_id=f"{action['message_id']}:result",
                schema_version=1,
                session_id=handshake.session_id,
                task_id="task-multi-scope",
                revision=action["revision"],
                kind="tool_result",
                capability="validation",
                policy_version=1,
                payload={
                    "validation_scope": expected_scope,
                    "status": "passed",
                    "summary": {"tests_passed": 1},
                },
            ),
            {"sub": "user-scopes"},
        )
        assert response.accepted is True

    assert response.state_status == "completed"
    assert (
        await get_agent_host_actions(handshake.session_id, {"sub": "user-scopes"})
    ).actions == []


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


@pytest.fixture
async def host_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_agent_host_heartbeat_marks_project_active(host_db) -> None:
    stale = datetime.now(timezone.utc) - timedelta(hours=3)
    project = ProjectSession(
        session_id="host-project-7",
        user_id="7",
        requirement="keep alive",
        output_dir="7/host-project-7",
        status="completed",
        lifecycle_status="idle",
        last_activity_at=stale,
    )
    host_db.add(project)
    await host_db.flush()

    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="host-project-7",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["workspace"],
        ),
        {"sub": "7"},
    )
    result = await agent_host_heartbeat(handshake.session_id, {"sub": "7"}, host_db)
    await host_db.refresh(project)

    assert result["session_id"] == handshake.session_id
    assert result["project_session_id"] == "host-project-7"
    assert result["status"] == "active"
    assert project.lifecycle_status == "active"
    assert project.last_activity_at.replace(tzinfo=None) > stale.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_agent_host_heartbeat_requires_owned_project(host_db) -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="missing-project",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["workspace"],
        ),
        {"sub": "7"},
    )

    with pytest.raises(HTTPException) as error:
        await agent_host_heartbeat(handshake.session_id, {"sub": "7"}, host_db)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_agent_host_heartbeat_rejects_non_numeric_user() -> None:
    handshake = await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-non-numeric",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["workspace"],
        ),
        {"sub": "user-1"},
    )

    with pytest.raises(HTTPException) as error:
        await agent_host_heartbeat(handshake.session_id, {"sub": "user-1"}, None)
    assert error.value.status_code == 403


def test_prune_expired_sessions_drops_memory_and_files(monkeypatch, tmp_path) -> None:
    """握手会话 30 分钟过期后必须同时从内存与磁盘清除。"""

    from app.api.v1 import agent_host

    store = AgentHostSessionStore(tmp_path)
    now = datetime.now(timezone.utc)
    stale = {
        "user_id": "7",
        "workspace_id": "w",
        "expires_at": now - timedelta(minutes=1),
        "pending_actions": [],
        "in_flight_actions": [],
        "events": {},
        "skills": {},
    }
    fresh = {
        **stale,
        "expires_at": now + timedelta(minutes=5),
    }

    for session_id, payload in (("stale", stale), ("fresh", fresh)):
        store.save(session_id, payload)

    monkeypatch.setattr(agent_host, "_session_store", store)
    monkeypatch.setattr(agent_host, "_sessions", {"stale": dict(stale), "fresh": dict(fresh)})
    monkeypatch.setattr(agent_host, "_last_prune_at", 0.0)

    removed = _prune_expired_sessions(now=now)

    assert removed == 1
    assert "stale" not in agent_host._sessions
    assert "fresh" in agent_host._sessions
    assert not (tmp_path / "stale.json").exists()
    assert (tmp_path / "fresh.json").exists()


@pytest.mark.asyncio
async def test_handshake_prunes_expired_sessions(monkeypatch, tmp_path) -> None:
    """握手入口必须触发过期清扫，否则过期会话永不回收。"""

    from app.api.v1 import agent_host

    store = AgentHostSessionStore(tmp_path)
    now = datetime.now(timezone.utc)
    stale = {
        "user_id": "7",
        "workspace_id": "w",
        "expires_at": now - timedelta(minutes=1),
        "pending_actions": [],
        "in_flight_actions": [],
        "events": {},
        "skills": {},
    }
    store.save("stale", stale)

    monkeypatch.setattr(agent_host, "_session_store", store)
    monkeypatch.setattr(agent_host, "_sessions", {"stale": dict(stale)})
    monkeypatch.setattr(agent_host, "_last_prune_at", 0.0)

    await agent_host_handshake(
        HostHandshakeRequest(
            workspace_id="workspace-prune",
            extension_version="0.1.0",
            protocol_versions=[1],
            capabilities=["workspace"],
        ),
        {"sub": "7"},
    )

    assert "stale" not in agent_host._sessions
    assert not (tmp_path / "stale.json").exists()


@pytest.mark.asyncio
async def test_authenticated_traffic_slides_host_session_expiry(monkeypatch, tmp_path) -> None:
    """活跃会话应滑动续期，避免 30 分钟边界把正在轮询的插件踢下线。"""

    from app.api.v1 import agent_host

    store = AgentHostSessionStore(tmp_path)
    session_id = "sliding-session"
    now = datetime.now(timezone.utc)
    near_expiry = now + timedelta(minutes=1)
    store.save(session_id, {
        "user_id": "user-slide",
        "workspace_id": "workspace-slide",
        "expires_at": near_expiry,
        "policy_version": 1,
        "policy": {},
        "pending_actions": [],
        "in_flight_actions": [],
        "events": {},
        "skills": {},
    })
    monkeypatch.setattr(agent_host, "_session_store", store)
    monkeypatch.setattr(agent_host, "_sessions", {})

    actions = await get_agent_host_actions(session_id, {"sub": "user-slide"})

    assert actions.actions == []
    refreshed = store.load(session_id)
    assert refreshed["expires_at"] > near_expiry
    assert refreshed["expires_at"] - now >= timedelta(minutes=29)


@pytest.mark.asyncio
async def test_expired_session_still_rejected_when_sliding(monkeypatch, tmp_path) -> None:
    """滑动续期只对未过期会话生效，过期会话仍返回 410。"""

    from app.api.v1 import agent_host

    store = AgentHostSessionStore(tmp_path)
    session_id = "expired-session"
    store.save(session_id, {
        "user_id": "user-expired",
        "workspace_id": "workspace-expired",
        "expires_at": datetime.now(timezone.utc) - timedelta(seconds=1),
        "policy_version": 1,
        "policy": {},
        "pending_actions": [],
        "in_flight_actions": [],
        "events": {},
        "skills": {},
    })
    monkeypatch.setattr(agent_host, "_session_store", store)
    monkeypatch.setattr(agent_host, "_sessions", {})

    with pytest.raises(HTTPException) as exc_info:
        await get_agent_host_actions(session_id, {"sub": "user-expired"})

    assert exc_info.value.status_code == 410
