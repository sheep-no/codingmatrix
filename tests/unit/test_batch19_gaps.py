"""Coverage gaps for logging, skill catalog, stack registry, image resources,
orchestration core, requirement constants, generation plans, and model registry."""

import asyncio
import json
import logging
import sys
from dataclasses import replace
from pathlib import Path
from types import ModuleType

import pytest

from app.agent.generation_plan import (
    GenerationPlan,
    _coerce_file,
    _match_plan_dependency,
    _normalize_path,
    add_profile_components,
)
from app.agent.orchestration import (
    OrchestrationCheckpointStore,
    OrchestrationCommand,
    OrchestrationStage,
    OrchestrationStatus,
    OrchestratorCore,
)
from app.agent.orchestration.generation_scheduler import GeneratedContent
from app.agent.orchestration.plan import build_file_plan
from app.agent.shared_context import SharedContext
from app.agent.skill_catalog import SkillCatalog
from app.agent.stack_adapters import FastAPIStackAdapter
from app.agent.stack_adapters.registry import StackAdapterRegistry
from app.services import image_resource_service as image_service
from app.services.image_resource_service import (
    GenerationConcurrencyLimiter,
    build_image_resource_fingerprint,
    cleanup_file,
    cleanup_stale_files,
)
from app.utils import logging as app_logging
from app.utils.aicloud import model_registry as model_registry_module


# ---------------------------------------------------------------- logging


def test_set_request_context_stores_optional_user_id():
    app_logging.clear_request_context()
    app_logging.set_request_context("request-1", user_id="user-1")
    assert app_logging.get_request_id() == "request-1"
    assert app_logging.get_user_id() == "user-1"
    app_logging.clear_request_context()


def test_json_formatter_emits_user_id_and_traceback():
    app_logging.set_request_context("request-2", user_id="user-2")
    try:
        raise ValueError("boom")
    except ValueError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="test.logger",
        level=logging.ERROR,
        pathname="",
        lineno=0,
        msg="failed",
        args=(),
        exc_info=exc_info,
    )
    try:
        formatted = app_logging.JsonFormatter().format(record)
    finally:
        app_logging.clear_request_context()
    assert '"user_id": "user-2"' in formatted
    assert "ValueError: boom" in formatted


def test_log_error_includes_exception_and_extra_fields(caplog):
    logger = logging.getLogger("batch19.log_error")
    records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collector()
    logger.addHandler(handler)
    logger.setLevel(logging.ERROR)
    try:
        try:
            raise RuntimeError("exploded")
        except RuntimeError as exc:
            app_logging.log_error(logger, "operation failed", exc, method="GET")
    finally:
        logger.removeHandler(handler)

    assert len(records) == 1
    record = records[0]
    payload = json.loads(record.getMessage())
    assert payload["error_type"] == "RuntimeError"
    assert payload["method"] == "GET"
    assert "exploded" in payload["traceback"]


@pytest.mark.asyncio
async def test_request_middleware_logs_and_reraises_downstream_errors():
    async def failing_app(scope, receive, send):
        raise RuntimeError("downstream failure")

    middleware = app_logging.RequestLoggingMiddleware(
        failing_app, logger_name="app.request.batch19"
    )
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/fail",
        "query_string": b"",
        "headers": [],
        "client": None,
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        return None

    records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    collector = _Collector()
    middleware.logger.addHandler(collector)
    middleware.logger.setLevel(logging.INFO)
    try:
        with pytest.raises(RuntimeError, match="downstream failure"):
            await middleware(scope, receive, send)
    finally:
        middleware.logger.removeHandler(collector)

    messages = [record.getMessage() for record in records]
    assert any("请求处理异常" in message for message in messages)
    assert records[-1].levelno in (logging.ERROR, logging.WARNING)


# ------------------------------------------------------------ skill catalog


def test_skill_catalog_missing_directory_is_empty(tmp_path):
    assert SkillCatalog.from_directory(tmp_path / "missing").all() == ()


def test_skill_catalog_skips_unreadable_skill(tmp_path, monkeypatch):
    skill_dir = tmp_path / "broken"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("---\nname: broken\n---\n", encoding="utf-8")

    def _raise(self, *args, **kwargs):
        raise OSError("unreadable")

    monkeypatch.setattr(Path, "read_text", _raise)
    assert SkillCatalog.from_directory(tmp_path).all() == ()


def test_skill_catalog_tolerates_malformed_front_matter(tmp_path):
    skill_dir = tmp_path / "plain"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: plain\nplain text without colon\ncapabilities: crud, persistence\n---\n"
        "# Plain skill\nBody text.",
        encoding="utf-8",
    )
    catalog = SkillCatalog.from_directory(tmp_path)
    assert catalog.all()[0].capabilities == ("crud", "persistence")

    unclosed = tmp_path / "unclosed"
    unclosed.mkdir()
    (unclosed / "SKILL.md").write_text("---\nname: unclosed\n\n", encoding="utf-8")
    manifests = {item.name for item in SkillCatalog.from_directory(tmp_path).all()}
    assert "unclosed" in manifests


# ----------------------------------------------------------- stack registry


def test_stack_registry_rejects_conflicting_alias():
    with pytest.raises(ValueError, match="already registered"):
        StackAdapterRegistry((FastAPIStackAdapter(), FastAPIStackAdapter()))


def test_stack_registry_require_reports_unknown_stack():
    registry = StackAdapterRegistry()
    with pytest.raises(LookupError, match="stack adapter not found"):
        registry.require("python", "flask")


def test_stack_registry_register_same_adapter_twice_keeps_single_entry():
    adapter = FastAPIStackAdapter()
    registry = StackAdapterRegistry((adapter,))
    registry.register(adapter)
    assert registry.all() == (adapter,)


# -------------------------------------------------------- image resources


def test_generation_limiter_requires_positive_limits():
    with pytest.raises(ValueError, match="must be positive"):
        GenerationConcurrencyLimiter(global_limit=0, user_limit=1)


def test_cleanup_file_swallows_directory_error(tmp_path):
    target = tmp_path / "a-directory"
    target.mkdir()
    assert cleanup_file(target) is False


def test_cleanup_stale_files_rejects_negative_age_and_missing_directory(tmp_path):
    with pytest.raises(ValueError, match="non-negative"):
        cleanup_stale_files(tmp_path, max_age_seconds=-1)
    assert cleanup_stale_files(tmp_path / "missing", max_age_seconds=10) == 0


def test_cleanup_stale_files_continues_after_oserror(tmp_path, monkeypatch):
    stale = tmp_path / "stale.png"
    stale.write_bytes(b"image")

    def _raise(path):
        raise OSError("locked")

    monkeypatch.setattr(image_service, "cleanup_file", _raise)
    assert cleanup_stale_files(tmp_path, max_age_seconds=0) == 0


def test_boolean_generation_parameter_normalizes_to_int():
    values = {
        "user_id": 1,
        "model": "m",
        "generation_type": "text-to-image",
        "prompt": "p",
        "negative_prompt": "n",
        "style": None,
        "reference_hash": None,
        "width": 512,
        "height": 512,
        "steps": 10,
        "guidance_scale": 7.0,
        "strength": None,
        "num_images": 1,
        "seed": True,
    }
    assert build_image_resource_fingerprint(**values) == build_image_resource_fingerprint(
        **{**values, "seed": 1}
    )


@pytest.mark.asyncio
async def test_singleflight_joins_task_that_is_still_running():
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def owner():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return "value"

    first = asyncio.create_task(
        image_service.get_or_create_generation(fingerprint="running", owner=owner)
    )
    await started.wait()
    second = asyncio.create_task(
        image_service.get_or_create_generation(fingerprint="running", owner=owner)
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(first, second) == ["value", "value"]
    assert calls == 1


@pytest.mark.asyncio
async def test_singleflight_reuses_existing_flight_task():
    async def owner():
        raise AssertionError("a registered flight must be reused")

    existing = asyncio.get_running_loop().create_future()
    existing.set_result("cached")
    image_service._generation_flights["existing-flight"] = existing

    assert (
        await image_service.get_or_create_generation(
            fingerprint="existing-flight", owner=owner
        )
        == "cached"
    )
    assert "existing-flight" not in image_service._generation_flights


# ------------------------------------------------------ orchestration core


def _command(task_id="batch19"):
    return OrchestrationCommand(
        task_id=task_id,
        session_id="session",
        mode="traditional",
        request={"requirement": "build an app"},
    )


@pytest.mark.asyncio
async def test_execute_returns_existing_terminal_state(tmp_path):
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    started = await core.run(_command("terminal"))
    await core.finish(
        "terminal",
        OrchestrationStatus.FAILED,
        event_id="terminal-state",
        expected_revision=started.state.revision,
    )

    class Adapter:
        async def create_plan(self, request):
            raise AssertionError("terminal task must not plan again")

    result = await core.execute(
        _command("terminal"),
        Adapter(),
        output_dir=tmp_path / "generated",
        shared_context=SharedContext("build", tmp_path / "generated"),
    )
    assert result.state.status is OrchestrationStatus.FAILED


@pytest.mark.asyncio
async def test_execute_rejects_resume_from_unsupported_stage(tmp_path):
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    started = await core.run(_command("unsupported"))
    await core.advance(
        "unsupported",
        OrchestrationStage.SCHEDULING,
        event_id="unsupported:2",
        expected_revision=started.state.revision,
    )

    result = await core.execute(
        _command("unsupported"),
        object(),
        output_dir=tmp_path / "generated",
        shared_context=SharedContext("build", tmp_path / "generated"),
    )
    assert result.state.status is OrchestrationStatus.FAILED
    assert result.state.diagnostics[-1]["code"] == "orchestration.resume_stage_unsupported"


@pytest.mark.asyncio
async def test_execute_maps_planning_cancellation_to_cancelled(tmp_path):
    class Adapter:
        async def create_plan(self, request):
            raise asyncio.CancelledError()

    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    result = await core.execute(
        _command("plan-cancel"),
        Adapter(),
        output_dir=tmp_path / "generated",
        shared_context=SharedContext("build", tmp_path / "generated"),
    )
    assert result.state.status is OrchestrationStatus.CANCELLED


def _change_plan(output_dir: Path, action: str):
    from app.agent.change_plan import ChangePlan
    from app.agent.project_snapshot import ProjectSnapshot

    snapshot = ProjectSnapshot.scan(output_dir, revision="base")
    return ChangePlan.build(snapshot, [{"path": "existing.py", "action": action}])


@pytest.mark.asyncio
async def test_execute_reports_transaction_stage_failure(tmp_path):
    output_dir = tmp_path / "generated"
    output_dir.mkdir()
    (output_dir / "existing.py").write_text("VALUE = 1\n", encoding="utf-8")

    class Adapter:
        change_plan = _change_plan(output_dir, "add")
        _project_context = {}

        async def create_plan(self, request):
            return build_file_plan([{"path": "existing.py"}])

    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path / "checkpoints"))
    result = await core.execute(
        _command("transaction-fail"),
        Adapter(),
        output_dir=output_dir,
        shared_context=SharedContext("build", output_dir),
    )
    assert result.state.status is OrchestrationStatus.FAILED
    assert result.state.diagnostics[-1]["code"] == "incremental.transaction_stage_failed"


@pytest.mark.asyncio
async def test_execute_rolls_back_transaction_when_execution_raises(tmp_path, monkeypatch):
    output_dir = tmp_path / "generated"
    output_dir.mkdir()

    from app.agent.change_plan import ChangePlan
    from app.agent.project_snapshot import ProjectSnapshot

    snapshot = ProjectSnapshot.scan(output_dir, revision="base")
    plan = ChangePlan.build(snapshot, [{"path": "new.py", "action": "add"}])
    rolled_back = []

    class Adapter:
        change_plan = plan
        _project_context = {}

        async def create_plan(self, request):
            return build_file_plan([{"path": "new.py"}])

    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path / "checkpoints"))

    async def _explode(*args, **kwargs):
        raise RuntimeError("execution aborted")

    monkeypatch.setattr(core, "_execute_frozen_plan", _explode)
    with pytest.raises(RuntimeError, match="execution aborted"):
        await core.execute(
            _command("rollback"),
            Adapter(),
            output_dir=output_dir,
            shared_context=SharedContext("build", output_dir),
        )
    assert not (output_dir / ".orchestration-txn" / "rollback").exists()


@pytest.mark.asyncio
async def test_execute_reraises_when_execution_fails_without_transaction(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "generated"

    class Adapter:
        async def create_plan(self, request):
            return build_file_plan([{"path": "main.py"}])

    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path / "checkpoints"))

    async def _explode(*args, **kwargs):
        raise RuntimeError("frozen plan aborted")

    monkeypatch.setattr(core, "_execute_frozen_plan", _explode)
    with pytest.raises(RuntimeError, match="frozen plan aborted"):
        await core.execute(
            _command("no-transaction"),
            Adapter(),
            output_dir=output_dir,
            shared_context=SharedContext("build", output_dir),
        )


@pytest.mark.asyncio
async def test_advance_is_idempotent_for_repeated_event(tmp_path):
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    started = await core.run(_command("idempotent-advance"))
    first = await core.advance(
        "idempotent-advance",
        OrchestrationStage.SCHEDULING,
        event_id="idempotent:2",
        expected_revision=started.state.revision,
    )
    second = await core.advance(
        "idempotent-advance",
        OrchestrationStage.SCHEDULING,
        event_id="idempotent:2",
        expected_revision=started.state.revision,
    )
    assert second.state == first.state


@pytest.mark.asyncio
async def test_execute_flags_untouched_incremental_file_changes(tmp_path):
    from app.agent.change_plan import ChangePlan
    from app.agent.project_snapshot import ProjectSnapshot

    base_dir = tmp_path / "base"
    base_dir.mkdir()
    (base_dir / "untouched.py").write_text("ORIGINAL = 1\n", encoding="utf-8")
    base_snapshot = ProjectSnapshot.scan(base_dir, revision="base")
    change_plan = ChangePlan.build(
        base_snapshot, [{"path": "main.py", "action": "add"}]
    )

    output_dir = tmp_path / "generated"
    output_dir.mkdir()
    (output_dir / "untouched.py").write_text("CHANGED = 2\n", encoding="utf-8")

    class Adapter:
        _project_context = {"base_snapshot": base_snapshot.model_dump(mode="json")}
        preserved_paths = ()

        def __init__(self):
            self.change_plan = change_plan

        async def create_plan(self, request):
            return build_file_plan([{"path": "main.py"}])

        async def generate_file(self, context):
            return GeneratedContent(content="VALUE = 1\n", model_name="test-model")

    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path / "checkpoints"))
    result = await core.execute(
        _command("untouched"),
        Adapter(),
        output_dir=output_dir,
        shared_context=SharedContext("build", output_dir),
    )
    assert result.state.status is OrchestrationStatus.FAILED
    assert result.state.diagnostics[-1]["code"] == "incremental.untouched_file_changed"


@pytest.mark.asyncio
async def test_execute_allows_incremental_run_when_untouched_files_are_stable(
    tmp_path, monkeypatch
):
    from app.agent.change_plan import ChangePlan
    from app.agent.orchestration import core as core_module
    from app.agent.orchestration.artifact_committer import ArtifactConsistencyResult
    from app.agent.project_snapshot import ProjectSnapshot

    base_dir = tmp_path / "base"
    base_dir.mkdir()
    (base_dir / "untouched.py").write_text("ORIGINAL = 1\n", encoding="utf-8")
    base_snapshot = ProjectSnapshot.scan(base_dir, revision="base")
    change_plan = ChangePlan.build(
        base_snapshot, [{"path": "main.py", "action": "add"}]
    )

    output_dir = tmp_path / "generated"
    output_dir.mkdir()
    (output_dir / "untouched.py").write_text("ORIGINAL = 1\n", encoding="utf-8")

    class Adapter:
        _project_context = {"base_snapshot": base_snapshot.model_dump(mode="json")}
        preserved_paths = ()

        def __init__(self):
            self.change_plan = change_plan

        async def create_plan(self, request):
            return build_file_plan([{"path": "main.py"}])

        async def generate_file(self, context):
            return GeneratedContent(content="VALUE = 1\n", model_name="test-model")

    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path / "checkpoints"))
    monkeypatch.setattr(
        core_module,
        "check_artifact_success_gate",
        lambda *args, **kwargs: ArtifactConsistencyResult(
            success=True,
            planned_paths=("main.py",),
            manifest_paths=("main.py",),
            completed_paths=("main.py",),
            disk_paths=("main.py",),
        ),
    )
    result = await core.execute(
        _command("untouched-stable"),
        Adapter(),
        output_dir=output_dir,
        shared_context=SharedContext("build", output_dir),
    )
    assert result.state.status is OrchestrationStatus.COMPLETED


@pytest.mark.asyncio
async def test_execute_rolls_back_transaction_when_result_is_not_completed(
    tmp_path, monkeypatch
):
    output_dir = tmp_path / "generated"
    output_dir.mkdir()

    from app.agent.change_plan import ChangePlan
    from app.agent.project_snapshot import ProjectSnapshot

    snapshot = ProjectSnapshot.scan(output_dir, revision="base")
    plan = ChangePlan.build(snapshot, [{"path": "new.py", "action": "add"}])

    class Adapter:
        change_plan = plan
        _project_context = {}

        async def create_plan(self, request):
            return build_file_plan([{"path": "new.py"}])

    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path / "checkpoints"))

    async def _fail(command, adapter, frozen_plan, **kwargs):
        return await core.finish(
            command.task_id,
            OrchestrationStatus.FAILED,
            event_id=f"{command.task_id}:failed",
            expected_revision=kwargs["expected_revision"],
        )

    monkeypatch.setattr(core, "_execute_frozen_plan", _fail)
    result = await core.execute(
        _command("rollback-failed"),
        Adapter(),
        output_dir=output_dir,
        shared_context=SharedContext("build", output_dir),
    )
    assert result.state.status is OrchestrationStatus.FAILED
    assert not (output_dir / ".orchestration-txn" / "rollback-failed").exists()


def test_contract_values_handles_non_mapping_and_string():
    from app.agent.orchestration.core import _contract_values

    assert _contract_values(None, "exports") == ()
    assert _contract_values({"exports": "app"}, "exports") == ("app",)
    assert _contract_values({"exports": ["b", "a"]}, "exports") == ("a", "b")


# ------------------------------------------------- requirement constants


def test_load_dual_models_falls_back_on_config_failure(monkeypatch):
    from app.agent.orchestrator_requirements import constants as constants_module

    fake_io = ModuleType("app.utils.model_config_io")

    def _raise(path):
        raise RuntimeError("bad config")

    fake_io.load_model_config = _raise
    monkeypatch.setitem(sys.modules, "app.utils.model_config_io", fake_io)
    monkeypatch.setattr(constants_module.os.path, "exists", lambda path: True)

    result = constants_module._load_dual_models_from_config()
    assert result == (
        constants_module.DEFAULT_REASONING_MODEL,
        constants_module.DEFAULT_ARCHITECT_MODEL,
        constants_module.DEFAULT_FAST_MODEL,
    )


def test_load_dual_models_uses_defaults_when_config_is_absent(monkeypatch):
    from app.agent.orchestrator_requirements import constants as constants_module

    monkeypatch.setattr(constants_module.os.path, "exists", lambda path: False)
    assert constants_module._load_dual_models_from_config() == (
        constants_module.DEFAULT_REASONING_MODEL,
        constants_module.DEFAULT_ARCHITECT_MODEL,
        constants_module.DEFAULT_FAST_MODEL,
    )


# --------------------------------------------------------- generation plan


def test_generation_plan_strict_policy_requires_requested_paths():
    with pytest.raises(ValueError, match="strict generation plan"):
        GenerationPlan.build(
            [{"path": "a.py"}], policy="strict", requested_paths=["b.py"]
        )


def test_generation_plan_from_architecture_normalizes_shape():
    from app.agent.dependency_manifest import DependencyManifest
    from app.agent.interface_registry import InterfaceRegistry

    interfaces = InterfaceRegistry.build(())
    dependencies = DependencyManifest.build(())
    plan = GenerationPlan.from_architecture(
        {
            "file_plan": "main.py",
            "interfaces": interfaces,
            "dependencies": dependencies,
        }
    )
    assert [item.path for item in plan.files] == ["main.py"]

    empty = GenerationPlan.from_architecture({"file_plan": {"not": "a list"}})
    assert empty.files == ()


def test_add_profile_components_skips_blank_and_existing_paths():
    plan = add_profile_components(
        [{"path": "main.py"}],
        {
            "capability_policy": {
                "component_file_plan": [
                    {"path": ""},
                    {"path": "main.py"},
                    {"path": "service.py", "component": "service"},
                    {"path": "repo.py", "component": "repo"},
                ]
            }
        },
    )
    paths = [item.path for item in plan.files]
    assert paths == ["main.py", "repo.py", "service.py"]
    by_path = {item.path: item.dependencies for item in plan.files}
    assert by_path["main.py"] == ()
    assert by_path["service.py"] == ()
    assert by_path["repo.py"] == ("service.py",)


def test_coerce_file_rejects_non_mapping_and_non_mapping_contract():
    with pytest.raises(ValueError, match="must be an object"):
        _coerce_file(123)
    with pytest.raises(ValueError, match="file contract must be an object"):
        _coerce_file({"path": "a.py", "contract": "bad"})


def test_coerce_file_normalizes_single_string_collections():
    plan_file = _coerce_file(
        {
            "path": "a.py",
            "depends_on": "b.py",
            "imports": "os",
            "contract_refs": "API",
        }
    )
    assert plan_file.dependencies == ("b.py",)
    assert plan_file.imports == ("os",)
    assert plan_file.contract_refs == ("API",)


def test_match_plan_dependency_handles_empty_and_package_directory():
    assert _match_plan_dependency("", {"a.py"}, {}) is None
    paths = {"pkg/a.py", "pkg/b.py"}
    assert _match_plan_dependency("pkg", paths, {}) == "pkg/a.py"
    assert _match_plan_dependency("pkg", paths, {"pkg": "pkg/b.py"}) == "pkg/b.py"


def test_normalize_path_rejects_empty_relative_path():
    with pytest.raises(ValueError, match="must identify a file"):
        _normalize_path("./")


# ----------------------------------------------------------- model registry


def test_model_registry_default_falls_back_to_first_entry(monkeypatch):
    registry = model_registry_module.MODEL_REGISTRY
    model = replace(next(iter(registry.values())), is_default=False)
    monkeypatch.setattr(model_registry_module, "MODEL_REGISTRY", {"only": model})
    assert model_registry_module.get_default_model() is model


def test_model_registry_available_models_supports_free_only_filter(monkeypatch):
    models = list(model_registry_module.MODEL_REGISTRY.values())
    free = replace(models[0], is_default=False, is_free=True)
    paid = replace(models[1], is_default=True, is_free=False)
    monkeypatch.setattr(
        model_registry_module, "MODEL_REGISTRY", {"free": free, "paid": paid}
    )
    assert model_registry_module.get_available_models(free_only=True) == [free]
