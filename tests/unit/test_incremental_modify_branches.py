import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.dependency_graph import DependencyGraph
from app.agent.orchestrator_generation.incremental_modify import IncrementalModifyMixin


def _write_graph(tmp_path, nodes=None, dependencies=None):
    nodes = nodes or {"main.py": {"type": "entry", "priority": 1, "description": "entry"}}
    graph = {
        "nodes": nodes,
        "dependencies": dependencies or {},
        "generation_order": list(nodes),
    }
    (tmp_path / ".dep_graph.json").write_text(json.dumps(graph), encoding="utf-8")


class _Harness(IncrementalModifyMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.complexity = None
        self.session_id = "sess"
        self.api_key_token = None
        self.generated_files = []
        self.errors = []
        self.warnings = []
        self.plans = []
        self.topology_result = {
            "files_generated": 0,
            "files_failed": 0,
            "generated_files": [],
            "errors": [],
            "warnings": [],
        }
        self.updated_graphs = []
        self.initialized = False

    async def _initialize_components_fast(self, requirement):
        self.initialized = True

    def _report_progress(self, *args, **kwargs):
        return None

    async def _analyze_changes_with_architect(self, requirement, summary, graph, callback):
        return self.plans

    async def _generate_with_dynamic_topology_incremental(self, *args, **kwargs):
        return self.topology_result

    async def _update_dependency_graph_incremental(self, graph, contents, adapter):
        self.updated_graphs.append(dict(contents))


@pytest.fixture(autouse=True)
def _stub_enrich(monkeypatch):
    monkeypatch.setattr(DependencyGraph, "enrich_and_save", lambda self, *a, **k: None)

    class _SpecStub:
        def __init__(self, *args, **kwargs):
            pass

        @staticmethod
        def get_spec_budget(context_length):
            return 1000

        def get_spec_context_for_file(self, *args, **kwargs):
            return {}

    monkeypatch.setattr(
        "app.agent.spec_first_generator.SpecFirstGenerator", _SpecStub
    )


@pytest.mark.asyncio
async def test_generate_incremental_add_modify_delete(tmp_path):
    _write_graph(
        tmp_path,
        nodes={
            "main.py": {"type": "entry", "priority": 1, "description": "entry"},
            "old.py": {"type": "utils", "priority": 3, "description": "old"},
        },
    )
    (tmp_path / "main.py").write_text("print('old')\n", encoding="utf-8")
    (tmp_path / "old.py").write_text("gone\n", encoding="utf-8")
    harness = _Harness(tmp_path)
    harness.plans = [
        {"action": "modify", "path": "main.py", "reason": "调整"},
        {"action": "add", "path": "new.py", "description": "new"},
        {"action": "delete", "path": "old.py"},
    ]
    harness.topology_result = {
        "files_generated": 2,
        "files_failed": 0,
        "generated_files": [{"path": "main.py"}, {"path": "new.py"}],
        "errors": [],
        "warnings": ["w"],
    }

    result = await harness.generate_incremental("add shout")

    assert harness.initialized is True
    assert result["success"] is True
    assert result["changes"] == {"added": 1, "modified": 1, "deleted": 1}
    assert result["total_files"] == 2
    assert not (tmp_path / "old.py").exists()
    assert harness.warnings == ["w"]
    assert harness.updated_graphs


@pytest.mark.asyncio
async def test_generate_incremental_adds_missing_modify_node_to_graph(tmp_path):
    _write_graph(tmp_path)
    (tmp_path / "missing.py").write_text("x\n", encoding="utf-8")
    harness = _Harness(tmp_path)
    harness.plans = [{"action": "modify", "path": "missing.py", "reason": "调整"}]
    harness.topology_result = {
        "files_generated": 1,
        "files_failed": 0,
        "generated_files": [{"path": "missing.py"}],
        "errors": [],
        "warnings": [],
    }

    result = await harness.generate_incremental("update")

    assert result["success"] is True
    assert result["total_files"] == 1


@pytest.mark.asyncio
async def test_generate_incremental_existing_add_and_missing_modify_file(tmp_path):
    _write_graph(tmp_path)
    harness = _Harness(tmp_path)
    harness.plans = [
        {"action": "add", "path": "main.py", "description": "already present"},
        {"action": "modify", "path": "absent.py", "reason": "调整"},
    ]
    harness.topology_result = {
        "files_generated": 2,
        "files_failed": 0,
        "generated_files": [],
        "errors": [],
        "warnings": [],
    }

    result = await harness.generate_incremental("update")

    assert result["total_files"] == 2


@pytest.mark.asyncio
async def test_generate_incremental_with_complexity(tmp_path):
    _write_graph(tmp_path)
    harness = _Harness(tmp_path)
    harness.complexity = SimpleNamespace(
        level=SimpleNamespace(value="medium"),
        estimated_files=3,
        has_frontend=True,
        has_backend=True,
        has_database=False,
        key_technologies=["FastAPI"],
    )
    harness.plans = [{"action": "add", "path": "new.py"}]

    result = await harness.generate_incremental("add")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_generate_incremental_skips_already_satisfied_modify(tmp_path):
    _write_graph(tmp_path)
    (tmp_path / "main.py").write_text(
        '@app.get("/health")\ndef health():\n    return "ok"\n', encoding="utf-8"
    )
    harness = _Harness(tmp_path)
    harness.plans = [{"action": "modify", "path": "main.py", "reason": "添加 /health 端点"}]

    result = await harness.generate_incremental("add health")

    assert result["success"] is True
    assert result["total_files"] == 0


@pytest.mark.asyncio
async def test_generate_incremental_skips_empty_modify_path(tmp_path):
    _write_graph(tmp_path)
    harness = _Harness(tmp_path)
    harness.plans = [{"action": "modify", "path": ""}]

    result = await harness.generate_incremental("noop")

    assert result["total_files"] == 0


@pytest.mark.asyncio
async def test_generate_incremental_delete_missing_file_and_node(tmp_path):
    _write_graph(tmp_path)
    harness = _Harness(tmp_path)
    harness.plans = [{"action": "delete", "path": "ghost.py"}, {"action": "delete", "path": ""}]

    result = await harness.generate_incremental("cleanup")

    assert result["total_files"] == 0


@pytest.mark.asyncio
async def test_generate_incremental_adds_profile_components(tmp_path, monkeypatch):
    _write_graph(tmp_path)
    harness = _Harness(tmp_path)
    harness.plans = [{"action": "modify", "path": "main.py", "reason": "调整"}]
    (tmp_path / "main.py").write_text("x\n", encoding="utf-8")

    class _Item:
        path = "extra.py"
        role = "extra component"
        file_type = "config"
        priority = 2
        dependencies = ("main.py",)

    class _Plan:
        files = [_Item()]

        def model_dump(self, mode="json"):
            return {"files": []}

    monkeypatch.setattr(
        "app.agent.orchestrator_generation.incremental_modify.add_profile_components",
        lambda *a, **k: _Plan(),
    )

    result = await harness.generate_incremental("add")

    assert result["success"] is True
    assert result["changes"]["added"] == 1


@pytest.mark.asyncio
async def test_generate_incremental_raises_on_failures(tmp_path):
    _write_graph(tmp_path)
    (tmp_path / "main.py").write_text("x\n", encoding="utf-8")
    harness = _Harness(tmp_path)
    harness.plans = [{"action": "modify", "path": "main.py", "reason": "调整"}]
    harness.topology_result = {
        "files_generated": 0,
        "files_failed": 1,
        "generated_files": [],
        "errors": ["文件生成失败: main.py"],
        "warnings": [],
    }

    with pytest.raises(RuntimeError, match="incremental file generation failed"):
        await harness.generate_incremental("broken")


@pytest.mark.asyncio
async def test_generate_incremental_failure_uses_baseline_errors(tmp_path):
    _write_graph(tmp_path)
    (tmp_path / "main.py").write_text("x\n", encoding="utf-8")
    harness = _Harness(tmp_path)
    harness.errors = ["pre-existing"]
    harness.plans = [{"action": "modify", "path": "main.py", "reason": "调整"}]
    harness.topology_result = {
        "files_generated": 0,
        "files_failed": 1,
        "generated_files": [],
        "errors": ["other failure"],
        "warnings": [],
    }

    with pytest.raises(RuntimeError, match="other failure"):
        await harness.generate_incremental("broken")


class _ArchitectHarness(IncrementalModifyMixin):
    def __init__(self, output_dir, architect):
        self.output_dir = output_dir
        self.architect = architect
        self.progress = []

    def _report_progress(self, *args, **kwargs):
        self.progress.append((args, kwargs))


@pytest.mark.asyncio
async def test_analyze_changes_returns_cached_plan(tmp_path):
    harness = _ArchitectHarness(tmp_path, architect=None)
    plan = [{"action": "add", "path": "x.py"}]
    key_input = f"req:summary"
    import hashlib

    key = hashlib.sha256(key_input.encode()).hexdigest()
    harness._save_cached_change_plan(key, plan)

    result = await harness._analyze_changes_with_architect("req", "summary", DependencyGraph())

    assert result == plan
    assert harness.progress[0][0][0] == "architect_cache_hit"


@pytest.mark.asyncio
async def test_analyze_changes_parses_json_and_collapses(tmp_path):
    class _Architect:
        async def call_llm(self, prompt, system_prompt=None):
            return """```json
[
  {"action": "add", "path": "a.py", "description": "a"},
  {"action": "add", "path": "a.py", "description": "dup"},
  {"action": "add", "path": "b.py"}
]
```"""

    harness = _ArchitectHarness(tmp_path, _Architect())
    graph = DependencyGraph()
    graph.add_file("a.py")

    result = await harness._analyze_changes_with_architect("req", "summary", graph)

    paths = [item["path"] for item in result]
    assert paths.count("a.py") == 1
    assert "b.py" in paths


@pytest.mark.asyncio
async def test_analyze_changes_rejects_non_array(tmp_path):
    class _Architect:
        async def call_llm(self, prompt, system_prompt=None):
            return '{"not": "array"}'

    harness = _ArchitectHarness(tmp_path, _Architect())

    with pytest.raises(ValueError, match="not a JSON array"):
        await harness._analyze_changes_with_architect("req", "summary", DependencyGraph())


@pytest.mark.asyncio
async def test_analyze_changes_propagates_architect_error(tmp_path):
    class _Architect:
        async def call_llm(self, prompt, system_prompt=None):
            raise RuntimeError("llm down")

    harness = _ArchitectHarness(tmp_path, _Architect())

    with pytest.raises(RuntimeError, match="llm down"):
        await harness._analyze_changes_with_architect("req", "summary", DependencyGraph())


def test_get_cached_change_plan_returns_none_without_file(tmp_path):
    harness = _ArchitectHarness(tmp_path, architect=None)

    assert harness._get_cached_change_plan("missing") is None


def test_get_cached_change_plan_expired_entry(tmp_path):
    harness = _ArchitectHarness(tmp_path, architect=None)
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    (cache_dir / "change_plans.json").write_text(
        json.dumps({"k": {"plan": [{"action": "add", "path": "x"}], "timestamp": time.time() - 90000}}),
        encoding="utf-8",
    )

    assert harness._get_cached_change_plan("k") is None


def test_get_cached_change_plan_missing_key(tmp_path):
    harness = _ArchitectHarness(tmp_path, architect=None)
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    (cache_dir / "change_plans.json").write_text(
        json.dumps({"other": {"plan": [], "timestamp": time.time()}}),
        encoding="utf-8",
    )

    assert harness._get_cached_change_plan("k") is None


def test_get_cached_change_plan_corrupt_file(tmp_path):
    harness = _ArchitectHarness(tmp_path, architect=None)
    cache_dir = tmp_path / ".cache"
    cache_dir.mkdir()
    (cache_dir / "change_plans.json").write_text("{not json", encoding="utf-8")

    assert harness._get_cached_change_plan("k") is None


def test_save_cached_change_plan_swallows_errors(tmp_path, monkeypatch):
    harness = _ArchitectHarness(tmp_path, architect=None)
    warnings = []
    monkeypatch.setattr(
        "app.agent.orchestrator_generation.incremental_modify.logger",
        SimpleNamespace(warning=warnings.append, info=lambda *a, **k: None, debug=lambda *a, **k: None, error=lambda *a, **k: None),
    )

    def boom(*_a, **_k):
        raise OSError("readonly")

    monkeypatch.setattr(Path, "mkdir", boom)

    harness._save_cached_change_plan("k", [])

    assert warnings


def test_finalize_change_plan_collapses_duplicates(tmp_path):
    harness = _ArchitectHarness(tmp_path, architect=None)
    graph = DependencyGraph()
    graph.add_file("a.py")

    result = harness._finalize_change_plan(
        [
            {"action": "modify", "path": "a.py", "reason": "one"},
            {"action": "modify", "path": "a.py", "reason": "two"},
        ],
        graph,
    )

    assert [item["path"] for item in result].count("a.py") == 1


class _TopologyHarness(IncrementalModifyMixin):
    def __init__(self, output_dir, result="print('ok')\n"):
        self.output_dir = output_dir
        self.cancel_event = None
        self.errors = []
        self.warnings = []
        self.result = result
        self.calls = []

    def _report_progress(self, *args, **kwargs):
        return None

    def _select_engineer(self, path):
        return object()

    def _select_model_for_file(self, path):
        return "model"

    def _get_model_semaphore(self, model):
        return asyncio.Semaphore(1)

    async def _generate_file_with_model(self, *args, **kwargs):
        self.calls.append((args[0], kwargs.get("tracker")))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@pytest.mark.asyncio
async def test_topology_generates_files_and_tracks_cancel(tmp_path):
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.add_file("b.py")
    graph.add_dependency("b.py", "a.py")
    harness = _TopologyHarness(tmp_path)
    harness.cancel_event = asyncio.Event()

    async def _generate(*args, **kwargs):
        harness.calls.append((args[0], kwargs.get("tracker")))
        harness.cancel_event.set()
        return "print('ok')\n"

    harness._generate_file_with_model = _generate

    result = await harness._generate_with_dynamic_topology_incremental(
        None, graph, None, "req", {}, {},
        [{"path": "a.py"}, {"path": "b.py", "action": "modify"}],
    )

    assert result["files_generated"] == 1
    assert result["generated_files"][0]["path"] == "a.py"
    assert len(harness.calls) == 1


@pytest.mark.asyncio
async def test_topology_skips_layers_outside_plan(tmp_path):
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.add_file("b.py")
    harness = _TopologyHarness(tmp_path)

    result = await harness._generate_with_dynamic_topology_incremental(
        None, graph, None, "req", {}, {}, [{"path": "b.py"}],
    )

    assert result["files_generated"] == 1
    assert [call[0] for call in harness.calls] == ["b.py"]


@pytest.mark.asyncio
async def test_topology_skips_empty_layers(tmp_path, monkeypatch):
    graph = DependencyGraph()
    graph.add_file("a.py")

    class _GraphStub:
        def get_generation_layers(self):
            return [[], ["a.py"]]

    harness = _TopologyHarness(tmp_path)
    result = await harness._generate_with_dynamic_topology_incremental(
        None, _GraphStub(), None, "req", {}, {}, [{"path": "a.py"}],
    )

    assert result["files_generated"] == 1


@pytest.mark.asyncio
async def test_topology_cancelled_result_counts_as_failure(tmp_path):
    graph = DependencyGraph()
    graph.add_file("a.py")
    harness = _TopologyHarness(tmp_path, result=asyncio.CancelledError())

    with pytest.raises(RuntimeError, match="a.py"):
        await harness._generate_with_dynamic_topology_incremental(
            None, graph, None, "req", {}, {}, [{"path": "a.py"}],
        )


@pytest.mark.asyncio
async def test_topology_empty_result_counts_as_failure(tmp_path):
    graph = DependencyGraph()
    graph.add_file("a.py")
    harness = _TopologyHarness(tmp_path, result="")

    with pytest.raises(RuntimeError, match="a.py"):
        await harness._generate_with_dynamic_topology_incremental(
            None, graph, None, "req", {}, {}, [{"path": "a.py"}],
        )


def test_get_context_length_fallback_on_error(monkeypatch):
    harness = _ContentHarness()

    assert harness._get_context_length("m") == 32768


def test_get_context_length_success(monkeypatch):
    import sys
    from types import ModuleType

    module = ModuleType("app.agent.context_budget")
    module.get_context_length = lambda model: 4096
    monkeypatch.setitem(sys.modules, "app.agent.context_budget", module)

    assert _ContentHarness()._get_context_length("m") == 4096


@pytest.mark.asyncio
async def test_initialize_components_fast_success(tmp_path, monkeypatch):
    created = {}

    class _Assignment:
        architect_model = "arch"
        frontend_model = "front"
        backend_model = "back"

    class _Router:
        def get_assignment(self):
            return _Assignment()

    class _Specialist:
        def __init__(self, name, model, **kwargs):
            created[name] = (model, kwargs)

    class _Harness(IncrementalModifyMixin):
        def __init__(self):
            self.api_key_token = "token"
            self.provider_id = "provider"
            self.cancel_event = None

        def _update_phase(self, phase):
            self.phase = phase

    monkeypatch.setattr("app.agent.dynamic_model_router.LayeredModelRouter", _Router)
    monkeypatch.setattr(
        "app.agent.specialist_base.get_global_llm_semaphore", lambda: "sem"
    )
    monkeypatch.setattr("app.agent.specialists.Architect", _Specialist)
    monkeypatch.setattr("app.agent.specialists.FrontendEngineer", _Specialist)
    monkeypatch.setattr("app.agent.specialists.BackendEngineer", _Specialist)

    harness = _Harness()
    await harness._initialize_components_fast("req")

    assert harness.phase == "analyzing"
    assert created["架构师"][0] == "arch"
    assert created["前端工程师"][0] == "front"
    assert created["后端工程师"][0] == "back"


def test_is_simple_change_complex_and_simple_keywords():
    harness = _ContentHarness()

    assert harness._is_simple_change({"action": "add", "description": "重构模块"}) is False
    assert harness._is_simple_change({"action": "modify", "reason": "add endpoint"}) is True


def test_extract_imports_empty_content():
    assert _ContentHarness()._extract_imports_from_content("", "main.py") == []


def test_get_relative_file_paths_skips_outside(tmp_path):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    inside = tmp_path / "a.py"
    inside.write_text("x\n", encoding="utf-8")
    outside = tmp_path.parent / "outside.py"
    outside.write_text("x\n", encoding="utf-8")
    harness._get_all_file_paths = lambda: {inside, outside}

    assert harness._get_relative_file_paths() == {"a.py"}


def test_emit_generated_file_events_empty_content_noop():
    harness = _FileEvents()

    harness._emit_generated_file_events("a.py", "", {})

    assert harness.events == []


def test_emit_generated_file_events_invokes_callable_diff(monkeypatch):
    harness = _ContentHarness()
    calls = []
    harness._report_file_event = lambda *a, **k: calls.append("file")
    harness._report_file_diff_event = lambda *a, **k: calls.append("diff")

    harness._emit_generated_file_events("a.py", "new", {"action": "modify"}, "old")

    assert calls == ["file", "diff"]


def test_emit_generated_file_events_ignores_non_callable_reporters():
    harness = _ContentHarness()
    harness._report_file_event = None
    harness._report_file_diff_event = None

    harness._emit_generated_file_events("a.py", "new", {"action": "modify"}, "old")


class _ContentHarness(IncrementalModifyMixin):
    pass


class _FileEvents(IncrementalModifyMixin):
    def __init__(self):
        self.events = []


def test_extract_python_imports_relative(tmp_path):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "util.py").write_text("x = 1\n", encoding="utf-8")

    imports = harness._extract_python_imports(
        "from .util import x\n", "pkg/main.py"
    )

    assert imports == ["pkg/util.py"]


def test_extract_python_imports_absolute_init(tmp_path):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "pkg.py").write_text("x = 1\n", encoding="utf-8")

    assert harness._extract_python_imports("from pkg import x\n", "main.py") == ["src/pkg.py"]


def test_extract_python_imports_unresolved(tmp_path):
    harness = _ContentHarness()
    harness.output_dir = tmp_path

    assert harness._extract_python_imports("from missing import x\n", "main.py") == []
    assert harness._extract_python_imports("import os\n", "main.py") == []


def test_extract_python_imports_edge_syntax(tmp_path):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "other.py").write_text("x = 1\n", encoding="utf-8")

    assert harness._extract_python_imports("from . import x\n", "pkg/main.py") == []
    assert harness._extract_python_imports("from .missing import x\n", "pkg/main.py") == []
    assert harness._extract_python_imports("from  import x\n", "main.py") == []


def test_extract_imports_via_adapter_without_adapter(tmp_path, monkeypatch):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    monkeypatch.setattr(
        "app.agent.adapters.LanguageAdapterRegistry.get_adapter_for_file",
        lambda path: None,
    )

    assert harness._extract_imports_via_adapter("x", "main.js") == []


def test_extract_imports_via_adapter_dedupes_and_skips(tmp_path, monkeypatch):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.ts").write_text("x\n", encoding="utf-8")

    class _Adapter:
        def parse_imports(self, content, path):
            return [object(), object()]

        def resolve_import_to_file(self, info, path):
            return ["", "../outside", "a/b.ts", "a/b.ts"]

    monkeypatch.setattr(
        "app.agent.adapters.LanguageAdapterRegistry.get_adapter_for_file",
        lambda path: _Adapter(),
    )

    assert harness._extract_imports_via_adapter("x", "main.ts") == ["a/b.ts"]


def test_extract_imports_via_adapter_candidate_not_in_project(tmp_path, monkeypatch):
    harness = _ContentHarness()
    harness.output_dir = tmp_path

    class _Adapter:
        def parse_imports(self, content, path):
            return [object()]

        def resolve_import_to_file(self, info, path):
            return ["missing.ts"]

    monkeypatch.setattr(
        "app.agent.adapters.LanguageAdapterRegistry.get_adapter_for_file",
        lambda path: _Adapter(),
    )

    assert harness._extract_imports_via_adapter("x", "main.ts") == []


def test_get_all_file_paths_swallows_errors():
    harness = _ContentHarness()
    harness.output_dir = SimpleNamespace(rglob=lambda pattern: (_ for _ in ()).throw(OSError("bad")))

    assert harness._get_all_file_paths() == set()


@pytest.mark.parametrize(
    ("content", "reason", "expected"),
    [
        ("", "reason", False),
        ("x", "", False),
        ('@app.get("/health")\n', "添加文件说明", False),
        ('@app.get("/status")\n', "添加 /status", True),
        ('@app.get("/api/v1")\n', "添加 /api 端点", False),
        ("from fastapi import FastAPI\n", "接入 FastAPI", True),
        ("from flask import Flask\n", "迁移 Flask", True),
        ("x = 1\n", "unrelated", False),
    ],
)
def test_content_already_satisfies_branches(content, reason, expected):
    harness = _ContentHarness()

    assert harness._content_already_satisfies(content, reason, "req") is expected


def test_route_registered_flat_decorator():
    harness = _ContentHarness()

    assert harness._route_registered('@router.get("/health")', "/health") is True
    assert harness._route_registered('router.route("/health")', "/health") is False
    assert harness._route_registered("no route", "/health") is False


@pytest.mark.asyncio
async def test_update_dependency_graph_skips_empty_and_handles_layers(tmp_path):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    graph = DependencyGraph()
    graph.add_file("a.py")
    graph.add_file("c.py")
    harness._extract_imports_from_content = lambda content, path: ["c.py"]

    await harness._update_dependency_graph_incremental(
        graph, {"a.py": "", "b.py": "from c import x"}, None
    )

    assert "c.py" in graph.adjacency.get("b.py", set())


@pytest.mark.asyncio
async def test_update_dependency_graph_swallows_layer_errors(tmp_path, monkeypatch):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    graph = DependencyGraph()
    graph.add_file("a.py")
    warnings = []
    monkeypatch.setattr(
        "app.agent.orchestrator_generation.incremental_modify.logger",
        SimpleNamespace(warning=warnings.append, info=lambda *a, **k: None, debug=lambda *a, **k: None, error=lambda *a, **k: None),
    )

    def boom():
        raise RuntimeError("cycle")

    monkeypatch.setattr(graph, "get_generation_layers", boom)
    harness._extract_imports_from_content = lambda content, path: []

    await harness._update_dependency_graph_incremental(graph, {"a.py": "x"}, None)

    assert warnings


@pytest.mark.asyncio
async def test_update_dependency_graph_skips_unknown_imports(tmp_path):
    harness = _ContentHarness()
    harness.output_dir = tmp_path
    graph = DependencyGraph()
    graph.add_file("a.py")
    harness._extract_imports_from_content = lambda content, path: ["ghost.py"]

    await harness._update_dependency_graph_incremental(graph, {"a.py": "x"}, None)

    assert "ghost.py" not in graph.adjacency.get("a.py", set())


class _FileHarness(IncrementalModifyMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self._quick_llm_check = None
        self.engineer_calls = []

    def _report_model_info(self, *args, **kwargs):
        return None

    def _get_context_length(self, model):
        return 8000

    def _emit_generated_file_events(self, *args, **kwargs):
        return None

    def _strip_output_dir_prefix(self, path):
        return path

    async def _recover_invalid_content(self, *args, **kwargs):
        return kwargs.pop("recover_result", self.recover_result)

    async def _retry_generate_file(self, *args, **kwargs):
        return self.retry_result


class _Engineer:
    name = "engineer"

    def __init__(self, content="print('ok')\n"):
        self.content = content
        self.kwargs = None

    async def generate_file(self, *args, **kwargs):
        self.kwargs = kwargs
        return self.content


class _Spec:
    def get_spec_context_for_file(self, *args, **kwargs):
        return {"spec": "x"}


class _Graph:
    language_adapter = None

    def get_context_for_file(self, *args, **kwargs):
        return {}


@pytest.mark.asyncio
async def test_generate_file_modify_with_spec_and_no_persist(tmp_path, monkeypatch):
    import app.agent.utils as agent_utils

    async def passthrough(content, *args, **kwargs):
        return content

    monkeypatch.setattr(agent_utils, "extract_engineer_content", passthrough)
    engineer = _Engineer()
    harness = _FileHarness(tmp_path)

    result = await harness._generate_file_with_model(
        "main.py",
        {"action": "modify", "original_content": "old\n", "reason": "调整", "file_type": "entry"},
        engineer,
        "model",
        {"architecture": {"language": "python"}},
        {"up.py": "print(1)\n"},
        _Spec(),
        _Graph(),
        persist=False,
    )

    assert result == "print('ok')\n"
    assert engineer.kwargs["is_existing_file"] is True
    assert not (tmp_path / "main.py").exists()


@pytest.mark.asyncio
async def test_generate_file_recovers_invalid_content(tmp_path, monkeypatch):
    import app.agent.utils as agent_utils

    async def empty_extract(*args, **kwargs):
        return ""

    monkeypatch.setattr(agent_utils, "extract_engineer_content", empty_extract)
    monkeypatch.setattr(agent_utils, "is_valid_code_content", lambda path, raw: (False, "invalid"))
    monkeypatch.setattr(agent_utils, "is_package_entry_file", lambda path: False)
    monkeypatch.setattr(agent_utils, "is_metadata_file", lambda path: False)
    harness = _FileHarness(tmp_path)
    harness.recover_result = "recovered content\n"
    harness.retry_result = None

    result = await harness._generate_file_with_model(
        "main.py", {"action": "add"}, _Engineer("bad"), "model", {}, {},
        None, _Graph(),
    )

    assert result == "recovered content\n"
    assert (tmp_path / "main.py").read_text(encoding="utf-8") == "recovered content\n"


@pytest.mark.asyncio
async def test_generate_file_retries_when_recovery_fails(tmp_path, monkeypatch):
    import app.agent.utils as agent_utils

    async def empty_extract(*args, **kwargs):
        return "   "

    monkeypatch.setattr(agent_utils, "extract_engineer_content", empty_extract)
    monkeypatch.setattr(agent_utils, "is_valid_code_content", lambda path, raw: (False, ""))
    monkeypatch.setattr(agent_utils, "is_placeholder_content", lambda raw, path: (True, "placeholder"))
    monkeypatch.setattr(agent_utils, "is_package_entry_file", lambda path: False)
    monkeypatch.setattr(agent_utils, "is_metadata_file", lambda path: False)
    harness = _FileHarness(tmp_path)
    harness.recover_result = None
    harness.retry_result = "retried content\n"

    result = await harness._generate_file_with_model(
        "main.py", {"action": "add"}, _Engineer("bad"), "model", {}, {},
        None, _Graph(),
    )

    assert result == "retried content\n"


@pytest.mark.asyncio
async def test_generate_file_raises_when_retry_fails(tmp_path, monkeypatch):
    import app.agent.utils as agent_utils

    async def empty_extract(*args, **kwargs):
        return None

    monkeypatch.setattr(agent_utils, "extract_engineer_content", empty_extract)
    monkeypatch.setattr(agent_utils, "is_valid_code_content", lambda path, raw: (False, ""))
    monkeypatch.setattr(agent_utils, "is_placeholder_content", lambda raw, path: (False, ""))
    monkeypatch.setattr(agent_utils, "is_package_entry_file", lambda path: False)
    monkeypatch.setattr(agent_utils, "is_metadata_file", lambda path: False)
    harness = _FileHarness(tmp_path)
    harness.recover_result = None
    harness.retry_result = None

    with pytest.raises(ValueError, match="文件生成失败"):
        await harness._generate_file_with_model(
            "main.py", {"action": "add"}, _Engineer("bad"), "model", {}, {},
            None, _Graph(),
        )


@pytest.mark.asyncio
async def test_generate_file_awaits_coroutine_result(tmp_path, monkeypatch):
    import app.agent.utils as agent_utils

    async def extract(content, *args, **kwargs):
        return content

    monkeypatch.setattr(agent_utils, "extract_engineer_content", extract)

    async def coroutine_content():
        return "value\n"

    harness = _FileHarness(tmp_path)
    result = await harness._generate_file_with_model(
        "main.py", {"action": "add"}, _Engineer(coroutine_content()), "model", {}, {},
        None, _Graph(),
    )

    assert result == "value\n"


def test_get_model_semaphore_caches_per_model():
    harness = _ContentHarness()

    first = harness._get_model_semaphore("a")
    assert harness._get_model_semaphore("a") is first
    assert harness._get_model_semaphore("b") is not first
