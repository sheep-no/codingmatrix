"""Branch coverage for app/api/v1/ai_agent/orchestrate_endpoints.py."""

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.ai_agent import orchestrate_endpoints as endpoints
from app.api.v1.ai_agent.schemas import (
    ComplexityAnalysisRequest,
    EvaluateRequest,
    ModifyRequest,
    OrchestratorRequest,
    SearchSessionsRequest,
)


class ConnectedRequest:
    async def is_disconnected(self):
        return False


class DisconnectedRequest:
    async def is_disconnected(self):
        return True


class BrokenRequest:
    async def is_disconnected(self):
        raise RuntimeError("socket gone")


RESULT = {
    "success": True,
    "output_dir": "/tmp/x",
    "total_files_created": 2,
    "files": [],
    "validation": {},
    "errors": [],
    "warnings": [],
    "elapsed_time": 0.1,
}


def _result(value=None, *, scalars=None, rowcount=0):
    scalar_getter = (lambda: value) if not callable(value) else value
    obj = SimpleNamespace(
        scalar_one_or_none=scalar_getter,
        rowcount=rowcount,
    )
    if scalars is not None:
        obj.scalars = lambda: SimpleNamespace(all=lambda: scalars)
    return obj


def _db(*executes, commit=None, rollback=None, close=None):
    remaining = list(executes)

    async def _execute(*_a, **_k):
        if remaining:
            return remaining.pop(0)
        return _result(None)

    return SimpleNamespace(
        execute=AsyncMock(side_effect=_execute),
        commit=commit or AsyncMock(),
        rollback=rollback or AsyncMock(),
        close=close or AsyncMock(),
    )


def _sm(**overrides):
    values = dict(
        resume_session=AsyncMock(return_value=None),
        create_session=AsyncMock(),
        complete_session=AsyncMock(),
        cancel_session=AsyncMock(),
        resume_from_pause=AsyncMock(),
        _lock=asyncio.Lock(),
        _active_sessions={},
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _reset_state(monkeypatch):
    monkeypatch.setattr(endpoints, "_approval_queues", {})
    monkeypatch.setattr(endpoints, "_decision_queues", {})
    monkeypatch.setattr(endpoints, "_cancel_events", {})
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {})
    monkeypatch.setattr(endpoints, "_active_tasks", {})
    monkeypatch.setattr(endpoints, "_user_creation_locks", {})


async def _drain(response):
    return [item async for item in response.body_iterator]


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def test_generation_result_error_variants():
    assert endpoints._generation_result_error({"success": True}) is None
    assert endpoints._generation_result_error({"success": False, "errors": "boom"}) == "boom"
    assert (
        endpoints._generation_result_error(
            {"success": False, "errors": ["a", "b"]}
        )
        == "a；b"
    )
    assert (
        endpoints._generation_result_error({"success": False})
        == "生成流程未达到成功终态"
    )


@pytest.mark.asyncio
async def test_client_disconnected_variants():
    assert await endpoints._client_disconnected(None) is False
    assert await endpoints._client_disconnected(ConnectedRequest()) is False
    assert await endpoints._client_disconnected(BrokenRequest()) is True


def test_is_analyze_intent_case_insensitive():
    assert endpoints._is_analyze_intent("Please REVIEW this module") is True
    assert endpoints._is_analyze_intent("create a new endpoint") is False


def test_legacy_requirement_boundary():
    assert endpoints._legacy_requirement_with_allowed_files("req", []) == "req"
    text = endpoints._legacy_requirement_with_allowed_files("req  ", ["a.py", "b.py"])
    assert text.startswith("req\n\n")
    assert "a.py, b.py" in text


# ---------------------------------------------------------------------------
# Analyze request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_handle_analyze_request_builds_language_context(monkeypatch, tmp_path):
    (tmp_path / ".dep_graph.json").write_text("{}")

    class _Node:
        file_type = "frontend"

    class _Graph:
        nodes = {"a": _Node()}

        @classmethod
        def load(cls, _path):
            return cls()

    engineer = SimpleNamespace(analyze=AsyncMock(return_value={"not": "a string"}))
    engineer_cls = MagicMock(return_value=engineer)
    router = SimpleNamespace(get_best_model=AsyncMock(return_value="model-a"))

    monkeypatch.setattr("app.agent.dependency_graph.DependencyGraph", _Graph)
    monkeypatch.setattr("app.agent.backend_engineer.BackendEngineer", engineer_cls)
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.get_dynamic_router",
        AsyncMock(return_value=router),
    )

    result = await endpoints._handle_analyze_request(
        ModifyRequest(requirement="review it"), tmp_path, "1"
    )

    assert result["type"] == "analysis"
    assert result["data"]["analysis"].startswith("{")
    context = engineer.analyze.await_args.kwargs["project_context"]
    assert context["architecture"]["language"] == "javascript"


@pytest.mark.asyncio
async def test_handle_analyze_request_swallows_dep_graph_errors(monkeypatch, tmp_path):
    (tmp_path / ".dep_graph.json").write_text("{}")

    def _boom(_path):
        raise ValueError("bad graph")

    engineer = SimpleNamespace(analyze=AsyncMock(return_value="ok"))
    monkeypatch.setattr("app.agent.dependency_graph.DependencyGraph", SimpleNamespace(load=_boom))
    monkeypatch.setattr(
        "app.agent.backend_engineer.BackendEngineer", MagicMock(return_value=engineer)
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.get_dynamic_router",
        AsyncMock(return_value=SimpleNamespace(get_best_model=AsyncMock(return_value="m"))),
    )

    result = await endpoints._handle_analyze_request(
        ModifyRequest(requirement="review"), tmp_path, "1"
    )
    assert result["data"]["analysis"] == "ok"
    assert engineer.analyze.await_args.kwargs["project_context"] == {}


@pytest.mark.asyncio
async def test_handle_analyze_request_maps_failures_to_500(monkeypatch, tmp_path):
    engineer = SimpleNamespace(analyze=AsyncMock(side_effect=RuntimeError("llm down")))
    monkeypatch.setattr(
        "app.agent.backend_engineer.BackendEngineer", MagicMock(return_value=engineer)
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.get_dynamic_router",
        AsyncMock(return_value=SimpleNamespace(get_best_model=AsyncMock(return_value="m"))),
    )
    monkeypatch.setattr(endpoints.logger, "exception", lambda *a, **k: None)

    with pytest.raises(HTTPException) as error:
        await endpoints._handle_analyze_request(
            ModifyRequest(requirement="review"), tmp_path, "1"
        )
    assert error.value.status_code == 500


# ---------------------------------------------------------------------------
# /modify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "token",
    [
        {},
        {"sub": "anonymous"},
        {"sub": "abc"},
    ],
)
async def test_modify_rejects_invalid_identity(token):
    with pytest.raises(HTTPException) as error:
        await endpoints.modify_project(
            ModifyRequest(requirement="x", project_path="1/p"), token, None
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_modify_rate_limit_and_disk_guards(monkeypatch):
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (False, "slow", 3))
    with pytest.raises(HTTPException) as error:
        await endpoints.modify_project(
            ModifyRequest(requirement="x", project_path="1/p"), {"sub": "1"}, None
        )
    assert error.value.status_code == 429
    assert error.value.headers == {"Retry-After": "3"}

    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (False, "full"))
    with pytest.raises(HTTPException) as error:
        await endpoints.modify_project(
            ModifyRequest(requirement="x", project_path="1/p"), {"sub": "1"}, None
        )
    assert error.value.status_code == 507


@pytest.mark.asyncio
async def test_modify_requires_project_path(monkeypatch):
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    with pytest.raises(HTTPException) as error:
        await endpoints.modify_project(ModifyRequest(requirement="x"), {"sub": "1"}, None)
    assert error.value.status_code == 400


async def _drive_modify(monkeypatch, tmp_path, *, history=None, engine=None,
                        run_error=None, existing_session=None, request=None):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: tmp_path)
    monkeypatch.setattr(endpoints, "_is_analyze_intent", lambda req: False)
    store = SimpleNamespace(
        get_history_async=AsyncMock(return_value=history or []),
        truncate_history=lambda items: items,
        append_message=AsyncMock(),
    )
    monkeypatch.setattr(endpoints, "get_conversation_store", lambda: store)
    sm = _sm()
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(endpoints, "get_spec_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "get_feedback_learner", AsyncMock(return_value=object()))
    generated = SimpleNamespace(
        generate_incremental=AsyncMock(return_value=RESULT),
        output_dir=str(tmp_path),
    )
    monkeypatch.setattr(
        endpoints, "OrchestratorAgent", lambda **kwargs: generated
    )
    if run_error is not None:
        monkeypatch.setattr(
            endpoints, "run_workflow", AsyncMock(side_effect=run_error)
        )
    else:
        async def fake_run_workflow(workflow, **_kwargs):
            if _kwargs.get("metadata", {}).get("engine") == "core":
                await workflow.core_handler(None)
            return None

        monkeypatch.setattr(endpoints, "run_workflow", fake_run_workflow)
    monkeypatch.setattr(
        endpoints, "execute_core_generation", AsyncMock(return_value=dict(RESULT))
    )
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: dict(RESULT))
    monkeypatch.setattr(endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(endpoints, "_create_project_session", AsyncMock())

    db = _db(_result(existing_session))
    req = request or ModifyRequest(
        requirement="add a field", project_path="1/demo", engine=engine
    )
    response = await endpoints.modify_project(req, {"sub": "1"}, db)
    events = await _drain(response)
    return events, generated, store, sm


@pytest.mark.asyncio
async def test_modify_stream_success_with_history(monkeypatch, tmp_path):
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
    existing = SimpleNamespace(status="running", lifecycle_status="stale",
                               last_activity_at=None, requirement=None)
    events, generated, store, sm = await _drive_modify(
        monkeypatch, tmp_path, history=history, existing_session=existing
    )

    assert existing.lifecycle_status == "active"
    assert existing.last_activity_at is not None
    assert existing.requirement == "add a field"
    roles = [call.args[2] for call in store.append_message.await_args_list]
    assert roles == ["user", "assistant"]
    sm.complete_session.assert_awaited()
    kinds = [json.loads(e[6:])["type"] for e in events]
    assert kinds[0] == "pipeline_mode"
    assert "done" in kinds
    assert events[-1].startswith("data: ")


@pytest.mark.asyncio
async def test_modify_stream_reports_generation_failure(monkeypatch, tmp_path):
    events, _, _, sm = await _drive_modify(
        monkeypatch, tmp_path, run_error=RuntimeError("boom")
    )
    assert sm.complete_session.await_args.kwargs["errors"] == ["boom"]
    assert any('"type": "error"' in event for event in events)


@pytest.mark.asyncio
async def test_modify_stream_forwards_passthrough_and_log_events(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: tmp_path)
    monkeypatch.setattr(endpoints, "_is_analyze_intent", lambda req: False)
    monkeypatch.setattr(
        endpoints,
        "get_conversation_store",
        lambda: SimpleNamespace(
            get_history_async=AsyncMock(return_value=[]),
            truncate_history=lambda items: items,
            append_message=AsyncMock(),
        ),
    )
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=_sm()))
    monkeypatch.setattr(endpoints, "get_spec_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "get_feedback_learner", AsyncMock(return_value=object()))
    captured = {}

    def factory(**kwargs):
        captured["callback"] = kwargs["callback"]
        return SimpleNamespace(
            output_dir=str(tmp_path), generate_incremental=AsyncMock(return_value=RESULT)
        )

    async def run_workflow(_workflow, **_kwargs):
        await captured["callback"](json.dumps({"type": "file", "data": {"path": "a.py"}}))
        await captured["callback"](json.dumps({"type": "other", "data": 1}))
        await captured["callback"]("plain log line")
        return None

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)
    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: dict(RESULT))
    monkeypatch.setattr(endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(endpoints, "_create_project_session", AsyncMock())

    response = await endpoints.modify_project(
        ModifyRequest(requirement="add", project_path="1/demo"),
        {"sub": "1"},
        _db(_result(None)),
    )
    events = await _drain(response)

    assert any('"type": "file"' in event for event in events)
    assert any('"type": "log"' in event for event in events)


# ---------------------------------------------------------------------------
# /orchestrate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrate_rejects_invalid_identity():
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project(
            OrchestratorRequest(requirement="build"), {"sub": "nope"}, None
        )
    assert error.value.status_code == 403


def _patch_orchestrate_common(monkeypatch, tmp_path, *, single_result=None,
                              single_error=None, work_error=None, result=None):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_validate_project_target", lambda path, user: tmp_path)
    monkeypatch.setattr(
        endpoints, "create_agent_session",
        AsyncMock(return_value=SimpleNamespace(id="sess-1")),
    )
    monkeypatch.setattr(
        endpoints, "generate_single_file",
        AsyncMock(side_effect=single_error) if single_error else AsyncMock(return_value=single_result),
    )
    monkeypatch.setattr(endpoints, "_skill_context_for_user", lambda *a, **k: "")
    monkeypatch.setattr(endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(endpoints, "update_model_stats", AsyncMock())
    fake_agent = SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock(return_value=result or RESULT))
    monkeypatch.setattr(endpoints, "OrchestratorAgent", lambda **kwargs: fake_agent)
    if work_error is not None:
        monkeypatch.setattr(endpoints, "run_workflow", AsyncMock(side_effect=work_error))
    else:
        monkeypatch.setattr(endpoints, "run_workflow", AsyncMock(return_value=None))
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: dict(result or RESULT))

    from app.utils.aicloud import llm_caller

    monkeypatch.setattr(llm_caller, "begin_llm_call_metrics", lambda: object())
    finish = MagicMock(return_value={"model_call_count": 1})
    monkeypatch.setattr(llm_caller, "finish_llm_call_metrics", finish)
    return fake_agent, finish


@pytest.mark.asyncio
async def test_orchestrate_single_file_short_circuit(monkeypatch, tmp_path):
    single = dict(RESULT, session_id="ignored")
    _, finish = _patch_orchestrate_common(monkeypatch, tmp_path, single_result=single)

    response = await endpoints.orchestrate_project(
        OrchestratorRequest(requirement="build", enable_skills=False),
        {"sub": "1"},
        None,
    )

    assert response.session_id == "sess-1"
    assert response.generation_metrics == {"model_call_count": 1}
    finish.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrate_single_file_failure_closes_metrics(monkeypatch, tmp_path):
    _, finish = _patch_orchestrate_common(
        monkeypatch, tmp_path, single_error=RuntimeError("provider broken")
    )
    with pytest.raises(RuntimeError):
        await endpoints.orchestrate_project(
            OrchestratorRequest(requirement="build", enable_skills=False),
            {"sub": "1"},
            None,
        )
    finish.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrate_success_records_model_stats(monkeypatch, tmp_path):
    result = dict(RESULT, models_used={"architect": "model-a"}, success=True)
    _, finish = _patch_orchestrate_common(monkeypatch, tmp_path, result=result)

    response = await endpoints.orchestrate_project(
        OrchestratorRequest(requirement="build", enable_skills=False),
        {"sub": "1"},
        None,
    )

    assert response.success is True
    assert response.generation_metrics["model_call_count"] == 1
    assert response.output_dir == str(tmp_path.resolve())
    finish.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrate_preserves_http_exception(monkeypatch, tmp_path):
    _, finish = _patch_orchestrate_common(
        monkeypatch, tmp_path, work_error=HTTPException(status_code=418, detail="teapot")
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project(
            OrchestratorRequest(requirement="build", enable_skills=False),
            {"sub": "1"},
            None,
        )
    assert error.value.status_code == 418
    finish.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrate_wraps_unexpected_error(monkeypatch, tmp_path):
    _, finish = _patch_orchestrate_common(
        monkeypatch, tmp_path, work_error=RuntimeError("db exploded")
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project(
            OrchestratorRequest(requirement="build", enable_skills=False),
            {"sub": "1"},
            None,
        )
    assert error.value.status_code == 500
    finish.assert_called_once()


@pytest.mark.asyncio
async def test_orchestrate_skills_and_core_engine(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_validate_project_target", lambda path, user: tmp_path)
    monkeypatch.setattr(
        endpoints, "create_agent_session",
        AsyncMock(return_value=SimpleNamespace(id="sess-1")),
    )
    single = AsyncMock(return_value=None)
    monkeypatch.setattr(endpoints, "generate_single_file", single)
    monkeypatch.setattr(
        endpoints, "_skill_context_for_user", lambda user, req: "\n[Available Skills]\nX"
    )
    monkeypatch.setattr(endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(endpoints, "update_model_stats", AsyncMock())
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock())

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)
    monkeypatch.setattr(endpoints, "run_workflow", AsyncMock(return_value=None))
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: dict(RESULT))

    response = await endpoints.orchestrate_project(
        OrchestratorRequest(
            requirement="build",
            engine="core",
            enable_skills=True,
            allowed_files=["a.py"],
        ),
        {"sub": "1"},
        None,
    )

    single.assert_not_awaited()
    assert captured["spec_first"] is True
    assert response.success is True


# ---------------------------------------------------------------------------
# /orchestrate/stream
# ---------------------------------------------------------------------------


def _patch_stream_common(monkeypatch, tmp_path, *, work_result=None,
                         work_error=None, store_session=None, existing=None):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_validate_project_target", lambda path, user: tmp_path)
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    monkeypatch.setattr("app.utils.guardrails.check_prompt_safety", lambda req: (True, ""))
    monkeypatch.setattr(
        endpoints, "_detect_and_clean_zombie_sessions", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(endpoints, "_create_project_session", AsyncMock())
    monkeypatch.setattr(endpoints, "_skill_context_for_user", lambda *a, **k: "")
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": False, "has_changes": False, "additional_requirement": "",
    }))
    sm = _sm(
        resume_session=AsyncMock(return_value=store_session),
        create_session=AsyncMock(),
        complete_session=AsyncMock(),
        cancel_session=AsyncMock(),
    )
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(endpoints, "get_spec_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "get_feedback_learner", AsyncMock(return_value=object()))
    agent = SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock())
    monkeypatch.setattr(endpoints, "OrchestratorAgent", lambda **kwargs: agent)
    if work_error is not None:
        monkeypatch.setattr(endpoints, "run_workflow", AsyncMock(side_effect=work_error))
    else:
        monkeypatch.setattr(endpoints, "run_workflow", AsyncMock(return_value=None))
    monkeypatch.setattr(
        endpoints, "get_legacy_result", lambda state: dict(work_result or RESULT)
    )

    class _FakeConcurrentLimit:
        def __init__(self):
            self.registered = []
            self.unregistered = []

        def register_session(self, role):
            self.registered.append(role)

        def unregister_session(self, role):
            self.unregistered.append(role)

    manager = _FakeConcurrentLimit()
    monkeypatch.setattr(
        "app.utils.dynamic_concurrent.ConcurrentLimitManager", lambda: manager
    )

    # First query: no running session. Second: existing session lookup.
    db = _db(
        _result(None),
        _result(existing),
    )
    return db, sm, agent, manager


@pytest.mark.asyncio
async def test_stream_rejects_invalid_identity():
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="build"), ConnectedRequest(), {"sub": "x"}, None
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_stream_success_emits_done_and_releases_limits(monkeypatch, tmp_path):
    db, sm, _, manager = _patch_stream_common(monkeypatch, tmp_path)

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build a thing", enable_skills=False),
        ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    events = await _drain(response)

    assert json.loads(events[0][6:])["type"] == "pipeline_mode"
    assert any('"type": "done"' in event for event in events)
    sm.complete_session.assert_awaited_once()
    assert manager.registered == ["user"]
    assert manager.unregistered == ["user"]
    assert endpoints._active_tasks == {}


@pytest.mark.asyncio
async def test_stream_success_reports_generation_error(monkeypatch, tmp_path):
    failing = dict(RESULT, success=False, errors=["boom"], total_files_created=0)
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path, work_result=failing)

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    events = await _drain(response)

    assert sm.complete_session.await_args.kwargs["errors"] == ["boom"]
    assert any('"type": "error"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_unexpected_failure_marks_session_failed(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(
        monkeypatch, tmp_path, work_error=RuntimeError("kaboom")
    )
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    events = await _drain(response)

    assert sm.complete_session.await_args.kwargs["errors"] == ["kaboom"]
    assert any('"type": "error"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_cancel_before_start_marks_session_cancelled(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    db.execute.side_effect = [
        _result(None),
        _result(None),
        _result(SimpleNamespace(status="running", error_message=None)),
    ]
    monkeypatch.setattr(endpoints, "_register_pending_stream", lambda sid, uid: _set_event())

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(),
        {"sub": "1"},
        db,
    )
    events = await _drain(response)

    assert '"cancelled"' in events[0]
    sm.create_session.assert_not_awaited()


def _set_event():
    event = asyncio.Event()
    event.set()
    return event


@pytest.mark.asyncio
async def test_stream_returns_cancelled_when_client_already_gone(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        DisconnectedRequest(),
        {"sub": "1"},
        db,
    )
    events = await _drain(response)
    assert '"cancelled"' in events[0]


@pytest.mark.asyncio
async def test_stream_foreign_pending_owner_is_rejected(monkeypatch, tmp_path):
    _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        endpoints, "_pending_stream_owners", {"1_busy": "99"}
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(
                requirement="build", session_id="1_busy", enable_skills=False
            ),
            ConnectedRequest(),
            {"sub": "1"},
            None,
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_stream_existing_session_is_updated(monkeypatch, tmp_path):
    existing = SimpleNamespace(
        status="completed", requirement="old", error_message="old error"
    )
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path, existing=existing)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="build", session_id="1_demo", enable_skills=False
        ),
        ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    await _drain(response)

    assert existing.status == "running"
    assert existing.requirement == "build"
    assert existing.error_message is None
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_stream_incremental_integrity_error_maps_to_409(monkeypatch, tmp_path):
    from sqlalchemy.exc import IntegrityError

    db, _, _, _ = _patch_stream_common(
        monkeypatch, tmp_path,
        existing=SimpleNamespace(status="completed", requirement="old", error_message=None),
    )
    db.commit = AsyncMock(side_effect=IntegrityError("stmt", {}, Exception("dup")))
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(
                requirement="build", session_id="1_demo", incremental=True,
                enable_skills=False,
            ),
            ConnectedRequest(),
            {"sub": "1"},
            db,
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_stream_running_session_without_task_returns_429(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    running = SimpleNamespace(
        session_id="1_old", status="running",
        created_at=datetime.now(timezone.utc),
    )
    db.execute.side_effect = [_result(running)]
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="build", enable_skills=False),
            ConnectedRequest(),
            {"sub": "1"},
            db,
        )
    assert error.value.status_code == 429
    assert error.value.detail["session_id"] == "1_old"


@pytest.mark.asyncio
async def test_stream_live_connected_task_conflicts(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    running = SimpleNamespace(session_id="1_old", status="running", created_at=None)
    monkeypatch.setattr(endpoints, "_active_tasks", {
        "1_old": {
            "gen_task": SimpleNamespace(done=lambda: False),
            "channel": endpoints._SseBroadcast(),
            "connected": True,
            "http_request": ConnectedRequest(),
        }
    })
    db.execute.side_effect = [_result(running)]
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="build", enable_skills=False),
            ConnectedRequest(),
            {"sub": "1"},
            db,
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_stream_supersedes_stale_running_session(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    running = SimpleNamespace(
        session_id="1_old", status="running", error_message=None, created_at=None,
    )
    superseded = AsyncMock()
    monkeypatch.setattr(endpoints, "_supersede_running_generation", superseded)
    db.execute.side_effect = [_result(running), _result(None)]

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", session_id="1_new", enable_skills=False),
        ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    await _drain(response)
    superseded.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_resume_intent_reuses_target_session(monkeypatch, tmp_path):
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    session_state = SimpleNamespace(
        file_statuses={
            "a.py": SimpleNamespace(status="completed"),
            "b.py": SimpleNamespace(status="failed"),
        }
    )
    (tmp_path / "a.py").write_text("x")
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path, store_session=session_state)
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": True, "additional_requirement": "also b",
    }))
    sm.resume_session = AsyncMock(return_value=session_state)
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=target))
    monkeypatch.setattr(
        endpoints, "get_user_recent_session", AsyncMock(return_value=target)
    )
    monkeypatch.setattr(
        endpoints, "analyze_files_to_regenerate", AsyncMock(return_value=["a.py"])
    )
    db.execute.side_effect = [_result(None)]

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="继续", is_resume=None, enable_skills=False
        ),
        ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    await _drain(response)

    assert not (tmp_path / "a.py").exists()
    assert target.session_id == "1_target"


@pytest.mark.asyncio
async def test_stream_explicit_resume_of_finished_task_conflicts(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    session = SimpleNamespace(session_id="sess-1", status="completed")
    monkeypatch.setattr(
        endpoints, "verify_session_ownership", AsyncMock(return_value=session)
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="x", session_id="sess-1", is_resume=True),
            ConnectedRequest(),
            {"sub": "1"},
            None,
        )
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_stream_explicit_resume_requires_session_id(monkeypatch):
    _reset_state(monkeypatch)
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="x", is_resume=True),
            ConnectedRequest(),
            {"sub": "1"},
            None,
        )
    assert error.value.status_code == 422


# ---------------------------------------------------------------------------
# Shared cleanup / cancel helpers
# ---------------------------------------------------------------------------


def test_bind_local_validation_session_passthrough_without_host():
    request = ModifyRequest(requirement="x")
    assert endpoints._bind_local_validation_session(request, "conv", "1") == "conv"


def test_bind_local_validation_session_rejects_unauthorized_host(monkeypatch):
    from app.api.v1 import agent_host

    def _deny(*_a):
        raise PermissionError("nope")

    monkeypatch.setattr(agent_host, "bind_workflow_session", _deny)
    request = ModifyRequest(requirement="x", host_session_id="host-1")
    with pytest.raises(HTTPException) as error:
        endpoints._bind_local_validation_session(request, "conv", "1")
    assert error.value.status_code == 403


def test_bind_local_validation_session_binds_host(monkeypatch):
    from app.api.v1 import agent_host

    seen = {}
    monkeypatch.setattr(
        agent_host,
        "bind_workflow_session",
        lambda conv, host, user: seen.update(conv=conv, host=host, user=user),
    )
    request = ModifyRequest(requirement="x", host_session_id="host-1")
    assert endpoints._bind_local_validation_session(request, "conv", "1") == "conv"
    assert seen == {"conv": "conv", "host": "host-1", "user": "1"}


@pytest.mark.asyncio
async def test_cleanup_all_queues_clears_everything(monkeypatch):
    _reset_state(monkeypatch)
    endpoints._approval_queues["a"] = object()
    endpoints._decision_queues["a"] = object()
    endpoints._cancel_events["a"] = asyncio.Event()
    endpoints._pending_stream_owners["a"] = "1"

    await endpoints._cleanup_all_queues()

    assert endpoints._approval_queues == {}
    assert endpoints._decision_queues == {}
    assert endpoints._cancel_events == {}
    assert endpoints._pending_stream_owners == {}


@pytest.mark.asyncio
async def test_cancel_active_generation_variants(monkeypatch):
    _reset_state(monkeypatch)
    assert await endpoints._cancel_active_generation("missing") is False

    endpoints._active_tasks["done"] = {"gen_task": SimpleNamespace(done=lambda: True)}
    assert await endpoints._cancel_active_generation("done") is True

    async def _forever():
        await asyncio.Event().wait()

    task = asyncio.create_task(_forever())
    endpoints._active_tasks["live"] = {"gen_task": task}
    try:
        assert await endpoints._cancel_active_generation("live") is True
        assert task.cancelled()
    finally:
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_active_generation_handles_timeout(monkeypatch):
    _reset_state(monkeypatch)
    logger = SimpleNamespace(warning=lambda *a, **k: None)
    monkeypatch.setattr(endpoints, "logger", logger)

    class _Stubborn:
        def done(self):
            return False

        def cancel(self):
            pass

        def __await__(self):
            async def _hang():
                await asyncio.Event().wait()

            return _hang().__await__()

    endpoints._active_tasks["slow"] = {"gen_task": _Stubborn()}

    async def _timeout(_awaitable, timeout):
        raise asyncio.TimeoutError

    monkeypatch.setattr(endpoints.asyncio, "wait_for", _timeout)
    assert await endpoints._cancel_active_generation("slow") is True


@pytest.mark.asyncio
async def test_supersede_running_generation_cancels_and_commits(monkeypatch):
    _reset_state(monkeypatch)
    event = asyncio.Event()
    endpoints._cancel_events["sess"] = event
    endpoints._approval_queues["sess"] = object()
    sm = _sm()
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    db = SimpleNamespace(commit=AsyncMock())
    session = SimpleNamespace(
        session_id="sess", status="running", error_message=None
    )

    await endpoints._supersede_running_generation(db, session, reason="replaced")

    assert event.is_set()
    assert session.status == "cancelled"
    assert session.error_message == "replaced"
    db.commit.assert_awaited_once()
    assert "sess" not in endpoints._approval_queues


@pytest.mark.asyncio
async def test_supersede_running_generation_swallows_cleanup_errors(monkeypatch):
    _reset_state(monkeypatch)
    sm = _sm(cancel_session=AsyncMock(side_effect=RuntimeError("manager down")))
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    db = SimpleNamespace(commit=AsyncMock())
    session = SimpleNamespace(session_id="sess", status="running", error_message=None)

    await endpoints._supersede_running_generation(db, session)

    assert session.status == "cancelled"
    db.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Lifecycle endpoints
# ---------------------------------------------------------------------------


async def _seed_session(db, **overrides):
    from app.db.models import ProjectSession

    values = dict(
        session_id="2_proj",
        user_id="2",
        requirement="hello",
        output_dir="2/proj",
        status="running",
        lifecycle_status="active",
    )
    values.update(overrides)
    db.add(ProjectSession(**values))
    await db.flush()


@pytest.fixture
async def db():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [{"sub": "anonymous"}, {"sub": "x"}, {}])
async def test_stop_project_rejects_bad_identity(db, token):
    with pytest.raises(HTTPException) as error:
        await endpoints.stop_project("s", token, db)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_stop_project_missing_and_wrong_status(db):
    with pytest.raises(HTTPException) as error:
        await endpoints.stop_project("missing-1", {"sub": "2"}, db)
    assert error.value.status_code == 404

    await _seed_session(db, session_id="2_done", status="completed")
    with pytest.raises(HTTPException) as error:
        await endpoints.stop_project("2_done", {"sub": "2"}, db)
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_stop_project_cancels_cleans_and_reports(db, monkeypatch):
    _reset_state(monkeypatch)
    await _seed_session(db)
    event = asyncio.Event()
    endpoints._cancel_events["2_proj"] = event
    monkeypatch.setattr(
        "app.agent.workflow_registry.cancel_workflows_for_session", AsyncMock()
    )
    monkeypatch.setattr(endpoints, "_cancel_active_generation", AsyncMock(return_value=True))
    monkeypatch.setattr(endpoints, "cleanup_session_files", lambda path: True)
    sm = _sm()
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))

    result = await endpoints.stop_project("2_proj", {"sub": "2"}, db)

    assert result["status"] == "cancelled"
    assert result["files_deleted"] is True
    assert event.is_set()
    sm.cancel_session.assert_awaited_once_with("2_proj")
    assert "2_proj" not in sm._active_sessions


@pytest.mark.asyncio
async def test_stop_project_reports_cleanup_failure(db, monkeypatch):
    _reset_state(monkeypatch)
    await _seed_session(db, session_id="2_fail")
    monkeypatch.setattr(
        "app.agent.workflow_registry.cancel_workflows_for_session", AsyncMock()
    )
    monkeypatch.setattr(endpoints, "_cancel_active_generation", AsyncMock(return_value=False))
    monkeypatch.setattr(endpoints, "cleanup_session_files", lambda path: False)
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=_sm()))

    result = await endpoints.stop_project("2_fail", {"sub": "2"}, db)
    assert result["files_deleted"] is False
    refreshed = await endpoints.get_user_session("2_fail", {"sub": "2"}, db)
    assert refreshed["error_message"] == "用户停止（文件清理失败）"


@pytest.mark.asyncio
async def test_complete_project_guards_and_success(db, monkeypatch):
    with pytest.raises(HTTPException) as error:
        await endpoints.complete_project("x", {"sub": ""}, db)
    assert error.value.status_code == 403

    with pytest.raises(HTTPException) as error:
        await endpoints.complete_project("missing-1", {"sub": "2"}, db)
    assert error.value.status_code == 404

    await _seed_session(db, session_id="2_idle", status="failed")
    with pytest.raises(HTTPException) as error:
        await endpoints.complete_project("2_idle", {"sub": "2"}, db)
    assert error.value.status_code == 400

    await _seed_session(db, session_id="2_done2")
    monkeypatch.setattr(endpoints, "cleanup_session_files", lambda path: True)
    result = await endpoints.complete_project("2_done2", {"sub": "2"}, db)
    assert result["status"] == "completed"


# ---------------------------------------------------------------------------
# Session search / list / detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_sessions_scores_and_sorts(db, monkeypatch):
    from types import SimpleNamespace as NS

    rows = [
        NS(session_id="a", requirement="login bug fix", status="completed",
           created_at=datetime.now(timezone.utc), files_generated=1, files_total=2),
        NS(session_id="b", requirement="payment module", status="completed",
           created_at=datetime.now(timezone.utc), files_generated=3, files_total=3),
    ]
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=fake_result)

    content = '{"scores": {"a": 0.2, "b": 0.9}}'
    monkeypatch.setattr(
        "app.utils.call_llm",
        AsyncMock(return_value={"choices": [{"message": {"content": content}}]}),
    )

    response = await endpoints.search_sessions(
        SearchSessionsRequest(query="payment", limit=10), {"sub": "2"}, db
    )
    assert [m.session_id for m in response.matches] == ["b", "a"]
    assert response.matches[0].relevance_score == 0.9


@pytest.mark.asyncio
async def test_search_sessions_parses_key_value_fallback(db, monkeypatch):
    from types import SimpleNamespace as NS

    rows = [
        NS(session_id="a", requirement="login", status="completed",
           created_at=None, files_generated=0, files_total=0),
    ]
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=fake_result)

    content = "a: 0.7\nnoise line\nweird: not-a-number"
    monkeypatch.setattr(
        "app.utils.call_llm",
        AsyncMock(return_value={"choices": [{"message": {"content": content}}]}),
    )

    response = await endpoints.search_sessions(
        SearchSessionsRequest(query="login", limit=10), {"sub": "2"}, db
    )
    assert response.matches[0].relevance_score == 0.7


@pytest.mark.asyncio
async def test_search_sessions_llm_failure_returns_zero_scores(db, monkeypatch):
    from types import SimpleNamespace as NS

    rows = [
        NS(session_id="a", requirement="login", status="completed",
           created_at=None, files_generated=0, files_total=0),
    ]
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=fake_result)
    monkeypatch.setattr("app.utils.call_llm", AsyncMock(side_effect=RuntimeError("down")))

    response = await endpoints.search_sessions(
        SearchSessionsRequest(query="login", limit=10), {"sub": "2"}, db
    )
    assert response.matches[0].relevance_score == 0.0


@pytest.mark.asyncio
async def test_search_sessions_maps_db_failure_to_500(db):
    db.execute = AsyncMock(side_effect=RuntimeError("db down"))
    with pytest.raises(HTTPException) as error:
        await endpoints.search_sessions(
            SearchSessionsRequest(query="x", limit=1), {"sub": "2"}, db
        )
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_session_payload_reconnectable_states(monkeypatch):
    base = dict(
        session_id="s", requirement="r", status="running", output_dir="2/s",
        files_generated=0, files_total=0, error_message=None, created_at=None,
        last_activity_at=None, lifecycle_status="active", retention_class="standard",
        pinned=False, archived_at=None, purge_after=None,
    )
    monkeypatch.setattr(endpoints, "_active_tasks", {
        "s": {"gen_task": SimpleNamespace(done=lambda: False), "connected": False}
    })
    assert endpoints._session_payload(SimpleNamespace(**base))["reconnectable"] is True

    monkeypatch.setattr(endpoints, "_active_tasks", {
        "s": {"gen_task": SimpleNamespace(done=lambda: True), "connected": False}
    })
    assert endpoints._session_payload(SimpleNamespace(**base))["reconnectable"] is False

    monkeypatch.setattr(endpoints, "_active_tasks", {})
    assert endpoints._session_payload(SimpleNamespace(**base))["reconnectable"] is False


# ---------------------------------------------------------------------------
# Analysis / snapshot / config endpoints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_analyze_project_complexity_delegates(monkeypatch):
    level = SimpleNamespace(value="medium")
    complexity = SimpleNamespace(
        level=level, estimated_files=4, has_frontend=True, has_backend=True,
        has_database=False, key_technologies=["fastapi"], risk_factors=[],
    )
    assignment = SimpleNamespace(
        architect_model="a", frontend_model="f", backend_model="b",
        reviewer_model="r", fallback_model="m",
    )
    monkeypatch.setattr(
        "app.agent.orchestrator.ComplexityAnalyzer",
        lambda: SimpleNamespace(analyze=lambda req: complexity),
    )
    monkeypatch.setattr(
        "app.agent.orchestrator.LayeredModelRouter",
        SimpleNamespace(get_assignment=lambda level: assignment),
    )

    response = await endpoints.analyze_project_complexity(
        ComplexityAnalysisRequest(requirement="build a web app"), {"sub": "1"}
    )
    assert response.level == "medium"
    assert response.model_assignment["architect"] == "a"


def _patch_snapshot_common(monkeypatch, session):
    monkeypatch.setattr(
        endpoints, "_authorize_snapshot_access", AsyncMock(return_value=session)
    )
    monkeypatch.setattr(
        endpoints, "_locate_snapshot_project_dir", lambda sid, out: "/tmp/project"
    )


@pytest.mark.asyncio
async def test_list_snapshots_maps_fields(monkeypatch):
    snap = SimpleNamespace(tag="v1", commit_hash="abc", message="m", timestamp="t")
    _patch_snapshot_common(monkeypatch, SimpleNamespace(output_dir=None))
    monkeypatch.setattr(
        "app.agent.git_operations.GitOperations",
        lambda: SimpleNamespace(list_snapshots=AsyncMock(return_value=[snap])),
    )
    result = await endpoints.list_snapshots("sess-1", {"sub": "1"}, None)
    assert result["snapshots"][0]["tag"] == "v1"


@pytest.mark.asyncio
async def test_list_snapshots_missing_project_dir(monkeypatch):
    monkeypatch.setattr(
        endpoints, "_authorize_snapshot_access",
        AsyncMock(return_value=SimpleNamespace(output_dir=None)),
    )
    monkeypatch.setattr(endpoints, "_locate_snapshot_project_dir", lambda sid, out: None)
    with pytest.raises(HTTPException) as error:
        await endpoints.list_snapshots("sess-1", {"sub": "1"}, None)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_rollback_to_snapshot_success_and_missing(monkeypatch):
    _patch_snapshot_common(monkeypatch, SimpleNamespace(output_dir=None))
    rollback = AsyncMock(return_value=SimpleNamespace(
        success=True, previous_tag="v0", current_tag="v1",
        files_restored=2, branch_deleted=True,
    ))
    monkeypatch.setattr(
        "app.agent.snapshot_manager.SnapshotManager",
        lambda git_ops: SimpleNamespace(rollback_to_snapshot=rollback),
    )
    result = await endpoints.rollback_to_snapshot("sess-1", "v1", token={"sub": "1"}, db=None)
    assert result["current_tag"] == "v1"

    rollback.return_value = None
    with pytest.raises(HTTPException) as error:
        await endpoints.rollback_to_snapshot("sess-1", "gone", token={"sub": "1"}, db=None)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_rollback_missing_project_dir(monkeypatch):
    monkeypatch.setattr(
        endpoints, "_authorize_snapshot_access",
        AsyncMock(return_value=SimpleNamespace(output_dir=None)),
    )
    monkeypatch.setattr(endpoints, "_locate_snapshot_project_dir", lambda sid, out: None)
    with pytest.raises(HTTPException) as error:
        await endpoints.rollback_to_snapshot("sess-1", "v1", token={"sub": "1"}, db=None)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_diff_snapshots_truncates(monkeypatch):
    _patch_snapshot_common(monkeypatch, SimpleNamespace(output_dir=None))
    monkeypatch.setattr(
        "app.agent.git_operations.GitOperations",
        lambda: SimpleNamespace(
            diff_between_commits=AsyncMock(return_value="x" * 6000)
        ),
    )
    result = await endpoints.diff_snapshots(
        "sess-1", "a", "b", token={"sub": "1"}, db=None
    )
    assert len(result["diff"]) == 5000


@pytest.mark.asyncio
async def test_diff_snapshots_missing_project_dir(monkeypatch):
    monkeypatch.setattr(
        endpoints, "_authorize_snapshot_access",
        AsyncMock(return_value=SimpleNamespace(output_dir=None)),
    )
    monkeypatch.setattr(endpoints, "_locate_snapshot_project_dir", lambda sid, out: None)
    with pytest.raises(HTTPException) as error:
        await endpoints.diff_snapshots("sess-1", "a", "b", token={"sub": "1"}, db=None)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_limit_endpoints(monkeypatch):
    record = SimpleNamespace(
        old_limit=1, new_limit=2, changed_by="admin", timestamp=datetime.now(timezone.utc)
    )
    manager = SimpleNamespace(
        update_concurrent_limit=AsyncMock(return_value=record),
        concurrent_mgr=SimpleNamespace(
            get_recommended_limits=AsyncMock(return_value={"user": 2})
        ),
        get_limit_change_history=lambda limit: [
            SimpleNamespace(role="user", old_limit=1, new_limit=2,
                            changed_by="admin", timestamp=datetime.now(timezone.utc))
        ],
    )
    monkeypatch.setattr(
        "app.utils.system_config.system_config_manager", manager
    )

    with pytest.raises(HTTPException) as error:
        await endpoints.update_concurrent_limits("user", 0, {"sub": "admin"})
    assert error.value.status_code == 400

    updated = await endpoints.update_concurrent_limits("user", 2, {"sub": "admin"})
    assert updated["new_limit"] == 2

    recommended = await endpoints.get_recommended_limits({"sub": "1"})
    assert recommended["recommendations"] == {"user": 2}


@pytest.mark.asyncio
async def test_limit_change_history_serializes(monkeypatch):
    history = [
        SimpleNamespace(role="user", old_limit=1, new_limit=2,
                        changed_by="admin", timestamp=datetime.now(timezone.utc))
    ]
    monkeypatch.setattr(
        "app.utils.system_config.system_config_manager",
        SimpleNamespace(get_limit_change_history=lambda limit: history),
    )
    result = await endpoints.get_limit_change_history(10, {"sub": "1"})
    assert result["history"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_cache_and_learning_endpoints(monkeypatch):
    cache = SimpleNamespace(
        get_stats=lambda: {"entries": 1},
        clear_all=lambda: 3,
        clear_expired=lambda: 2,
    )
    learner = SimpleNamespace(
        get_learning_stats=lambda: {"patterns": 1},
        get_common_errors=lambda ft: [{"type": ft}],
    )
    monkeypatch.setattr(endpoints, "get_spec_cache", AsyncMock(return_value=cache))
    monkeypatch.setattr(
        endpoints, "get_feedback_learner", AsyncMock(return_value=learner)
    )

    assert await endpoints.get_cache_stats({"sub": "1"}) == {"entries": 1}
    assert (await endpoints.clear_cache("all", {"sub": "1"}))["cleared_count"] == 3
    assert (await endpoints.clear_cache("expired", {"sub": "1"}))["cleared_count"] == 2
    assert await endpoints.get_learning_stats({"sub": "1"}) == {"patterns": 1}
    assert await endpoints.get_common_errors("python", {"sub": "1"}) == {
        "errors": [{"type": "python"}]
    }


@pytest.mark.asyncio
async def test_evaluate_project_guards_and_success(monkeypatch):
    with pytest.raises(HTTPException) as error:
        await endpoints.evaluate_project(EvaluateRequest(requirement="x"), {"sub": "x"})
    assert error.value.status_code == 403

    monkeypatch.setattr(endpoints, "_validate_project_target", lambda path, user: path)
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            generate=AsyncMock(
                return_value=dict(RESULT, mode="evaluation_only", requirement="review it")
            )
        )

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)
    response = await endpoints.evaluate_project(
        EvaluateRequest(requirement="review it", output_dir="2/review"),
        {"sub": "2"},
    )
    assert response.mode == "evaluation_only"
    assert captured["evaluation_only"] is True
    assert captured["output_dir"] == "2/review"


@pytest.mark.asyncio
async def test_evaluate_project_maps_failure_to_500(monkeypatch):
    monkeypatch.setattr(endpoints, "_validate_project_target", lambda path, user: path)
    monkeypatch.setattr(
        endpoints, "OrchestratorAgent",
        lambda **kw: SimpleNamespace(generate=AsyncMock(side_effect=RuntimeError("bad"))),
    )
    monkeypatch.setattr(endpoints.logger, "exception", lambda *a, **k: None)
    with pytest.raises(HTTPException) as error:
        await endpoints.evaluate_project(EvaluateRequest(requirement="x"), {"sub": "2"})
    assert error.value.status_code == 500


# ---------------------------------------------------------------------------
# Session actions / decisions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_session_action_rejects_bad_identity():
    with pytest.raises(HTTPException) as error:
        await endpoints.session_action_endpoint("sess-1", "cancel", {"sub": "anonymous"}, None)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_session_action_resume_and_unknown(monkeypatch):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess-1": "2"})
    sm = _sm()
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))

    result = await endpoints.session_action_endpoint(
        "sess-1", "resume", {"sub": "2"}, None
    )
    assert result["status"] == "resumed"
    sm.resume_from_pause.assert_awaited_once_with("sess-1", approved=True)

    with pytest.raises(HTTPException) as error:
        await endpoints.session_action_endpoint(
            "sess-1", "explode", {"sub": "2"}, None
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
@pytest.mark.parametrize("action,approved", [("approve", True), ("reject", False)])
async def test_session_action_approval_pushes_queue(monkeypatch, action, approved):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess-1": "2"})
    queue = asyncio.Queue()
    monkeypatch.setattr(endpoints, "_approval_queues", {"sess-1": queue})
    sm = _sm()
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))

    result = await endpoints.session_action_endpoint(
        "sess-1", action, {"sub": "2"}, None
    )
    assert result["status"] == action
    assert await queue.get() == {"approved": approved}
    sm.resume_from_pause.assert_awaited_once_with("sess-1", approved=approved)


@pytest.mark.asyncio
async def test_session_action_approval_without_queue(monkeypatch):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess-1": "2"})
    sm = _sm()
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    result = await endpoints.session_action_endpoint(
        "sess-1", "approve", {"sub": "2"}, None
    )
    assert result["status"] == "approve"


@pytest.mark.asyncio
async def test_session_action_cancel_with_session_row(monkeypatch):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess-1": "2"})
    event = asyncio.Event()
    monkeypatch.setattr(endpoints, "_cancel_events", {"sess-1": event})
    monkeypatch.setattr(endpoints, "_cancel_active_generation", AsyncMock(return_value=True))
    monkeypatch.setattr(endpoints, "cleanup_session_files", lambda path: True)
    sm = _sm(_active_sessions={"sess-1": object()})
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(
        "app.utils.dynamic_concurrent.ConcurrentLimitManager",
        lambda: SimpleNamespace(unregister_session=lambda role: None),
    )
    row = SimpleNamespace(output_dir="2/x", status="running", error_message=None)
    db = _db(_result(row))

    result = await endpoints.session_action_endpoint(
        "sess-1", "cancel", {"sub": "2", "role": "user"}, db
    )
    assert result["files_deleted"] is True
    assert event.is_set()
    assert row.status == "cancelled"
    assert row.error_message == "用户取消"
    assert "sess-1" not in sm._active_sessions


@pytest.mark.asyncio
async def test_session_action_cancel_without_row(monkeypatch):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess-1": "2"})
    monkeypatch.setattr(endpoints, "_cancel_active_generation", AsyncMock(return_value=False))
    sm = _sm()
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(
        "app.utils.dynamic_concurrent.ConcurrentLimitManager",
        lambda: SimpleNamespace(unregister_session=lambda role: None),
    )
    result = await endpoints.session_action_endpoint(
        "sess-1", "cancel", {"sub": "2"}, _db(_result(None))
    )
    assert result["files_deleted"] is False


@pytest.mark.asyncio
async def test_submit_decision_guards_and_submits(monkeypatch):
    _reset_state(monkeypatch)
    with pytest.raises(HTTPException) as error:
        await endpoints.submit_decision_endpoint("sess-1", {"a": "b"}, {"sub": "x"}, None)
    assert error.value.status_code == 403

    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess-1": "2"})
    queue = asyncio.Queue()
    monkeypatch.setattr(endpoints, "_decision_queues", {"sess-1": queue})
    result = await endpoints.submit_decision_endpoint(
        "sess-1", {"a": "b"}, {"sub": "2"}, None
    )
    assert result["status"] == "submitted"
    assert await queue.get() == {"a": "b"}


@pytest.mark.asyncio
async def test_submit_decision_without_queue_is_ignored(monkeypatch):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"sess-1": "2"})
    result = await endpoints.submit_decision_endpoint(
        "sess-1", {"a": "b"}, {"sub": "2"}, None
    )
    assert result["status"] == "ignored"


@pytest.mark.asyncio
async def test_verify_session_ownership_falls_back_without_db(monkeypatch):
    _reset_state(monkeypatch)
    with pytest.raises(HTTPException) as error:
        await endpoints._verify_session_ownership_or_queue("sess-1", "2", None)
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_verify_session_ownership_uses_db(monkeypatch):
    _reset_state(monkeypatch)
    seen = {}

    async def fake_verify(db, session_id, user_id):
        seen.update(db=db, session_id=session_id, user_id=user_id)

    monkeypatch.setattr(
        "app.api.v1.ai_agent.helpers.verify_session_ownership", fake_verify
    )
    db = object()
    await endpoints._verify_session_ownership_or_queue("sess-1", "2", db)
    assert seen == {"db": db, "session_id": "sess-1", "user_id": "2"}


@pytest.mark.asyncio
async def test_delete_session_bad_identity_and_missing(db):
    with pytest.raises(HTTPException) as error:
        await endpoints.delete_session_endpoint("sess-1", {"sub": None}, db)
    assert error.value.status_code == 401

    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=0))
    with pytest.raises(HTTPException) as error:
        await endpoints.delete_session_endpoint("sess-1", {"sub": "2"}, db)
    assert error.value.status_code == 404


# ---------------------------------------------------------------------------
# Additional stream branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancelled_stream_response_yields_event():
    response = endpoints._cancelled_stream_response()
    events = await _drain(response)
    assert json.loads(events[0][6:])["type"] == "cancelled"


@pytest.mark.asyncio
async def test_iter_queue_events_timeout_continues_then_breaks(monkeypatch):
    class _Task:
        def __init__(self, done):
            self._done = done

        def done(self):
            return self._done

    queue: asyncio.Queue = asyncio.Queue()
    heartbeat = asyncio.create_task(asyncio.Event().wait())
    try:
        # A timeout with a live generation keeps waiting; once the generation
        # task is done the iterator terminates on the next timeout.
        iterator = endpoints._iter_queue_events(
            queue, _Task(True), heartbeat, timeout=0.01
        )
        assert [item async for item in iterator] == []
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)


@pytest.mark.asyncio
async def test_cancel_stream_generation_timeout_then_cancel(monkeypatch):
    _reset_state(monkeypatch)
    cancel_event = asyncio.Event()

    async def _hang():
        await asyncio.Event().wait()

    task = asyncio.create_task(_hang())
    endpoints._active_tasks["s"] = {"gen_task": task}

    async def _timeout(_awaitable, timeout):
        raise asyncio.TimeoutError

    monkeypatch.setattr(endpoints.asyncio, "wait_for", _timeout)
    try:
        await endpoints._cancel_stream_generation("s", cancel_event, task, grace_seconds=0.01)
        assert cancel_event.is_set()
        assert task.cancelled()
        assert "s" not in endpoints._active_tasks
    finally:
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_watch_stream_disconnect_with_channel_unsubscribes(monkeypatch):
    _reset_state(monkeypatch)
    channel = endpoints._SseBroadcast()
    subscriber = channel.subscribe()
    cancel_event = asyncio.Event()
    task = SimpleNamespace(done=lambda: False)
    endpoints._active_tasks["s"] = {"gen_task": task, "connected": True}

    await endpoints._watch_stream_disconnect(
        DisconnectedRequest(), "s", cancel_event, task,
        channel=channel, subscriber_queue=subscriber,
    )
    assert channel.has_subscribers() is False
    assert endpoints._active_tasks["s"]["connected"] is False


@pytest.mark.asyncio
async def test_watch_stream_disconnect_cancelled_returns(monkeypatch):
    cancel_event = asyncio.Event()
    task = SimpleNamespace(done=lambda: False)

    class _CancelOnCheck:
        async def is_disconnected(self):
            raise asyncio.CancelledError

    await endpoints._watch_stream_disconnect(
        _CancelOnCheck(), "s", cancel_event, task
    )


def test_skill_context_includes_workspace_and_session_skills(monkeypatch):
    from types import SimpleNamespace as NS

    workspace = [NS(name="workspace-skill", content="WORKSPACE")]
    manager = SimpleNamespace(
        list_skills=lambda owner_user_id=None: [
            {"name": "user-skill", "description": "alpha beta"},
        ],
        get_skill=lambda name, owner_user_id=None: {"content": "USER"},
    )
    monkeypatch.setattr(
        "app.services.skill_registry.get_registry",
        lambda: SimpleNamespace(discover_skills=lambda req: workspace),
    )
    monkeypatch.setattr(
        "app.services.custom_skill_manager.get_skill_manager", lambda: manager
    )
    monkeypatch.setattr(
        "app.api.v1.agent_host.get_latest_session_skills",
        lambda uid: {
            "session-skill": {"content": "SESSION", "description": "alpha beta"},
            "ignored": {"content": 123},
        },
    )
    monkeypatch.setattr(endpoints.logger, "info", lambda *a, **k: None)

    context = endpoints._skill_context_for_user("1", "alpha beta")
    assert "WORKSPACE" in context
    assert "[user:user-skill]" in context
    assert "[session-skill]" in context
    assert "ignored" not in context


@pytest.mark.asyncio
async def test_handle_analyze_defaults_to_python_without_frontend(monkeypatch, tmp_path):
    (tmp_path / ".dep_graph.json").write_text("{}")

    class _Node:
        file_type = "backend"

    class _NoType:
        pass

    class _Graph:
        nodes = {"a": _NoType(), "b": _Node()}

        @classmethod
        def load(cls, _path):
            return cls()

    engineer = SimpleNamespace(analyze=AsyncMock(return_value="ok"))
    monkeypatch.setattr("app.agent.dependency_graph.DependencyGraph", _Graph)
    monkeypatch.setattr(
        "app.agent.backend_engineer.BackendEngineer", MagicMock(return_value=engineer)
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.get_dynamic_router",
        AsyncMock(return_value=SimpleNamespace(get_best_model=AsyncMock(return_value="m"))),
    )
    await endpoints._handle_analyze_request(
        ModifyRequest(requirement="review"), tmp_path, "1"
    )
    assert engineer.analyze.await_args.kwargs["project_context"]["architecture"]["language"] == "python"


@pytest.mark.asyncio
async def test_modify_core_engine_routes_through_core_handler(monkeypatch, tmp_path):
    events, generated, _, _ = await _drive_modify(
        monkeypatch, tmp_path, engine="core",
        request=ModifyRequest(requirement="add", project_path="1/demo", engine="core"),
    )
    assert any('"type": "done"' in e for e in events)


@pytest.mark.asyncio
async def test_modify_history_summary_counts_errors(monkeypatch, tmp_path):
    result = dict(RESULT, errors=["e1", "e2"])
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: tmp_path)
    monkeypatch.setattr(endpoints, "_is_analyze_intent", lambda req: False)
    store = SimpleNamespace(
        get_history_async=AsyncMock(return_value=[]),
        truncate_history=lambda items: items,
        append_message=AsyncMock(),
    )
    monkeypatch.setattr(endpoints, "get_conversation_store", lambda: store)
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=_sm()))
    monkeypatch.setattr(endpoints, "get_spec_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "get_feedback_learner", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        endpoints, "OrchestratorAgent",
        lambda **kw: SimpleNamespace(
            output_dir=str(tmp_path), generate_incremental=AsyncMock(return_value=result)
        ),
    )
    monkeypatch.setattr(endpoints, "run_workflow", AsyncMock(return_value=None))
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: dict(result))
    monkeypatch.setattr(endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(endpoints, "_create_project_session", AsyncMock())

    response = await endpoints.modify_project(
        ModifyRequest(requirement="add", project_path="1/demo"),
        {"sub": "1"},
        _db(_result(None)),
    )
    await _drain(response)
    summary = store.append_message.await_args_list[-1].args[3]
    assert "2 个错误" in summary


@pytest.mark.asyncio
async def test_modify_outer_exception_yields_error(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda path, user: tmp_path)
    monkeypatch.setattr(endpoints, "_is_analyze_intent", lambda req: False)
    monkeypatch.setattr(
        endpoints,
        "get_conversation_store",
        lambda: SimpleNamespace(
            get_history_async=AsyncMock(return_value=[]),
            truncate_history=lambda items: items,
            append_message=AsyncMock(),
        ),
    )
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=_sm()))
    monkeypatch.setattr(endpoints, "get_spec_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "get_feedback_learner", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "_create_project_session", AsyncMock())
    monkeypatch.setattr(
        endpoints, "OrchestratorAgent",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("ctor boom")),
    )
    monkeypatch.setattr(endpoints.logger, "exception", lambda *a, **k: None)

    response = await endpoints.modify_project(
        ModifyRequest(requirement="add", project_path="1/demo"),
        {"sub": "1"},
        _db(_result(None)),
    )
    events = await _drain(response)
    assert any('"type": "error"' in e for e in events)


@pytest.mark.asyncio
async def test_stream_rate_limit_and_prompt_guard(monkeypatch, tmp_path):
    _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (False, "slow", 2))
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="build", enable_skills=False),
            ConnectedRequest(), {"sub": "1"}, None,
        )
    assert error.value.status_code == 429

    _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (False, "full"))
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="build", enable_skills=False),
            ConnectedRequest(), {"sub": "1"}, None,
        )
    assert error.value.status_code == 507

    _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr("app.utils.guardrails.check_prompt_safety", lambda req: (False, "unsafe"))
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="build", enable_skills=False),
            ConnectedRequest(), {"sub": "1"}, None,
        )
    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_stream_reconnect_existing_live_task_on_default_flag(monkeypatch, tmp_path):
    _patch_stream_common(monkeypatch, tmp_path)
    channel = endpoints._SseBroadcast()
    channel.publish('data: {"type":"done","data":{}}\n\n')
    channel.publish("[DONE]")
    running = SimpleNamespace(session_id="1_old", status="running", created_at=None)
    monkeypatch.setattr(endpoints, "_active_tasks", {
        "1_old": {
            "gen_task": SimpleNamespace(done=lambda: False),
            "channel": channel,
            "connected": True,
            "http_request": DisconnectedRequest(),
        }
    })
    db = _db(_result(running))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert any('"done"' in event for event in events)
    assert events[-1] == "[DONE]"


@pytest.mark.asyncio
async def test_stream_approval_callback_approve_reject_cancel(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    captured = {}
    outcomes = []

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock())

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)

    async def run_workflow(_workflow, **_kwargs):
        queue = endpoints._approval_queues["1_demo"]
        await queue.put({"approved": True})
        outcomes.append(await captured["approval_callback"]("a.py"))
        await queue.put("nope")
        outcomes.append(await captured["approval_callback"]("a.py"))
        captured["cancel_event"].set()
        outcomes.append(await captured["approval_callback"]("a.py"))
        return None

    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="build", project_name="demo",
            enable_skills=False, require_approval=True,
        ),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert captured["approval_callback"] is not None
    assert outcomes == [True, False, False]
    assert any('"cancelled"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_approval_callback_handles_exceptions(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    captured = {}
    outcome = []

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock())

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)

    async def run_workflow(_workflow, **_kwargs):
        async def _boom(*_a, **_k):
            raise RuntimeError("wait broken")

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(endpoints.asyncio, "wait", _boom)
            outcome.append(await captured["approval_callback"]("a.py"))
        return None

    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="build", project_name="demo",
            enable_skills=False, require_approval=True,
        ),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)
    assert outcome == [False]


@pytest.mark.asyncio
async def test_stream_decision_callback_paths(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock())

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)

    async def run_workflow(_workflow, **_kwargs):
        queue = endpoints._decision_queues["1_demo"]
        await queue.put({"db": "sqlite"})
        captured["decision_result"] = await captured["decision_callback"]({"q": ["a", "b"]})
        return None

    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", project_name="demo", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)
    assert captured["decision_result"] == {"db": "sqlite"}


@pytest.mark.asyncio
async def test_stream_stream_callback_wraps_and_passes_through(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    captured = {}

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_dir=str(tmp_path),
            generate=AsyncMock(),
        )

    async def run_workflow(_workflow, **_kwargs):
        cb = captured["callback"]
        await cb(json.dumps({"type": "file", "data": {"path": "a.py"}}))
        await cb(json.dumps({"type": "other", "data": 1}))
        await cb("not json")
        return None

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)
    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert any('"type": "file"' in event for event in events)
    assert any('"type": "progress"' in event for event in events)
    assert any('"type": "log"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_cancel_after_generation_skips_complete(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    cancel_event = asyncio.Event()
    monkeypatch.setattr(endpoints, "_register_pending_stream", lambda sid, uid: cancel_event)

    async def run_workflow(_workflow, **_kwargs):
        cancel_event.set()
        return None

    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    sm.cancel_session.assert_awaited()
    sm.complete_session.assert_not_awaited()
    assert any('"cancelled"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_generation_cancelled_error(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        endpoints, "run_workflow", AsyncMock(side_effect=asyncio.CancelledError())
    )
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    sm.cancel_session.assert_awaited()
    assert events


@pytest.mark.asyncio
async def test_stream_outer_generator_error(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(
        endpoints, "OrchestratorAgent",
        lambda **kw: (_ for _ in ()).throw(RuntimeError("ctor down")),
    )
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert any('"type": "error"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_uses_session_state_for_incremental(monkeypatch, tmp_path):
    state = SimpleNamespace(file_statuses={})
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path, store_session=state)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="build", session_id="1_demo", incremental=True,
            enable_skills=False,
        ),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)
    sm.resume_session.assert_awaited_with("1_demo")
    sm.create_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_reconnect_times_out_while_task_runs(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    channel = endpoints._SseBroadcast()
    running = SimpleNamespace(session_id="1_old", status="running", created_at=None)
    monkeypatch.setattr(endpoints, "_active_tasks", {
        "1_old": {
            "gen_task": SimpleNamespace(done=lambda: False),
            "channel": channel,
            "connected": True,
            "http_request": DisconnectedRequest(),
        }
    })
    monkeypatch.setattr(endpoints, "_mark_disconnected_if_stale", AsyncMock(return_value=True))
    db = _db(_result(running))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    iterator = response.body_iterator
    first = await _anext_or_none(iterator)
    assert first is None or first.startswith("data: ")


async def _anext_or_none(iterator):
    async def _consume():
        return await iterator.__anext__()

    try:
        return await asyncio.wait_for(_consume(), timeout=0.01)
    except asyncio.TimeoutError:
        return None
    except StopAsyncIteration:
        return None


# ---------------------------------------------------------------------------
# Token usage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_usage_rejects_bad_identity():
    with pytest.raises(HTTPException) as error:
        await endpoints.get_token_usage_stats({"sub": "anonymous"}, None)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_token_usage_aggregates_rows(db):
    totals = SimpleNamespace(
        total_tokens=100, total_prompt_tokens=60,
        total_completion_tokens=40, total_messages=5,
    )
    today = SimpleNamespace(today_tokens=10)
    month = SimpleNamespace(month_tokens=50)
    model_result = MagicMock()
    model_result.all.return_value = [
        SimpleNamespace(model="m1", model_tokens=70),
        SimpleNamespace(model="m2", model_tokens=None),
    ]
    db.execute = AsyncMock(side_effect=[
        SimpleNamespace(first=lambda: totals),
        SimpleNamespace(first=lambda: today),
        SimpleNamespace(first=lambda: month),
        model_result,
    ])

    result = await endpoints.get_token_usage_stats({"sub": "2"}, db)
    assert result.total_tokens == 100
    assert result.today_tokens == 10
    assert result.this_month_tokens == 50
    assert result.by_model == {"m1": 70, "m2": 0}


@pytest.mark.asyncio
async def test_token_usage_falls_back_to_defaults(db):
    db.execute = AsyncMock(side_effect=RuntimeError("db unavailable"))
    monkeypatch_result = await endpoints.get_token_usage_stats({"sub": "2"}, db)
    assert monkeypatch_result.total_tokens == 0
    assert monkeypatch_result.by_model == {}


# ---------------------------------------------------------------------------
# Remaining narrow branches
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mark_disconnected_when_generation_done():
    active = {"gen_task": SimpleNamespace(done=lambda: True), "connected": True}
    assert await endpoints._mark_disconnected_if_stale(active) is True
    assert active["connected"] is False


@pytest.mark.asyncio
async def test_mark_disconnected_reports_not_connected():
    active = {
        "gen_task": SimpleNamespace(done=lambda: False),
        "connected": False,
        "http_request": ConnectedRequest(),
    }
    assert await endpoints._mark_disconnected_if_stale(active) is True


@pytest.mark.asyncio
async def test_mark_disconnected_live_and_connected():
    active = {
        "gen_task": SimpleNamespace(done=lambda: False),
        "connected": True,
        "http_request": ConnectedRequest(),
    }
    assert await endpoints._mark_disconnected_if_stale(active) is False


@pytest.mark.asyncio
async def test_cancel_stream_generation_no_active_record(monkeypatch):
    _reset_state(monkeypatch)
    cancel_event = asyncio.Event()

    async def _done():
        return None

    task = asyncio.create_task(_done())
    await asyncio.gather(task)
    await endpoints._cancel_stream_generation("missing", cancel_event, task)
    assert cancel_event.is_set()


@pytest.mark.asyncio
async def test_watch_stream_disconnect_without_channel(monkeypatch):
    _reset_state(monkeypatch)
    endpoints._active_tasks["s"] = {"gen_task": SimpleNamespace(done=lambda: False),
                                    "connected": True}
    cancel_event = asyncio.Event()
    await endpoints._watch_stream_disconnect(
        DisconnectedRequest(), "s", cancel_event, SimpleNamespace(done=lambda: False)
    )
    assert endpoints._active_tasks["s"]["connected"] is False


@pytest.mark.asyncio
async def test_stream_requested_cancel_from_previous_session(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    old = asyncio.Event()
    old.set()
    monkeypatch.setattr(endpoints, "_cancel_events", {"1_old": old})
    monkeypatch.setattr(endpoints, "_pending_stream_owners", {"1_old": "1"})
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="build", session_id="1_old",
            project_name="demo", enable_skills=False,
        ),
        ConnectedRequest(), {"sub": "1"}, db,
    )
    events = await _drain(response)
    assert '"cancelled"' in events[0]


@pytest.mark.asyncio
async def test_stream_session_row_missing_when_cancelled_before_start(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(endpoints, "_register_pending_stream", lambda sid, uid: _set_event())
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1"}, db,
    )
    events = await _drain(response)
    assert '"cancelled"' in events[0]
    sm.create_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_stream_cancelled_before_start_updates_row_error(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    row = SimpleNamespace(status="running", error_message=None)
    db.execute.side_effect = [_result(None), _result(None), _result(row)]
    db.commit = AsyncMock(side_effect=RuntimeError("commit failed"))
    monkeypatch.setattr(endpoints, "_register_pending_stream", lambda sid, uid: _set_event())
    monkeypatch.setattr(endpoints.logger, "warning", lambda *a, **k: None)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1"}, db,
    )
    events = await _drain(response)
    assert '"cancelled"' in events[0]


@pytest.mark.asyncio
async def test_stream_resume_intent_falls_back_to_new_session(monkeypatch, tmp_path):
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": False, "additional_requirement": "",
    }))
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="continue", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert any('"done"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_resume_target_without_changes_uses_original(monkeypatch, tmp_path):
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": False, "additional_requirement": "",
    }))
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=target))
    monkeypatch.setattr(
        endpoints, "get_user_recent_session", AsyncMock(return_value=None)
    )
    db.execute.side_effect = [
        _result(None),
        _result(SimpleNamespace(status="running", requirement="original")),
    ]
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="continue", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert any('"done"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_resume_row_lookup_exception_creates_session(monkeypatch, tmp_path):
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    db, sm, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": False, "additional_requirement": "",
    }))
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=target))
    monkeypatch.setattr(endpoints, "get_user_recent_session", AsyncMock(return_value=None))
    db.execute.side_effect = [_result(None)]
    db.commit = AsyncMock(side_effect=RuntimeError("commit boom"))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="continue", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert any('"done"' in event for event in events)


@pytest.mark.asyncio
async def test_decision_callback_cancel_and_none_paths(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    captured = {}
    results = []

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock())

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)

    async def run_workflow(_workflow, **_kwargs):
        queue = endpoints._decision_queues["1_demo"]

        async def _none_timeout(*_a, **_k):
            return set(), set()

        queue.put_nowait(None)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(endpoints.asyncio, "wait", _none_timeout)
            results.append(await captured["decision_callback"]({"q": []}))

        captured["cancel_event"].set()
        results.append(await captured["decision_callback"]({"q": []}))
        return None

    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", project_name="demo", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)
    assert results == [None, None]


@pytest.mark.asyncio
async def test_stream_approval_timeout_path(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    captured = {}
    outcome = []

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock())

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)

    async def run_workflow(_workflow, **_kwargs):
        async def _empty(*_a, **_k):
            return set(), set()

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(endpoints.asyncio, "wait", _empty)
            outcome.append(await captured["approval_callback"]("a.py"))
        return None

    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="build", project_name="demo",
            enable_skills=False, require_approval=True,
        ),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)
    assert outcome == [False]


@pytest.mark.asyncio
async def test_iter_queue_events_live_task_times_out_then_finishes():
    class _Task:
        def __init__(self):
            self.calls = 0

        def done(self):
            self.calls += 1
            return self.calls > 1

    queue: asyncio.Queue = asyncio.Queue()
    heartbeat = asyncio.create_task(asyncio.Event().wait())
    try:
        events = [
            item
            async for item in endpoints._iter_queue_events(
                queue, _Task(), heartbeat, timeout=0.01
            )
        ]
    finally:
        heartbeat.cancel()
        await asyncio.gather(heartbeat, return_exceptions=True)
    assert events == []


@pytest.mark.asyncio
async def test_watch_stream_disconnect_without_active_record(monkeypatch):
    _reset_state(monkeypatch)
    cancel_event = asyncio.Event()
    await endpoints._watch_stream_disconnect(
        DisconnectedRequest(), "s", cancel_event, SimpleNamespace(done=lambda: False)
    )
    assert endpoints._active_tasks == {}


def test_skill_context_skips_missing_user_detail(monkeypatch):
    manager = SimpleNamespace(
        list_skills=lambda owner_user_id=None: [
            {"name": "user-skill", "description": "alpha beta"},
        ],
        get_skill=lambda name, owner_user_id=None: None,
    )
    monkeypatch.setattr(
        "app.services.skill_registry.get_registry",
        lambda: SimpleNamespace(discover_skills=lambda req: []),
    )
    monkeypatch.setattr(
        "app.services.custom_skill_manager.get_skill_manager", lambda: manager
    )
    monkeypatch.setattr(
        "app.api.v1.agent_host.get_latest_session_skills", lambda uid: {}
    )

    assert endpoints._skill_context_for_user("1", "alpha beta") == ""


@pytest.mark.asyncio
async def test_list_user_sessions_rejects_bad_identity(db):
    with pytest.raises(HTTPException) as error:
        await endpoints.list_user_sessions({"sub": "abc"}, db, 50)
    assert error.value.status_code == 403


@pytest.mark.asyncio
async def test_list_user_sessions_returns_payloads(db):
    rows = [SimpleNamespace(
        session_id="s1", requirement="r", status="running",
        lifecycle_status="active", retention_class="standard", pinned=False,
        archived_at=None, purge_after=None, files_generated=1, files_total=2,
        error_message=None, created_at=None, last_activity_at=None,
        output_dir="2/s1",
    )]
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=result)

    response = await endpoints.list_user_sessions({"sub": "2"}, db, 10)
    assert response["sessions"][0]["session_id"] == "s1"


@pytest.mark.asyncio
async def test_stop_and_complete_without_output_dir(db, monkeypatch):
    _reset_state(monkeypatch)
    await _seed_session(db, session_id="2_nodir1", output_dir="")
    monkeypatch.setattr(
        "app.agent.workflow_registry.cancel_workflows_for_session", AsyncMock()
    )
    monkeypatch.setattr(endpoints, "_cancel_active_generation", AsyncMock(return_value=False))
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=_sm()))
    stopped = await endpoints.stop_project("2_nodir1", {"sub": "2"}, db)
    assert stopped["files_deleted"] is False

    await _seed_session(db, session_id="2_nodir2", output_dir="")
    completed = await endpoints.complete_project("2_nodir2", {"sub": "2"}, db)
    assert completed["status"] == "completed"


@pytest.mark.asyncio
async def test_delete_session_cleans_existing_project_dir(db, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    project = tmp_path / "projects" / "orchestrator" / "2_sess"
    project.mkdir(parents=True)
    db.execute = AsyncMock(return_value=SimpleNamespace(rowcount=1))
    monkeypatch.setattr(endpoints, "_cancel_active_generation", AsyncMock(return_value=False))
    monkeypatch.setattr(endpoints, "_cleanup_session_queues", AsyncMock())
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=_sm()))

    result = await endpoints.delete_session_endpoint(
        "2_sess", {"sub": "2", "role": "user"}, db
    )
    assert result["success"] is True
    assert not project.exists()


@pytest.mark.asyncio
async def test_search_sessions_rejects_invalid_identity(db):
    with pytest.raises(HTTPException) as error:
        await endpoints.search_sessions(
            SearchSessionsRequest(query="x", limit=1), {"sub": "anonymous"}, db
        )
    assert error.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize("content", ["[1, 2]", '{"scores": broken}'])
async def test_search_sessions_falls_back_when_json_shape_invalid(db, monkeypatch, content):
    rows = [SimpleNamespace(
        session_id="a", requirement="login", status="completed",
        created_at=None, files_generated=0, files_total=0,
    )]
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = rows
    db.execute = AsyncMock(return_value=fake_result)
    monkeypatch.setattr(
        "app.utils.call_llm",
        AsyncMock(return_value={"choices": [{"message": {"content": content}}]}),
    )

    response = await endpoints.search_sessions(
        SearchSessionsRequest(query="login", limit=10), {"sub": "2"}, db
    )
    assert response.matches[0].relevance_score == 0.0


@pytest.mark.asyncio
async def test_orchestrate_response_validation_failure_closes_metrics_once_more(
    monkeypatch, tmp_path
):
    _patch_orchestrate_common(monkeypatch, tmp_path)
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: {"success": True})
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project(
            OrchestratorRequest(requirement="build", enable_skills=False),
            {"sub": "1"},
            None,
        )
    assert error.value.status_code == 500


@pytest.mark.asyncio
async def test_orchestrate_core_handler_runs(monkeypatch, tmp_path):
    _reset_state(monkeypatch)
    monkeypatch.setattr(endpoints, "_validate_project_target", lambda path, user: tmp_path)
    monkeypatch.setattr(
        endpoints, "create_agent_session",
        AsyncMock(return_value=SimpleNamespace(id="sess-1")),
    )
    monkeypatch.setattr(endpoints, "generate_single_file", AsyncMock(return_value=None))
    monkeypatch.setattr(endpoints, "_skill_context_for_user", lambda *a, **k: "")
    monkeypatch.setattr(endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(endpoints, "update_model_stats", AsyncMock())
    monkeypatch.setattr(
        endpoints, "OrchestratorAgent",
        lambda **kw: SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock()),
    )
    executed = AsyncMock(return_value=dict(RESULT))
    monkeypatch.setattr(endpoints, "execute_core_generation", executed)

    async def fake_run_workflow(workflow, **_kwargs):
        await workflow.core_handler(None)
        return None

    monkeypatch.setattr(endpoints, "run_workflow", fake_run_workflow)
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: dict(RESULT))

    response = await endpoints.orchestrate_project(
        OrchestratorRequest(
            requirement="build", engine="core", enable_skills=False,
        ),
        {"sub": "1"},
        None,
    )
    assert response.success is True
    executed.assert_awaited_once()


@pytest.mark.asyncio
async def test_resume_events_heartbeat_then_task_done(monkeypatch):
    _reset_state(monkeypatch)
    channel = endpoints._SseBroadcast()

    class _Task:
        def __init__(self):
            self.calls = 0

        def done(self):
            self.calls += 1
            return self.calls > 2

    active = {
        "gen_task": _Task(), "channel": channel, "connected": False,
        "http_request": ConnectedRequest(),
    }
    session = SimpleNamespace(session_id="1_sess", status="running")
    monkeypatch.setattr(endpoints, "verify_session_ownership", AsyncMock(return_value=session))
    monkeypatch.setattr(
        endpoints, "_mark_disconnected_if_stale", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(endpoints, "_active_tasks", {"1_sess": active})

    async def fake_wait_for(awaitable, timeout):
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(endpoints.asyncio, "wait_for", fake_wait_for)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="x", session_id="1_sess", is_resume=True, enable_skills=False,
        ),
        ConnectedRequest(), {"sub": "1"}, None,
    )
    events = await _drain(response)
    assert events == [": heartbeat\n\n"]
    assert "1_sess" in endpoints._active_tasks


@pytest.mark.asyncio
async def test_stream_supersede_live_stale_task_for_new_session(monkeypatch, tmp_path):
    db, _, _, _ = _patch_stream_common(monkeypatch, tmp_path)
    running = SimpleNamespace(
        session_id="1_old", status="running", error_message=None, created_at=None,
    )
    superseded = AsyncMock()
    monkeypatch.setattr(endpoints, "_supersede_running_generation", superseded)
    monkeypatch.setattr(endpoints, "_mark_disconnected_if_stale", AsyncMock(return_value=True))
    monkeypatch.setattr(endpoints, "_active_tasks", {
        "1_old": {"gen_task": SimpleNamespace(done=lambda: False)},
    })
    db.execute.side_effect = [_result(running), _result(None)]

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", session_id="1_new", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)
    superseded.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_reconnect_timeout_heartbeat_then_done(monkeypatch, tmp_path):
    _patch_stream_common(monkeypatch, tmp_path)

    class _Task:
        def __init__(self):
            self.calls = 0

        def done(self):
            self.calls += 1
            return self.calls > 1

    running = SimpleNamespace(session_id="1_old", status="running", created_at=None)
    monkeypatch.setattr(endpoints, "_active_tasks", {
        "1_old": {
            "gen_task": _Task(), "channel": endpoints._SseBroadcast(),
            "connected": True, "http_request": DisconnectedRequest(),
        }
    })
    monkeypatch.setattr(endpoints, "_mark_disconnected_if_stale", AsyncMock(return_value=True))
    db = _db(_result(running))

    async def fake_wait_for(awaitable, timeout):
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(endpoints.asyncio, "wait_for", fake_wait_for)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    assert await _drain(response) == []
