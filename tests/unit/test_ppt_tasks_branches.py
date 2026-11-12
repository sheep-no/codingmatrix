"""Branch coverage for app/tasks/ppt_tasks.py with stubbed pipeline modules."""

import asyncio
import sys
import types
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.tasks import ppt_tasks as module


def _install_stub(monkeypatch, name: str, **attrs):
    stub = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(stub, key, value)
    monkeypatch.setitem(sys.modules, name, stub)
    return stub


def _run_task(task_self, *args):
    """Invoke the unbound Celery task body with a fake bound task instance."""
    task = module.generate_ppt._get_current_object()
    return task.run.__func__(task_self, *args)


class _OutputFormat:
    PPTX = "pptx"
    HTML = "html"
    MARKDOWN = "markdown"
    PDF = "pdf"


class _Request:
    def __init__(
        self,
        output_format="pptx",
        options=None,
        template=None,
        slide_count=3,
        api_key_token="token",
    ):
        self.output_format = output_format
        self.options = options
        self.template = template
        self.slide_count = slide_count
        self.api_key_token = api_key_token


class _SessionCtx:
    def __init__(self, session):
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _Db:
    def __init__(self):
        self.commits = 0

    async def commit(self):
        self.commits += 1


class _Progress:
    def __init__(self):
        self.updates = []

    async def update(self, value, message):
        self.updates.append((value, message))
        return None


def _install_pipeline_stubs(
    monkeypatch,
    tmp_path,
    *,
    output_mode="pptx",
    reflow_attempts=0,
    approved_outline=None,
    success=True,
):
    calls = {"persist": [], "review": [], "convert": [], "checkpoints": []}
    request = _Request(
        output_format=output_mode,
        options={
            "quality_mode": "strict",
            **(approved_outline if approved_outline else {}),
        },
        template="template-a",
    )

    class _PPTGenerationRequest:
        @classmethod
        def model_validate(cls, data):
            request.options = data.get("options", request.options)
            return request

    async def _to_thread(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr(module.asyncio, "to_thread", _to_thread)

    async def generate_ppt_outline(req, user_id=None):
        return {"slides": [{"id": "s1"}]}

    def _normalize_approved_outline(outline):
        return {"slides": outline}

    async def generate_pptx_file_enhanced(filepath, outline, req, **kwargs):
        calls.setdefault("pptx", []).append(filepath)

    async def _convert_pptx_to_pdf(src, dst):
        calls["convert"].append((src, dst))

    async def generate_html_ppt(filepath, outline, req):
        calls.setdefault("html", []).append(filepath)

    async def generate_markdown_ppt(filepath, outline, req):
        calls.setdefault("markdown", []).append(filepath)

    _install_stub(
        monkeypatch,
        "app.api.v1.aiGeneratorPptx",
        PPT_OUTPUT_DIR=str(tmp_path),
        OutputFormat=_OutputFormat,
        PPTGenerationRequest=_PPTGenerationRequest,
        _convert_pptx_to_pdf=_convert_pptx_to_pdf,
        generate_html_ppt=generate_html_ppt,
        generate_markdown_ppt=generate_markdown_ppt,
        generate_ppt_outline=generate_ppt_outline,
        generate_pptx_file_enhanced=generate_pptx_file_enhanced,
        _normalize_approved_outline=_normalize_approved_outline,
    )

    db = _Db()
    _install_stub(monkeypatch, "app.db.database", async_session=lambda: _SessionCtx(db))

    class _Orchestrator:
        def __init__(self, handlers):
            self.handlers = handlers

        async def run(self, state):
            context = dict(state)
            for name in (
                "planning",
                "assets",
                "rendering",
                "rule_qa",
                "reflow",
                "vision_qa",
                "completed",
            ):
                result = self.handlers[name](context)
                context = await result if asyncio.iscoroutine(result) else result
            if not success:
                return SimpleNamespace(
                    status="failed", error=None, stage="rendering", context=context
                )
            return SimpleNamespace(
                status="completed", error=None, stage="completed", context=context
            )

    _install_stub(
        monkeypatch,
        "app.services.ppt_generation_orchestrator",
        PPTGenerationOrchestrator=_Orchestrator,
    )

    def build_ppt_trace_context(options, template, quality_mode):
        return {"template_version": "v1", "quality_mode": quality_mode}

    def serialize_quality_report(report):
        return {"reflow_attempts": report.reflow_attempts}

    async def persist_ppt_generation_result(*args):
        calls["persist"].append(args)

    async def save_ppt_stage_checkpoint(*args):
        calls["checkpoints"].append(args)

    _install_stub(
        monkeypatch,
        "app.services.ppt_generation_persistence",
        build_ppt_trace_context=build_ppt_trace_context,
        persist_ppt_generation_result=persist_ppt_generation_result,
        save_ppt_stage_checkpoint=save_ppt_stage_checkpoint,
        serialize_quality_report=serialize_quality_report,
    )

    report = SimpleNamespace(reflow_attempts=reflow_attempts)

    async def run_quality_pipeline(slides, mode):
        return slides, report

    async def review_rendered_deck(*args):
        calls["review"].append(args)

    _install_stub(
        monkeypatch,
        "app.services.ppt_quality_orchestrator",
        review_rendered_deck=review_rendered_deck,
        run_quality_pipeline=run_quality_pipeline,
    )
    _install_stub(
        monkeypatch,
        "app.utils.pptx.semantic_planner",
        slide_capacity=lambda slide: 5,
    )
    _install_stub(
        monkeypatch,
        "app.utils.pptx.semantic_renderer",
        build_render_metadata=lambda slide, token_version=None: {
            "version": token_version
        },
    )
    return calls, db


@pytest.mark.asyncio
@pytest.mark.parametrize("output_mode", ["pptx", "pdf", "html", "markdown"])
async def test_generate_ppt_output_formats(monkeypatch, tmp_path, output_mode) -> None:
    calls, db = _install_pipeline_stubs(monkeypatch, tmp_path, output_mode=output_mode)
    progress = _Progress()

    result = await module._generate_ppt("task-1", 7, {"options": {}}, progress)

    assert result["ppt_id"] == "task-1"
    assert result["filename"].endswith(result["filename"].split(".")[-1])
    assert calls["persist"]
    assert db.commits >= 2
    if output_mode == "pdf":
        assert calls["convert"]
    if output_mode == "html":
        assert calls["html"]
    if output_mode == "markdown":
        assert calls["markdown"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("output_mode", "expected_preview"),
    [("pptx", "/api/v1/pptx/preview/task-1"), ("html", None)],
)
async def test_generate_ppt_preview_url_only_for_pptx(
    monkeypatch, tmp_path, output_mode, expected_preview
) -> None:
    _install_pipeline_stubs(monkeypatch, tmp_path, output_mode=output_mode)

    result = await module._generate_ppt("task-1", 7, {}, _Progress())

    assert result["preview_url"] == expected_preview


@pytest.mark.asyncio
async def test_generate_ppt_uses_approved_outline(monkeypatch, tmp_path) -> None:
    _install_pipeline_stubs(
        monkeypatch,
        tmp_path,
        approved_outline={"approved_outline": [{"id": "s1"}]},
    )

    await module._generate_ppt("task-1", 7, {}, _Progress())

    snapshot = (tmp_path / "task-1_slides.json").read_text(encoding="utf-8")
    assert '"s1"' in snapshot


@pytest.mark.asyncio
async def test_generate_ppt_reflow_rerenders(monkeypatch, tmp_path) -> None:
    calls, _ = _install_pipeline_stubs(monkeypatch, tmp_path, reflow_attempts=1)

    await module._generate_ppt("task-1", 7, {}, _Progress())

    assert len(calls.get("pptx", [])) == 2


@pytest.mark.asyncio
async def test_generate_ppt_quality_slides_defaults(monkeypatch, tmp_path) -> None:
    calls, _ = _install_pipeline_stubs(monkeypatch, tmp_path, reflow_attempts=0)

    await module._generate_ppt("task-1", 7, {}, _Progress())

    persisted = calls["persist"][0]
    slides = persisted[7]
    assert slides[0]["id"] == "s1"
    assert slides[0]["elements"] == []
    assert slides[0]["capacity"] == 5
    assert slides[0]["render_metadata"] == {"version": "v1"}


@pytest.mark.asyncio
async def test_generate_ppt_failure_with_error(monkeypatch, tmp_path) -> None:
    _install_pipeline_stubs(monkeypatch, tmp_path, success=False)

    class _Orch:
        def __init__(self, handlers):
            self.handlers = handlers

        async def run(self, state):
            return SimpleNamespace(status="failed", error="boom", stage="x", context={})

    monkeypatch.setitem(
        sys.modules,
        "app.services.ppt_generation_orchestrator",
        SimpleNamespace(PPTGenerationOrchestrator=_Orch),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await module._generate_ppt("task-1", 7, {}, _Progress())


@pytest.mark.asyncio
async def test_generate_ppt_failure_without_error(monkeypatch, tmp_path) -> None:
    _install_pipeline_stubs(monkeypatch, tmp_path)

    class _Orch:
        def __init__(self, handlers):
            self.handlers = handlers

        async def run(self, state):
            return SimpleNamespace(
                status="failed", error=None, stage="render", context={}
            )

    monkeypatch.setitem(
        sys.modules,
        "app.services.ppt_generation_orchestrator",
        SimpleNamespace(PPTGenerationOrchestrator=_Orch),
    )

    with pytest.raises(RuntimeError, match="render"):
        await module._generate_ppt("task-1", 7, {}, _Progress())


# ---------------------------------------------------------------------------
# Celery wrapper
# ---------------------------------------------------------------------------


class _TaskSelf:
    def __init__(self, *, hostname="worker-1", retry_error=None):
        self.request = SimpleNamespace(hostname=hostname)
        self.calls = []
        self.retry_error = retry_error

    def _get_progress_callback(self, task_id, user_id):
        return _Progress()

    def retry(self, exc=None, countdown=None):
        self.calls.append(("retry", str(exc), countdown))
        if self.retry_error:
            raise self.retry_error
        from celery.exceptions import Retry

        raise Retry("retried")


def _install_task_stubs(monkeypatch, *, transition_side_effect=None):
    events = {"transitions": [], "events": [], "heartbeats": [], "rollbacks": 0}

    class _Db:
        async def commit(self):
            events.setdefault("commits", 0)
            events["commits"] += 1

        async def rollback(self):
            events["rollbacks"] += 1

    _install_stub(
        monkeypatch, "app.db.database", async_session=lambda: _SessionCtx(_Db())
    )

    async def transition_task(db, task_id, user_id, status, **kwargs):
        if transition_side_effect and status in transition_side_effect:
            raise RuntimeError("transition failed")
        events["transitions"].append((status, kwargs))

    async def append_task_event(db, task_id, user_id, event, **kwargs):
        if transition_side_effect and event in transition_side_effect:
            raise RuntimeError("event failed")
        events["events"].append((event, kwargs))

    async def heartbeat_task(db, task_id, user_id, **kwargs):
        events["heartbeats"].append(kwargs)

    _install_stub(
        monkeypatch,
        "app.services.unified_state_service",
        transition_task=transition_task,
        heartbeat_task=heartbeat_task,
    )
    _install_stub(
        monkeypatch,
        "app.services.task_event_service",
        append_task_event=append_task_event,
    )
    return events


def test_generate_ppt_task_success(monkeypatch) -> None:
    events = _install_task_stubs(monkeypatch)

    async def fake_generate(task_id, user_id, request_data, progress):
        await progress.update(30, "half")
        return {"ok": True}

    monkeypatch.setattr(module, "_generate_ppt", fake_generate)
    task_self = _TaskSelf()

    result = _run_task(task_self, "task-1", 7, {})

    assert result == {"ok": True}
    assert events["heartbeats"]
    assert ("success", {"progress": 100, "result": {"ok": True}}) in events["transitions"]


def test_generate_ppt_task_progress_from_kwargs(monkeypatch) -> None:
    _install_task_stubs(monkeypatch)

    async def fake_generate(task_id, user_id, request_data, progress):
        await progress.update(progress=45, message="kw")
        return {}

    monkeypatch.setattr(module, "_generate_ppt", fake_generate)

    assert _run_task(_TaskSelf(), "task-1", 7, {}) == {}


def test_generate_ppt_task_persist_progress_failure_rolls_back(monkeypatch) -> None:
    events = _install_task_stubs(
        monkeypatch, transition_side_effect={"running"}
    )

    async def fake_generate(task_id, user_id, request_data, progress):
        await progress.update(40, "boom")
        return {}

    monkeypatch.setattr(module, "_generate_ppt", fake_generate)

    _run_task(_TaskSelf(), "task-1", 7, {})

    assert events["rollbacks"] >= 1


def test_generate_ppt_task_success_persist_failure_rolls_back(monkeypatch) -> None:
    events = _install_task_stubs(monkeypatch, transition_side_effect={"success"})

    async def fake_generate(task_id, user_id, request_data, progress):
        return {}

    monkeypatch.setattr(module, "_generate_ppt", fake_generate)

    _run_task(_TaskSelf(), "task-1", 7, {})

    assert events["rollbacks"] >= 1


def test_generate_ppt_task_heartbeat_failure_rolls_back(monkeypatch) -> None:
    events = _install_task_stubs(monkeypatch)

    async def failing_heartbeat(*args, **kwargs):
        raise RuntimeError("heartbeat down")

    monkeypatch.setitem(
        sys.modules,
        "app.services.unified_state_service",
        SimpleNamespace(
            transition_task=sys.modules["app.services.unified_state_service"].transition_task,
            heartbeat_task=failing_heartbeat,
        ),
    )

    async def fake_generate(task_id, user_id, request_data, progress):
        return {}

    monkeypatch.setattr(module, "_generate_ppt", fake_generate)

    _run_task(_TaskSelf(), "task-1", 7, {})

    assert events["rollbacks"] >= 1


def test_generate_ppt_task_soft_timeout(monkeypatch) -> None:
    def fake_run(coro):
        coro.close()
        raise module.SoftTimeLimitExceeded()

    monkeypatch.setattr(module.asyncio, "run", fake_run)
    errors = []
    monkeypatch.setattr(
        module.logger, "error", lambda *args, **kwargs: errors.append(args)
    )

    with pytest.raises(RuntimeError, match="PPT 任务执行超时"):
        _run_task(_TaskSelf(), "task-1", 7, {})

    assert errors


def test_generate_ppt_task_generic_error_retries(monkeypatch) -> None:
    def fake_run(coro):
        coro.close()
        raise ValueError("boom")

    monkeypatch.setattr(module.asyncio, "run", fake_run)
    monkeypatch.setattr(module.logger, "exception", lambda *args, **kwargs: None)
    task_self = _TaskSelf()

    from celery.exceptions import Retry

    with pytest.raises(Retry):
        _run_task(task_self, "task-1", 7, {})
    assert task_self.calls == [("retry", "boom", 60)]


def test_generate_ppt_task_unknown_hostname(monkeypatch) -> None:
    events = _install_task_stubs(monkeypatch)

    async def fake_generate(task_id, user_id, request_data, progress):
        return {}

    monkeypatch.setattr(module, "_generate_ppt", fake_generate)

    _run_task(_TaskSelf(hostname=None), "task-1", 7, {})

    assert events["heartbeats"][0]["worker_id"] == "celery:unknown"
