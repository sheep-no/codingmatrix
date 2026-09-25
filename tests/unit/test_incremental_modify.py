import asyncio
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


@pytest.mark.asyncio
async def test_generate_file_with_model_accepts_empty_dotfile(tmp_path, monkeypatch):
    """空 .gitkeep 提取到空字符串就是正确结果，不应触发恢复或重试。"""
    import app.agent.utils as agent_utils

    async def _empty_extract(*_args, **_kwargs):
        return ""

    monkeypatch.setattr(agent_utils, "extract_engineer_content", _empty_extract)

    class _Engineer:
        name = "engineer"

        async def generate_file(self, *_args, **_kwargs):
            return ""

    class _DepGraph:
        def get_context_for_file(self, *_args, **_kwargs):
            return {}

    class _Harness(IncrementalModifyMixin):
        def __init__(self, output_dir):
            self.output_dir = output_dir
            self._quick_llm_check = None

        def _report_model_info(self, *_args, **_kwargs):
            return None

        def _get_context_length(self, _model_name):
            return 8000

        def _emit_generated_file_events(self, *_args, **_kwargs):
            return None

        def _strip_output_dir_prefix(self, path):
            return path

    harness = _Harness(tmp_path)

    content = await harness._generate_file_with_model(
        "assets/.gitkeep",
        {"action": "add", "description": "empty placeholder"},
        _Engineer(),
        "test-model",
        {},
        {},
        None,
        _DepGraph(),
    )

    assert content == ""
    assert (tmp_path / "assets" / ".gitkeep").read_text(encoding="utf-8") == ""


# ---------- IM2: 端点"已满足"必须是真实路由注册 ----------

class _ContentCheckHarness(IncrementalModifyMixin):
    def __init__(self):
        pass


@pytest.mark.parametrize("content", [
    '# /health 端点待实现\n',
    'HEALTH_PATH = "/health"\n',
    'def describe():\n    return "添加 /health 端点"\n',
])
def test_content_satisfies_rejects_mere_keyword(content):
    harness = _ContentCheckHarness()
    assert harness._content_already_satisfies(
        content, "添加 /health 端点并返回数据库状态", "需求"
    ) is False


@pytest.mark.parametrize("content", [
    '@app.get("/health")\nasync def health():\n    return {"ok": True}\n',
    '@router.route("/health")\ndef health():\n    return "ok"\n',
    'app.add_url_rule("/health", view_func=health)\n',
])
def test_content_satisfies_accepts_registered_route(content):
    harness = _ContentCheckHarness()
    assert harness._content_already_satisfies(content, "添加 /health 端点", "需求") is True



def test_content_satisfies_requires_all_requested_endpoints():
    harness = _ContentCheckHarness()
    content = '@app.get("/health")\ndef health():\n    return "ok"\n'
    assert harness._content_already_satisfies(
        content, "添加 /health 与 /status 端点", "需求"
    ) is False


def test_content_satisfies_framework_only_reason_still_skips():
    harness = _ContentCheckHarness()
    content = "from fastapi import FastAPI\n"
    assert harness._content_already_satisfies(content, "接入 FastAPI", "需求") is True


# ---------- IM4: 非 Python 文件的 import 走语言适配器 ----------

def test_extract_imports_handles_javascript(tmp_path):
    harness = _ContentCheckHarness()
    harness.output_dir = tmp_path
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "utils.js").write_text("export const x = 1;\n", encoding="utf-8")

    imports = harness._extract_imports_from_content(
        "import { x } from './utils';\n", "src/main.js"
    )
    assert "src/utils.js" in imports


def test_extract_imports_handles_typescript_alias(tmp_path):
    harness = _ContentCheckHarness()
    harness.output_dir = tmp_path
    (tmp_path / "src" / "api").mkdir(parents=True)
    (tmp_path / "src" / "api" / "client.ts").write_text("export const c = 1;\n", encoding="utf-8")

    imports = harness._extract_imports_from_content(
        "import { c } from '@/api/client';\n", "src/view.ts"
    )
    assert "src/api/client.ts" in imports


def test_extract_imports_python_behavior_unchanged(tmp_path):
    harness = _ContentCheckHarness()
    harness.output_dir = tmp_path
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "utils.py").write_text("A = 1\n", encoding="utf-8")

    imports = harness._extract_imports_from_content(
        "from utils import A\n", "src/main.py"
    )
    assert "src/utils.py" in imports


# ---------- IM7: 增量生成接线心跳跟踪器 ----------

@pytest.mark.asyncio
async def test_incremental_wires_heartbeat_tracker(tmp_path):
    """IM7：tracker 参数此前恒为 None，现每个文件创建 HeartbeatTracker 并透传。"""
    from app.agent.dependency_graph import DependencyGraph
    from app.agent.topology_scheduler import HeartbeatTracker

    captured = []

    class _Harness(IncrementalModifyMixin):
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

        def _get_model_semaphore(self, _model_name):
            return asyncio.Semaphore(1)

        async def _generate_file_with_model(self, *args, **_kwargs):
            captured.append(args[9] if len(args) > 9 else _kwargs.get("tracker"))
            return "print('ok')\n"

    graph = DependencyGraph()
    graph.add_file("main.py")
    harness = _Harness(tmp_path)

    result = await harness._generate_with_dynamic_topology_incremental(
        ctx=None,
        dep_graph=graph,
        spec_generator=None,
        requirement="add entry",
        project_context={},
        generated_contents={},
        file_plan=[{"path": "main.py", "description": "entry", "action": "add"}],
    )

    assert result["files_generated"] == 1
    assert len(captured) == 1
    assert isinstance(captured[0], HeartbeatTracker)
