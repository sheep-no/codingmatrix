"""Branch coverage for Agent Host session lifecycle and event handling."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api.v1 import agent_host
from app.api.v1.agent_host import (
    AgentHostActionAckRequest,
    AgentHostEnvelope,
    AgentHostSessionStore,
    HostHandshakeRequest,
    PolicyUpdateRequest,
    SessionControlRequest,
    acknowledge_agent_host_action,
    agent_host_handshake,
    bind_workflow_session,
    broadcast_user_skill_update,
    control_agent_host_session,
    enqueue_state_actions,
    get_agent_host_actions,
    get_latest_session_skills,
    list_agent_host_sessions,
    post_agent_host_event,
    get_agent_host_actions,
    sync_agent_host_skills,
    revoke_agent_host_skill,
    update_agent_host_policy,
)


def _session_payload(user_id="u", **overrides):
    payload = {
        "user_id": user_id,
        "workspace_id": "w",
        "expires_at": datetime.now(timezone.utc) + timedelta(minutes=30),
        "policy_version": 1,
        "policy": {},
        "pending_actions": [],
        "in_flight_actions": [],
        "events": {},
        "skills": {},
        "control_status": "active",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def store(tmp_path, monkeypatch):
    instance = AgentHostSessionStore(tmp_path)
    monkeypatch.setattr(agent_host, "_session_store", instance)
    monkeypatch.setattr(agent_host, "_sessions", {})
    monkeypatch.setattr(agent_host, "_last_prune_at", agent_host._last_prune_at)
    return instance


class TestSessionStoreValidation:
    def test_rejects_unsafe_session_ids(self, tmp_path):
        store = AgentHostSessionStore(tmp_path)

        with pytest.raises(ValueError):
            store.load("")
        with pytest.raises(ValueError):
            store.load("../escape")
        with pytest.raises(ValueError):
            store.save("nested/id", _session_payload())

    def test_save_failure_removes_temporary_file(self, tmp_path, monkeypatch):
        store = AgentHostSessionStore(tmp_path)
        monkeypatch.setattr(agent_host.os, "replace", lambda *args: (_ for _ in ()).throw(OSError("disk")))

        with pytest.raises(OSError):
            store.save("s", _session_payload())

        assert list(tmp_path.iterdir()) == []


class TestPruneBranches:
    def test_skips_when_interval_not_elapsed(self, store, monkeypatch):
        monkeypatch.setattr(agent_host, "_last_prune_at", agent_host.time.monotonic())
        store.save("live", _session_payload())
        agent_host._sessions["live"] = _session_payload()

        assert agent_host._prune_expired_sessions() == 0
        assert "live" in agent_host._sessions

    def test_unreadable_store_files_are_skipped(self, store, monkeypatch):
        (store.directory / "broken.json").write_text("not json", encoding="utf-8")

        assert agent_host._prune_expired_sessions(now=datetime.now(timezone.utc)) == 0
        assert (store.directory / "broken.json").exists()

    def test_unlink_failure_is_swallowed(self, store, monkeypatch):
        stale = _session_payload(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
        store.save("stale", stale)
        monkeypatch.setattr(agent_host.Path, "unlink", lambda self, *a, **k: (_ for _ in ()).throw(OSError("busy")))

        assert agent_host._prune_expired_sessions(now=datetime.now(timezone.utc)) == 0

    def test_removes_expired_memory_and_disk_sessions(self, store):
        now = datetime.now(timezone.utc)
        agent_host._sessions["live"] = _session_payload(expires_at=now + timedelta(minutes=5))
        agent_host._sessions["gone"] = _session_payload(expires_at=now - timedelta(minutes=5))
        store.save("disk-live", _session_payload(expires_at=now + timedelta(minutes=5)))
        store.save("disk-gone", _session_payload(expires_at=now - timedelta(minutes=5)))

        assert agent_host._prune_expired_sessions(now=now) == 1

        assert "gone" not in agent_host._sessions
        assert "disk-live" in {p.stem for p in store.directory.glob("*.json")}
        assert "disk-gone" not in {p.stem for p in store.directory.glob("*.json")}


class TestEnqueueBranches:
    @pytest.mark.asyncio
    async def test_unknown_session_raises(self, store):
        with pytest.raises(KeyError, match="not found"):
            enqueue_state_actions("missing", {"pending_actions": []})

    @pytest.mark.asyncio
    async def test_expired_session_raises(self, store):
        agent_host._sessions["expired"] = _session_payload(
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )

        with pytest.raises(KeyError, match="expired"):
            enqueue_state_actions("expired", {"pending_actions": []})

        assert "expired" not in agent_host._sessions

    @pytest.mark.asyncio
    async def test_state_session_mismatch_raises(self, store):
        agent_host._sessions["host"] = _session_payload()

        with pytest.raises(ValueError, match="does not match"):
            enqueue_state_actions("host", {"session_id": "other", "pending_actions": []})

    @pytest.mark.asyncio
    async def test_bound_workflow_mismatch_raises(self, store):
        agent_host._sessions["host"] = _session_payload(workflow_session_id="conversation")

        with pytest.raises(ValueError, match="does not match"):
            enqueue_state_actions("host", {"session_id": "host", "pending_actions": []})

    @pytest.mark.asyncio
    async def test_non_dict_pending_action_is_skipped(self, store):
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host", {"pending_actions": ["nope", {"type": "file_sync"}]}
        )

        assert added == 1

    @pytest.mark.asyncio
    async def test_install_without_workspace_keeps_legacy_payload(self, store):
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host",
            {
                "pending_actions": [
                    {"type": "install_dependencies", "action_id": "install"}
                ]
            },
        )

        assert added == 1
        action = agent_host._sessions["host"]["pending_actions"][0]
        assert "command" not in action["payload"]

    @pytest.mark.asyncio
    async def test_install_without_detected_command_is_skipped(self, store, tmp_path, monkeypatch):
        workspace = tmp_path / "empty"
        workspace.mkdir()
        monkeypatch.setattr(
            "app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR", str(tmp_path)
        )
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host",
            {
                "metadata": {"project_path": str(workspace)},
                "pending_actions": [
                    {"type": "dependency_install", "action_id": "install"}
                ],
            },
        )

        assert added == 0

    @pytest.mark.asyncio
    async def test_toolchain_detection_failure_is_skipped(self, store, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        workspace.mkdir()

        def boom(path):
            raise OSError("no toolchain")

        monkeypatch.setattr("app.agent.toolchain.detect_toolchain", boom)
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host",
            {
                "metadata": {"project_path": str(workspace)},
                "pending_actions": [
                    {"type": "local_validation", "action_id": "v", "scopes": ["local_runtime"]}
                ],
            },
        )

        assert added == 1
        assert "command" not in agent_host._sessions["host"]["pending_actions"][0]["payload"]

    @pytest.mark.asyncio
    async def test_local_validation_without_scope_keeps_legacy_payload(self, store, tmp_path, monkeypatch):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host",
            {
                "metadata": {"project_path": str(workspace)},
                "pending_actions": [
                    {"type": "local_validation", "action_id": "v"}
                ],
            },
        )

        assert added == 1

    def test_pending_scopes_string_and_unknown(self):
        assert agent_host._pending_scopes({"scope": "local_runtime"}) == ["local_runtime"]
        assert agent_host._pending_scopes({"scopes": ["nope"]}) == []

    @pytest.mark.parametrize(
        ("action", "scope", "operation"),
        [
            ("test", "local_e2e", "e2e_test"),
            ("test", "local_runtime", "unit_test"),
            ("build", None, "build"),
            ("install", None, "dependency_install"),
            ("lint", None, "syntax_check"),
            ("format", None, "syntax_check"),
            ("typecheck", None, "build"),
            ("smoke", None, "service_check"),
            ("health", None, "service_check"),
            ("start", None, "service_check"),
            ("inspect", None, "unit_test"),
        ],
    )
    def test_validation_operation_mapping(self, action, scope, operation):
        from app.agent.toolchain import ToolchainAction

        assert agent_host._validation_operation(ToolchainAction(action), scope) == operation

    @pytest.mark.parametrize(
        ("action", "expected"),
        [
            ({"capability": "file"}, "file"),
            ({"type": "file_sync"}, "file"),
            ({"type": "dependency_install"}, "terminal"),
            ({"type": "unknown"}, "validation"),
        ],
    )
    def test_pending_action_capability(self, action, expected):
        assert agent_host._pending_action_capability(action) == expected

    @pytest.mark.asyncio
    async def test_duplicate_existing_action_is_not_requeued(self, store):
        agent_host._sessions["host"] = _session_payload(
            pending_actions=[{"payload": {"action_id": "a"}}]
        )

        added = enqueue_state_actions(
            "host", {"pending_actions": [{"type": "file_sync", "action_id": "a"}]}
        )

        assert added == 0

    @pytest.mark.asyncio
    async def test_local_validation_with_detected_command_emits_executable_action(
        self, store, tmp_path, monkeypatch
    ):
        from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainProbePlan

        plan = ToolchainProbePlan(
            workspace=str(tmp_path),
            commands=(
                CommandSpec(action=ToolchainAction.TEST, command=("pytest", "-q")),
            ),
        )
        monkeypatch.setattr("app.agent.toolchain.detect_toolchain", lambda path: plan)
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host",
            {
                "metadata": {"project_path": str(tmp_path)},
                "pending_actions": [
                    {"type": "local_validation", "action_id": "v", "scopes": ["local_runtime"]}
                ],
            },
        )

        assert added == 1
        payload = agent_host._sessions["host"]["pending_actions"][0]["payload"]
        assert payload["operation"] == "unit_test"
        assert payload["command"] == ["pytest", "-q"]

    @pytest.mark.asyncio
    async def test_local_validation_without_matching_command_is_skipped(
        self, store, tmp_path, monkeypatch
    ):
        from app.agent.toolchain import ToolchainProbePlan

        monkeypatch.setattr(
            "app.agent.toolchain.detect_toolchain",
            lambda path: ToolchainProbePlan(workspace=str(tmp_path)),
        )
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host",
            {
                "metadata": {"project_path": str(tmp_path)},
                "pending_actions": [
                    {"type": "local_validation", "action_id": "v", "scopes": ["local_runtime"]}
                ],
            },
        )

        assert added == 0

    @pytest.mark.asyncio
    async def test_install_action_emits_dependency_command(self, store, tmp_path, monkeypatch):
        from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainProbePlan

        plan = ToolchainProbePlan(
            workspace=str(tmp_path),
            commands=(
                CommandSpec(action=ToolchainAction.INSTALL, command=("pip", "install", "-r", "requirements.txt")),
            ),
        )
        monkeypatch.setattr("app.agent.toolchain.detect_toolchain", lambda path: plan)
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host",
            {
                "metadata": {"project_path": str(tmp_path)},
                "pending_actions": [
                    {"type": "dependency_install", "action_id": "i"}
                ],
            },
        )

        assert added == 1
        payload = agent_host._sessions["host"]["pending_actions"][0]["payload"]
        assert payload["operation"] == "dependency_install"

    @pytest.mark.asyncio
    async def test_install_action_without_command_is_skipped(self, store, tmp_path, monkeypatch):
        from app.agent.toolchain import ToolchainProbePlan

        monkeypatch.setattr(
            "app.agent.toolchain.detect_toolchain",
            lambda path: ToolchainProbePlan(workspace=str(tmp_path)),
        )
        agent_host._sessions["host"] = _session_payload()

        added = enqueue_state_actions(
            "host",
            {
                "metadata": {"project_path": str(tmp_path)},
                "pending_actions": [
                    {"type": "install_dependencies", "action_id": "i"}
                ],
            },
        )

        assert added == 0


class TestWorkspaceDirectory:
    def test_absolute_path(self, tmp_path):
        assert agent_host._workspace_directory({"project_path": str(tmp_path)}) == tmp_path.resolve()

    def test_missing_or_non_string_metadata(self, tmp_path):
        assert agent_host._workspace_directory({}) is None
        assert agent_host._workspace_directory({"project_path": ""}) is None
        assert agent_host._workspace_directory({"output_dir": 123}) is None
        assert agent_host._workspace_directory({"output_dir": "does/not/exist"}) is None

    def test_relative_project_path_under_projects(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "app.api.v1.ai_agent.project_config.PROJECTS_BASE_DIR", str(tmp_path)
        )
        (tmp_path / "demo").mkdir()

        assert agent_host._workspace_directory({"output_dir": "projects/demo"}) == tmp_path / "demo"
        assert agent_host._workspace_directory({"output_dir": "./demo"}) == tmp_path / "demo"


class TestBindWorkflowBranches:
    def test_requires_both_ids(self, store):
        with pytest.raises(KeyError, match="required"):
            bind_workflow_session("", "host", "u")

    def test_unknown_session_raises(self, store):
        with pytest.raises(KeyError, match="not found"):
            bind_workflow_session("conversation", "missing", "u")

    def test_expired_session_raises(self, store):
        agent_host._sessions["host"] = _session_payload(
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )

        with pytest.raises(KeyError, match="expired"):
            bind_workflow_session("conversation", "host", "u")
        assert "host" not in agent_host._sessions

    def test_rebinds_memory_and_disk_sessions(self, store):
        agent_host._sessions["new"] = _session_payload(user_id="u")
        agent_host._sessions["old"] = _session_payload(
            user_id="u", workflow_session_id="conversation"
        )
        store.save("old", _session_payload(user_id="u", workflow_session_id="conversation"))
        store.save("other", _session_payload(user_id="u", workflow_session_id="conversation"))
        (store.directory / "broken.json").write_text("not json", encoding="utf-8")

        bind_workflow_session("conversation", "new", "u")

        assert "workflow_session_id" not in agent_host._sessions["old"]
        assert store.load("other").get("workflow_session_id") is None
        assert store.load("new")["workflow_session_id"] == "conversation"

    def test_host_session_lookup_reads_disk(self, store):
        store.save(
            "persisted",
            _session_payload(workflow_session_id="conversation"),
        )
        (store.directory / "broken.json").write_text("not json", encoding="utf-8")

        assert agent_host._host_session_id_for("conversation") == "persisted"
        assert agent_host._host_session_id_for("unknown") is None

    def test_host_session_lookup_ignores_expired_disk_session(self, store):
        store.save(
            "persisted",
            _session_payload(
                workflow_session_id="conversation",
                expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            ),
        )

        assert agent_host._host_session_id_for("conversation") is None

    def test_host_session_lookup_uses_memory_binding(self, store):
        agent_host._sessions["host"] = _session_payload(workflow_session_id="conversation")

        assert agent_host._host_session_id_for("conversation") == "host"

    def test_bind_rejects_foreign_user(self, store):
        agent_host._sessions["host"] = _session_payload(user_id="other")

        with pytest.raises(PermissionError):
            bind_workflow_session("conversation", "host", "u")

    def test_bind_skips_host_session_file_when_rewriting_disk(self, store):
        session = _session_payload(
            user_id="u", workflow_session_id="conversation"
        )
        store.save("host", session)

        bind_workflow_session("conversation", "host", "u")

        assert store.load("host")["workflow_session_id"] == "conversation"


class TestSkillBroadcast:
    def test_broadcast_updates_owned_sessions(self, store, monkeypatch):
        class Manager:
            def list_skills(self, owner_user_id=None):
                return [{"name": "review"}, {"name": "missing"}]

            def get_skill(self, name, owner_user_id=None):
                return {"name": name, "content": "c"} if name == "review" else None

        monkeypatch.setattr(
            "app.services.custom_skill_manager.get_skill_manager", lambda: Manager()
        )
        agent_host._sessions["mine"] = _session_payload(user_id="7")
        agent_host._sessions["theirs"] = _session_payload(user_id="8")

        assert broadcast_user_skill_update("7") == 1
        payload = agent_host._sessions["mine"]["pending_actions"][0]["payload"]
        assert set(payload["skills"]) == {"user:review"}

    def test_latest_skills_uses_last_matching_session(self, store):
        agent_host._sessions["a"] = _session_payload(
            user_id="7",
            skills={"a": {"x": 1}},
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        agent_host._sessions["b"] = _session_payload(user_id="7", skills={"b": {"x": 2}})
        agent_host._sessions["c"] = _session_payload(user_id="8", skills={"c": {}})

        assert get_latest_session_skills("7") == {"b": {"x": 2}}
        assert get_latest_session_skills("9") == {}


class TestListSessionBranches:
    @pytest.mark.asyncio
    async def test_skips_unloaded_foreign_and_expired(self, store):
        agent_host._sessions["own"] = _session_payload(user_id="7")
        agent_host._sessions["theirs"] = _session_payload(user_id="8")
        agent_host._sessions["stale"] = _session_payload(
            user_id="7", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
        )
        store.save(
            "orphan",
            _session_payload(user_id="7", expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
        )

        summaries = await list_agent_host_sessions({"sub": "7"})

        assert [item.session_id for item in summaries] == ["own"]

    @pytest.mark.asyncio
    async def test_missing_persisted_session_is_skipped(self, store, monkeypatch):
        class MissingStore:
            directory = store.directory

            def load(self, session_id):
                return None

        (store.directory / "ghost.json").write_text("{}", encoding="utf-8")
        monkeypatch.setattr(agent_host, "_session_store", MissingStore())

        assert await list_agent_host_sessions({"sub": "7"}) == []


class TestEventBranches:
    @pytest.mark.asyncio
    async def test_event_session_mismatch(self, store):
        agent_host._sessions["host"] = _session_payload()
        event = AgentHostEnvelope(
            message_id="e", schema_version=1, session_id="other",
            kind="progress_event", payload={},
        )

        with pytest.raises(HTTPException) as exc:
            await post_agent_host_event("host", event, {"sub": "u"})
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_unsupported_event_kind(self, store):
        agent_host._sessions["host"] = _session_payload()
        event = AgentHostEnvelope(
            message_id="e", schema_version=1, session_id="host",
            kind="policy_update", payload={},
        )

        with pytest.raises(HTTPException) as exc:
            await post_agent_host_event("host", event, {"sub": "u"})
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_tool_result_requires_revision(self, store):
        agent_host._sessions["host"] = _session_payload()
        event = AgentHostEnvelope(
            message_id="e", schema_version=1, session_id="host",
            kind="tool_result", task_id="t", payload={},
        )

        with pytest.raises(HTTPException) as exc:
            await post_agent_host_event("host", event, {"sub": "u"})
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize("error", [KeyError("missing"), ValueError("bad")])
    async def test_resume_errors_become_conflicts(self, store, monkeypatch, error):
        agent_host._sessions["host"] = _session_payload()
        event = AgentHostEnvelope(
            message_id="e", schema_version=1, session_id="host",
            kind="tool_result", task_id="t", revision=1, payload={},
        )

        async def boom(**kwargs):
            raise error

        monkeypatch.setattr(
            "app.agent.workflow_registry.resume_workflow_from_local_result", boom
        )

        with pytest.raises(HTTPException) as exc:
            await post_agent_host_event("host", event, {"sub": "u"})
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    async def test_result_event_clears_source_action(self, store, monkeypatch):
        agent_host._sessions["host"] = _session_payload(
            pending_actions=[{"message_id": "a1"}],
            in_flight_actions=[{"message_id": "a1"}, {"message_id": "a2"}],
        )
        event = AgentHostEnvelope(
            message_id="a1:result", schema_version=1, session_id="host",
            kind="tool_result", task_id="t", revision=1, payload={},
        )

        async def resume(**kwargs):
            return SimpleNamespace(status="completed")

        monkeypatch.setattr(
            "app.agent.workflow_registry.resume_workflow_from_local_result", resume
        )
        response = await post_agent_host_event("host", event, {"sub": "u"})

        assert response.state_status == "completed"
        session = agent_host._sessions["host"]
        assert session["pending_actions"] == []
        assert session["in_flight_actions"] == [{"message_id": "a2"}]

    @pytest.mark.asyncio
    async def test_duplicate_event_is_ignored(self, store):
        agent_host._sessions["host"] = _session_payload(events={"e": {}})
        event = AgentHostEnvelope(
            message_id="e", schema_version=1, session_id="host",
            kind="progress_event", payload={},
        )

        response = await post_agent_host_event("host", event, {"sub": "u"})

        assert response.duplicate is True

    @pytest.mark.asyncio
    async def test_non_result_event_does_not_clear_actions(self, store):
        agent_host._sessions["host"] = _session_payload(
            pending_actions=[{"message_id": "a1"}],
            in_flight_actions=[{"message_id": "a1"}],
        )
        event = AgentHostEnvelope(
            message_id="progress", schema_version=1, session_id="host",
            kind="tool_result", task_id="t", revision=1, payload={},
        )

        async def resume(**kwargs):
            return SimpleNamespace(status="running")

        monkeypatch = pytest.MonkeyPatch()
        monkeypatch.setattr(
            "app.agent.workflow_registry.resume_workflow_from_local_result", resume
        )
        try:
            response = await post_agent_host_event("host", event, {"sub": "u"})
        finally:
            monkeypatch.undo()

        assert response.state_status == "running"
        assert agent_host._sessions["host"]["pending_actions"] == [{"message_id": "a1"}]


class TestPolicyAndControlBranches:
    @pytest.mark.asyncio
    async def test_policy_version_conflict(self, store):
        agent_host._sessions["host"] = _session_payload()

        with pytest.raises(HTTPException) as exc:
            await update_agent_host_policy(
                "host",
                PolicyUpdateRequest(expected_policy_version=2, policy={}),
                {"sub": "u"},
            )
        assert exc.value.status_code == 409

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("action", "expected"),
        [("cancel", "cancelled"), ("pause", "paused"), ("resume", "active")],
    )
    async def test_control_status_paths(self, store, action, expected):
        agent_host._sessions["host"] = _session_payload()

        result = await control_agent_host_session(
            "host", SessionControlRequest(action=action), {"sub": "u"}
        )

        assert result == {"status": expected}
        assert agent_host._sessions["host"]["pending_actions"][0]["kind"] == "session_control"

    @pytest.mark.asyncio
    async def test_ack_unknown_action_reports_false(self, store):
        agent_host._sessions["host"] = _session_payload(
            in_flight_actions=[{"message_id": "a1", "payload": {"action_id": "a1"}}]
        )

        result = await acknowledge_agent_host_action(
            "host", AgentHostActionAckRequest(action_id="missing"), {"sub": "u"}
        )

        assert result["acknowledged"] is False

    @pytest.mark.asyncio
    async def test_policy_update_success(self, store):
        agent_host._sessions["host"] = _session_payload()

        result = await update_agent_host_policy(
            "host", PolicyUpdateRequest(expected_policy_version=1, policy={"a": 1}), {"sub": "u"}
        )

        assert result.policy_version == 2
        assert agent_host._sessions["host"]["pending_actions"][0]["kind"] == "policy_update"

    @pytest.mark.asyncio
    async def test_sync_and_revoke_skills(self, store):
        agent_host._sessions["host"] = _session_payload()

        synced = await sync_agent_host_skills(
            "host", agent_host.SkillSyncRequest(skills={"s": {"v": 1}}), {"sub": "u"}
        )
        assert synced["skills"] == {"s": {"v": 1}}
        assert agent_host._sessions["host"]["pending_actions"][0]["capability"] == "skill_runtime"

        revoked = await revoke_agent_host_skill("host", "s", {"sub": "u"})
        assert revoked["skills"] == {}
        assert agent_host._sessions["host"]["pending_actions"][1]["kind"] == "skill_revoke"


class TestGetSessionBranches:
    def test_missing_session_is_404(self, store):
        with pytest.raises(HTTPException) as exc:
            agent_host._get_session("missing", {"sub": "u"})
        assert exc.value.status_code == 404

    def test_foreign_session_is_404(self, store):
        store.save("host", _session_payload(user_id="other"))

        with pytest.raises(HTTPException) as exc:
            agent_host._get_session("host", {"sub": "u"})
        assert exc.value.status_code == 404

    def test_expired_session_is_410(self, store):
        store.save(
            "host",
            _session_payload(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)),
        )

        with pytest.raises(HTTPException) as exc:
            agent_host._get_session("host", {"sub": "u"})
        assert exc.value.status_code == 410

    def test_touch_false_keeps_expiry(self, store):
        expires = datetime.now(timezone.utc) + timedelta(minutes=5)
        store.save("host", _session_payload(expires_at=expires))

        session = agent_host._get_session("host", {"sub": "u"}, touch=False)

        assert session["expires_at"] == expires

    def test_restored_in_flight_actions_are_requeued(self, store):
        store.save(
            "host", _session_payload(in_flight_actions=[{"message_id": "a1"}])
        )

        session = agent_host._get_session("host", {"sub": "u"})

        assert session["pending_actions"] == [{"message_id": "a1"}]
        assert "in_flight_actions" not in session


class TestEndpointBranches:
    @pytest.mark.asyncio
    async def test_get_actions_moves_pending_to_in_flight(self, store):
        agent_host._sessions["host"] = _session_payload(
            pending_actions=[{"message_id": "a1"}]
        )

        response = await get_agent_host_actions("host", {"sub": "u"})

        assert response.actions == [{"message_id": "a1"}]
        assert agent_host._sessions["host"]["pending_actions"] == []
        assert agent_host._sessions["host"]["in_flight_actions"] == [{"message_id": "a1"}]

    @pytest.mark.asyncio
    async def test_handshake_rejects_unsupported_capability(self, store):
        with pytest.raises(HTTPException) as exc:
            await agent_host_handshake(
                HostHandshakeRequest(
                    workspace_id="w",
                    extension_version="1",
                    protocol_versions=[1],
                    capabilities=["nope"],
                ),
                {"sub": "u"},
            )
        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_handshake_rejects_unsupported_protocol(self, store):
        with pytest.raises(HTTPException) as exc:
            await agent_host_handshake(
                HostHandshakeRequest(
                    workspace_id="w",
                    extension_version="1",
                    protocol_versions=[2],
                    capabilities=["workspace"],
                ),
                {"sub": "u"},
            )
        assert exc.value.status_code == 426

    @pytest.mark.asyncio
    async def test_heartbeat_requires_numeric_identity(self, store):
        agent_host._sessions["host"] = _session_payload(user_id="abc")
        db = SimpleNamespace(scalar=None, commit=None)

        with pytest.raises(HTTPException) as exc:
            await agent_host.agent_host_heartbeat("host", {"sub": "abc"}, db)
        assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_heartbeat_unknown_project_is_404(self, store):
        agent_host._sessions["host"] = _session_payload(user_id="7")

        async def scalar(*args, **kwargs):
            return None

        db = SimpleNamespace(scalar=scalar)

        with pytest.raises(HTTPException) as exc:
            await agent_host.agent_host_heartbeat("host", {"sub": "7"}, db)
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_heartbeat_updates_project(self, store):
        agent_host._sessions["host"] = _session_payload(user_id="7", workspace_id="w")
        project = SimpleNamespace(last_activity_at=None, lifecycle_status="idle", session_id="w")
        committed = []

        async def scalar(*args, **kwargs):
            return project

        async def commit():
            committed.append(True)

        db = SimpleNamespace(scalar=scalar, commit=commit)

        result = await agent_host.agent_host_heartbeat("host", {"sub": "7"}, db)

        assert result["status"] == "active"
        assert project.lifecycle_status == "active"
        assert committed == [True]

    @pytest.mark.asyncio
    async def test_progress_event_is_accepted(self, store):
        agent_host._sessions["host"] = _session_payload()
        event = AgentHostEnvelope(
            message_id="p", schema_version=1, session_id="host",
            kind="progress_event", payload={"percent": 10},
        )

        response = await post_agent_host_event("host", event, {"sub": "u"})

        assert response.accepted is True
        assert response.state_status is None
        assert "p" in agent_host._sessions["host"]["events"]


class TestDumpModel:
    def test_dict_fallback(self):
        assert agent_host._dump_model(SimpleNamespace(dict=lambda: {"a": 1})) == {"a": 1}


class TestHandshakeSkills:
    @pytest.mark.asyncio
    async def test_handshake_includes_owned_skill_content(self, store, monkeypatch):
        class Manager:
            def list_skills(self, owner_user_id=None):
                return [{"name": "review"}]

            def get_skill(self, name, owner_user_id=None):
                return {"name": name, "content": "hello"}

        monkeypatch.setattr(
            "app.services.custom_skill_manager.get_skill_manager", lambda: Manager()
        )

        response = await agent_host_handshake(
            HostHandshakeRequest(
                workspace_id="w",
                extension_version="1",
                protocol_versions=[1],
                capabilities=["workspace"],
            ),
            {"sub": "u"},
        )

        assert response.user_skills["user:review"]["content"] == "hello"
