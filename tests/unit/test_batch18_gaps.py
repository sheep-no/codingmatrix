"""Coverage gaps for adapter, companion, planner, registry, PPT and config."""

import importlib
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.adapter as adapter_pkg
from app.agent import task_planner as planner_module
from app.agent.service_config_templates import (
    ServiceTemplate,
    detect_services_from_requirements,
    generate_docker_compose,
    generate_env_example,
    get_all_service_names,
    get_connection_snippets,
    get_python_packages_for_services,
    get_service_template,
)
from app.agent.state import State, StateGraphBuilder
from app.agent.task_planner import TaskPlanner
from app.agent.workflow_registry import (
    WorkflowDefinition,
    WorkflowRegistry,
    _active_workflows,
    _recoverable_workflow_factories,
    build_legacy_workflow,
    cancel_workflows_for_session,
    get_legacy_result,
    register_recoverable_workflow_factory,
    resume_workflow_from_local_result,
    run_workflow,
)
import app.agent.workflow_registry as workflow_registry
from app.services import girlai_companion_service as companion
from app.services.ppt_generation_orchestrator import (
    PPTGenerationOrchestrator,
    run_ppt_generation,
)
from app.services.ppt_quality_orchestrator import review_rendered_deck, run_quality_pipeline
from app.utils import url_safety
import app.api.v1.aiGeneratorPptx as ppt_api
from app.utils import vision


# ---------------------------------------------------------------------------
# app/adapter/__init__.py
# ---------------------------------------------------------------------------

def test_adapter_package_skips_sys_path_insert_when_present():
    package_dir = str(adapter_pkg.__file__.rsplit("/", 1)[0])
    sys.path.insert(0, package_dir)
    try:
        importlib.reload(adapter_pkg)
    finally:
        while package_dir in sys.path:
            sys.path.remove(package_dir)
    assert adapter_pkg.ModelAdapter is not None


# ---------------------------------------------------------------------------
# girlai_companion_service
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "response",
    [
        {},
        {"choices": []},
        {"choices": [{"message": {}}]},
        {"choices": [{"message": {"content": "   "}}]},
        {"choices": [{"message": {"content": 123}}]},
    ],
)
def test_parse_companion_turn_rejects_invalid_response(response):
    with pytest.raises(ValueError):
        companion.parse_companion_turn(response)


def test_parse_json_content_skips_invalid_object_prefix():
    class Decoder:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def raw_decode(self, text):
            self.calls += 1
            if self.calls == 1:
                raise json.JSONDecodeError("bad", text, 0)
            return {"assistant_text": "ok"}, len(text)

    original = companion.json.JSONDecoder
    companion.json.JSONDecoder = Decoder
    try:
        turn = companion.parse_companion_turn(
            {"choices": [{"message": {"content": "{not-valid-json {"}}]}
        )
    finally:
        companion.json.JSONDecoder = original
    assert turn.assistant_text == "ok"


def test_structured_payload_without_text_uses_fallback_and_degraded_flag():
    turn = companion.parse_companion_turn(
        {
            "choices": [
                {"message": {"content": json.dumps({"emotion": {"label": "happy"}})}}
            ]
        },
        character_name="小柔",
    )
    assert turn.assistant_text == "小柔暂时没能整理好回复，请稍后再试一次。"
    assert "assistant_text" in turn.degraded_capabilities


def test_parse_json_content_continues_after_non_dict_decoding():
    class Decoder:
        def __init__(self, *args, **kwargs):
            self.calls = 0

        def raw_decode(self, text):
            self.calls += 1
            if self.calls == 1:
                return ["not-a-dict"], 0
            return {"assistant_text": "ok"}, len(text)

    original = companion.json.JSONDecoder
    companion.json.JSONDecoder = Decoder
    try:
        turn = companion.parse_companion_turn(
            {"choices": [{"message": {"content": "{not-valid-json {"}}]}
        )
    finally:
        companion.json.JSONDecoder = original
    assert turn.assistant_text == "ok"


def test_parse_falls_back_to_parse_obj_when_model_validate_missing(monkeypatch):
    calls = {}

    class FakeTurn:
        @classmethod
        def model_validate(cls, payload):
            raise AttributeError("no model_validate")

        @classmethod
        def parse_obj(cls, payload):
            calls["payload"] = payload
            return SimpleNamespace(
                assistant_text=payload["assistant_text"],
                model_context=SimpleNamespace(calls=1),
            )

    monkeypatch.setattr(companion, "CompanionTurn", FakeTurn)
    turn = companion.parse_companion_turn(
        {"choices": [{"message": {"content": '{"assistant_text": "ok"}'}}]}
    )
    assert turn.assistant_text == "ok"
    assert calls["payload"]["assistant_text"] == "ok"


# ---------------------------------------------------------------------------
# task_planner
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decompose_includes_project_exploration(monkeypatch):
    planner = TaskPlanner.__new__(TaskPlanner)
    planner.model = SimpleNamespace(name="m", max_tokens=10)
    planner.api_key_token = None

    async def fake_explore(task, path, tools):
        return "project uses FastAPI"

    async def fake_call(**kwargs):
        return {"choices": [{"message": {"content": "[]"}}]}

    monkeypatch.setattr(planner, "_explore_project", fake_explore)
    monkeypatch.setattr(planner_module, "call_llm", fake_call)
    result = await planner.decompose("t", project_path="/tmp", tools={"list_files": {}})
    assert result == []


@pytest.mark.asyncio
async def test_decompose_degrades_when_parser_returns_scalar(monkeypatch):
    planner = TaskPlanner.__new__(TaskPlanner)
    planner.model = SimpleNamespace(name="m", max_tokens=10)
    planner.api_key_token = None

    async def fake_call(**kwargs):
        return {"choices": [{"message": {"content": "scalar"}}]}

    monkeypatch.setattr(planner_module, "call_llm", fake_call)
    monkeypatch.setattr(planner_module, "safe_parse_json", lambda content: "scalar")
    result = await planner.decompose("t")
    assert result[0]["degraded"] is True


@pytest.mark.asyncio
async def test_explore_project_degrades_when_engine_fails(monkeypatch):
    planner = TaskPlanner.__new__(TaskPlanner)
    planner.model = SimpleNamespace(name="m", max_tokens=10)
    planner.api_key_token = None

    class FailingEngine:
        def __init__(self, **kwargs):
            self.steps = []

        async def run(self, *args):
            raise RuntimeError("engine down")

    monkeypatch.setattr(
        "app.agent.react_engine.ReActEngine", FailingEngine
    )
    result = await planner._explore_project(
        "task", "/tmp", {"list_files": {"fn": AsyncMock(), "description": "", "params": {}}}
    )
    assert result == ""


# ---------------------------------------------------------------------------
# workflow_registry
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_recoverable_legacy_workflow_requires_runtime_handler():
    factory = _recoverable_workflow_factories["generate"]
    definition = factory()
    state = await run_workflow(definition, session_id="recover-s", task_id="recover-t")
    assert state.status == "failed"
    assert any("recovered from checkpoint" in str(error) for error in state.errors)


def test_register_recoverable_factory_validates_inputs():
    with pytest.raises(ValueError, match="requires a name"):
        register_recoverable_workflow_factory("", lambda: None)
    with pytest.raises(ValueError, match="requires a name"):
        register_recoverable_workflow_factory("name", "not-callable")


def test_register_recoverable_factory_stores_valid_factory():
    calls = []
    register_recoverable_workflow_factory("custom-test", lambda: calls.append(1))
    try:
        _recoverable_workflow_factories["custom-test"]()
    finally:
        _recoverable_workflow_factories.pop("custom-test", None)
    assert calls == [1]


def test_workflow_registry_rejects_duplicate_and_unknown_lookup():
    graph = StateGraphBuilder().add_node("start", lambda state: None).compile()
    definition = WorkflowDefinition("dup", "start", graph, "/dup")
    registry = WorkflowRegistry([definition])
    with pytest.raises(ValueError, match="duplicate"):
        registry.register(definition)
    assert registry.get("missing") is None


def test_get_legacy_result_without_result_or_errors():
    state = State("s", "t")
    with pytest.raises(RuntimeError, match="completed without a result"):
        get_legacy_result(state)


def test_get_legacy_result_returns_wrapped_dict():
    state = State("s", "t", metadata={"legacy_result": {"success": True}})
    assert get_legacy_result(state) == {"success": True}


@pytest.mark.asyncio
async def test_run_workflow_accepts_string_validation_scope():
    definition = build_legacy_workflow("g", "/g", lambda state: {"success": True})
    state = await run_workflow(
        definition,
        session_id="scope-s",
        task_id="scope-t",
        metadata={"required_validation_scopes": "local_runtime"},
    )
    assert state.status == "waiting_local_validation"
    assert state.pending_actions[0]["scopes"] == ["local_runtime"]


@pytest.mark.asyncio
async def test_run_workflow_persists_state_when_db_context_given(monkeypatch):
    persisted = []

    async def fake_persist(db, user_id, state):
        persisted.append((user_id, state.task_id))

    monkeypatch.setattr(
        "app.services.agent_state_adapter.persist_agent_state", fake_persist
    )
    definition = build_legacy_workflow("g", "/g", lambda state: {"success": True})
    await run_workflow(
        definition, session_id="persist-s", task_id="persist-t", db=object(), user_id=3
    )
    assert persisted == [(3, "persist-t")]


@pytest.mark.asyncio
async def test_resume_missing_checkpoint_raises_key_error():
    with pytest.raises(KeyError, match="active workflow not found"):
        await resume_workflow_from_local_result(
            session_id="missing-s", task_id="missing-t", result={}
        )


@pytest.mark.asyncio
async def test_resume_uses_active_execution_and_continues_next_node(monkeypatch):
    graph = (
        StateGraphBuilder()
        .add_node("wait", lambda state: None)
        .add_node("finish", lambda state: {"status": "completed"})
        .compile()
    )
    definition = WorkflowDefinition("resume", "wait", graph, "/r")
    state = State(
        "resume-s",
        "resume-t",
        status="waiting_local_validation",
        metadata={"_next_node": "finish"},
    )
    _active_workflows[("resume-s", "resume-t")] = (definition, state)
    monkeypatch.setattr(
        workflow_registry,
        "dispatch_state_actions",
        lambda session_id, state: state.pending_actions.append({"type": "dispatched"}),
    )
    try:
        resumed = await resume_workflow_from_local_result(
            session_id="resume-s",
            task_id="resume-t",
            result={
                "task_id": "resume-t",
                "session_id": "resume-s",
                "revision": state.revision,
                "scope": "local_runtime",
                "status": "passed",
                "event_id": "resume-event",
                "schema_version": 1,
                "source": "local",
            },
        )
    finally:
        _active_workflows.pop(("resume-s", "resume-t"), None)
    assert resumed.session_id == "resume-s"


@pytest.mark.asyncio
async def test_resume_dispatches_remaining_pending_actions(monkeypatch):
    graph = StateGraphBuilder().add_node("wait", lambda state: None).compile()
    definition = WorkflowDefinition("resume-dispatch", "wait", graph, "/r")
    state = State(
        "resume-dispatch-s",
        "resume-dispatch-t",
        status="waiting_local_validation",
        pending_actions=[{"type": "local_validation", "scopes": ["local_e2e"]}],
    )
    _active_workflows[("resume-dispatch-s", "resume-dispatch-t")] = (definition, state)
    dispatched = []
    monkeypatch.setattr(
        workflow_registry,
        "dispatch_state_actions",
        lambda session_id, current: dispatched.append(session_id),
    )
    try:
        await resume_workflow_from_local_result(
            session_id="resume-dispatch-s",
            task_id="resume-dispatch-t",
            result={
                "task_id": "resume-dispatch-t",
                "session_id": "resume-dispatch-s",
                "revision": state.revision,
                "scope": "local_runtime",
                "status": "passed",
                "event_id": "resume-dispatch-event",
                "schema_version": 1,
                "source": "local",
            },
        )
    finally:
        _active_workflows.pop(("resume-dispatch-s", "resume-dispatch-t"), None)
    assert dispatched == ["resume-dispatch-s"]


@pytest.mark.asyncio
async def test_resume_orphan_checkpoint_without_factory(monkeypatch):
    state = State(
        "orphan-s",
        "orphan-t",
        status="waiting_local_validation",
        metadata={"_workflow_name": "unknown-workflow"},
        pending_actions=[{"type": "local_validation", "scopes": ["local_runtime"]}],
    )
    workflow_registry._checkpoint_store.save(
        state, workflow_registry._checkpoint_id("orphan-s", "orphan-t")
    )
    dispatched = []
    monkeypatch.setattr(
        workflow_registry,
        "dispatch_state_actions",
        lambda session_id, current: dispatched.append(session_id),
    )

    resumed = await resume_workflow_from_local_result(
        session_id="orphan-s",
        task_id="orphan-t",
        result={
            "task_id": "orphan-t",
            "session_id": "orphan-s",
            "revision": state.revision,
            "scope": "local_runtime",
            "status": "passed",
            "event_id": "orphan-event",
            "schema_version": 1,
            "source": "local",
        },
    )

    assert resumed.pending_actions == []
    assert dispatched == []


@pytest.mark.asyncio
async def test_cancel_skips_terminal_states():
    definition = WorkflowDefinition(
        "terminal", "wait", StateGraphBuilder().add_node("wait", lambda state: None).compile(), "/t"
    )
    terminal_states = [
        State("cancel-terminal", f"t-{status}", status=status)
        for status in ("completed", "failed", "cancelled", "timed_out")
    ]
    for state in terminal_states:
        workflow_registry._active_workflows[(state.session_id, state.task_id)] = (definition, state)

    assert await cancel_workflows_for_session("cancel-terminal") == 0


@pytest.mark.asyncio
async def test_cancel_persists_when_db_context_given(monkeypatch):
    persisted = []

    async def fake_persist(db, user_id, state):
        persisted.append((user_id, state.task_id))

    monkeypatch.setattr(
        "app.services.agent_state_adapter.persist_agent_state", fake_persist
    )
    definition = WorkflowDefinition(
        "cancel", "wait", StateGraphBuilder().add_node("wait", lambda state: None).compile(), "/c"
    )
    state = State("cancel-db", "task-cancel-db", status="running")
    workflow_registry._active_workflows[("cancel-db", "task-cancel-db")] = (definition, state)

    cancelled = await cancel_workflows_for_session(
        "cancel-db", db=object(), user_id=7
    )

    assert cancelled == 1
    assert persisted == [(7, "task-cancel-db")]


# ---------------------------------------------------------------------------
# url_safety
# ---------------------------------------------------------------------------

def test_check_outbound_url_handles_urlparse_value_error(monkeypatch):
    def boom(url):
        raise ValueError("bad url")

    monkeypatch.setattr(url_safety, "urlparse", boom)
    assert url_safety.check_outbound_url("http://example.com") == "URL 格式无效"


def test_check_outbound_url_skips_unparseable_ip_entries(monkeypatch):
    monkeypatch.setattr(
        url_safety.socket,
        "getaddrinfo",
        lambda *args, **kwargs: [
            (url_safety.socket.AF_INET, 0, 0, "", ("not-an-ip", 0)),
            (url_safety.socket.AF_INET, 0, 0, "", ("93.184.216.34", 0)),
        ],
    )
    assert url_safety.check_outbound_url("https://api.example.com/v1") is None


def test_check_outbound_url_dns_failure_fail_closed(monkeypatch):
    def fake_getaddrinfo(*args, **kwargs):
        raise url_safety.socket.gaierror("no dns")

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)
    error = url_safety.check_outbound_url(
        "https://no-such-host.invalid/v1", fail_closed_on_dns_error=True
    )
    assert "无法解析主机名" in error


# ---------------------------------------------------------------------------
# ppt_generation_orchestrator
# ---------------------------------------------------------------------------

async def _noop_handler(context):
    return context


@pytest.mark.asyncio
async def test_generation_rejects_unknown_start_stage():
    with pytest.raises(ValueError, match="start_stage must be one of"):
        await PPTGenerationOrchestrator().run({}, start_stage="nope")


@pytest.mark.asyncio
async def test_generation_rejects_vision_stage_in_standard_mode():
    with pytest.raises(ValueError, match="unavailable for quality_mode"):
        await PPTGenerationOrchestrator().run(
            {"quality_mode": "standard"}, start_stage="vision_qa"
        )


@pytest.mark.asyncio
async def test_generation_awaits_async_cancel_check_and_callback():
    events = []

    async def async_cancel():
        return False

    async def async_callback(event):
        events.append(event["status"])

    result = await PPTGenerationOrchestrator(
        {"planning": _noop_handler},
        cancel_check=async_cancel,
        progress_callback=async_callback,
    ).run({})

    assert result.status == "completed"
    assert events[0] == "started"


@pytest.mark.asyncio
async def test_run_ppt_generation_convenience_wrapper():
    result = await run_ppt_generation({}, start_stage="planning")
    assert result.status == "completed"


@pytest.mark.asyncio
async def test_generation_awaits_async_handler_and_keeps_state_on_none():
    async def async_handler(context):
        return {**context, "touched": True}

    result = await PPTGenerationOrchestrator(
        {"planning": async_handler, "assets": lambda context: None}
    ).run({})

    assert result.context["touched"] is True


# ---------------------------------------------------------------------------
# ppt_quality_orchestrator
# ---------------------------------------------------------------------------

def _patch_review(monkeypatch, stdout=b"\x89PNGimage", response='{"issues": []}'):
    convert = AsyncMock()
    monkeypatch.setattr(ppt_api, "_convert_pptx_to_pdf", convert)
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(stdout=stdout),
    )
    call = AsyncMock(return_value=response)
    monkeypatch.setattr(vision, "_call_vision_model", call)
    return convert, call


@pytest.mark.asyncio
async def test_review_rejects_non_file_output(tmp_path, monkeypatch):
    convert, call = _patch_review(monkeypatch)
    _, report = await run_quality_pipeline([{"id": "s1", "elements": []}])

    await review_rendered_deck(tmp_path / "missing.pptx", [], report, "token", "1")

    convert.assert_not_awaited()
    assert any(i["issue_type"] == "vision_review_unavailable" for i in report.issues)


@pytest.mark.asyncio
async def test_review_reports_missing_credentials(tmp_path, monkeypatch):
    path = tmp_path / "deck.pptx"
    path.touch()
    convert, call = _patch_review(monkeypatch)
    _, report = await run_quality_pipeline([])

    await review_rendered_deck(path, [], report, "", "1")

    convert.assert_not_awaited()
    call.assert_not_awaited()
    assert any(i["issue_type"] == "vision_review_unavailable" for i in report.issues)


@pytest.mark.asyncio
async def test_append_visual_review_without_reviewer_records_degradation():
    from app.services.ppt_quality_orchestrator import append_visual_review
    from app.utils.pptx.quality import QualityReport

    report = QualityReport(issues=[])
    await append_visual_review([{"id": "s1"}], report, None)
    assert report.issues[0]["issue_type"] == "vision_review_unavailable"


@pytest.mark.asyncio
async def test_review_rejects_non_png_render(tmp_path, monkeypatch):
    path = tmp_path / "deck.pptx"
    path.touch()
    _patch_review(monkeypatch, stdout=b"not-a-png")
    _, report = await run_quality_pipeline([{"id": "s1", "elements": []}])

    await review_rendered_deck(path, [], report, "token", "1")

    assert any(i["issue_type"] == "vision_review_unavailable" for i in report.issues)


@pytest.mark.asyncio
async def test_review_returns_findings_for_valid_payload(tmp_path, monkeypatch):
    path = tmp_path / "deck.pptx"
    path.touch()
    _, call = _patch_review(
        monkeypatch,
        response='{"issues": [{"issue_type": "text_overflow", "message": "m", '
                 '"confidence": 0.9, "severity": "high"}]}',
    )
    _, report = await run_quality_pipeline([{"id": "s1", "elements": []}])

    await review_rendered_deck(path, [{"id": "s1"}], report, "token", "1")

    assert call.await_count == 2
    assert any(i["issue_type"] == "text_overflow" for i in report.issues)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        '{"issues": "bad"}',
        '{"issues": [{"foo": 1}]}',
        '{"issues": [{"issue_type": "x", "message": "m", "confidence": 2, "severity": "high"}]}',
        '{"issues": [{"issue_type": "x", "message": "m", "confidence": 0.5, "severity": "bogus"}]}',
    ],
)
async def test_review_rejects_malformed_payloads(tmp_path, monkeypatch, response):
    path = tmp_path / "deck.pptx"
    path.touch()
    _patch_review(monkeypatch, response=response)
    _, report = await run_quality_pipeline([{"id": "s1", "elements": []}])

    await review_rendered_deck(path, [], report, "token", "1")

    assert any(i["issue_type"] == "vision_review_unavailable" for i in report.issues)


# ---------------------------------------------------------------------------
# service_config_templates
# ---------------------------------------------------------------------------

def test_env_example_handles_unknown_service_and_empty_custom_vars():
    content = generate_env_example(["unknown-service"], {})
    assert "# Custom" not in content


def test_env_example_renders_empty_defaults_as_comments():
    from app.agent import service_config_templates as module

    template = ServiceTemplate(
        name="EmptyDefault",
        category="cache",
        env_vars={"BLANK": ""},
    )
    module.SERVICE_TEMPLATES["emptydefault"] = template
    try:
        content = generate_env_example(["emptydefault"])
    finally:
        module.SERVICE_TEMPLATES.pop("emptydefault")
    assert "# BLANK=" in content


def test_env_example_renders_custom_vars():
    content = generate_env_example([], {"EXTRA": "value"})
    assert "# Custom" in content
    assert "EXTRA=value" in content


def test_detect_services_deduplicates_keyword_matches(monkeypatch):
    from app.agent import service_config_templates as module

    monkeypatch.setattr(module, "_keyword_matches", lambda keyword, text: True)
    services = detect_services_from_requirements("redis cache")
    assert len(services) == len(set(services))


def test_get_all_service_names_lists_templates():
    from app.agent.service_config_templates import SERVICE_TEMPLATES

    assert get_all_service_names() == list(SERVICE_TEMPLATES.keys())


def test_detect_services_uses_ascii_word_boundary():
    assert "elasticsearch" not in detect_services_from_requirements("services include cache")
    assert "redis" in detect_services_from_requirements("use redis")


def test_detect_services_matches_multiple_keywords_per_service():
    assert detect_services_from_requirements("redis cache backend") == ["redis"]


def test_docker_compose_skips_unknown_and_handles_template_without_volumes(monkeypatch):
    template = ServiceTemplate(
        name="NoVolume",
        category="cache",
        env_vars={"NV_URL": "http://localhost"},
        python_packages=["nv-lib"],
        docker_service={"nv": {"image": "nv:latest"}},
        connection_code="client = None",
    )
    monkeypatch.setitem(
        __import__("app.agent.service_config_templates", fromlist=["SERVICE_TEMPLATES"]).SERVICE_TEMPLATES,
        "novolume",
        template,
    )

    compose = generate_docker_compose(["novolume", "unknown"], app_name="demo")

    assert "nv:" in compose
    assert "volumes" not in compose.split("app:")[0]


def test_docker_compose_without_services_has_no_volume_section():
    compose = generate_docker_compose([], app_name="empty")
    assert "volumes:\n  redis_data" not in compose


def test_docker_compose_declares_named_volumes():
    compose = generate_docker_compose(["redis"], app_name="demo")
    assert "volumes:" in compose
    assert "redis_data" in compose


def test_service_helpers_skip_unknown_services():
    assert get_python_packages_for_services(["unknown"]) == [
        "fastapi", "uvicorn", "pydantic", "pydantic-settings"
    ]
    assert get_connection_snippets(["unknown"]) == {}
    assert get_service_template("missing") is None


def test_service_helpers_include_known_service_packages_and_snippets():
    assert "redis" in get_python_packages_for_services(["redis"])
    snippets = get_connection_snippets(["redis"])
    assert "redis" in snippets
