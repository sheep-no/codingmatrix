"""Coverage gaps for admin APIs, orchestration helpers, adapters, and utils."""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.agent.adapters.language_adapter import (
    LanguageAdapterRegistry,
    iter_logical_lines,
)
from app.agent.languages import get_language_adapter
from app.agent.orchestration.artifact_committer import (
    ArtifactCommitter,
    ArtifactConsistencyResult,
    ArtifactDiagnostic,
    check_artifact_success_gate,
)
from app.agent.orchestration.models import OrchestrationState
from app.agent.orchestration.runtime import _checkpoint_task_id
from app.agent.orchestrator_generation.coverage_checker import (
    check_requirement_coverage,
)
from app.agent.orchestrator_requirements.data_models import (
    AssociationItem,
    AssociationResult,
)
from app.agent.shared_context import SharedContext
from app.agent.stack_adapters import FastAPIStackAdapter
from app.agent.stack_adapters.adapters import (
    _java_runtime,
    _node_runtime,
    _python_runtime,
    _require_workspace,
    _source_files,
)
from app.agent.stack_adapters.base import UnsupportedStackError
from app.utils.pptx.ppt_style import apply_design_tokens


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from app.main import app
    from app.utils.security import require_superadmin

    app.dependency_overrides[require_superadmin] = lambda: {
        "sub": "1",
        "permission_level": "superadmin",
    }
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def tmp_config(tmp_path):
    path = tmp_path / "mcp_servers.json"
    path.write_text(
        json.dumps(
            {
                "mcp_servers": {
                    "test-server": {
                        "transport": "stdio",
                        "enabled": True,
                        "command": "echo",
                        "args": ["hello"],
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    return str(path)


# ------------------------------------------------------------- MCP admin API


def _mcp_module():
    from app.api.v2 import mcp_admin

    return mcp_admin


def test_save_config_reports_failure_when_directory_unwritable(monkeypatch, tmp_path):
    module = _mcp_module()
    monkeypatch.setattr(module, "MCP_CONFIG_PATH", str(tmp_path / "cfg.json"))

    def _raise(*args, **kwargs):
        raise OSError("readonly")

    import tempfile

    monkeypatch.setattr(tempfile, "mkstemp", _raise)
    assert module._save_config({"mcp_servers": {}}) is False


def test_add_stdio_server_persists_env_and_reports_save_failure(
    client, tmp_config, monkeypatch
):
    module = _mcp_module()
    monkeypatch.setattr(module, "MCP_CONFIG_PATH", tmp_config)
    response = client.post(
        "/api/v2/mcp/servers",
        json={
            "name": "env-server",
            "transport": "stdio",
            "command": "echo",
            "env": {"TOKEN": "x"},
        },
    )
    assert response.status_code == 200

    monkeypatch.setattr(module, "_save_config", lambda config: False)
    failed = client.post(
        "/api/v2/mcp/servers",
        json={"name": "second", "transport": "stdio", "command": "echo"},
    )
    assert failed.status_code == 500


def test_update_server_saves_all_optional_fields(client, tmp_config):
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(_mcp_module(), "MCP_CONFIG_PATH", tmp_config)
        response = client.put(
            "/api/v2/mcp/servers/test-server",
            json={
                "command": "run",
                "args": ["a"],
                "env": {"K": "v"},
                "url": "http://localhost/mcp",
            },
        )
    assert response.status_code == 200


@pytest.mark.parametrize("method,path", [
    ("put", "/api/v2/mcp/servers/test-server"),
    ("delete", "/api/v2/mcp/servers/test-server"),
    ("post", "/api/v2/mcp/servers/test-server/toggle"),
])
def test_mutations_report_save_failures(
    client, tmp_config, monkeypatch, method, path
):
    module = _mcp_module()
    monkeypatch.setattr(module, "MCP_CONFIG_PATH", tmp_config)
    monkeypatch.setattr(module, "_save_config", lambda config: False)
    if method == "put":
        response = client.put(path, json={"enabled": False})
    else:
        response = getattr(client, method)(path)
    assert response.status_code == 500


# --------------------------------------------------------- artifact committer


def _committer(tmp_path, **kwargs):
    context = SharedContext("build", tmp_path)
    return (
        ArtifactCommitter(tmp_path, context, task_id="batch20", **kwargs),
        context,
    )


def test_consistency_result_rejects_diagnostic_combinations():
    diagnostic = ArtifactDiagnostic(code="x", message="boom")
    with pytest.raises(ValidationError, match="cannot contain a diagnostic"):
        ArtifactConsistencyResult(
            success=True,
            planned_paths=(),
            manifest_paths=(),
            completed_paths=(),
            disk_paths=(),
            diagnostic=diagnostic,
        )
    with pytest.raises(ValidationError, match="requires a diagnostic"):
        ArtifactConsistencyResult(
            success=False,
            planned_paths=(),
            manifest_paths=(),
            completed_paths=(),
            disk_paths=(),
        )


def test_committer_rejects_non_positive_limit_and_non_string_content(tmp_path):
    with pytest.raises(ValueError, match="max_file_bytes must be positive"):
        ArtifactCommitter(tmp_path, SharedContext("x", tmp_path), task_id="t", max_file_bytes=0)

    committer, _ = _committer(tmp_path)
    result = committer.commit("main.py", None, model_name="m")
    assert result.success is False
    assert "non-empty" in result.diagnostic.message


def test_committer_idempotent_read_failure_is_reported(tmp_path):
    committer, context = _committer(tmp_path)
    first = committer.commit("main.py", "print('ok')\n", model_name="m")
    assert first.success

    failing = ArtifactCommitter(
        tmp_path,
        context,
        task_id="batch20",
        reader=lambda path: (_ for _ in ()).throw(OSError("gone")),
    )
    result = failing.commit("main.py", "print('ok')\n", model_name="m")
    assert result.success is False
    assert "disk read failed" in result.diagnostic.message


def test_committer_detects_manifest_hash_mismatch(tmp_path):
    class TamperingContext(SharedContext):
        def save_file_content(self, path, content, model_name):
            self._manifest = {path: {"content_hash": "0" * 64}}

    context = TamperingContext("build", tmp_path)
    committer = ArtifactCommitter(tmp_path, context, task_id="batch20")
    result = committer.commit("main.py", "print('ok')\n", model_name="m")
    assert result.success is False
    assert "manifest hash" in result.diagnostic.message


def test_committer_reports_empty_disk_content_for_regular_file(tmp_path):
    def empty_reader(path):
        return b"   \n"

    committer, _ = _committer(tmp_path, reader=empty_reader)
    result = committer.commit("main.py", "print('ok')\n", model_name="m")
    assert result.success is False
    assert "disk content is empty" in result.diagnostic.message


def test_success_gate_reports_unenumerable_output_dir(tmp_path, monkeypatch):
    import app.agent.orchestration.artifact_committer as module

    plan = SimpleNamespace(files=(SimpleNamespace(path="main.py"),))

    def _raise(output_dir, include):
        raise OSError("cannot list")

    monkeypatch.setattr(module, "_business_disk_paths", _raise)
    result = check_artifact_success_gate(plan, {}, [], tmp_path)
    assert result.success is False
    assert "enumerate" in result.diagnostic.message


def test_success_gate_rejects_symlink_artifact(tmp_path):
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    real = tmp_path / "real.py"
    real.write_text("print('ok')\n", encoding="utf-8")
    link = output_dir / "main.py"
    link.symlink_to(real)

    from app.agent.orchestration.artifact_committer import ArtifactCompletionEvent

    content_hash = __import__("hashlib").sha256(real.read_bytes()).hexdigest()
    event = ArtifactCompletionEvent(
        event_id="e", path="main.py", content_hash=content_hash, size_bytes=len(real.read_bytes())
    )
    manifest = {"main.py": {"content_hash": content_hash, "status": "valid", "validation_passed": True}}
    plan = SimpleNamespace(files=(SimpleNamespace(path="main.py"),))

    result = check_artifact_success_gate(plan, manifest, [event], output_dir)
    assert result.success is False
    assert "symbolic link" in result.diagnostic.message


def test_business_disk_paths_returns_empty_when_output_missing(tmp_path):
    from app.agent.orchestration.artifact_committer import _business_disk_paths

    assert _business_disk_paths(tmp_path / "missing") == ()


# ---------------------------------------------------------- orchestration runtime


def test_checkpoint_task_id_hashes_unsafe_candidates():
    safe = _checkpoint_task_id("task", "traditional")
    assert safe == "task-traditional"

    unsafe = _checkpoint_task_id("task/with/slash", "mode")
    assert unsafe.startswith("core-")
    assert len(unsafe) == len("core-") + 64


@pytest.mark.asyncio
async def test_runtime_appends_validation_failure_diagnostic(tmp_path, monkeypatch):
    import app.agent.orchestration.runtime as runtime

    state = OrchestrationState(
        task_id="runtime-task",
        session_id="session",
        engine_version="core-v1",
        mode="traditional",
    )
    state = state.model_copy(
        update={
            "metadata": {
                "candidate_validation": {"status": "checked", "passed": False},
            },
            "status": __import__(
                "app.agent.orchestration.models", fromlist=["OrchestrationStatus"]
            ).OrchestrationStatus.COMPLETED,
            "terminal_event_id": "done",
            "applied_event_ids": ("done",),
            "revision": 1,
        }
    )

    class FakeAdapter:
        def bind_shared_context(self, context):
            self.context = context

        async def finalize(self, state):
            return SimpleNamespace(result={"success": True})

    class FakeCore:
        def __init__(self, store):
            pass

        async def execute(self, *args, **kwargs):
            return SimpleNamespace(state=state)

    monkeypatch.setattr(runtime, "OrchestratorCore", FakeCore)
    monkeypatch.setattr(runtime, "profile_context", lambda path: {}, raising=False)

    payload = await runtime.execute_core_generation(
        FakeAdapter(),
        requirement="build",
        task_id="runtime-task",
        session_id="session",
        mode="traditional",
        output_dir=tmp_path,
        metadata={"profile_context": {}, "toolchain_plan": {}},
    )
    codes = {item["code"] for item in payload["repair_feedback"]["diagnostics"]}
    assert "project.validation_failed" in codes


# --------------------------------------------------------- coverage checker


def test_coverage_checker_handles_single_char_cjk_tokens():
    association = AssociationResult(
        items=[AssociationItem(content="好", category="functional", source="s", confidence=0.9)]
    )
    result = check_requirement_coverage("好", {}, [], association)
    assert result["checked"] is True


def test_coverage_checker_returns_unchecked_for_skipped_or_empty():
    assert check_requirement_coverage("x", {}, [], None)["checked"] is False
    skipped = AssociationResult(items=[AssociationItem("x", "functional", "s", 0.9)], skipped=True)
    assert check_requirement_coverage("x", {}, [], skipped)["checked"] is False
    empty = AssociationResult(items=[])
    assert check_requirement_coverage("x", {}, [], empty)["checked"] is False


def test_coverage_checker_returns_full_rate_without_confirmed_items():
    low = AssociationResult(
        items=[AssociationItem("login", "functional", "s", 0.1)]
    )
    result = check_requirement_coverage("x", {}, [], low)
    assert result == {"checked": True, "total_items": 0, "uncovered": [], "coverage_rate": 1.0}


def test_coverage_checker_reads_list_architecture_fields():
    association = AssociationResult(
        items=[AssociationItem("user login endpoint", "functional", "s", 0.9)]
    )
    result = check_requirement_coverage(
        "build login",
        {"api_endpoints": ["/user/login"]},
        [{"path": "main.py", "description": "entry"}],
        association,
    )
    assert result["checked"] is True
    assert result["coverage_rate"] == 1.0


# ------------------------------------------------------- language adapters


def test_iter_logical_lines_flushes_unterminated_import():
    lines = iter_logical_lines("from x import (a,\n b")
    assert lines == ["from x import (a, b"]


def test_language_adapter_empty_module_names_are_external_safe():
    adapter = get_language_adapter("python")
    assert adapter.is_known_external_module("") is False
    assert adapter.is_known_external_module("...") is False


def test_python_adapter_package_helpers():
    python_adapter = get_language_adapter("python")
    assert python_adapter.normalize_module_path("app.models") == "app/models"

    from app.agent.adapters.language_adapter import LanguageAdapter

    stub = SimpleNamespace(get_package_init_file=lambda path: f"{path}/__init__.py")
    assert LanguageAdapter.get_required_package_files(stub, "pkg") == ["pkg/__init__.py"]


def test_language_registry_scaffold_returns_none_without_adapter(monkeypatch):
    monkeypatch.setattr(
        LanguageAdapterRegistry, "get_adapter", classmethod(lambda cls, name: None)
    )
    assert LanguageAdapterRegistry.scaffold_file("main.py") is None


def test_language_detection_returns_generic_for_mixed_projects():
    files = {"a.py": "", "b.py": "", "c.js": "", "d.ts": ""}
    assert LanguageAdapterRegistry.detect_language(files) == "generic"


def test_language_registry_introspection_helpers():
    assert "python" in LanguageAdapterRegistry.get_all_adapters()
    assert ".py" in LanguageAdapterRegistry.get_supported_extensions()
    assert LanguageAdapterRegistry.is_extension_supported(".py") is True
    assert LanguageAdapterRegistry.is_extension_supported(".nope") is False
    assert LanguageAdapterRegistry.get_adapter_for_project({"a.py": "x"}) is not None


def test_get_language_adapter_raises_for_unknown_language():
    original = LanguageAdapterRegistry._adapters
    LanguageAdapterRegistry._adapters = {
        name: adapter for name, adapter in original.items() if name != "generic"
    }
    try:
        with pytest.raises(LookupError, match="language adapter not found"):
            get_language_adapter("cobol")
    finally:
        LanguageAdapterRegistry._adapters = original


# ------------------------------------------------------- stack adapters


def test_require_workspace_rejects_missing_and_unsupported(tmp_path):
    with pytest.raises(ValueError, match="existing directory"):
        _require_workspace(tmp_path / "missing", (("python", "fastapi"),))

    unsupported = tmp_path / "unsupported"
    unsupported.mkdir()
    (unsupported / "package.json").write_text('{"dependencies":{"express":"5"}}', encoding="utf-8")
    with pytest.raises(UnsupportedStackError, match="not supported"):
        _require_workspace(unsupported, (("python", "fastapi"),))


def test_source_files_respects_limit_and_skips_ignored_dirs(tmp_path):
    (tmp_path / "a.py").write_text("A=1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("B=2\n", encoding="utf-8")
    ignored = tmp_path / "node_modules"
    ignored.mkdir()
    (ignored / "c.py").write_text("C=3\n", encoding="utf-8")

    files = _source_files(tmp_path, (".py",), limit=1)
    assert files == (("a.py", "A=1\n"),)


def test_runtime_helpers_cover_version_file_and_fallbacks(tmp_path):
    (tmp_path / ".python-version").write_text("3.12.1\n", encoding="utf-8")
    assert _python_runtime(tmp_path) == "3.12.1"

    other = tmp_path / "other"
    other.mkdir()
    (other / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    assert _python_runtime(other) == ""
    empty = tmp_path / "empty"
    empty.mkdir()
    assert _python_runtime(empty) == ""
    assert _node_runtime(None) == ""
    assert _node_runtime({"engines": "bad"}) == ""
    assert _java_runtime("nothing") == ""


# ------------------------------------------------------- project metadata


def test_project_metadata_recovers_from_corrupt_file(tmp_path, monkeypatch):
    from app.agent import project_metadata as module

    path = tmp_path / "meta.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(module, "METADATA_PATH", path)
    manager = module.ProjectMetadataManager()
    assert manager.get_all_projects() == []


@pytest.mark.asyncio
async def test_project_metadata_survives_vector_index_failure(tmp_path, monkeypatch):
    from app.agent import project_metadata as module

    monkeypatch.setattr(module, "METADATA_PATH", tmp_path / "meta.json")
    manager = module.ProjectMetadataManager()

    async def fake_extract(requirement, files):
        return ["feature"], "llm"

    monkeypatch.setattr(manager, "_extract_feature_list", fake_extract)

    class BrokenIndex:
        def load_or_create(self):
            raise RuntimeError("index unavailable")

    monkeypatch.setattr("app.agent.vector_index.VectorIndexManager", BrokenIndex)
    result = await manager.extract_and_save("req", {"a.py": "x"})
    assert result["feature_list"] == ["feature"]


def test_project_metadata_file_fallback_skips_entrypoint_names(tmp_path, monkeypatch):
    from app.agent import project_metadata as module

    monkeypatch.setattr(module, "METADATA_PATH", tmp_path / "meta.json")
    manager = module.ProjectMetadataManager()
    features = manager._fallback_feature_list(
        "req", {"main.py": "", "app.py": "", "orders.py": ""}
    )
    assert features == ["orders 模块"]


@pytest.mark.asyncio
async def test_project_metadata_template_extraction_threshold(tmp_path, monkeypatch):
    from app.agent import project_metadata as module

    monkeypatch.setattr(module, "METADATA_PATH", tmp_path / "meta.json")
    manager = module.ProjectMetadataManager()
    assert await manager.trigger_template_extraction("ecommerce", min_projects=2) is None

    manager._projects = [
        {"domain": "ecommerce"},
        {"domain": "ecommerce"},
    ]

    class FakeExtractor:
        async def extract_template(self, domain, projects):
            return {"domain": domain, "count": len(projects)}

    monkeypatch.setattr("app.agent.template_extractor.TemplateExtractor", FakeExtractor)
    result = await manager.trigger_template_extraction("ecommerce", min_projects=2)
    assert result == {"domain": "ecommerce", "count": 2}


# --------------------------------------------------------- search history


@pytest.mark.asyncio
async def test_search_history_applies_date_filters(test_db):
    from datetime import datetime, timezone

    from app.db.search_history import _apply_conversation_filters
    from app.models.history import History

    stmt = _apply_conversation_filters(
        __import__("sqlalchemy").select(History.conversation_id),
        "user-1",
        None,
        datetime(2020, 1, 1, tzinfo=timezone.utc),
        datetime(2030, 1, 1, tzinfo=timezone.utc),
    )
    compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
    assert "created_at >=" in compiled
    assert "created_at <=" in compiled


# ------------------------------------------------------------- celery app


def test_celery_status_sync_logs_and_swallows_errors(monkeypatch, caplog):
    import app.celery_app as module

    monkeypatch.setenv("DATABASE_URL", "sqlite:///nonexistent/dir/tasks.db")
    records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collector()
    module.logger.addHandler(handler)
    module.logger.setLevel(logging.ERROR)
    try:
        module._sync_set_task_status("task-1", "RUNNING")
    finally:
        module.logger.removeHandler(handler)
    assert any("Failed to sync task status" in record.getMessage() for record in records)


def test_celery_signal_handlers_dispatch(monkeypatch):
    import app.celery_app as module

    captured = []
    monkeypatch.setattr(module, "_sync_update_task_status", lambda tid, st: captured.append((tid, st)))
    monkeypatch.setattr(module, "_sync_notify_failure", lambda tid, err: captured.append((tid, "failure")))
    monkeypatch.setattr(module, "_sync_notify_retry", lambda tid, err: captured.append((tid, "retry")))

    handlers = {}

    class FakeSignal:
        def __init__(self, name):
            self.name = name

        def connect(self, handler):
            handlers[self.name] = handler
            return handler

    monkeypatch.setattr(module, "task_prerun", FakeSignal("prerun"))
    monkeypatch.setattr(module, "task_postrun", FakeSignal("postrun"))
    monkeypatch.setattr(module, "task_failure", FakeSignal("failure"))
    monkeypatch.setattr(module, "task_retry", FakeSignal("retry"))
    monkeypatch.setattr(module, "task_revoked", FakeSignal("revoked"))

    module.setup_celery_signals()
    handlers["prerun"](task_id="t1")
    handlers["postrun"](task_id="t1", state="SUCCESS")
    handlers["failure"](task_id="t1", exception=RuntimeError("x"))
    handlers["retry"](task_id="t1", exception=RuntimeError("y"))
    handlers["revoked"](task_id="t1")

    assert ("t1", "running") in captured
    assert ("t1", "success") in captured
    assert ("t1", "failure") in captured
    assert ("t1", "retry") in captured
    assert ("t1", "cancelled") in captured


# ---------------------------------------------------------- model defaults


def test_model_defaults_fall_back_on_config_errors(monkeypatch):
    import importlib

    import app.utils.model_defaults as module

    def boom(path):
        raise ValueError("bad yaml")

    monkeypatch.setattr(module, "load_model_config", boom)
    reloaded = importlib.reload(module)
    try:
        assert reloaded.MODEL_DEFAULTS["code"] == module._FALLBACK_DEFAULTS["code"]
    finally:
        monkeypatch.undo()
        importlib.reload(module)


# ---------------------------------------------------------- provider router


def test_provider_router_covers_registry_paths():
    from app.utils.aicloud.provider_router import ProviderRouter

    sentinel = object()
    router = ProviderRouter(registry=sentinel)
    assert router._registry is sentinel

    ProviderRouter.set_registry(sentinel)
    assert ProviderRouter.get_instance()._registry is sentinel


def test_provider_router_maps_anthropic_and_other_protocols(monkeypatch):
    from app.utils.aicloud import provider_router as module
    from app.utils.aicloud.providers import ModelProvider

    class FakeDynamic:
        def __init__(self, protocol):
            self.protocol = SimpleNamespace(value=protocol)

    class FakeManager:
        def __init__(self, protocol):
            self.protocol = protocol

        def get_by_model(self, model, user):
            return FakeDynamic(self.protocol)

    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager",
        lambda: FakeManager("anthropic"),
    )
    router = module.ProviderRouter()
    assert router.route("claude") is ModelProvider.ANTHROPIC

    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager",
        lambda: FakeManager("custom"),
    )
    assert router.route("custom-model") is ModelProvider.OPENAI


def test_provider_router_logs_config_failure(monkeypatch, caplog):
    import app.utils.aicloud.provider_router as module

    def boom(path):
        raise RuntimeError("config down")

    monkeypatch.setattr(module, "load_model_config", boom)
    records = []

    class _Collector(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Collector()
    module.logger.addHandler(handler)
    module.logger.setLevel(logging.WARNING)
    try:
        mapping = module._load_provider_map()
    finally:
        module.logger.removeHandler(handler)
    assert any("加载统一模型配置失败" in record.getMessage() for record in records)
    assert mapping["qwen-plus"]


# ------------------------------------------------------------- ppt style


def test_apply_design_tokens_keeps_fallback_for_invalid_colors():
    style = SimpleNamespace(
        PRIMARY_COLOR="p", PRIMARY_LIGHT="l", PRIMARY_DARK="d",
        ACCENT_COLOR="a", BG_WHITE="w", TEXT_DARK="t", TEXT_GRAY="tg",
        FONT_MAIN="f", FONT_TITLE="f", language="zh-CN",
    )
    tokens = SimpleNamespace(
        colors={
            "primary": 123,
            "secondary": "#12",
            "accent": "#aabbcc",
        },
        typography={"body_font": "Font", "title_font": "Title"},
    )
    result = apply_design_tokens(style, tokens)
    assert result.PRIMARY_COLOR == "p"
    assert result.PRIMARY_LIGHT == "l"
    assert result.ACCENT_COLOR is not None


# ------------------------------------------------------------- rate limiter


def test_rate_limiter_disabled_and_all_tiers(monkeypatch):
    from app.middleware.rate_limiter import RateLimiter, RateLimitTier

    def make_config(global_limit, ip_limit, user_limit, endpoint_limit):
        return SimpleNamespace(
            enabled=True,
            global_limit=global_limit,
            ip_limit=ip_limit,
            user_limit=user_limit,
            max_window=60,
            get_endpoint_rule=lambda endpoint: endpoint_limit,
        )

    limiter = RateLimiter()
    monkeypatch.setattr(
        limiter, "_config", SimpleNamespace(enabled=False, max_window=60)
    )
    assert limiter.check_multi_tier("ip", "user", "/x") == (False, "", 0, 0)

    monkeypatch.setattr(limiter, "_config", make_config((1, 60), (1, 60), (1, 60), (1, 60)))

    assert limiter.check_multi_tier("1.1.1.1", None, "/a")[0] is False
    assert limiter.check_multi_tier("1.1.1.1", None, "/a")[1] == RateLimitTier.GLOBAL

    limiter = RateLimiter()
    monkeypatch.setattr(
        limiter, "_config", make_config((100, 60), (1, 60), (100, 60), (100, 60))
    )
    assert limiter.check_multi_tier("2.2.2.2", None, "/a")[0] is False
    assert limiter.check_multi_tier("2.2.2.2", None, "/a")[1] == RateLimitTier.IP

    limiter = RateLimiter()
    monkeypatch.setattr(
        limiter, "_config", make_config((100, 60), (100, 60), (1, 60), (100, 60))
    )
    assert limiter.check_multi_tier("3.3.3.3", "u1", "/a")[0] is False
    assert limiter.check_multi_tier("3.3.3.3", "u1", "/a")[1] == RateLimitTier.USER

    limiter = RateLimiter()
    monkeypatch.setattr(
        limiter, "_config", make_config((100, 60), (100, 60), (100, 60), (1, 60))
    )
    assert limiter.check_multi_tier("4.4.4.4", None, "/a")[0] is False
    assert limiter.check_multi_tier("4.4.4.4", None, "/a")[1] == RateLimitTier.ENDPOINT


def test_rate_limiter_stats_and_testing_bypass(monkeypatch):
    from app.middleware import rate_limiter as module

    limiter = module.RateLimiter()
    stats = limiter.get_stats()
    assert stats["total_keys"] == 0

    monkeypatch.setenv("ENV", "testing")
    assert module.check_login_rate_limit("user") is True

    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.setattr(module.login_tracker, "is_blocked", lambda identifier: True)
    assert module.check_login_rate_limit("user") is False


# ------------------------------------------------- attached module gaps


def test_orchestration_state_validation_rejects_bad_payloads():
    from app.agent.orchestration.models import (
        OrchestrationResult,
        OrchestrationStatus,
    )

    base = dict(
        task_id="t",
        session_id="s",
        engine_version="e",
        mode="m",
    )
    with pytest.raises(ValidationError, match="running state cannot have terminal_event_id"):
        OrchestrationState(**base, terminal_event_id="done")
    with pytest.raises(ValidationError, match="terminal_event_id must be an applied event"):
        OrchestrationState(
            **base,
            status=OrchestrationStatus.COMPLETED,
            terminal_event_id="done",
            applied_event_ids=("other",),
            revision=1,
        )
    with pytest.raises(ValidationError, match="must be unique"):
        OrchestrationState(
            **base,
            status=OrchestrationStatus.COMPLETED,
            terminal_event_id="done",
            applied_event_ids=("done", "done"),
            revision=2,
        )

    state = OrchestrationState(
        **base,
        status=OrchestrationStatus.COMPLETED,
        terminal_event_id="done",
        applied_event_ids=("done",),
        revision=1,
    )
    assert OrchestrationResult(state=state).is_terminal is True


def test_model_defaults_load_defaults_survives_bad_config(monkeypatch):
    import app.utils.model_defaults as module

    def boom(path):
        raise ValueError("bad yaml")

    monkeypatch.setattr(module, "load_model_config", boom)
    assert module._load_defaults() == module._FALLBACK_DEFAULTS


def test_provider_router_routes_openai_dynamic_provider(monkeypatch):
    from app.utils.aicloud import provider_router as module
    from app.utils.aicloud.providers import ModelProvider

    class FakeDynamic:
        protocol = SimpleNamespace(value="openai")

    class FakeManager:
        def get_by_model(self, model, user):
            return FakeDynamic()

    monkeypatch.setattr(
        "app.utils.aicloud.dynamic_provider.get_dynamic_provider_manager",
        lambda: FakeManager(),
    )
    assert module.ProviderRouter().route("gpt") is ModelProvider.OPENAI


@pytest.mark.asyncio
async def test_rate_limit_middleware_bypass_paths(monkeypatch):
    from app.middleware import rate_limiter as module

    calls = []

    async def app(scope, receive, send):
        calls.append(scope["type"])

    middleware = module.RateLimitMiddleware(app)
    await middleware({"type": "lifespan"}, None, None)
    assert calls == ["lifespan"]

    monkeypatch.setenv("ENV", "testing")
    await middleware({"type": "http", "path": "/x"}, None, None)
    assert calls[-1] == "http"


def test_impact_analyzer_handles_errors_and_dynamic_summary(tmp_path):
    from app.agent.impact_analyzer import ImpactAnalyzer

    analyzer = ImpactAnalyzer(str(tmp_path))
    (tmp_path / "bad.py").write_text("def broken(:\n", encoding="utf-8")
    (tmp_path / "dyn.py").write_text("import importlib\nimportlib.import_module('x')\n", encoding="utf-8")

    summary = analyzer.analyze(["missing.py", "bad.py", "dyn.py"])
    assert summary.modified_files == ["missing.py", "bad.py", "dyn.py"]
    assert summary.dynamic_imports == ["dyn.py"]
    assert "动态导入" in summary.summary

    class BoomAdapter:
        language = "js"

        def extract_definitions(self, content):
            raise RuntimeError("parser down")

    assert analyzer._extract_adapter_symbols(BoomAdapter(), "", "a.js") == []

    from app.agent.adapters import LanguageAdapterRegistry as Registry

    original = Registry.get_adapter_for_file
    Registry.get_adapter_for_file = classmethod(
        lambda cls, path: BoomAdapter()
    )
    try:
        assert analyzer._extract_symbols("x", "app.js") == [{
            "name": "app",
            "type": "file",
            "line_number": 0,
            "file": "app.js",
        }]
    finally:
        Registry.get_adapter_for_file = original


def test_impact_analyzer_read_failure_is_logged(tmp_path):
    from app.agent.impact_analyzer import ImpactAnalyzer

    analyzer = ImpactAnalyzer(str(tmp_path))
    target = tmp_path / "locked.py"
    target.write_text("x = 1\n", encoding="utf-8")

    def refuse(self, *args, **kwargs):
        raise OSError("unreadable")

    original = Path.read_text
    Path.read_text = refuse
    try:
        summary = analyzer.analyze(["locked.py"])
    finally:
        Path.read_text = original
    assert summary.modified_files == ["locked.py"]
    assert summary.new_symbols == []


# --------------------------------------------------- remaining <95% modules


def test_markup_self_closing_and_unbalanced_parens():
    from app.agent.markup_syntax import (
        RawTextTagBalance,
        css_structure_errors,
        html_structure_errors,
    )

    parser = RawTextTagBalance()
    parser.feed("<br/><img src='x'/>")
    assert parser.starts["br"] == 1
    assert parser.ends["br"] == 1

    assert html_structure_errors("<scr" + "ipt src='x'></scr" + "ipt>") == []
    assert css_structure_errors("a { color: red; ", check_parentheses=True)
    assert css_structure_errors(".a { width: calc(1px + 2px); }", check_parentheses=True) == []
    assert css_structure_errors(".a { width: calc(1px; }", check_parentheses=True)


def test_classifier_response_validation_errors():
    from app.services.girlai_companion_classifier import parse_classification_response

    with pytest.raises(ValueError, match="无效 JSON"):
        parse_classification_response(
            {"choices": [{"message": {"content": "plain text"}}]}
        )
    with pytest.raises(ValueError, match="无效响应"):
        parse_classification_response({})
    with pytest.raises(ValueError, match="空响应"):
        parse_classification_response({"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(ValueError, match="无效 JSON"):
        parse_classification_response({"choices": [{"message": {"content": "not json"}}]})
    with pytest.raises(ValueError, match="缺少情绪或意图字段"):
        parse_classification_response({"choices": [{"message": {"content": '{"emotion": {}}'}}]})


def test_classifier_state_payload_shortcuts():
    from app.services.girlai_companion_classifier import (
        _state_payload,
        normalize_emotion,
        normalize_intent,
    )

    assert _state_payload("happy") == {"label": "happy"}
    assert _state_payload(None) == {}
    emotion = normalize_emotion("happy")
    assert emotion.label == "neutral"
    assert emotion.low_confidence is True
    assert normalize_intent({"label": "task_review", "confidence": 1.1}).confidence == 1.0


@pytest.mark.asyncio
async def test_classifier_skips_empty_candidate_models(monkeypatch):
    from app.services import girlai_companion_classifier as module

    class FakeService:
        async def select_models(self):
            return {"classification": "", "fallback": None}

    result = await module.classify_companion_input(
        "hello", model_service=FakeService(), llm_caller=None
    )
    assert result.parse_failed is True
    assert result.calls == 0


def test_ppt_outline_missing_version_raises():
    from app.schema.ppt_outline import OutlineCreateRequest
    from app.services.ppt_outline_service import PPTOutlineService

    service = PPTOutlineService()
    draft = service.create("u", OutlineCreateRequest(topic="t", num_slides=2))
    with pytest.raises(KeyError):
        service.get("u", draft.id, version=99)
    versions = service.list_versions("u", draft.id)
    assert len(versions) == 1


@pytest.mark.asyncio
async def test_agent_executor_analysis_enriches_mcp_and_handles_empty(monkeypatch):
    from app.agent import agent_executor as module

    class FakeEngine:
        def __init__(self, **kwargs):
            self.steps = []

        async def run(self, task, prompt):
            return ""

    class FakeManager:
        @classmethod
        def get_instance(cls):
            return cls()

        def get_all_tools(self):
            return {"extra": {"fn": lambda: 1, "description": "d", "params": {}}}

    import app.agent.mcp_client as mcp_client
    import app.agent.react_engine as react_engine

    monkeypatch.setattr(react_engine, "ReActEngine", FakeEngine)
    monkeypatch.setattr(mcp_client, "MCPClientManager", FakeManager)

    executor = module.AgentExecutor(file_operator=SimpleNamespace())
    result = await executor.execute_analysis("task", "/tmp", max_rounds=1)
    assert result["success"] is False
    assert "未产生输出" in result["error"]


@pytest.mark.asyncio
async def test_agent_executor_analysis_swallows_mcp_errors(monkeypatch):
    from app.agent import agent_executor as module

    class FakeEngine:
        def __init__(self, **kwargs):
            self.steps = []

        async def run(self, task, prompt):
            return "done"

    class BadManager:
        @classmethod
        def get_instance(cls):
            raise RuntimeError("mcp down")

    import app.agent.mcp_client as mcp_client
    import app.agent.react_engine as react_engine

    monkeypatch.setattr(react_engine, "ReActEngine", FakeEngine)
    monkeypatch.setattr(mcp_client, "MCPClientManager", BadManager)

    executor = module.AgentExecutor(file_operator=SimpleNamespace())
    result = await executor.execute_analysis("task", "/tmp", max_rounds=1)
    assert result["success"] is True
    assert result["analysis"] == "done"


def test_template_manager_missing_template_and_invalid_keywords(tmp_path):
    from app.utils.pptx.templates.manager import TemplateManager

    manager = TemplateManager(template_dir=str(tmp_path))
    with pytest.raises(KeyError):
        manager.resolve_design_tokens("nope")
    assert len(manager.recommend_template(keywords=["zzz"])) == 5

    class Boom:
        def __init__(self):
            raise RuntimeError("no presets")

    import app.utils.pptx.templates.presets as presets

    created = []
    for name in (
        "BusinessReportTemplate",
        "AcademicPresetTemplate",
        "PitchDeckTemplate",
        "EducationTemplate",
        "ElegantTemplate",
        "MedicalTemplate",
        "MinimalTemplate",
        "ModernTemplate",
        "TechTemplate",
    ):
        original = getattr(presets, name)
        setattr(presets, name, type(name, (), {"__init__": lambda self: (_ for _ in ()).throw(RuntimeError("x"))}))
        created.append((name, original))
    try:
        TemplateManager(template_dir=str(tmp_path))
    finally:
        for name, original in created:
            setattr(presets, name, original)


def test_graph_validator_semantic_and_invalid_branches(monkeypatch):
    from app.schema.workflow import TaskGraph, TaskNode, TaskType
    from app.utils.workflow import graph_validator

    node = TaskNode(id="n1", type=TaskType.WEB_SEARCH, params={})
    valid, errors = graph_validator.GraphValidator().validate(
        TaskGraph(workflow_id="w", nodes=[node]), check_semantics=True
    )
    assert valid is False
    assert any("Missing required parameter: query" in err for err in errors)

    class BoomNode:
        task_type = TaskType.WEB_SEARCH

        def __init__(self, node_id, params):
            raise RuntimeError("boom")

    monkeypatch.setattr(graph_validator, "_NODE_CLASS_CACHE", {TaskType.WEB_SEARCH: BoomNode})
    valid, errors = graph_validator.GraphValidator().validate(
        TaskGraph(workflow_id="w", nodes=[node]), check_semantics=True
    )
    assert valid is False
    assert any("参数校验异常" in err for err in errors)

    conditional = TaskNode(
        id="c1",
        type=TaskType.CONDITIONAL,
        params={"true_branch": ["ghost"], "false_branch": []},
    )
    valid, errors = graph_validator.GraphValidator().validate(
        TaskGraph(workflow_id="w", nodes=[conditional])
    )
    assert valid is False
    assert any("non-existent node 'ghost'" in err for err in errors)

    monkeypatch.setattr(graph_validator, "_NODE_CLASS_CACHE", None)

    def broken_import():
        raise ImportError("no node types")

    monkeypatch.setattr(
        "app.utils.workflow.node_types.__getattr__",
        lambda name: (_ for _ in ()).throw(ImportError("no")),
        raising=False,
    )
    monkeypatch.setattr(
        graph_validator,
        "_NODE_CLASS_CACHE",
        None,
    )
    assert isinstance(graph_validator._get_node_classes(), dict)


@pytest.mark.asyncio
async def test_requirement_association_timeout_and_exception(monkeypatch):
    import asyncio as aio

    from app.agent.orchestrator_requirements.mixin import RequirementAssociationMixin
    from app.agent.orchestrator_requirements.data_models import AssociationResult

    class Mixin(RequirementAssociationMixin):
        def __init__(self, mode):
            self.mode = mode

        async def _association_pipeline(self, requirement, complexity_level):
            if self.mode == "timeout":
                await aio.sleep(5)
            raise RuntimeError("boom")

    monkeypatch.setattr(
        "app.agent.orchestrator_requirements.mixin.TIME_BUDGET_SECONDS",
        {"medium": 0.01},
    )

    timeout_result = await Mixin("timeout")._generate_requirement_associations("r", "medium")
    assert timeout_result.skipped is False
    assert isinstance(timeout_result, AssociationResult)

    failed = await Mixin("boom")._generate_requirement_associations("r", "medium")
    assert failed.skipped is True
    assert "联想异常" in failed.skip_reason


def test_classify_items_collapsed_creates_bucket(monkeypatch):
    from app.agent.orchestrator_requirements.mixin import RequirementAssociationMixin
    from app.agent.orchestrator_requirements.data_models import AssociationItem

    mixin = RequirementAssociationMixin()
    items = [
        AssociationItem(content="low", category="risk", source="s", confidence=0.5),
        AssociationItem(content="high", category="risk", source="s", confidence=0.9),
        AssociationItem(content="skip", category="risk", source="s", confidence=0.1),
    ]
    result = mixin._classify_items_for_display(items)
    assert len(result["risk"]["shown"]) == 1
    assert len(result["risk"]["collapsed"]) == 1

    collapsed_only = mixin._classify_items_for_display(
        [AssociationItem(content="low", category="risk", source="s", confidence=0.5)]
    )
    assert collapsed_only["risk"]["shown"] == []
    assert len(collapsed_only["risk"]["collapsed"]) == 1


def test_template_manager_keyword_name_match_and_apply_config(tmp_path):
    from app.utils.pptx.templates.manager import TemplateManager

    manager = TemplateManager(template_dir=str(tmp_path))
    config = manager.get_config("business_report")
    matched = manager.recommend_template(keywords=[config.name.lower()])
    assert "business_report" in matched

    prs = SimpleNamespace(slide_width=0, slide_height=0)
    manager.apply_template_from_config(prs, config)
    assert prs.slide_width is not None
    assert prs.slide_height is not None


def test_graph_validator_import_failure_and_untyped_node(monkeypatch):
    import sys

    from app.schema.workflow import TaskGraph, TaskNode, TaskType
    from app.utils.workflow import graph_validator

    monkeypatch.setattr(graph_validator, "_NODE_CLASS_CACHE", None)
    monkeypatch.setitem(sys.modules, "app.utils.workflow.node_types", None)
    assert graph_validator._get_node_classes() == {}
    monkeypatch.undo()

    monkeypatch.setattr(graph_validator, "_NODE_CLASS_CACHE", {TaskType.WEB_SEARCH: object})
    graph = TaskGraph(
        workflow_id="w",
        nodes=[TaskNode(id="n", type=TaskType.CODE_EXECUTION, params={})],
    )
    valid, errors = graph_validator.GraphValidator().validate(graph, check_semantics=True)
    assert valid is True
    assert errors == []

    bad_node = TaskNode.model_construct(
        id="bad", type="bogus", params={}, depends_on=[]
    )
    bad_graph = TaskGraph.model_construct(workflow_id="w", nodes=[bad_node])
    validator = graph_validator.GraphValidator()
    validator._check_task_type_validity(bad_graph)
    assert any("has invalid type" in err for err in validator.errors)


def test_get_node_classes_skips_none_task_type(monkeypatch):
    from app.utils.workflow import graph_validator

    monkeypatch.setattr(graph_validator, "_NODE_CLASS_CACHE", None)
    import app.utils.workflow.node_types as node_types

    monkeypatch.setattr(node_types.WebSearchNode, "task_type", None, raising=False)
    classes = graph_validator._get_node_classes()
    assert classes


def test_classify_items_shown_reuses_existing_category():
    from app.agent.orchestrator_requirements.mixin import RequirementAssociationMixin
    from app.agent.orchestrator_requirements.data_models import AssociationItem

    mixin = RequirementAssociationMixin()
    items = [
        AssociationItem(content="a", category="risk", source="s", confidence=0.9),
        AssociationItem(content="b", category="risk", source="s", confidence=0.8),
    ]
    result = mixin._classify_items_for_display(items)
    assert len(result["risk"]["shown"]) == 2
