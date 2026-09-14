import inspect
from pathlib import Path

import json

import pytest

from app.agent.generation_plan import add_profile_components
from app.agent.orchestrator_files import FilesMixin
from app.agent.orchestrator_generation.incremental_modify import IncrementalModifyMixin


def test_select_engineer_does_not_accept_force_model():
    params = inspect.signature(FilesMixin._select_engineer).parameters
    assert "force_model" not in params


def test_simple_change_does_not_pass_force_model():
    source = Path("app/agent/orchestrator_generation/incremental_modify.py").read_text(encoding="utf-8")
    assert "force_model=" not in source
    assert "_retry_with_fallback_model" not in source
    assert "简单变更，使用轻量模型" not in source
    assert "DEFAULT_FAST_MODEL" not in source
    assert "DEFAULT_ARCHITECT_MODEL" not in source
    assert "DEFAULT_CODE_MODEL" not in source
    assert "model assignment is required to initialize incremental components" in source


def test_incremental_strict_plan_keeps_architect_files_only():
    context = {"capability_policy": {"component_file_plan": [
        {"path": "app/command.py", "component": "command"},
    ]}}
    change_plan = [
        {"action": "modify", "path": "greet.py", "reason": "add whisper"},
        {"action": "modify", "path": "main.py", "reason": "import whisper"},
    ]
    plan = add_profile_components(
        [change for change in change_plan if change.get("path")],
        context,
        policy="strict",
        requested_paths=[change["path"] for change in change_plan],
    )
    assert {item.path for item in plan.files} == {"greet.py", "main.py"}


def test_add_action_is_simple_change():
    mixin = IncrementalModifyMixin()
    assert mixin._is_simple_change({"action": "add", "path": "app/command.py"}) is True
    assert mixin._is_simple_change({"action": "modify", "path": "greet.py", "reason": "add whisper"}) is False


class _FileEventHarness(IncrementalModifyMixin):
    def __init__(self):
        self.file_events = []
        self.diff_events = []

    def _report_file_event(self, *args, **kwargs):
        self.file_events.append((args, kwargs))

    def _report_file_diff_event(self, *args, **kwargs):
        self.diff_events.append((args, kwargs))


def test_legacy_incremental_emits_file_and_diff_events():
    harness = _FileEventHarness()
    original = "def greet(name):\n    return f'Hello, {name}'\n"
    updated = original + "\ndef whisper(name):\n    return f'Hello, {name}...'\n"
    harness._emit_generated_file_events(
        "greet.py",
        updated,
        {"action": "modify", "reason": "add whisper", "file_type": "utils"},
        original,
    )
    assert harness.file_events == [
        (("greet.py", updated, "add whisper", "utils"), {"operation": "modify"}),
    ]
    assert harness.diff_events == [
        (("greet.py", original, updated), {"operation": "modify"}),
    ]


def test_legacy_incremental_skips_diff_when_content_unchanged():
    harness = _FileEventHarness()
    content = "print('hello')\n"
    harness._emit_generated_file_events(
        "main.py",
        content,
        {"action": "add", "description": "entry", "file_type": "entry"},
        "",
    )
    assert harness.file_events == [
        (("main.py", content, "entry", "entry"), {"operation": "create"}),
    ]
    assert harness.diff_events == []


class _IncrementalFailLoudHarness(IncrementalModifyMixin):
    def __init__(self, output_dir):
        self.output_dir = output_dir
        self.generated_files = []
        self.errors = []
        self.warnings = []
        self.complexity = None
        self.session_id = "test-session"
        self.api_key_token = None
        self.cancel_event = None
        self.spec_first_calls = 0

    async def _initialize_components_fast(self, requirement):
        return None

    def _report_progress(self, *args, **kwargs):
        return None

    async def generate_with_spec_first(self, requirement, callback=None):
        self.spec_first_calls += 1
        raise AssertionError("incremental modify must not fall back to full generation")


@pytest.mark.asyncio
async def test_incremental_raises_without_dependency_graph(tmp_path):
    harness = _IncrementalFailLoudHarness(tmp_path)
    with pytest.raises(RuntimeError, match="dependency graph"):
        await harness.generate_incremental("add shout")
    assert harness.spec_first_calls == 0


@pytest.mark.asyncio
async def test_incremental_empty_change_plan_returns_without_regenerating(tmp_path):
    (tmp_path / "main.py").write_text("print('hello')\n", encoding="utf-8")
    (tmp_path / ".dep_graph.json").write_text(json.dumps({
        "nodes": {"main.py": {"type": "entry", "priority": 1, "description": "entry"}},
        "dependencies": {},
        "generation_order": ["main.py"],
    }), encoding="utf-8")

    harness = _IncrementalFailLoudHarness(tmp_path)

    async def empty_plan(*_args, **_kwargs):
        return []

    harness._analyze_changes_with_architect = empty_plan
    result = await harness.generate_incremental("do nothing")

    assert result["success"] is True
    assert result["total_files_created"] == 0
    assert harness.spec_first_calls == 0


@pytest.mark.asyncio
async def test_incremental_topology_failure_raises_without_weaker_retry(tmp_path):
    from app.agent.dependency_graph import DependencyGraph

    class _TopologyHarness(IncrementalModifyMixin):
        def __init__(self, output_dir):
            self.output_dir = output_dir
            self.cancel_event = None
            self.errors = []
            self.warnings = []

        def _report_progress(self, *_args, **_kwargs):
            return None

        def _select_engineer(self, _path):
            return object()

        def _select_model_for_file(self, _path):
            return "test-model"

        def _is_simple_change(self, _info):
            return False

        async def _generate_file_with_model(self, *_args, **_kwargs):
            raise RuntimeError("engineer failed")

    graph = DependencyGraph()
    graph.add_file("main.py")
    harness = _TopologyHarness(tmp_path)

    with pytest.raises(RuntimeError, match="incremental file generation failed"):
        await harness._generate_with_dynamic_topology_incremental(
            ctx=None,
            dep_graph=graph,
            spec_generator=None,
            requirement="add shout",
            project_context={},
            generated_contents={},
            file_plan=[{"path": "main.py", "description": "entry", "action": "add"}],
        )


@pytest.mark.asyncio
async def test_initialize_components_fast_requires_assignment(monkeypatch):
    class _Harness(IncrementalModifyMixin):
        def __init__(self):
            self.api_key_token = None
            self.provider_id = None
            self.cancel_event = None
            self.cost_tracker = None

        def _update_phase(self, phase):
            self.phase = phase

    class _Router:
        def get_assignment(self):
            return None

    monkeypatch.setattr(
        "app.agent.dynamic_model_router.LayeredModelRouter",
        lambda: _Router(),
    )
    with pytest.raises(RuntimeError, match="model assignment is required to initialize incremental components"):
        await _Harness()._initialize_components_fast("add shout")
