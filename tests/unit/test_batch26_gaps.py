"""Batch 26 coverage gaps: profiler, rate limiter, models and planners."""

import dataclasses
import re
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from types import SimpleNamespace
from unittest.mock import patch

import asyncio
import pytest

import app.utils.resource_guard as resource_guard
from app.agent.orchestration import (
    ArtifactCommitter,
    ExecutionBudget,
    GeneratedContent,
    GenerationNodeStatus,
    GenerationScheduleStatus,
    GenerationScheduler,
    build_file_plan,
)
from app.agent.orchestration.generation_scheduler import _MutableNode
from app.agent.orchestration.plan import PlannedFile
from app.agent.shared_context import SharedContext
from app.agent.constrained_generation import (
    _resolve_layout,
    select_fastapi_crud_renderer,
)
from app.agent.orchestrator_requirements.feedback_tracker import (
    AssociationFeedbackTracker,
)
from app.agent.project_profiler import ProjectProfiler
from app.agent.validation_report import ValidationReport
from app.agent import symbol_table as symbol_table_module
from app.api.v1.ai_agent import helpers as helpers_module
from app.db.models import WorkflowHistory
from app.models.task import Task
from app.schema.ppt_outline import (
    AssetIntent,
    ContentBlock,
    OutlineDraft,
    OutlineSlide,
)
from app.utils import rate_limiter
from app.utils.pptx.semantic_planner import _layout_score, plan_outline


def _draft(slides):
    return OutlineDraft(
        id="o",
        user_id="1",
        version=1,
        title="t",
        scenario="general",
        template_id="modern",
        slide_limit=10,
        slides=slides,
        created_at="2026-01-01T00:00:00Z",
    )


def _request(host, headers=None):
    from starlette.requests import Request

    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "headers": [
                (key.lower().encode(), value.encode())
                for key, value in (headers or {}).items()
            ],
            "client": (host, 1234),
            "server": ("testserver", 80),
            "scheme": "http",
        }
    )


def test_profiler_mixin_heavy_without_layers(tmp_path):
    (tmp_path / "widget.py").write_text("class FooMixin:\n    pass\n", encoding="utf-8")

    profile = ProjectProfiler(str(tmp_path), language="python").profile()

    assert profile.architecture.pattern == "mixin-heavy"
    assert profile.architecture.aggregate_classes == ["widget.py:FooMixin"]


def test_profiler_unknown_language_falls_back_to_python(tmp_path):
    profiler = ProjectProfiler(str(tmp_path), language="klingon")

    assert profiler.language == "python"


def test_profiler_source_enumeration_falls_back_when_path_outside_root(
    tmp_path, monkeypatch
):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(Path, "rglob", lambda self, pattern: iter([outside]))

    profiler = ProjectProfiler(str(root), language="python")

    assert [path.name for path in profiler._iter_source_files(root)] == ["outside.py"]


def test_profiler_skips_import_regex_with_empty_module(tmp_path):
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    profiler = ProjectProfiler(str(tmp_path), language="python")
    profiler.profile_rules = dataclasses.replace(
        profiler.profile_rules, import_pattern=re.compile(r"^(x?)")
    )

    assert profiler._count_imports(tmp_path) == {}


def test_profiler_export_detection_swallows_errors(tmp_path, monkeypatch):
    (tmp_path / "__init__.py").write_text("from .x import y\n", encoding="utf-8")
    profiler = ProjectProfiler(str(tmp_path), language="python")

    def boom(content):
        raise RuntimeError("parse failure")

    monkeypatch.setattr(profiler, "_is_python_pure_export", boom)

    assert profiler._detect_export_modules(tmp_path) == []


def test_profiler_layer_detection_deduplicates_same_directory(tmp_path):
    (tmp_path / "api").mkdir()
    (tmp_path / "services").mkdir()

    layers = ProjectProfiler(str(tmp_path), language="python")._detect_layers(tmp_path)

    assert layers["api"] == ["api"]
    assert layers["service"] == ["services"]


def test_profiler_unknown_language_file_mapping_falls_back(tmp_path, monkeypatch):
    profiler = ProjectProfiler(str(tmp_path), language="python")
    profiler.language = "elixir"

    assert profiler._module_to_filename("MyApp.Core") == "MyApp.Core"


def test_rate_limiter_skips_forwarded_header_without_entries():
    request = _request("10.0.0.5", {"X-Forwarded-For": " , , "})

    assert rate_limiter.get_client_ip(request) == "10.0.0.5"


def test_rate_limiter_falls_back_when_storage_init_fails(monkeypatch):
    monkeypatch.setattr(
        rate_limiter.settings, "REDIS_URL", "redis://127.0.0.1:6379/0"
    )

    class FakeLimiter:
        def __init__(self, **kwargs):
            if "storage_uri" in kwargs:
                raise RuntimeError("storage unavailable")
            self.kwargs = kwargs

    monkeypatch.setattr(rate_limiter, "Limiter", FakeLimiter)

    limiter = rate_limiter._create_limiter()

    assert "storage_uri" not in limiter.kwargs


def test_layout_score_rewards_assets_and_title_slides():
    image_slide = OutlineSlide(
        id="img",
        position=0,
        slide_type="image_text",
        title="图",
        key_message="说明",
        content_blocks=[ContentBlock(content="x")],
        asset_intent=AssetIntent(description="chart"),
    )
    cover_slide = OutlineSlide(
        id="cover",
        position=1,
        slide_type="cover",
        title="封面",
        key_message="开场",
        content_blocks=[ContentBlock(content="x")],
    )

    assert _layout_score(image_slide, "image_text", "content_with_image", None, 0) == 4.0
    assert _layout_score(cover_slide, "cover", "title_slide", None, 0) == 3.0

    plans = plan_outline(_draft([image_slide, cover_slide]))
    assert plans[0].layout_id == "content_with_image"
    assert plans[1].layout_id == "title_slide"


def test_renderer_selection_rejects_incomplete_layout():
    assert select_fastapi_crud_renderer("FastAPI CRUD", {"main.py": {}}) is None


def test_layout_resolution_requires_all_six_roles():
    paths = ("main.py", "models.py", "database.py", "schemas.py", "crud.py", "notes.py")

    assert _resolve_layout(paths) is None


def test_task_to_dict_serializes_nullable_timestamps():
    payload = Task(user_id=1).to_dict()

    assert payload["task_id"] is None
    assert payload["created_at"] is None
    assert payload["completed_at"] is None


def test_workflow_history_to_dict_serializes_nullable_timestamps():
    payload = WorkflowHistory(
        workflow_id="wf", user_id="u", request="r"
    ).to_dict()

    assert payload["workflow_id"] == "wf"
    assert payload["created_at"] is None


def test_validation_report_scopes_are_sorted_and_unique():
    report = (
        ValidationReport.create()
        .with_finding("first", scope="beta")
        .with_finding("second", scope="alpha")
        .with_finding("third", scope="beta")
    )

    assert report.scopes == ("alpha", "beta")


def test_feedback_cleanup_swallows_size_query_failure(tmp_path):
    class BrokenConnection:
        def execute(self, sql, *args):
            if "pragma_page_count" in sql:
                raise RuntimeError("database gone")
            return SimpleNamespace(fetchone=lambda: (0,))

        def commit(self):
            return None

    with patch.object(AssociationFeedbackTracker, "DB_PATH", tmp_path / "fb.db"):
        AssociationFeedbackTracker._last_cleanup_at = time.time()
        tracker = AssociationFeedbackTracker()

    tracker._conn = BrokenConnection()

    tracker._cleanup()


def _meminfo_handle(text):
    handle = MagicMock()
    handle.read.return_value = text
    handle.__enter__ = MagicMock(return_value=handle)
    handle.__exit__ = MagicMock(return_value=False)
    return handle


def _statvfs(blocks=100, free=50):
    stat = MagicMock()
    stat.f_blocks = blocks
    stat.f_frsize = 1024
    stat.f_bavail = free
    return stat


def test_resource_guard_skips_unrelated_meminfo_lines(monkeypatch):
    guard = resource_guard.ResourceGuard()
    meminfo = "MemFree: 10 kB\nMemTotal: 1000 kB\nMemAvailable: 500 kB\n"

    monkeypatch.setattr(resource_guard, "_HAS_PSUTIL", False)
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: _meminfo_handle(meminfo))
    monkeypatch.setattr("os.statvfs", lambda path: _statvfs())
    monkeypatch.setattr("os.getloadavg", lambda: (0.0, 0.0, 0.0))

    assert guard.check_resources() is True
    assert guard.get_safe_concurrency() == 4
    status = guard.get_resource_status()
    assert status["memory_percent"] == 50
    assert guard.should_reduce_cache() is False


def test_resource_guard_status_falls_back_when_meminfo_incomplete(monkeypatch):
    guard = resource_guard.ResourceGuard()
    meminfo = "MemTotal: 2000 kB\n"

    monkeypatch.setattr(resource_guard, "_HAS_PSUTIL", False)
    monkeypatch.setattr("builtins.open", lambda *args, **kwargs: _meminfo_handle(meminfo))
    monkeypatch.setattr("os.statvfs", lambda path: _statvfs(free=50))

    status = guard.get_resource_status()

    assert status["memory_percent"] == 0
    assert status["disk_percent"] == 50


def test_resource_guard_status_survives_unreadable_meminfo(monkeypatch):
    guard = resource_guard.ResourceGuard()

    monkeypatch.setattr(resource_guard, "_HAS_PSUTIL", False)
    monkeypatch.setattr(
        "builtins.open", MagicMock(side_effect=OSError("unreadable"))
    )
    monkeypatch.setattr("os.statvfs", lambda path: _statvfs())

    status = guard.get_resource_status()

    assert status["memory_percent"] == 0
    assert status["memory_available_mb"] == 0


def test_rewrite_manifests_saves_requirements_through_context(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(
        "app.agent.utils.write_file_atomic", lambda *args, **kwargs: None
    )
    ctx = SimpleNamespace(save_file_content=lambda *args: saved.append(args))
    architecture = {
        "language": "python",
        "file_plan": [{"path": "requirements.txt"}],
    }

    symbol_table_module.rewrite_manifests(tmp_path, architecture, {}, ctx)

    assert any(item[0] == "requirements.txt" for item in saved)


def test_rewrite_manifests_skips_requirements_for_non_python(tmp_path, monkeypatch):
    written = []
    monkeypatch.setattr(
        "app.agent.utils.write_file_atomic",
        lambda root, name, content, **kwargs: written.append(name),
    )

    symbol_table_module.rewrite_manifests(
        tmp_path, {"language": "javascript", "file_plan": []}, {}
    )

    assert written == []


def test_rewrite_manifests_saves_scaffolded_tests_through_context(
    tmp_path, monkeypatch
):
    saved = []
    monkeypatch.setattr(
        "app.agent.utils.write_file_atomic", lambda *args, **kwargs: None
    )
    monkeypatch.setattr(
        "app.agent.adapters.boilerplate.scaffold_for_language",
        lambda *args: "def test_x():\n    pass\n",
    )
    ctx = SimpleNamespace(save_file_content=lambda *args: saved.append(args))
    architecture = {
        "language": "python",
        "file_plan": [{"path": "tests/test_app.py", "file_type": "test"}],
    }

    symbol_table_module.rewrite_manifests(tmp_path, architecture, {}, ctx)

    assert any(item[0] == "tests/test_app.py" for item in saved)


def test_sync_project_spec_merges_dialect_when_type_missing():
    architecture = {"project_spec": {"default": {}}}

    symbol_table_module._sync_project_spec(
        architecture, {"storage": {"dialect": "postgresql"}}
    )

    assert architecture["project_spec"]["default"]["storage"] == {
        "type": "postgresql"
    }


def test_router_prefixes_tracks_nested_parentheses():
    text = 'router = APIRouter(\n    prefix="/api/v1",\n    dependencies=[Depends(guard())],\n)\n'

    assert symbol_table_module._router_prefixes(text) == {"router": "/api/v1"}


def test_file_type_ignores_non_matching_plan_entry():
    architecture = {"file_plan": [{"path": "other.py", "file_type": "api"}]}

    assert symbol_table_module._file_type("app/models.py", architecture) == "model"


def test_local_module_detected_by_matching_stem():
    assert symbol_table_module._is_local_python_module("app", {"app.py": ""}) is True


def _scheduler(tmp_path, *, max_concurrent=2, max_retries=0):
    context = SharedContext("batch26", tmp_path)
    committer = ArtifactCommitter(tmp_path, context, task_id="batch26")
    return GenerationScheduler(
        committer, max_concurrent=max_concurrent, max_retries=max_retries
    )


def _budget(*, task=5.0, stage=5.0, file=2.0):
    return ExecutionBudget(
        task_seconds=task,
        stage_seconds=stage,
        file_seconds=file,
        model_call_seconds=min(file, 1.0),
    )


@pytest.mark.asyncio
async def test_scheduler_waits_for_finished_task_when_cancel_watcher_idle(tmp_path):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])
    cancel_event = asyncio.Event()

    async def generator(context):
        return GeneratedContent(content="x = 1\n", model_name="m")

    result = await scheduler.run(
        plan,
        generator,
        _budget(),
        task_id="t",
        stage_id="s",
        cancel_event=cancel_event,
    )

    assert result.status is GenerationScheduleStatus.COMPLETED


@pytest.mark.asyncio
async def test_scheduler_skips_ready_node_that_became_terminal(tmp_path):
    scheduler = _scheduler(tmp_path, max_concurrent=1)
    plan = build_file_plan(
        [{"path": "a.py"}, {"path": "b.py"}, {"path": "c.py"}, {"path": "d.py"}],
        requested_paths=["a.py", "b.py", "c.py", "d.py"],
    )

    async def generator(context):
        if context.file_path == "a.py":
            scheduler.nodes["c.py"].status = GenerationNodeStatus.BLOCKED
        return GeneratedContent(content="x = 1\n", model_name="m")

    result = await scheduler.run(
        plan, generator, _budget(), task_id="t", stage_id="s"
    )

    assert result.nodes["a.py"].status is GenerationNodeStatus.COMPLETED
    assert result.nodes["b.py"].status is GenerationNodeStatus.COMPLETED
    assert result.nodes["c.py"].status is GenerationNodeStatus.BLOCKED
    assert result.nodes["d.py"].status is GenerationNodeStatus.COMPLETED


@pytest.mark.asyncio
async def test_scheduler_ignores_downstream_that_is_no_longer_pending(tmp_path):
    scheduler = _scheduler(tmp_path, max_concurrent=1)
    plan = build_file_plan(
        [{"path": "a.py"}, {"path": "b.py", "dependencies": ["a.py"]}],
        requested_paths=["a.py", "b.py"],
    )

    async def generator(context):
        if context.file_path == "a.py":
            scheduler.nodes["b.py"].status = GenerationNodeStatus.COMPLETED
        return GeneratedContent(content="x = 1\n", model_name="m")

    result = await scheduler.run(
        plan, generator, _budget(), task_id="t", stage_id="s"
    )

    assert result.nodes["b.py"].status is GenerationNodeStatus.COMPLETED


@pytest.mark.asyncio
async def test_scheduler_only_readies_downstream_whose_dependencies_finished(tmp_path):
    scheduler = _scheduler(tmp_path, max_concurrent=1)
    plan = build_file_plan(
        [
            {"path": "a.py"},
            {"path": "b.py", "dependencies": ["a.py"]},
            {"path": "c.py", "dependencies": ["a.py", "b.py"]},
        ],
        requested_paths=["a.py", "b.py", "c.py"],
    )

    async def generator(context):
        return GeneratedContent(content="x = 1\n", model_name="m")

    result = await scheduler.run(
        plan, generator, _budget(), task_id="t", stage_id="s"
    )

    assert result.status is GenerationScheduleStatus.COMPLETED


@pytest.mark.asyncio
async def test_scheduler_block_descendants_skips_already_blocked_node(tmp_path):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan(
        [{"path": "a.py"}, {"path": "b.py", "dependencies": ["a.py"]}],
        requested_paths=["a.py", "b.py"],
    )

    async def generator(context):
        if context.file_path == "a.py":
            scheduler.nodes["b.py"].status = GenerationNodeStatus.BLOCKED
            raise RuntimeError("upstream failed")
        return GeneratedContent(content="x = 1\n", model_name="m")

    result = await scheduler.run(
        plan, generator, _budget(), task_id="t", stage_id="s"
    )

    assert result.nodes["a.py"].status is GenerationNodeStatus.FAILED
    assert result.nodes["b.py"].status is GenerationNodeStatus.BLOCKED


@pytest.mark.asyncio
async def test_scheduler_commit_failure_without_diagnostic(tmp_path, monkeypatch):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    class _Result:
        success = False
        diagnostic = None
        completion_event = None

    monkeypatch.setattr(scheduler.committer, "commit", lambda *a, **k: _Result())

    async def generator(context):
        return GeneratedContent(content="ok", model_name="m")

    result = await scheduler.run(
        plan, generator, _budget(), task_id="t", stage_id="s"
    )

    assert result.nodes["main.py"].status is GenerationNodeStatus.FAILED
    assert result.nodes["main.py"].diagnostics == ()


@pytest.mark.asyncio
async def test_scheduler_file_deadline_expires_between_retries(tmp_path):
    scheduler = _scheduler(tmp_path, max_retries=1)
    node = _MutableNode(
        planned_file=PlannedFile(
            path="main.py", language="python", dependencies=()
        )
    )
    queue: asyncio.Queue[str] = asyncio.Queue()

    class _Clock:
        def __init__(self):
            self.values = iter([0.0, 0.0, 10.0])

        def time(self):
            return next(self.values)

    async def generator(context):
        raise RuntimeError("first attempt fails")

    await scheduler._execute_node(
        node,
        generator,
        _budget(file=0.5),
        task_id="t",
        stage_id="s",
        cancel_event=None,
        contract_index=None,
        completion_queue=queue,
        loop=_Clock(),
    )

    assert node.status is GenerationNodeStatus.TIMED_OUT
    assert node.diagnostics[-1].code == "file_timeout"
    assert await queue.get() == "main.py"


def test_sanitize_imported_relpath_rejects_dot_only():
    assert helpers_module._sanitize_imported_relpath(".") is None


def test_materialize_imported_project_treats_null_content_as_empty(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(helpers_module, "PROJECTS_BASE_DIR", str(tmp_path))

    result = helpers_module.materialize_imported_project(
        "1", [{"path": "empty.txt", "content": None}]
    )

    assert result["files"] == ["empty.txt"]
    assert (tmp_path / result["project_path"] / "empty.txt").read_text() == ""


def test_materialize_imported_project_skips_path_escaping_destination(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(helpers_module, "PROJECTS_BASE_DIR", str(tmp_path))
    real_resolve = Path.resolve
    outside = tmp_path / "outside"
    outside.mkdir()

    def fake_resolve(self, *args, **kwargs):
        if self.name == "escape.py":
            return outside / "escape.py"
        return real_resolve(self, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", fake_resolve)

    with pytest.raises(ValueError, match="没有可写入的有效文件"):
        helpers_module.materialize_imported_project(
            "1", [{"path": "escape.py", "content": "x"}]
        )


def test_collect_files_skips_entry_when_stat_fails(tmp_path, monkeypatch):
    (tmp_path / "a.py").write_text("x", encoding="utf-8")
    real_stat = Path.stat

    def boom(self, *args, **kwargs):
        if self.name == "a.py":
            raise OSError("stat failed")
        return real_stat(self, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", boom)

    assert helpers_module._collect_files_sync(tmp_path) == []


@pytest.mark.asyncio
async def test_singleton_getters_recheck_after_lock(monkeypatch):
    sentinel = SimpleNamespace()

    class _Lock:
        async def __aenter__(self):
            helpers_module._session_manager = sentinel
            helpers_module._spec_cache = sentinel
            helpers_module._feedback_learner = sentinel

        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(helpers_module, "_session_manager", None)
    monkeypatch.setattr(helpers_module, "_spec_cache", None)
    monkeypatch.setattr(helpers_module, "_feedback_learner", None)
    monkeypatch.setattr(helpers_module, "_session_manager_lock", _Lock())
    monkeypatch.setattr(helpers_module, "_spec_cache_lock", _Lock())
    monkeypatch.setattr(helpers_module, "_feedback_learner_lock", _Lock())

    assert await helpers_module.get_session_manager() is sentinel
    assert await helpers_module.get_spec_cache() is sentinel
    assert await helpers_module.get_feedback_learner() is sentinel


def test_delete_session_files_without_output_dir(tmp_path):
    helpers_module._delete_session_files(tmp_path / "s.json", None)


@pytest.mark.asyncio
async def test_update_session_status_skips_missing_memory_state(monkeypatch):
    session = SimpleNamespace(
        status="running",
        error_message=None,
        completed_at=None,
        output_dir=None,
    )

    class _DB:
        async def execute(self, *args, **kwargs):
            return SimpleNamespace(scalar_one_or_none=lambda: session)

        async def commit(self):
            return None

    sm = SimpleNamespace(
        _get_state=AsyncMock(return_value=None),
        _save_session=AsyncMock(),
    )
    monkeypatch.setattr(
        helpers_module, "get_session_manager", AsyncMock(return_value=sm)
    )

    await helpers_module._update_project_session_status(_DB(), "s", "completed")

    assert session.status == "completed"
    sm._save_session.assert_not_awaited()


@pytest.mark.asyncio
async def test_resolve_resume_session_without_numeric_reply(monkeypatch):
    import app.utils as utils

    session = SimpleNamespace(
        session_id="a",
        requirement="req",
        created_at=None,
        status="completed",
        files_generated=0,
        files_total=0,
    )

    class _DB:
        async def execute(self, *args, **kwargs):
            return SimpleNamespace(
                scalars=lambda: SimpleNamespace(all=lambda: [session])
            )

    monkeypatch.setattr(
        utils,
        "call_llm",
        AsyncMock(return_value={"choices": [{"message": {"content": "none"}}]}),
    )

    result = await helpers_module.resolve_resume_session(_DB(), "1", "x")

    assert result is session


def test_collect_files_skips_hidden_file_name(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / ".env").write_text("SECRET=1", encoding="utf-8")
    (tmp_path / "visible.py").write_text("x = 1\n", encoding="utf-8")

    entries = helpers_module._collect_files_sync(tmp_path)

    assert [entry["name"] for entry in entries] == ["visible.py"]
