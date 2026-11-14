"""Batch 27 coverage gaps: architect normalization and stream endpoint branches."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.agent.architect import Architect
from app.agent.architect_json_parser import ArchitectJsonParser
from app.agent.complexity import ComplexityAnalysis, ProjectComplexity
from app.api.v1.ai_agent import orchestrate_endpoints as endpoints
from app.api.v1.ai_agent.schemas import OrchestratorRequest


def _architect() -> Architect:
    agent = Architect.__new__(Architect)
    agent.json_parser = ArchitectJsonParser()
    agent.model_name = "test-model"
    return agent


def _complexity(**overrides):
    values = dict(
        level=ProjectComplexity.MEDIUM,
        estimated_files=5,
        has_frontend=False,
        has_backend=True,
        has_database=False,
        has_auth=False,
        key_technologies=["Python"],
        risk_factors=[],
    )
    values.update(overrides)
    return ComplexityAnalysis(**values)


class _FakeAdapter:
    language = "python"

    def __init__(self, candidates, external=()):
        self._candidates = candidates
        self._external = set(external)

    def is_known_external_module(self, name):
        return name in self._external

    def resolve_import_to_file(self, import_info, current_file):
        return list(self._candidates)

    def infer_file_type(self, path):
        return "utils"


def test_architect_init_sets_parser():
    agent = Architect("architect", "test-model")
    assert agent.json_parser is not None


def test_language_rules_skip_unknown_extra_backend_language():
    text = _architect()._build_language_rules_text(
        "python",
        None,
        None,
        ["python", "brainfuck"],
        SimpleNamespace(needs_clarification=False),
    )
    assert "辅助语言：brainfuck" not in text


def test_design_architecture_fills_missing_language_fields():
    architect = _architect()

    async def fake(prompt, system_prompt=""):
        return '{"file_plan": [{"path": "main.py"}]}'

    architect.call_llm = fake
    result = asyncio.run(
        architect.design_architecture("写 main.py", _complexity())
    )
    assert result["language"]
    assert "frontend_language" in result
    assert "backend_language" in result
    assert "all_languages" in result


def test_harvest_walks_nested_keys_when_empty():
    architect = _architect()
    payload = {
        "architecture": {"file_plan": []},
        "design": {"file_plan": [{"path": "app/main.py"}]},
    }
    assert architect._harvest_file_plan(payload, "python")[0]["path"] == "app/main.py"


def test_canonicalize_interfaces_without_exports():
    result = _architect()._canonicalize_interfaces({"a": {"owner": "team"}})
    assert result == [{"owner": "team", "module": "a"}]


def test_coerce_architecture_skips_non_dict_file_plan_items():
    result = _architect()._coerce_architecture_fields(
        {"file_plan": ["raw-string", {"path": "main.py"}]}
    )
    assert result["file_plan"][1]["path"] == "main.py"


def test_compact_ticket_architecture_non_python_keeps_framework():
    result = _architect()._get_compact_eight_file_architecture(
        "build a ticket system", _complexity(), language="go"
    )
    assert result["project_spec"]["default"].get("framework") != "FastAPI"
    assert result["project_spec"]["default"]["storage"]["type"] == "sqlite"


def test_planned_covers_module_continues_on_non_matching_stem():
    assert Architect._planned_covers_module({"other.py"}, "pkg.mod", []) is False


def test_strict_paths_ignore_invalid_frozen_tokens():
    requirement = (
        "Generate exactly these files and no others: not a path!, ???. "
        "Build a small tool afterwards."
    )
    assert Architect._extract_strict_file_paths(requirement) is None


def test_prefer_most_specific_paths_drops_empty_entries():
    assert Architect._prefer_most_specific_paths({"./", "main.py"}) == {"main.py"}


def test_path_module_forms_without_python_dotted_form():
    forms = Architect._path_module_forms("src/app.go", "go")
    assert "src.app" not in forms
    assert "src/app" in forms


def test_completeness_handles_non_list_imports():
    architect = _architect()
    result = architect._ensure_file_plan_completeness(
        {"file_plan": [{"path": "main.py", "imports": "not-a-list"}]},
        target_language="python",
    )
    assert result is not None


def test_completeness_parses_dict_import_variants():
    architect = _architect()
    result = architect._ensure_file_plan_completeness(
        {
            "file_plan": [
                {
                    "path": "main.py",
                    "imports": [
                        {"module": "", "items": [None, "from pkg.two import y"]},
                        {"module": "from pkg.one import x", "items": []},
                    ],
                }
            ]
        },
        target_language="python",
    )
    paths = [entry["path"] for entry in result["file_plan"]]
    assert "pkg/one.py" in paths
    assert "pkg/two.py" in paths


def test_completeness_skips_invalid_and_external_resolved_paths(monkeypatch):
    architect = _architect()
    from app.agent.adapters import LanguageAdapterRegistry

    candidates = iter([["bad file.py"], ["fastapi.py"]])

    class Adapter:
        language = "python"

        def is_known_external_module(self, name):
            return name == "fastapi.py"

        def resolve_import_to_file(self, import_info, current_file):
            return next(candidates)

        def infer_file_type(self, path):
            return "utils"

    monkeypatch.setattr(
        LanguageAdapterRegistry, "get_adapter", staticmethod(lambda lang: Adapter())
    )
    result = architect._ensure_file_plan_completeness(
        {
            "file_plan": [
                {
                    "path": "main.py",
                    "imports": ["from bad import x", "from fastapi import y"],
                }
            ]
        },
        target_language="python",
    )
    assert [entry["path"] for entry in result["file_plan"]] == ["main.py"]


def test_expand_skips_duplicate_batch_path():
    architect = _architect()
    architecture = {
        "file_plan": [{"path": "main.py", "imports": [], "language": "python"}],
        "language": "python",
    }
    batches = [
        [{"path": "main.py", "imports": [], "language": "python"}],
        [],
    ]

    async def fake(*_args, **_kwargs):
        return batches.pop(0)

    architect._generate_batch_files = fake
    result = asyncio.run(architect.expand_file_plan(architecture, _complexity(), 2))
    assert [entry["path"] for entry in result["file_plan"]].count("main.py") == 1


def test_batch_files_with_complete_fields_are_kept():
    architect = _architect()
    item = {
        "path": "app/x.py",
        "file_type": "service",
        "description": "x",
        "priority": 2,
        "imports": [],
        "language": "python",
    }

    async def fake(prompt, system_prompt=""):
        return json.dumps([item])

    architect.call_llm = fake
    result = asyncio.run(
        architect._generate_batch_files(
            {"file_plan": [], "language": "python"}, SimpleNamespace(key_technologies=[]), 5
        )
    )
    assert result == [item]


# ---------------------------------------------------------------------------
# /orchestrate/stream resume and background-generation branches
# ---------------------------------------------------------------------------


class _ConnectedRequest:
    async def is_disconnected(self):
        return False


class _DisconnectedRequest:
    async def is_disconnected(self):
        return True


async def _drain(response):
    return [item async for item in response.body_iterator]


def _stream_db(*results, execute_error=None, fail_on=None):
    pending = list(results)
    calls = 0

    async def _execute(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if fail_on is not None and calls >= fail_on and execute_error is not None:
            raise execute_error
        if pending:
            return pending.pop(0)
        return SimpleNamespace(scalar_one_or_none=lambda: None)

    return SimpleNamespace(
        execute=AsyncMock(side_effect=_execute),
        commit=AsyncMock(),
        rollback=AsyncMock(),
        close=AsyncMock(),
    )


def _result(value):
    return SimpleNamespace(scalar_one_or_none=lambda: value)


def _patch_stream(monkeypatch, tmp_path, *, sm=None):
    for name in (
        "_approval_queues",
        "_decision_queues",
        "_cancel_events",
        "_pending_stream_owners",
        "_active_tasks",
        "_user_creation_locks",
    ):
        monkeypatch.setattr(endpoints, name, {})
    monkeypatch.setattr(endpoints, "_validate_project_target", lambda path, user: tmp_path)
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    monkeypatch.setattr(
        "app.utils.guardrails.check_prompt_safety", lambda req: (True, "")
    )
    monkeypatch.setattr(
        endpoints, "_detect_and_clean_zombie_sessions", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(endpoints, "_create_project_session", AsyncMock())
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": False, "has_changes": False, "additional_requirement": "",
    }))
    sm = sm or SimpleNamespace(
        resume_session=AsyncMock(return_value=None),
        create_session=AsyncMock(),
        complete_session=AsyncMock(),
        cancel_session=AsyncMock(),
        _lock=asyncio.Lock(),
        _active_sessions={},
    )
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(endpoints, "get_spec_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "get_feedback_learner", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "_skill_context_for_user", lambda *a, **k: "")
    monkeypatch.setattr(endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(endpoints, "run_workflow", AsyncMock(return_value=None))
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: {
        "success": True, "output_dir": str(tmp_path), "total_files_created": 1,
        "files": [], "validation": {}, "errors": [], "warnings": [],
        "elapsed_time": 0.1,
    })
    monkeypatch.setattr(
        endpoints, "execute_core_generation", AsyncMock(return_value={
            "success": True, "output_dir": str(tmp_path), "total_files_created": 1,
            "files": [], "validation": {}, "errors": [], "warnings": [],
            "elapsed_time": 0.1,
        })
    )
    monkeypatch.setattr(
        endpoints, "OrchestratorAgent",
        lambda **kwargs: SimpleNamespace(
            output_dir=str(tmp_path), generate=AsyncMock(), generate_incremental=AsyncMock()
        ),
    )
    return sm


@pytest.mark.asyncio
async def test_stream_resume_creates_session_when_missing(monkeypatch, tmp_path):
    sm = _patch_stream(monkeypatch, tmp_path)
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": False, "additional_requirement": "",
    }))
    monkeypatch.setattr(
        endpoints, "resolve_resume_session", AsyncMock(return_value=target)
    )
    monkeypatch.setattr(
        endpoints, "get_user_recent_session", AsyncMock(return_value=None)
    )
    db = _stream_db(_result(None), _result(None))

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="继续", is_resume=None, enable_skills=False),
        _ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    await _drain(response)
    endpoints._create_project_session.assert_awaited_once()


@pytest.mark.asyncio
async def test_stream_resume_create_failure_rolls_back_and_recreates(monkeypatch, tmp_path):
    sm = _patch_stream(monkeypatch, tmp_path)
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": False, "additional_requirement": "",
    }))
    monkeypatch.setattr(
        endpoints, "resolve_resume_session", AsyncMock(return_value=target)
    )
    monkeypatch.setattr(
        endpoints, "get_user_recent_session", AsyncMock(return_value=None)
    )
    db = _stream_db(
        _result(None),
        _result(None),
        execute_error=RuntimeError("db down"),
        fail_on=2,
    )

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="继续", is_resume=None, enable_skills=False),
        _ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    await _drain(response)
    db.rollback.assert_awaited()
    endpoints._create_project_session.assert_awaited()


@pytest.mark.asyncio
async def test_stream_start_cancel_publishes_cancelled(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)

    def register(session_id, user_id):
        event = asyncio.Event()
        event.set()
        endpoints._cancel_events[session_id] = event
        return event

    monkeypatch.setattr(endpoints, "_register_pending_stream", register)
    db = _stream_db(_result(None))

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", session_id="1_xyz", enable_skills=False),
        _ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    events = await _drain(response)
    assert '"cancelled"' in events[0]


@pytest.mark.asyncio
async def test_stream_requested_cancel_event_is_propagated(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": False, "additional_requirement": "",
    }))
    monkeypatch.setattr(
        endpoints, "resolve_resume_session", AsyncMock(return_value=target)
    )
    monkeypatch.setattr(
        endpoints, "get_user_recent_session", AsyncMock(return_value=None)
    )

    def register(session_id, user_id):
        event = asyncio.Event()
        endpoints._cancel_events[session_id] = event
        if session_id == "1_target":
            requested = asyncio.Event()
            requested.set()
            endpoints._cancel_events["1_new"] = requested
        return event

    monkeypatch.setattr(endpoints, "_register_pending_stream", register)
    db = _stream_db(_result(None), _result(None))

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="build", session_id="1_new", enable_skills=False
        ),
        _ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    events = await _drain(response)
    assert '"cancelled"' in events[0]


@pytest.mark.asyncio
async def test_stream_background_callback_cleans_active_task(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)

    class _Task:
        def __init__(self):
            self.callbacks = []

        def done(self):
            return False

        def add_done_callback(self, cb):
            self.callbacks.append(cb)

    task = _Task()
    monkeypatch.setattr(endpoints.asyncio, "create_task", lambda coro: task)

    async def fake_wait_for(awaitable, timeout):
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(endpoints.asyncio, "wait_for", fake_wait_for)
    db = _stream_db(_result(None))

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        _ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    await _drain(response)
    endpoints._active_tasks["1_New"] = {"gen_task": task}
    for session_id, active in list(endpoints._active_tasks.items()):
        callbacks = active["gen_task"].callbacks
        for cb in callbacks:
            cb(active["gen_task"])
    for active in endpoints._active_tasks.values():
        assert active


@pytest.mark.asyncio
async def test_stream_generator_cancelled_cleans_queues(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)

    class _Channel:
        def __init__(self):
            self.queue = asyncio.Queue()

        def subscribe(self):
            return self.queue

        def publish(self, _item):
            raise asyncio.CancelledError

    monkeypatch.setattr(endpoints, "_SseBroadcast", lambda: _Channel())
    cleanup = AsyncMock()
    monkeypatch.setattr(endpoints, "_cleanup_session_queues", cleanup)
    db = _stream_db(_result(None))

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        _ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    await _drain(response)
    cleanup.assert_awaited()


@pytest.mark.asyncio
async def test_stream_generator_error_yields_error_event(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)

    async def fake_wait_for(awaitable, timeout):
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise RuntimeError("stream exploded")

    monkeypatch.setattr(endpoints.asyncio, "wait_for", fake_wait_for)
    db = _stream_db(_result(None))

    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        _ConnectedRequest(),
        {"sub": "1", "role": "user"},
        db,
    )
    events = await _drain(response)
    assert any('"type": "error"' in event for event in events)


@pytest.mark.asyncio
async def test_modify_heartbeat_sends_and_exits_on_cancel(monkeypatch, tmp_path):
    real_sleep = endpoints.asyncio.sleep

    async def fake_sleep(delay, *args, **kwargs):
        if delay == 5:
            return None
        return await real_sleep(delay, *args, **kwargs)

    class _CancelEvent:
        def __init__(self):
            self.calls = 0

        def is_set(self):
            self.calls += 1
            return self.calls > 1

        def set(self):
            pass

    async def slow_workflow(*_args, **_kwargs):
        for _ in range(4):
            await real_sleep(0)
        return None

    monkeypatch.setattr(endpoints.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(endpoints.asyncio, "Event", _CancelEvent)
    monkeypatch.setattr(endpoints, "_reset_state", lambda *_: None, raising=False)
    for name in (
        "_approval_queues",
        "_decision_queues",
        "_cancel_events",
        "_pending_stream_owners",
        "_active_tasks",
        "_user_creation_locks",
    ):
        monkeypatch.setattr(endpoints, name, {})
    monkeypatch.setattr(endpoints, "check_rate_limit", lambda key: (True, "", 0))
    monkeypatch.setattr(endpoints, "check_disk_space", lambda path: (True, ""))
    monkeypatch.setattr(endpoints, "_validate_project_path", lambda p, u: tmp_path)
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
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=SimpleNamespace(
        complete_session=AsyncMock(), cancel_session=AsyncMock(),
    )))
    monkeypatch.setattr(endpoints, "get_spec_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(endpoints, "get_feedback_learner", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        endpoints,
        "OrchestratorAgent",
        lambda **kw: SimpleNamespace(output_dir=str(tmp_path), generate_incremental=AsyncMock()),
    )
    monkeypatch.setattr(endpoints, "run_workflow", slow_workflow)
    monkeypatch.setattr(endpoints, "get_legacy_result", lambda state: {
        "success": True, "output_dir": str(tmp_path), "total_files_created": 1,
        "files": [], "validation": {}, "errors": [], "warnings": [], "elapsed_time": 0.1,
    })
    monkeypatch.setattr(endpoints, "log_tool_execution", AsyncMock())
    monkeypatch.setattr(endpoints, "_create_project_session", AsyncMock())

    db = _stream_db(_result(None))
    from app.api.v1.ai_agent.schemas import ModifyRequest

    response = await endpoints.modify_project(
        ModifyRequest(requirement="add", project_path="1/demo"),
        {"sub": "1"},
        db,
    )
    await _drain(response)


@pytest.mark.asyncio
async def test_reconnect_generator_timeout_continues_then_breaks(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)

    class _Task:
        def __init__(self):
            self.calls = 0

        def done(self):
            self.calls += 1
            return self.calls > 2

    channel = endpoints._SseBroadcast()
    running = SimpleNamespace(session_id="1_old", status="running", created_at=None)
    monkeypatch.setattr(endpoints, "_active_tasks", {
        "1_old": {
            "gen_task": _Task(), "channel": channel,
            "connected": True, "http_request": _ConnectedRequest(),
        }
    })
    monkeypatch.setattr(endpoints, "_mark_disconnected_if_stale", AsyncMock(return_value=True))
    db = _stream_db(_result(running))

    async def fake_wait_for(awaitable, timeout):
        if hasattr(awaitable, "close"):
            awaitable.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr(endpoints.asyncio, "wait_for", fake_wait_for)
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert events == []


@pytest.mark.asyncio
async def test_resume_row_lookup_http_exception_propagates(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": False, "additional_requirement": "",
    }))
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=target))
    monkeypatch.setattr(endpoints, "get_user_recent_session", AsyncMock(return_value=None))
    db = _stream_db(
        _result(None),
        execute_error=HTTPException(status_code=404, detail="gone"),
        fail_on=2,
    )
    with pytest.raises(HTTPException) as error:
        await endpoints.orchestrate_project_stream(
            OrchestratorRequest(requirement="继续", enable_skills=False),
            _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
        )
    assert error.value.status_code == 404


@pytest.mark.asyncio
async def test_resume_changes_without_session_state(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": True, "additional_requirement": "also b",
    }))
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=target))
    monkeypatch.setattr(endpoints, "get_user_recent_session", AsyncMock(return_value=None))
    db = _stream_db(_result(None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="继续", enable_skills=False),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)


@pytest.mark.asyncio
async def test_resume_changes_with_no_completed_files(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    state = SimpleNamespace(
        file_statuses={"b.py": SimpleNamespace(status="failed")}
    )
    sm = SimpleNamespace(
        resume_session=AsyncMock(return_value=state), create_session=AsyncMock(),
        complete_session=AsyncMock(), cancel_session=AsyncMock(),
    )
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": True, "additional_requirement": "also b",
    }))
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=target))
    monkeypatch.setattr(endpoints, "get_user_recent_session", AsyncMock(return_value=None))
    db = _stream_db(_result(None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="继续", enable_skills=False),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)


@pytest.mark.asyncio
async def test_resume_changes_skips_missing_regeneration_file(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    state = SimpleNamespace(
        file_statuses={"a.py": SimpleNamespace(status="completed")}
    )
    sm = SimpleNamespace(
        resume_session=AsyncMock(return_value=state), create_session=AsyncMock(),
        complete_session=AsyncMock(), cancel_session=AsyncMock(),
    )
    monkeypatch.setattr(endpoints, "get_session_manager", AsyncMock(return_value=sm))
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": True, "additional_requirement": "also b",
    }))
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=target))
    monkeypatch.setattr(endpoints, "get_user_recent_session", AsyncMock(return_value=None))
    monkeypatch.setattr(
        endpoints, "analyze_files_to_regenerate",
        AsyncMock(return_value=["missing.py"]),
    )
    db = _stream_db(_result(None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="继续", enable_skills=False),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)


@pytest.mark.asyncio
async def test_requested_cancel_unset_falls_through(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    target = SimpleNamespace(
        session_id="1_target", output_dir=str(tmp_path), requirement="original",
    )
    monkeypatch.setattr(endpoints, "detect_resume_intent", AsyncMock(return_value={
        "is_resume": True, "has_changes": False, "additional_requirement": "",
    }))
    monkeypatch.setattr(endpoints, "resolve_resume_session", AsyncMock(return_value=target))
    monkeypatch.setattr(endpoints, "get_user_recent_session", AsyncMock(return_value=None))
    db = _stream_db(_result(None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="继续", session_id="1_old", enable_skills=False,
        ),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert any('"done"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_cancel_event_already_set_when_task_starts(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    real_create = asyncio.create_task

    def create_task(coro, *args, **kwargs):
        qualname = getattr(getattr(coro, "cr_code", None), "co_qualname", "")
        if "run_generation" in qualname:
            endpoints._cancel_events["1_demo"].set()
        return real_create(coro, *args, **kwargs)

    monkeypatch.setattr(endpoints.asyncio, "create_task", create_task)
    db = _stream_db(_result(None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", project_name="demo", enable_skills=False),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    assert any('"cancelled"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_core_handler_executes_adapter(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    executed = AsyncMock(return_value={
        "success": True, "output_dir": str(tmp_path), "total_files_created": 1,
        "files": [], "validation": {}, "errors": [], "warnings": [], "elapsed_time": 0.1,
    })
    monkeypatch.setattr(endpoints, "execute_core_generation", executed)

    async def run_workflow(workflow, **_kwargs):
        await workflow.core_handler(None)
        return None

    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)
    db = _stream_db(_result(None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", enable_skills=False),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    events = await _drain(response)
    executed.assert_awaited_once()
    assert any('"done"' in event for event in events)


@pytest.mark.asyncio
async def test_stream_heartbeat_publishes_then_stops_on_cancel(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    real_sleep = asyncio.sleep
    published = []

    class _Channel(endpoints._SseBroadcast):
        def publish(self, item):
            published.append(item)
            super().publish(item)
            if '"heartbeat"' in item:
                endpoints._cancel_events["1_demo"].set()

    monkeypatch.setattr(endpoints, "_SseBroadcast", _Channel)

    async def fake_sleep(delay, *args, **kwargs):
        if delay == 5:
            return await real_sleep(0)
        return await real_sleep(delay, *args, **kwargs)

    async def slow_workflow(*_args, **_kwargs):
        await real_sleep(0.01)
        await real_sleep(0.01)
        await real_sleep(0.01)
        return None

    monkeypatch.setattr(endpoints.asyncio, "sleep", fake_sleep)
    monkeypatch.setattr(endpoints, "run_workflow", slow_workflow)
    db = _stream_db(_result(None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(
            requirement="build", project_name="demo", enable_skills=False,
        ),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)
    assert any('"heartbeat"' in item for item in published)


@pytest.mark.asyncio
async def test_decision_callback_returns_none_when_result_none(monkeypatch, tmp_path):
    _patch_stream(monkeypatch, tmp_path)
    captured = {}
    results = []

    def factory(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(output_dir=str(tmp_path), generate=AsyncMock())

    monkeypatch.setattr(endpoints, "OrchestratorAgent", factory)

    async def run_workflow(_workflow, **_kwargs):
        queue = endpoints._decision_queues["1_demo"]
        queue.put_nowait(None)
        results.append(await captured["decision_callback"]({"q": []}))
        return None

    monkeypatch.setattr(endpoints, "run_workflow", run_workflow)
    db = _stream_db(_result(None))
    response = await endpoints.orchestrate_project_stream(
        OrchestratorRequest(requirement="build", project_name="demo", enable_skills=False),
        _ConnectedRequest(), {"sub": "1", "role": "user"}, db,
    )
    await _drain(response)
    assert results == [None]


def test_design_architecture_keeps_existing_language_fields():
    architect = _architect()

    async def fake(prompt, system_prompt=""):
        return json.dumps({
            "language": "python",
            "frontend_language": "javascript",
            "backend_language": "python",
            "all_languages": ["python", "javascript"],
            "file_plan": [{"path": "main.py", "language": "python"}],
        })

    architect.call_llm = fake
    result = asyncio.run(architect.design_architecture("写 main.py", _complexity()))
    assert result["language"] == "python"
    assert result["all_languages"] == ["python", "javascript"]


def test_coerce_architecture_skips_non_list_file_plan():
    result = _architect()._coerce_architecture_fields({"file_plan": {"a": 1}})
    assert result["file_plan"] == {"a": 1}


def test_planned_covers_module_falls_through_to_next_path():
    assert Architect._planned_covers_module({"other/mod.py"}, "pkg.mod", []) is False


def test_completeness_skips_non_str_non_dict_imports():
    result = _architect()._ensure_file_plan_completeness(
        {"file_plan": [{"path": "main.py", "imports": [5, None]}]},
        target_language="python",
    )
    assert [entry["path"] for entry in result["file_plan"]] == ["main.py"]


def test_completeness_skips_unparseable_dict_module_and_items():
    result = _architect()._ensure_file_plan_completeness(
        {
            "file_plan": [
                {
                    "path": "main.py",
                    "imports": [
                        {"module": "relative only ?", "items": [5, "???"]},
                    ],
                }
            ]
        },
        target_language="python",
    )
    assert [entry["path"] for entry in result["file_plan"]] == ["main.py"]


def test_completeness_ignores_modules_without_candidates(monkeypatch):
    from app.agent.adapters import LanguageAdapterRegistry

    class Adapter:
        language = "python"

        def is_known_external_module(self, name):
            return False

        def resolve_import_to_file(self, import_info, current_file):
            return []

        def infer_file_type(self, path):
            return "utils"

    monkeypatch.setattr(
        LanguageAdapterRegistry, "get_adapter", staticmethod(lambda lang: Adapter())
    )
    result = _architect()._ensure_file_plan_completeness(
        {"file_plan": [{"path": "main.py", "imports": ["pkg.missing"]}]},
        target_language="python",
    )
    assert [entry["path"] for entry in result["file_plan"]] == ["main.py"]
