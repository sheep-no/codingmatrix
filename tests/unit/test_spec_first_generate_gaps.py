"""spec_first_generate.py 剩余分支补测：上下文复用、失败回退与重构边界。"""

import json
import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.orchestrator_generation import spec_first_generate as module
from app.agent.orchestrator_generation.spec_first_generate import (
    SpecFirstGenerateMixin,
)

from tests.unit.test_spec_first_generate_branches2 import (
    _CtxStub,
    _DynamicGraph,
    _Engineer,
    _FakeIntegrityValidator,
    _Harness,
    _fake_integrity,
    _patch_generation_collaborators,
    _result,
)


class _ScriptedRefinement:
    def __init__(self, contents=None, success=True, error=None):
        self.contents = list(contents or ["def main():\n    return 1\n"])
        self.success = success
        self.error = error
        self.calls = 0

    async def refine(self, **kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        content = self.contents[min(self.calls - 1, len(self.contents) - 1)]
        return _result(content, success=self.success)


class _RecordingScheduler:
    """把 upstream/tracker 透传给 file_generator 的最小调度器。"""

    def __init__(self, upstream=None, tracker=None, nodes=None):
        self.upstream = upstream or {}
        self.tracker = tracker
        self.nodes = nodes or {}
        self.errors = []

    def build_from_dependency_graph(self, dep_graph):
        self.nodes = dict(dep_graph.nodes)

    async def run(self, file_generator, _progress_report):
        failed = []
        for path in self.nodes:
            try:
                await file_generator(path, self.upstream, self.tracker)
            except Exception:
                failed.append(path)
        return {"failed_files": failed}

    def get_stats(self):
        return {}


def _graph_with(missing=None, completeness=None, context=""):
    graph = _DynamicGraph(missing=missing or [], completeness=completeness or [])
    graph.reverse_adjacency = {}
    graph.context = context

    def get_context(*_args, **_kwargs):
        return graph.context

    graph.get_context_for_file = get_context
    return graph


async def _run_dynamic(
    harness,
    monkeypatch,
    ctx=None,
    graph=None,
    architecture=None,
    scheduler=None,
    adapter=None,
    allow_plan_expansion=True,
    after_patch=None,
):
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    if after_patch:
        after_patch()
    if scheduler is not None:
        monkeypatch.setattr(module, "TopologyScheduler", lambda **_kwargs: scheduler)
    graph = graph or _graph_with()
    ctx = ctx or _CtxStub()
    return await harness._generate_with_dynamic_topology(
        ctx,
        graph,
        None,
        architecture if architecture is not None else {
            "language": "python",
            "file_plan": [{"path": "app/main.py"}],
        },
        "需求",
        {"architecture": {}, "profile": {}},
        {},
        None,
        adapter if adapter is not None else SimpleNamespace(
            language="python", extensions=[".py"], package_init_filename="__init__.py"
        ),
        allow_plan_expansion,
    )


class _PreRegisteredContext:
    """预注册 app/main.py 的 SharedContext，用于覆盖已有文件依赖更新分支。"""

    def __new__(cls, requirement, output_dir):
        from app.agent.shared_context import SharedContext

        ctx = SharedContext(requirement, output_dir)
        ctx.register_file("app/main.py", "entry", ["app/base.py"])
        return ctx


@pytest.mark.asyncio
async def test_existing_context_file_updates_dependencies(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "SharedContext", _PreRegisteredContext)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_critical_alt_empty_refine_error_is_reraised(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"
    harness._select_engineer_for_model = lambda _model: _Engineer(content="")
    harness.refinement = _ScriptedRefinement(error=TimeoutError("slow"))
    monkeypatch.setattr(module, "RefinementLoop", lambda *a, **k: harness.refinement)

    with pytest.raises(RuntimeError, match="slow"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_quality_retry_empty_result_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    class _RetryEmpty(_Engineer):
        def __init__(self):
            super().__init__()
            self.calls = 0

        async def generate_file(self, *_args, **_kwargs):
            self.calls += 1
            return "def main():\n    return 1\n" if self.calls == 1 else ""

    harness.engineer = _RetryEmpty()
    monkeypatch.setattr(
        "app.agent.utils.validate_content_quality", lambda *a, **k: "leak"
    )

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_unverified_result_records_warning(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    harness.refinement = _ScriptedRefinement(success=False)
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(harness, monkeypatch, scheduler=scheduler)

    assert any("验证未完全通过" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_static_missing_modules_auto_filled(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    graph = _graph_with(missing=["app/__init__.py"], completeness=[{"type": "missing"}])

    class _GraphFactory:
        @staticmethod
        def load(*_args, **_kwargs):
            return graph

        def __new__(cls, *_args, **_kwargs):
            return graph

    monkeypatch.setattr(module, "DependencyGraph", _GraphFactory)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert (tmp_path / "app" / "__init__.py").exists()


@pytest.mark.asyncio
async def test_dynamic_upstream_context_and_tracker(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"
    tracker = SimpleNamespace(touches=0)

    def touch():
        tracker.touches += 1

    tracker.touch = touch
    scheduler = _RecordingScheduler(
        upstream={"app/base.py": "x = 1\n"},
        tracker=tracker,
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)},
    )

    result = await _run_dynamic(harness, monkeypatch, scheduler=scheduler)

    assert result["files_generated"] >= 1
    assert tracker.touches >= 2


@pytest.mark.asyncio
async def test_dynamic_alt_edited_file_is_read_back(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"

    class _EditingEngineer(_Engineer):
        def __init__(self):
            super().__init__(content="def alt():\n    return 1\n")

        async def generate_file(self, file_path, *_args, **_kwargs):
            path = Path(_kwargs.get("project_path", tmp_path)) / file_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("def edited():\n    return 2\n", encoding="utf-8")
            return "def alt():\n    return 1\n"

        def get_edited_files(self):
            return ["app/main.py"]

    harness._select_engineer_for_model = lambda _model: _EditingEngineer()
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(harness, monkeypatch, scheduler=scheduler)

    assert result["files_generated"] >= 1


@pytest.mark.asyncio
async def test_dynamic_quality_retry_failure_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )
    monkeypatch.setattr(module, "TopologyScheduler", lambda **_kwargs: scheduler)
    monkeypatch.setattr(
        "app.agent.utils.validate_content_quality", lambda *a, **k: "leak"
    )

    async def no_retry(*_args, **_kwargs):
        return None

    harness._retry_generate_file = no_retry

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_dynamic_error_recovery_requires_backend_model(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.syntax_ok = False
    harness.error_recovery = SimpleNamespace()
    harness.model_assignment = SimpleNamespace(backend_model=None)
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    with pytest.raises(RuntimeError, match="file generation failed"):
        await _run_dynamic(harness, monkeypatch, scheduler=scheduler)


@pytest.mark.asyncio
async def test_dynamic_error_recovery_success_marks_syntax_ok(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    outcomes = iter([False, True])

    async def validate_syntax(_path, _content):
        return next(outcomes, True)

    harness._validate_content_syntax = validate_syntax

    async def fix(**_kwargs):
        return True, "def fixed():\n    return 1\n"

    harness.error_recovery = SimpleNamespace(validate_and_fix=fix)
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(harness, monkeypatch, scheduler=scheduler)

    assert result["files_generated"] == 1


@pytest.mark.asyncio
async def test_dynamic_retry_leaves_syntax_invalid(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.syntax_ok = False
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    async def retry(*_args, **_kwargs):
        return "def still_bad(:\n"

    harness._retry_generate_file = retry

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(harness, monkeypatch, scheduler=scheduler)


@pytest.mark.asyncio
async def test_dynamic_symbol_table_warnings_are_collected(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(
        harness,
        monkeypatch,
        scheduler=scheduler,
        after_patch=lambda: monkeypatch.setattr(
            "app.agent.symbol_table.remember_generated_file",
            lambda *a, **k: ["symbol issue"],
        ),
    )

    assert "symbol issue" in result["warnings"]


@pytest.mark.asyncio
async def test_dynamic_without_architecture_skips_planned_extensions(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(
        harness, monkeypatch, scheduler=scheduler, architecture={}
    )

    assert result["files_generated"] == 1


@pytest.mark.asyncio
async def test_dynamic_missing_graph_files_but_none_missing(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    graph = _graph_with(missing=[], completeness=[{"type": "noise"}])

    result = await _run_dynamic(harness, monkeypatch, graph=graph)

    assert result["files_generated"] == 1


@pytest.mark.asyncio
async def test_dynamic_keeps_chinese_filename(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    ctx = _CtxStub(
        files={"app/图表.py": SimpleNamespace(generated_by="engineer", file_type="entry")},
        contents={"app/图表.py": "a = 1\n"},
    )
    graph = _graph_with()
    graph.nodes = {"app/图表.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    scheduler = _RecordingScheduler(
        nodes={"app/图表.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(
        harness, monkeypatch, ctx=ctx, graph=graph, scheduler=scheduler
    )

    assert "app/图表.py" in ctx.files


@pytest.mark.asyncio
async def test_dynamic_missing_file_on_disk_skips_rename(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    ctx = _CtxStub(
        files={"app/bad name.py": SimpleNamespace(generated_by="engineer", file_type="entry")},
        contents={"app/bad name.py": "a = 1\n"},
    )
    graph = _graph_with()
    graph.nodes = {"app/bad name.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    scheduler = _RecordingScheduler(
        nodes={"app/bad name.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(
        harness, monkeypatch, ctx=ctx, graph=graph, scheduler=scheduler
    )

    assert result["files_generated"] >= 1


def test_vue_without_script_is_valid():
    harness = _Harness(Path("/tmp"))
    result = asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(
            harness, "app/App.vue", "<template><div /></template>"
        )
    )
    assert result is True


def test_css_structure_error_is_invalid():
    harness = _Harness(Path("/tmp"))
    result = asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(
            harness, "app/style.css", "a { color: red;"
        )
    )
    assert result is False


@pytest.mark.asyncio
async def test_infer_skips_already_typed_nodes():
    harness = _Harness(Path("/tmp"))
    graph = SimpleNamespace(
        nodes={"a.py": SimpleNamespace(file_type="utils")},
        _enrich_unknown_file_type=lambda *_args: False,
    )
    await harness._infer_unknown_file_types(graph, ["a.py"], {}, "python")


@pytest.mark.asyncio
async def test_retry_generate_file_invalid_then_valid(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = None
    responses = iter(["def broken(:", "def ok():\n    return 1\n"])

    class _Engineer:
        SYSTEM_PROMPT = "sys"

        async def call_llm(self, *_args, **_kwargs):
            return next(responses)

    monkeypatch.setattr(
        "app.agent.utils.is_valid_code_content",
        lambda _path, content: (not content.startswith("def broken"), ""),
    )

    content = await harness._retry_generate_file(
        "main.py", "entry", {"architecture": {"language": "python"}}, "", "", _Engineer(), None
    )
    assert content.startswith("def ok():")


@pytest.mark.asyncio
async def test_fix_sandbox_errors_duplicate_file_and_missing_type(monkeypatch):
    harness = _Harness(Path("/tmp"))
    errors = [
        'app/main.py: ImportError: one (File "app/main.py", line 1)',
        'app/main.py: ImportError: two (File "app/main.py", line 2)',
        "app/main.py.Class.method(): boom",
        "app/main.py: plain failure",
    ]
    fixed = await harness._fix_sandbox_errors(
        errors, {"app/main.py": "import missing\n"}, SimpleNamespace()
    )
    assert fixed == []


@pytest.mark.asyncio
async def test_refactor_falls_back_to_python_adapter(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")
    monkeypatch.setattr(
        module.LanguageAdapterRegistry, "get_adapter_for_file", staticmethod(lambda _p: None)
    )

    async def fake_call_llm(**_kwargs):
        return json.dumps({"new_files": []})

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["errors"] == ["拆分方案中没有新文件"]


@pytest.mark.asyncio
async def test_refactor_plain_fenced_json(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")

    async def fake_call_llm(**_kwargs):
        return "```\n" + json.dumps({"new_files": []}) + "\n```"

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["errors"] == ["拆分方案中没有新文件"]


@pytest.mark.asyncio
async def test_refactor_validation_failure_only_warns(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")

    async def fake_call_llm(**_kwargs):
        return json.dumps({"new_files": [{"path": "app/part.py", "file_type": "utils"}]})

    class _FailingValidator:
        def __init__(self, *_args, **_kwargs):
            pass

        async def validate(self, *_args, **_kwargs):
            return SimpleNamespace(
                passed=False,
                issues=[SimpleNamespace(issue_type="cycle", message="loop")],
            )

    async def extract(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)
    monkeypatch.setattr(module, "DependencyGraphValidator", _FailingValidator)
    monkeypatch.setattr("app.agent.utils.extract_engineer_content", extract)
    monkeypatch.setattr(module, "extract_engineer_content", extract)
    monkeypatch.setattr(module, "write_file_atomic", lambda *a, **k: True)
    harness._select_engineer = lambda _path: _Engineer()

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_refactor_includes_upstream_context(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    graph.get_context_for_file = lambda *_a, **_k: "upstream body"
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")

    async def fake_call_llm(**_kwargs):
        return json.dumps({"new_files": [{"path": "app/part.py", "file_type": "utils"}]})

    captured = {}

    class _Engineer:
        async def generate_file(self, path, description, context, *_args, **_kwargs):
            captured["context"] = context
            return "x = 1\n"

    async def extract(content, *_args, **_kwargs):
        return content

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)
    monkeypatch.setattr("app.agent.utils.extract_engineer_content", extract)
    monkeypatch.setattr(module, "extract_engineer_content", extract)
    monkeypatch.setattr(module, "write_file_atomic", lambda *a, **k: True)
    harness._select_engineer = lambda _path: _Engineer()

    await harness.refactor_file("app/main.py", "拆分")

    assert "upstream body" in captured["context"]


@pytest.mark.asyncio
async def test_decision_questions_without_callback_uses_defaults(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    class _Decision:
        def extract_from_architecture(self, *_args):
            return []

        def format_as_questions(self):
            return [{"id": "auth_strategy"}]

        def apply_user_choice(self, *_args):
            raise AssertionError("should not be called without callback")

        def get_all_choices(self):
            return {}

        def skip_remaining_decisions(self):
            raise AssertionError("should not skip when questions exist")

    monkeypatch.setattr(module, "CriticalDecisionExtractor", _Decision)
    monkeypatch.setattr(module, "should_skip_user_decision", lambda *a, **k: False)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_dep_graph_issues_without_missing_files(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    graph = _graph_with(missing=[], completeness=[{"type": "noise"}])

    class _GraphFactory:
        @staticmethod
        def load(*_args, **_kwargs):
            return graph

        def __new__(cls, *_args, **_kwargs):
            return graph

    monkeypatch.setattr(module, "DependencyGraph", _GraphFactory)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_dynamic_quality_retry_succeeds_then_final_check_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )
    monkeypatch.setattr(module, "TopologyScheduler", lambda **_kwargs: scheduler)
    monkeypatch.setattr(
        "app.agent.utils.validate_content_quality", lambda *a, **k: "leak"
    )

    async def retry(*_args, **_kwargs):
        return "def retried():\n    return 1\n"

    harness._retry_generate_file = retry

    class _PropagatingScheduler(_RecordingScheduler):
        async def run(self, file_generator, _progress_report):
            for path in self.nodes:
                await file_generator(path, self.upstream, self.tracker)
            return {"failed_files": []}

    monkeypatch.setattr(
        module, "TopologyScheduler",
        lambda **_kwargs: _PropagatingScheduler(nodes=scheduler.nodes),
    )

    with pytest.raises(RuntimeError, match="content quality validation failed"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_dynamic_error_recovery_unsuccessful_falls_back_to_retry(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    outcomes = iter([False, True])

    async def validate_syntax(_path, _content):
        return next(outcomes, True)

    harness._validate_content_syntax = validate_syntax

    async def fix(**_kwargs):
        return False, ""

    harness.error_recovery = SimpleNamespace(validate_and_fix=fix)
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(harness, monkeypatch, scheduler=scheduler)

    assert result["files_generated"] == 1


@pytest.mark.asyncio
async def test_dynamic_duplicate_missing_on_disk_still_removed_from_context(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.engineer.content = "a = 1\n"
    ctx = _CtxStub(
        files={
            "app/main.py": SimpleNamespace(generated_by="engineer", file_type="entry"),
            "main.py": SimpleNamespace(generated_by="engineer", file_type="entry"),
        },
        contents={"app/main.py": "a = 1\n", "main.py": "a = 1\n"},
    )
    scheduler = _RecordingScheduler(
        nodes={"app/main.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    await _run_dynamic(harness, monkeypatch, ctx=ctx, scheduler=scheduler)

    assert "main.py" not in ctx.files


@pytest.mark.asyncio
async def test_dynamic_second_space_file_missing_on_disk_skips_rename(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    ctx = _CtxStub(
        files={
            "app/a b.py": SimpleNamespace(generated_by="engineer", file_type="entry"),
            "app/c d.py": SimpleNamespace(generated_by="engineer", file_type="entry"),
        },
        contents={"app/a b.py": "a = 1\n", "app/c d.py": "b = 2\n"},
    )
    scheduler = _RecordingScheduler(
        nodes={"app/a b.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(harness, monkeypatch, ctx=ctx, scheduler=scheduler)

    assert result["files_generated"] >= 1


def test_vue_with_script_is_validated():
    harness = _Harness(Path("/tmp"))
    result = asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(
            harness, "app/App.vue", "<template><div /></template><script>const a = 1</script>"
        )
    )
    assert result is True


def test_html_structure_is_validated():
    harness = _Harness(Path("/tmp"))
    result = asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(
            harness, "app/index.html", "<!DOCTYPE html><html><body><p>ok</p></body></html>"
        )
    )
    assert result is True


@pytest.mark.asyncio
async def test_fix_sandbox_errors_zero_rounds_returns_empty():
    harness = _Harness(Path("/tmp"))
    errors = ['app/main.py: ImportError: boo (File "app/main.py", line 1)']

    fixed = await harness._fix_sandbox_errors(
        errors, {"app/main.py": "import missing\n"}, SimpleNamespace(), max_rounds=0
    )

    assert fixed == []


@pytest.mark.asyncio
async def test_dynamic_renames_multiple_space_files_on_disk(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    for name in ("app/a b.py", "app/c d.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a = 1\n", encoding="utf-8")
    ctx = _CtxStub(
        files={
            "app/a b.py": SimpleNamespace(generated_by="engineer", file_type="entry"),
            "app/c d.py": SimpleNamespace(generated_by="engineer", file_type="entry"),
        },
        contents={"app/a b.py": "a = 1\n", "app/c d.py": "b = 2\n"},
    )
    scheduler = _RecordingScheduler(
        nodes={"app/a b.py": SimpleNamespace(file_type="entry", description="e", priority=3)}
    )

    result = await _run_dynamic(harness, monkeypatch, ctx=ctx, scheduler=scheduler)

    assert "app/ab.py" in ctx.files
    assert "app/cd.py" in ctx.files
    assert result["files_generated"] >= 1
