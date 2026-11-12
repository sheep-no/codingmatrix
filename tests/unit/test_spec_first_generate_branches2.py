"""SpecFirstGenerateMixin 协调层分支覆盖（spec_first_generate.py）。

既有测试分别覆盖了收尾清理、并发限流和重构接线。本文件补齐
``generate_with_spec_first`` / ``_generate_with_dynamic_topology`` 主流程，
以及恢复、重试、沙箱修复等辅助方法的分支。
"""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.orchestrator_generation import spec_first_generate as module
from app.agent.orchestrator_generation.spec_first_generate import (
    SpecFirstGenerateMixin,
    _package_entry_content,
    _require_project_complete,
)
from app.agent.refinement_loop import RefinementResult, ValidationIssue


def _result(content: str, success: bool = True):
    return RefinementResult(
        success=success,
        final_content=content,
        attempts=1,
        issues_found=[],
        issues_fixed=0,
        remaining_issues=[] if success else [
            ValidationIssue(type="syntax", severity="error", message="bad")
        ],
    )


class _Engineer:
    SYSTEM_PROMPT = "sys"
    name = "backend"
    role_name = "后端工程师"

    def __init__(self, content="def main():\n    return 1\n"):
        self.content = content
        self.calls = 0
        self.llm_responses = []
        self.edited_files = []

    async def generate_file(self, *_args, **_kwargs):
        self.calls += 1
        return self.content

    async def call_llm(self, *_args, **_kwargs):
        if self.llm_responses:
            return self.llm_responses.pop(0)
        return self.content

    def get_edited_files(self):
        return list(self.edited_files)


class _FakeSpecCache:
    def __init__(self, cached=None, fail_save=False):
        self.cached = cached
        self.saved = None
        self.fail_save = fail_save

    def lookup(self, requirement, complexity_level=""):
        return self.cached

    def save(self, **kwargs):
        if self.fail_save:
            raise RuntimeError("cache write down")
        self.saved = kwargs


class _FakeRefinementLoop:
    def __init__(self, *_args, **_kwargs):
        self.calls = 0
        self.content = None

    async def refine(self, **kwargs):
        self.calls += 1
        return _result(self.content or kwargs["initial_content"])


class _FakeCrossValidator:
    fixed_files = {}
    issues_payload = []
    raise_validate = None
    raise_cross = None

    def __init__(self, *_args, **_kwargs):
        self.critical = False
        self.fixed = dict(type(self).fixed_files)
        self.issues = list(type(self).issues_payload)
        self.calls = 0

    def is_critical_file(self, *_args, **_kwargs):
        return self.critical

    async def cross_validate_with_refinement(self, **kwargs):
        if type(self).raise_cross is not None:
            raise type(self).raise_cross
        self.calls += 1
        return _result(kwargs["content_b"])

    async def validate_and_fix(self, *_args, **_kwargs):
        if type(self).raise_validate is not None:
            raise type(self).raise_validate
        return self.fixed, self.issues


class _FakeIntegrityValidator:
    instance = None
    passed = True
    issues = []
    error_count = 0
    fixes = {}

    def __init__(self, *_args, **_kwargs):
        self.passed = type(self).passed
        self.issues = list(type(self).issues)
        self.error_count = type(self).error_count
        self.fixes = dict(type(self).fixes)
        _FakeIntegrityValidator.instance = self

    def validate(self, _files):
        return SimpleNamespace(passed=self.passed, issues=self.issues, error_count=self.error_count)

    def generate_fixes(self, *_args, **_kwargs):
        return dict(self.fixes)

    def _generate_init_content(self, path, _files):
        return f"# init {path}\n"

    def _generate_index_content(self, path, _files):
        return f"// index {path}\n"


class _FakeDependencyGraphValidator:
    static_passed = True
    incremental_passed = True
    issues = []

    def __init__(self, *_args, **_kwargs):
        pass

    def validate_static(self, *_args, **_kwargs):
        return SimpleNamespace(passed=self.static_passed, issues=self.issues)

    async def validate(self, *_args, **_kwargs):
        return SimpleNamespace(passed=self.incremental_passed, issues=self.issues)


class _FakeArchitectureInspector:
    passed = True
    violations = []

    def set_context(self, **_kwargs):
        pass

    def inspect(self):
        return SimpleNamespace(
            passed=type(self).passed,
            architecture_alignment_score=100,
            violations=list(type(self).violations),
            suggestions=[],
        )


class _FakeSpecFirstGenerator:
    def __init__(self, *_args, **_kwargs):
        pass

    async def generate_all_specs(self, *_args, **_kwargs):
        return True

    def get_spec_context_for_file(self, *_args, **_kwargs):
        return {"openapi": {}}

    @staticmethod
    def get_spec_budget(_context_length):
        return 2000


class _FakeValidationCoordinator:
    def build_plan(self, *_args, **_kwargs):
        return SimpleNamespace(commands=[], unsupported_steps=[])


class _Harness(SpecFirstGenerateMixin):
    def __init__(self, output_dir: Path, **attrs):
        self.output_dir = Path(output_dir)
        self.errors = []
        self.warnings = []
        self.generated_files = []
        self._relative_output_dir = None
        self.api_key_token = None
        self.cancel_event = None
        self.use_dynamic_topology = False
        self.spec_cache = None
        self.incremental = False
        self.decision_callback = None
        self.enable_validation = False
        self.enable_review = False
        self.memory_enabled = False
        self.session_id = None
        self.complexity = SimpleNamespace(
            level=SimpleNamespace(value="simple"),
            estimated_files=2,
            has_frontend=False,
            has_backend=True,
            has_database=False,
            key_technologies=["FastAPI"],
        )
        self.model_assignment = SimpleNamespace(
            architect_model="arch",
            frontend_model="front",
            backend_model="back",
            reviewer_model="review",
            fallback_model="fallback",
        )
        self.engineer = _Engineer()
        self.architect = SimpleNamespace(
            design_architecture=self._design,
            expand_file_plan=self._expand,
            _get_compact_eight_file_architecture=lambda *a, **k: {
                "language": "python",
                "file_plan": [{"path": "main.py", "file_type": "entry"}],
            },
        )
        self.refinement = _FakeRefinementLoop()
        self.cross = _FakeCrossValidator()
        self.validation_calls = 0
        self.progress_events = []
        self.association = SimpleNamespace(
            skipped=True,
            enhanced_requirement=None,
            domain_matched="",
            items=[],
            history_matched_count=0,
        )
        self.syntax_ok = True
        self.syntax_calls = 0
        self.completeness = {
            "is_complete": True,
            "total_generated": 1,
            "total_planned": 1,
            "missing_files": [],
            "empty_files": [],
            "invalid_files": [],
            "placeholder_files": [],
        }
        for key, value in attrs.items():
            setattr(self, key, value)

    async def _initialize_components(self, _requirement):
        pass

    async def _design(self, requirement, complexity, callback=None):
        return {
            "language": "python",
            "project_type": "backend",
            "file_plan": [
                {"path": "app/main.py", "file_type": "entry", "description": "entry"},
            ],
        }

    async def _expand(self, architecture, _complexity, target_file_count=0, target_language=""):
        architecture["file_plan"].append(
            {"path": "app/service.py", "file_type": "service", "description": "svc"}
        )
        return architecture

    async def _generate_requirement_associations(self, _requirement, _level):
        return self.association

    def _select_engineer(self, _file_path):
        return self.engineer

    def _select_model_for_file(self, _file_path):
        return "back"

    def _select_alternative_model(self, _primary):
        return None

    def _select_engineer_for_model(self, _model):
        return self.engineer

    def _report_progress(self, step, current, total, callback=None, **kwargs):
        self.progress_events.append((step, current, total, kwargs))

    def _report_step_detail(self, *_args, **_kwargs):
        pass

    def _report_thinking(self, *_args, **_kwargs):
        pass

    def _report_model_info(self, *_args, **_kwargs):
        pass

    def _report_file_event(self, *_args, **_kwargs):
        pass

    def _report_validation_results(self, _results):
        self.validation_calls += 1

    def _report_current_cost(self):
        pass

    def _report_final_metrics(self):
        pass

    def _check_requirement_coverage(self, *_args, **_kwargs):
        return {"covered": True}

    async def _save_to_memory(self, *_args, **_kwargs):
        pass

    async def _validate_content_syntax(self, _file_path, _content):
        self.syntax_calls += 1
        return self.syntax_ok

    async def _validate_project_completeness(self, _file_plan, _files):
        return self.completeness

    def _clean_code_block(self, content):
        from app.agent.utils import clean_code_block

        return clean_code_block(content)


def _patch_generation_collaborators(monkeypatch, harness):
    monkeypatch.setattr(module, "SpecFirstGenerator", _FakeSpecFirstGenerator)
    monkeypatch.setattr(module, "RefinementLoop", lambda *a, **k: harness.refinement)
    monkeypatch.setattr(module, "CrossValidator", lambda *a, **k: harness.cross)
    monkeypatch.setattr(module, "IntegrityValidator", _FakeIntegrityValidator, raising=False)
    monkeypatch.setattr(module, "DependencyGraphValidator", _FakeDependencyGraphValidator)
    monkeypatch.setattr(module, "ArchitectureInspector", _FakeArchitectureInspector)
    monkeypatch.setattr(module, "ValidationCoordinator", _FakeValidationCoordinator)
    monkeypatch.setattr(module, "detect_toolchain", lambda _output: object())
    monkeypatch.setattr(module, "_is_adapter_owned_file", lambda *a, **k: False)
    monkeypatch.setattr(
        "app.agent.profile_discovery.profile_context",
        lambda _workspace: {"capability_policy": {}},
    )
    monkeypatch.setattr(
        "app.agent.utils.extract_engineer_content",
        _async_echo,
    )
    monkeypatch.setattr(module, "extract_engineer_content", _async_echo)
    monkeypatch.setattr("app.agent.utils.validate_content_quality", lambda *a, **k: "")
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a, **k: (True, ""))
    monkeypatch.setattr("app.agent.utils.is_placeholder_content", lambda *a, **k: (False, ""))
    monkeypatch.setattr("app.agent.utils.validate_in_sandbox", lambda **kwargs: (True, []))
    monkeypatch.setattr("app.agent.utils.write_file_atomic", _write_atomic)
    monkeypatch.setattr("app.agent.symbol_table.remember_generated_file", lambda *a, **k: [])
    monkeypatch.setattr("app.agent.symbol_table.finalize_generated_project", lambda *a, **k: [])
    monkeypatch.setattr(module, "DependencyGraph", _patch_graph_load(monkeypatch))
    monkeypatch.setattr(module, "write_file_atomic", _write_atomic)


async def _async_echo(content, *_args, **_kwargs):
    return content


def _write_atomic(output_dir, file_path, content, **_kwargs):
    path = Path(output_dir) / file_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return True


def _patch_graph_load(monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    original = DependencyGraph.load

    def fake_load(cls, path, language_adapter=None):
        return None

    monkeypatch.setattr(DependencyGraph, "load", classmethod(fake_load))
    return DependencyGraph


def _fake_integrity(monkeypatch):
    monkeypatch.setattr(
        "app.agent.integrity_validator.IntegrityValidator", _FakeIntegrityValidator
    )


@pytest.fixture(autouse=True)
def _reset_fake_state():
    _FakeIntegrityValidator.passed = True
    _FakeIntegrityValidator.issues = []
    _FakeIntegrityValidator.error_count = 0
    _FakeIntegrityValidator.fixes = {}
    _FakeScheduler.failed = []
    _FakeDependencyGraphValidator.static_passed = True
    _FakeDependencyGraphValidator.incremental_passed = True
    _FakeDependencyGraphValidator.issues = []
    _FakeCrossValidator.fixed_files = {}
    _FakeCrossValidator.issues_payload = []
    _FakeCrossValidator.raise_validate = None
    _FakeCrossValidator.raise_cross = None
    _FakeArchitectureInspector.passed = True
    _FakeArchitectureInspector.violations = []
    yield
    _FakeIntegrityValidator.passed = True
    _FakeIntegrityValidator.issues = []
    _FakeIntegrityValidator.error_count = 0
    _FakeIntegrityValidator.fixes = {}
    _FakeScheduler.failed = []
    _FakeDependencyGraphValidator.static_passed = True
    _FakeDependencyGraphValidator.incremental_passed = True
    _FakeDependencyGraphValidator.issues = []
    _FakeCrossValidator.fixed_files = {}
    _FakeCrossValidator.issues_payload = []
    _FakeCrossValidator.raise_validate = None
    _FakeCrossValidator.raise_cross = None
    _FakeArchitectureInspector.passed = True
    _FakeArchitectureInspector.violations = []


@pytest.mark.asyncio
async def test_generate_with_spec_first_static_happy_path(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert result["total_files_created"] == 1
    assert (tmp_path / "app" / "main.py").exists()
    assert result["models_used"]["backend"] == "back"
    assert harness.validation_calls == 0
    assert any(event[0] == "files_generated" for event in harness.progress_events)


@pytest.mark.asyncio
async def test_generate_with_spec_first_runs_validation_when_enabled(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.enable_validation = True
    harness.validator = SimpleNamespace(
        run_full_validation=_full_validation
    )
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert harness.validation_calls == 1
    assert result["validation"]["is_valid"] is True


async def _full_validation():
    return {
        "is_valid": True,
        "checks": ["syntax"],
        "score": 100,
        "syntax_errors": [],
        "dependency_errors": [{"message": "x"}],
    }


@pytest.mark.asyncio
async def test_generate_with_spec_first_expands_small_plan(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.complexity.estimated_files = 12
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert result["total_files_created"] == 2


@pytest.mark.asyncio
async def test_generate_with_spec_first_uses_cache_and_specs(tmp_path, monkeypatch):
    cached = SimpleNamespace(
        requirement_hash="hash",
        specs={"openapi": {"paths": {}}},
        architecture={
            "language": "python",
            "file_plan": [{"path": "app/main.py", "file_type": "entry"}],
        },
        file_plan=[{"path": "app/main.py", "file_type": "entry"}],
        dependency_graph=None,
    )
    harness = _Harness(tmp_path)
    harness.spec_cache = _FakeSpecCache(cached=cached)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert harness.spec_cache.saved is not None
    assert harness.spec_cache.saved["requirement"] == "做一个后端服务"
    assert any(event[0] == "cache_hit" for event in harness.progress_events)


@pytest.mark.asyncio
async def test_generate_with_spec_first_cache_lookup_failure_is_tolerated(tmp_path, monkeypatch):
    class _BrokenCache(_FakeSpecCache):
        def lookup(self, *_args, **_kwargs):
            raise RuntimeError("cache down")

    harness = _Harness(tmp_path)
    harness.spec_cache = _BrokenCache()
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_generate_with_spec_first_force_eight_files(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_FORCE_FILE_COUNT", "8")
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert result["total_files_created"] == 1


@pytest.mark.asyncio
async def test_generate_with_spec_first_invalid_force_count_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_FORCE_FILE_COUNT", "not-a-number")
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_generate_with_spec_first_association_enhances_requirement(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.association = SimpleNamespace(
        skipped=False,
        enhanced_requirement="增强后的需求",
        domain_matched="order",
        items=["a", "b"],
        history_matched_count=2,
    )
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert any(event[0] == "requirement_association" for event in harness.progress_events)


@pytest.mark.asyncio
async def test_generate_with_spec_first_specs_failure_raises(tmp_path, monkeypatch):
    class _FailingSpecs(_FakeSpecFirstGenerator):
        async def generate_all_specs(self, *_args, **_kwargs):
            return False

    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    monkeypatch.setattr(module, "SpecFirstGenerator", _FailingSpecs)

    with pytest.raises(RuntimeError, match="spec generation failed"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_generate_with_spec_first_empty_plan_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)

    async def empty_design(*_args, **_kwargs):
        return {"language": "python", "file_plan": []}

    harness.architect.design_architecture = empty_design

    with pytest.raises(RuntimeError, match="did not include a file_plan"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_generate_with_spec_first_static_validation_failure_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _FakeDependencyGraphValidator.static_passed = False
    _FakeDependencyGraphValidator.issues = [
        SimpleNamespace(issue_type="cycle", message="boom")
    ]
    try:
        with pytest.raises(RuntimeError, match="dependency graph static validation failed"):
            await harness.generate_with_spec_first("做一个后端服务")
    finally:
        _FakeDependencyGraphValidator.static_passed = True
        _FakeDependencyGraphValidator.issues = []


@pytest.mark.asyncio
async def test_generate_with_spec_first_incremental_graph_validation(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    existing = DependencyGraph()
    existing.add_file("app/old.py", file_type="utils")

    monkeypatch.setattr(
        DependencyGraph, "load", classmethod(lambda cls, path, language_adapter=None: existing)
    )

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert "app/main.py" in existing.nodes


@pytest.mark.asyncio
async def test_generate_with_spec_first_incremental_validation_failure_raises(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    existing = DependencyGraph()
    existing.add_file("app/old.py", file_type="utils")
    monkeypatch.setattr(
        DependencyGraph, "load", classmethod(lambda cls, path, language_adapter=None: existing)
    )
    _FakeDependencyGraphValidator.incremental_passed = False
    _FakeDependencyGraphValidator.issues = [
        SimpleNamespace(issue_type="missing", message="gone")
    ]
    try:
        with pytest.raises(RuntimeError, match="incremental dependency graph validation failed"):
            await harness.generate_with_spec_first("做一个后端服务")
    finally:
        _FakeDependencyGraphValidator.incremental_passed = True
        _FakeDependencyGraphValidator.issues = []


@pytest.mark.asyncio
async def test_generate_with_spec_first_dynamic_topology_result(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    async def dynamic(*_args, **_kwargs):
        return {
            "files_generated": 3,
            "files_failed": 0,
            "files_skipped": 1,
            "generated_files": [{"path": "app/main.py"}],
            "errors": [],
            "warnings": ["w"],
            "total_files": 3,
        }

    harness._generate_with_dynamic_topology = dynamic

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert result["total_files_created"] == 3
    assert result["total_files_skipped"] == 1


@pytest.mark.asyncio
async def test_generate_with_spec_first_dynamic_topology_clears_whitelist(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    calls = []

    def fake_set_allowed(paths):
        calls.append(paths)

    monkeypatch.setattr("app.agent.tools.set_allowed_file_paths", fake_set_allowed)

    async def dynamic(*_args, **_kwargs):
        return {
            "files_generated": 1,
            "files_failed": 0,
            "files_skipped": 0,
            "generated_files": [],
            "errors": [],
            "warnings": [],
            "total_files": 1,
        }

    harness._generate_with_dynamic_topology = dynamic
    await harness.generate_with_spec_first("做一个后端服务")

    assert calls[-1] is None


@pytest.mark.asyncio
async def test_generate_with_spec_first_decision_callback_applied(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    applied = {}

    class _Decision:
        def extract_from_architecture(self, *_args):
            return []

        def format_as_questions(self):
            return [{"id": "auth_strategy"}]

        def apply_user_choice(self, key, value):
            applied[key] = value

        def get_all_choices(self):
            return applied

        def skip_remaining_decisions(self):
            applied["skipped"] = True

    async def decisions(_questions):
        return {"auth_strategy": "JWT"}

    harness.decision_callback = decisions
    monkeypatch.setattr(module, "CriticalDecisionExtractor", _Decision)
    monkeypatch.setattr(module, "should_skip_user_decision", lambda *a, **k: False)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert applied == {"auth_strategy": "JWT"}


@pytest.mark.asyncio
async def test_generate_with_spec_first_decision_timeout_uses_defaults(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    class _Decision:
        def extract_from_architecture(self, *_args):
            return []

        def format_as_questions(self):
            return [{"id": "auth_strategy"}]

        def apply_user_choice(self, *_args):
            pass

        def get_all_choices(self):
            return {}

    async def slow(_questions):
        await asyncio.sleep(10)

    harness.decision_callback = slow
    monkeypatch.setattr(module, "CriticalDecisionExtractor", _Decision)
    monkeypatch.setattr(module, "should_skip_user_decision", lambda *a, **k: False)
    monkeypatch.setattr(asyncio, "wait_for", _raise_timeout)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert any("timed out" in warning for warning in harness.warnings)


async def _raise_timeout(*_args, **_kwargs):
    raise asyncio.TimeoutError


@pytest.mark.asyncio
async def test_generate_with_spec_first_decision_error_uses_defaults(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    class _Decision:
        def extract_from_architecture(self, *_args):
            return []

        def format_as_questions(self):
            return [{"id": "auth_strategy"}]

        def apply_user_choice(self, *_args):
            pass

        def get_all_choices(self):
            return {}

    async def boom(_questions):
        raise RuntimeError("boom")

    harness.decision_callback = boom
    monkeypatch.setattr(module, "CriticalDecisionExtractor", _Decision)
    monkeypatch.setattr(module, "should_skip_user_decision", lambda *a, **k: False)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert any("user decision failed" in warning for warning in harness.warnings)


@pytest.mark.asyncio
async def test_generate_with_spec_first_simple_skips_decisions(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    skipped = []

    class _Decision:
        def extract_from_architecture(self, *_args):
            return []

        def format_as_questions(self):
            return [{"id": "auth_strategy"}]

        def get_all_choices(self):
            return {}

        def skip_remaining_decisions(self):
            skipped.append(True)

    monkeypatch.setattr(module, "CriticalDecisionExtractor", _Decision)
    monkeypatch.setattr(module, "should_skip_user_decision", lambda *a, **k: True)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert skipped == [True]


@pytest.mark.asyncio
async def test_generate_with_spec_first_plan_freeze_failure_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)

    async def design(*_args, **_kwargs):
        return {"language": "python", "file_plan": [{"path": "same.py"}, {"path": "same.py"}]}

    harness.architect.design_architecture = design

    with pytest.raises(RuntimeError, match="generation plan could not be frozen"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_generate_with_spec_first_layer_failure_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    harness.engineer.content = ""
    monkeypatch.setattr(module, "extract_engineer_content", lambda *a, **k: _async_none())
    harness._recover_invalid_content = lambda *a, **k: _async_none()
    harness._retry_generate_file = lambda *a, **k: _async_none()

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


async def _async_none(*_args, **_kwargs):
    return None


# ---------------------------------------------------------------------------
# generate_single_file 分支（经由完整静态流程触发）
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_path_reuses_existing_file(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    target = tmp_path / "app" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("def main():\n    return 42\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.agent.utils.reusable_existing_file_content",
        lambda *a, **k: (True, ""),
    )

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert result["total_files_skipped"] == 1
    assert harness.engineer.calls == 0


@pytest.mark.asyncio
async def test_static_path_read_failure_regenerates(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    target = tmp_path / "app" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff\xfe")

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert harness.engineer.calls >= 1


@pytest.mark.asyncio
async def test_static_path_recovers_invalid_content(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "extract_engineer_content", lambda *a, **k: _async_none())
    recovered = []

    async def recover(*args, **kwargs):
        recovered.append((args, kwargs))
        return "def recovered():\n    return 1\n"

    harness._recover_invalid_content = recover

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert recovered


@pytest.mark.asyncio
async def test_static_path_retries_after_recover_failure(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "extract_engineer_content", lambda *a, **k: _async_none())
    retried = []

    async def no_recover(*_args, **_kwargs):
        return None

    async def retry(*args, **kwargs):
        retried.append((args, kwargs))
        return "def retried():\n    return 1\n"

    harness._recover_invalid_content = no_recover
    harness._retry_generate_file = retry

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert retried


@pytest.mark.asyncio
async def test_static_path_adapter_owned_file_skips_review(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "_is_adapter_owned_file", lambda *a, **k: True)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert harness.refinement.calls == 0


@pytest.mark.asyncio
async def test_static_path_critical_without_alternative_degrades(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    harness.cross.critical = True

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert harness.refinement.calls >= 1
    assert any(event[0] == "cross_validation_skipped" for event in harness.progress_events)


@pytest.mark.asyncio
async def test_static_path_critical_with_alternative_cross_validates(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_path_critical_alt_empty_falls_back_to_refine(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"
    alt = _Engineer(content="")
    harness._select_engineer_for_model = lambda _model: alt

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert alt.calls >= 1
    assert harness.refinement.calls >= 1


@pytest.mark.asyncio
async def test_static_path_quality_retry_succeeds(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    warnings = iter(["leak", ""])
    monkeypatch.setattr(
        "app.agent.utils.validate_content_quality",
        lambda *a, **k: next(warnings, ""),
    )

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert harness.engineer.calls >= 2


@pytest.mark.asyncio
async def test_static_path_quality_retry_failure_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(
        "app.agent.utils.validate_content_quality",
        lambda *a, **k: "leak",
    )
    harness.engineer.content = ""

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_path_syntax_failure_retries(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []
    harness.syntax_ok = False
    retried = []

    async def retry(*_args, **kwargs):
        retried.append(kwargs.get("reason"))
        harness.syntax_ok = True
        return "def fixed():\n    return 1\n"

    harness._retry_generate_file = retry

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert retried == ["语法验证失败"]


@pytest.mark.asyncio
async def test_static_path_syntax_failure_without_retry_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []
    harness.syntax_ok = False

    async def retry(*_args, **_kwargs):
        return None

    harness._retry_generate_file = retry

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_path_write_failure_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: False)

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_path_cancelled_layer_stops(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    class _Cancel:
        def __init__(self):
            self.calls = 0

        def is_set(self):
            self.calls += 1
            return self.calls > 1

    harness.cancel_event = _Cancel()

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_path_persisted_empty_file_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.use_dynamic_topology = True
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []

    class _EmptyRefinement(_FakeRefinementLoop):
        async def refine(self, **kwargs):
            return _result("")

    harness.refinement = _EmptyRefinement()
    monkeypatch.setattr(module, "RefinementLoop", lambda *a, **k: harness.refinement)
    harness.engineer.content = "def main():\n    return 1\n"

    async def no_retry(*_args, **_kwargs):
        return None

    harness._retry_generate_file = no_retry

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


# ---------------------------------------------------------------------------
# _generate_with_dynamic_topology
# ---------------------------------------------------------------------------


class _FakeScheduler:
    instances = []
    failed = []
    stats = {"ok": 1}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.nodes = {}
        _FakeScheduler.instances.append(self)

    def build_from_dependency_graph(self, dep_graph):
        self.nodes = dict(dep_graph.nodes)

    async def run(self, file_generator, progress_report):
        for path in self.nodes:
            try:
                await file_generator(path, {}, None)
            except Exception:
                self.failed.append(path)
        return {"failed_files": list(self.failed)}

    def get_stats(self):
        return dict(self.stats)


def _dynamic_harness(tmp_path, **attrs):
    harness = _Harness(tmp_path, **attrs)
    harness.use_dynamic_topology = True
    return harness


@pytest.mark.asyncio
async def test_dynamic_topology_happy_path(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert result["total_files_created"] == 1
    assert (tmp_path / "app" / "main.py").exists()


@pytest.mark.asyncio
async def test_dynamic_topology_skips_existing_file(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []
    target = tmp_path / "app" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_text("def main():\n    return 7\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.agent.utils.reusable_existing_file_content",
        lambda *a, **k: (True, ""),
    )

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert result["total_files_skipped"] == 1


@pytest.mark.asyncio
async def test_dynamic_topology_removes_language_mismatch(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []

    async def dynamic(*_args, **_kwargs):
        return {
            "files_generated": 1,
            "files_failed": 0,
            "files_skipped": 0,
            "generated_files": [],
            "errors": [],
            "warnings": [],
            "total_files": 1,
        }

    harness._generate_with_dynamic_topology = dynamic
    result = await harness.generate_with_spec_first("做一个后端服务")
    assert result["success"] is True


@pytest.mark.asyncio
async def test_dynamic_topology_reports_failures(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = ["app/main.py"]
    try:
        async def failing_run(_generator, _progress):
            return {"failed_files": ["app/main.py"]}

        monkeypatch.setattr(_FakeScheduler, "run", _FakeScheduler_run_failing)
        with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
            await harness.generate_with_spec_first("做一个后端服务")
    finally:
        _FakeScheduler.failed = []
        monkeypatch.setattr(_FakeScheduler, "run", _FakeScheduler_run_ok)


async def _FakeScheduler_run_ok(self, file_generator, progress_report):
    for path in self.nodes:
        try:
            await file_generator(path, {}, None)
        except Exception:
            self.failed.append(path)
    return {"failed_files": list(self.failed)}


async def _FakeScheduler_run_failing(self, _generator, _progress):
    return {"failed_files": list(_FakeScheduler.failed)}


_FakeScheduler.run = _FakeScheduler_run_ok


@pytest.mark.asyncio
async def test_dynamic_topology_sandbox_failure_retries_then_raises(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []
    monkeypatch.setattr("app.agent.utils.validate_in_sandbox", lambda **kwargs: (False, ["boom"]))

    async def no_fix(*_args, **_kwargs):
        return []

    harness._fix_sandbox_errors = no_fix

    with pytest.raises(RuntimeError, match="sandbox validation failed"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_dynamic_topology_sandbox_fix_passes(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []
    outcomes = iter([(False, ["boom"]), (True, [])])

    def validate(**kwargs):
        return next(outcomes, (True, []))

    monkeypatch.setattr("app.agent.utils.validate_in_sandbox", validate)

    async def fix(*_args, **_kwargs):
        return ["app/main.py"]

    harness._fix_sandbox_errors = fix

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_dynamic_topology_integrity_fixes_and_missing_files(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []

    class _Graph:
        def __init__(self):
            self.nodes = {"app/main.py": SimpleNamespace(file_type="entry", description="entry", priority=3)}
            self.adjacency = {}

        def get_generation_layers(self):
            return [["app/main.py"]]

        def get_unknown_type_files(self):
            return []

        def validate_completeness(self):
            return [{"type": "missing", "file": "app/main.py"}]

        def get_missing_files(self):
            return ["app/__init__.py"]

        def add_missing_files(self, architecture):
            return architecture

        def remove_node(self, path):
            return True

        def get_context_for_file(self, *_args, **_kwargs):
            return ""

        def save(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(
        module, "DependencyGraph", SimpleNamespace(**{
            "load": classmethod(lambda cls, path, language_adapter=None: None),
            "from_dict": classmethod(lambda cls, data, language_adapter=None: _Graph()),
        })
    )
    monkeypatch.setattr(harness, "_build_graph", lambda: _Graph(), raising=False)

    result = await harness._generate_with_dynamic_topology(
        SimpleNamespace(
            files={},
            errors=[],
            add_error=lambda e: None,
            save_file_content=lambda *a, **k: None,
            update_file_validation=lambda *a, **k: None,
            get_file_content=lambda _f: "",
            complexity={},
            specs={},
            set_metric=lambda *a, **k: None,
            get_metric=lambda *a, **k: None,
            to_export_dict=lambda: {},
            get_summary=lambda: {},
        ),
        _Graph(),
        None,
        {"language": "python", "file_plan": [{"path": "app/main.py"}]},
        "需求",
        {"architecture": {}, "profile": {}},
        {},
        None,
        SimpleNamespace(language="python", extensions=[".py"], package_init_filename="__init__.py"),
        True,
    )

    assert result["files_generated"] >= 1


# ---------------------------------------------------------------------------
# 辅助方法
# ---------------------------------------------------------------------------


def test_package_entry_content_prefers_package_init():
    adapter = SimpleNamespace(package_init_filename="__init__.py")
    validator = SimpleNamespace(
        _generate_init_content=lambda path, _files: f"init:{path}",
        _generate_index_content=lambda path, _files: f"index:{path}",
    )
    assert _package_entry_content("app/__init__.py", validator, adapter, {}) == "init:app/__init__.py"


def test_package_entry_content_supports_js_index():
    validator = SimpleNamespace(
        _generate_init_content=lambda *a: "init",
        _generate_index_content=lambda path, _files: f"index:{path}",
    )
    assert _package_entry_content("web/index.js", validator, None, {}) == "index:web/index.js"
    assert _package_entry_content("web/index.ts", validator, None, {}) == "index:web/index.ts"


def test_package_entry_content_returns_none_for_other_files():
    assert _package_entry_content("main.py", None, None, {}) is None


def test_require_project_complete_handles_string_entries():
    with pytest.raises(RuntimeError, match="invalid=a.py"):
        _require_project_complete(
            {
                "is_complete": False,
                "invalid_files": ["a.py"],
                "placeholder_files": ["b.py"],
            }
        )


def test_require_project_complete_without_details():
    with pytest.raises(RuntimeError, match="incomplete"):
        _require_project_complete({"is_complete": False})


@pytest.mark.asyncio
async def test_degrade_cross_validation_reports_and_refines(monkeypatch):
    harness = _Harness(Path("/tmp"))
    calls = []
    harness._report_progress = lambda *a, **k: calls.append((a, k))
    loop = _FakeRefinementLoop()

    result = await harness._degrade_cross_validation(
        refinement_loop=loop,
        file_path="app/main.py",
        file_type="entry",
        description="entry",
        model_name="back",
        initial_content="def x():\n    return 1\n",
        project_context={},
        callback=None,
        progress_current=1,
        progress_total=2,
    )

    assert result.success is True
    assert harness.warnings
    assert calls[0][0][0] == "cross_validation_skipped"


@pytest.mark.asyncio
async def test_retry_generate_file_success_with_language_check(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = lambda _prompt: _async_yes()
    monkeypatch.setattr(
        "app.agent.utils.validate_language_with_llm",
        lambda *a, **k: _async_tuple(True, ""),
    )

    content = await harness._retry_generate_file(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "",
        "",
        _Engineer(),
        None,
        reason="bad",
    )

    assert content == "def main():\n    return 1"


async def _async_yes():
    return "YES"


async def _async_tuple(*values):
    return values


@pytest.mark.asyncio
async def test_retry_generate_file_skips_language_check_without_quick_llm():
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = None

    content = await harness._retry_generate_file(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "",
        "",
        _Engineer(),
        None,
    )

    assert content == "def main():\n    return 1"


@pytest.mark.asyncio
async def test_retry_generate_file_retries_after_empty(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = None
    engineer = _Engineer()
    engineer.llm_responses = ["", "def main():\n    return 2\n"]

    content = await harness._retry_generate_file(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "",
        "",
        engineer,
        None,
    )

    assert "return 2" in content


@pytest.mark.asyncio
async def test_recover_invalid_content_json_hint(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = None
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: True)

    content = await harness._recover_invalid_content(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "返回 JSON 元数据",
        _Engineer(),
        persist=False,
    )

    assert content == "def main():\n    return 1"


@pytest.mark.asyncio
async def test_recover_invalid_content_markdown_hint(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = None
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: True)
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.is_placeholder_content", lambda *a: (False, ""))

    content = await harness._recover_invalid_content(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "Markdown 文档",
        _Engineer(),
        persist=True,
    )

    assert content == "def main():\n    return 1"


@pytest.mark.asyncio
async def test_recover_invalid_content_placeholder_then_success(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = None
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: True)
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    outcomes = iter([(True, "placeholder"), (False, "")])
    monkeypatch.setattr(
        "app.agent.utils.is_placeholder_content", lambda *a: next(outcomes)
    )

    content = await harness._recover_invalid_content(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "other",
        _Engineer(),
        persist=False,
    )

    assert content == "def main():\n    return 1"


@pytest.mark.asyncio
async def test_recover_invalid_content_language_check_failure(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = lambda _prompt: _async_yes()
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.is_placeholder_content", lambda *a: (False, ""))
    language_outcomes = iter([(False, "wrong language"), (True, "")])

    async def fake_validate_language(*_args, **_kwargs):
        return next(language_outcomes)

    monkeypatch.setattr(
        "app.agent.utils.validate_language_with_llm", fake_validate_language
    )
    engineer = _Engineer()
    engineer.llm_responses = ["wrong", "", "right"]

    content = await harness._recover_invalid_content(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "other",
        engineer,
        persist=False,
    )

    assert content == "right"


@pytest.mark.asyncio
async def test_recover_invalid_content_returns_none_after_attempts(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = None
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (False, "bad"))
    engineer = _Engineer(content="oops")

    content = await harness._recover_invalid_content(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "other",
        engineer,
        persist=False,
    )

    assert content is None


@pytest.mark.asyncio
async def test_fix_sandbox_errors_parses_and_fixes(monkeypatch, tmp_path):
    harness = _Harness(tmp_path)
    harness.model_assignment.reviewer_model = "review"

    async def fake_call_llm(**_kwargs):
        return {"choices": [{"message": {"content": "def main():\n    return 2\n"}}]}

    monkeypatch.setattr("app.utils.aicloud.llm_caller.call_llm", fake_call_llm)
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: True)
    monkeypatch.setattr("app.agent.utils.validate_in_sandbox", lambda **kwargs: (True, []))

    fixed = await harness._fix_sandbox_errors(
        ['app/main.py: ImportError: no module'],
        {"app/main.py": "import missing\n"},
        SimpleNamespace(save_file_content=lambda *a, **k: None),
    )

    assert fixed == ["app/main.py"]


@pytest.mark.asyncio
async def test_fix_sandbox_errors_ignores_unknown_and_empty(monkeypatch, tmp_path):
    harness = _Harness(tmp_path)
    called = []

    async def fake_call_llm(**_kwargs):
        called.append(True)
        return {}

    monkeypatch.setattr("app.utils.aicloud.llm_caller.call_llm", fake_call_llm)

    fixed = await harness._fix_sandbox_errors(
        ["no file here", "other.py: ImportError: x"],
        {"app/main.py": "x = 1\n"},
        SimpleNamespace(),
    )

    assert fixed == []
    assert called == []


@pytest.mark.asyncio
async def test_fix_sandbox_errors_line_number_context(monkeypatch, tmp_path):
    harness = _Harness(tmp_path)

    async def fake_call_llm(**kwargs):
        assert "上下文" in kwargs["prompt"]
        return {"choices": [{"message": {"content": "def main():\n    return 1\n"}}]}

    monkeypatch.setattr("app.utils.aicloud.llm_caller.call_llm", fake_call_llm)
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: True)
    monkeypatch.setattr("app.agent.utils.validate_in_sandbox", lambda **kwargs: (True, []))

    fixed = await harness._fix_sandbox_errors(
        ['app/main.py.Class.method(): NameError: x (File "app/main.py", line 2)'],
        {"app/main.py": "a = 1\nb = x\n"},
        SimpleNamespace(save_file_content=lambda *a, **k: None),
    )

    assert fixed == ["app/main.py"]


@pytest.mark.asyncio
async def test_fix_sandbox_errors_breaks_on_empty_response(monkeypatch, tmp_path):
    harness = _Harness(tmp_path)

    async def fake_call_llm(**_kwargs):
        return {"choices": [{"message": {"content": ""}}]}

    monkeypatch.setattr("app.utils.aicloud.llm_caller.call_llm", fake_call_llm)

    fixed = await harness._fix_sandbox_errors(
        ["app/main.py: ImportError: x"],
        {"app/main.py": "x = 1\n"},
        SimpleNamespace(),
    )

    assert fixed == []


@pytest.mark.asyncio
async def test_fix_sandbox_errors_rejects_invalid_fix(monkeypatch, tmp_path):
    harness = _Harness(tmp_path)

    async def fake_call_llm(**_kwargs):
        return {"choices": [{"message": {"content": "def main():\n    return 1\n"}}]}

    monkeypatch.setattr("app.utils.aicloud.llm_caller.call_llm", fake_call_llm)
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (False, "bad"))

    fixed = await harness._fix_sandbox_errors(
        ["app/main.py: ImportError: x"],
        {"app/main.py": "x = 1\n"},
        SimpleNamespace(),
    )

    assert fixed == []


@pytest.mark.asyncio
async def test_fix_sandbox_errors_swallows_exceptions(monkeypatch, tmp_path):
    harness = _Harness(tmp_path)

    async def fake_call_llm(**_kwargs):
        raise RuntimeError("llm down")

    monkeypatch.setattr("app.utils.aicloud.llm_caller.call_llm", fake_call_llm)

    fixed = await harness._fix_sandbox_errors(
        ["app/main.py: ImportError: x"],
        {"app/main.py": "x = 1\n"},
        SimpleNamespace(),
    )

    assert fixed == []


@pytest.mark.asyncio
async def test_fix_sandbox_errors_runtime_format_second_round_failure(monkeypatch, tmp_path):
    harness = _Harness(tmp_path)
    calls = []

    async def fake_call_llm(**_kwargs):
        calls.append(True)
        return {"choices": [{"message": {"content": "def main():\n    return 1\n"}}]}

    monkeypatch.setattr("app.utils.aicloud.llm_caller.call_llm", fake_call_llm)
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: True)
    monkeypatch.setattr(
        "app.agent.utils.validate_in_sandbox",
        lambda **kwargs: (False, ["ValueError: still broken"]),
    )

    fixed = await harness._fix_sandbox_errors(
        ["app/main.py.Class.method(): NameError: x"],
        {"app/main.py": "x = 1\n"},
        SimpleNamespace(save_file_content=lambda *a, **k: None),
        max_rounds=2,
    )

    assert fixed == []
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_validate_project_completeness_reports_invalid_and_placeholder(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("x\n", encoding="utf-8")
    monkeypatch.setattr(
        "app.agent.utils.is_valid_code_content",
        lambda path, content: (False, "syntax") if "main" in path else (True, ""),
    )
    monkeypatch.setattr(
        "app.agent.utils.is_placeholder_content",
        lambda content, path: (True, "TODO") if "svc" in path else (False, ""),
    )

    result = await SpecFirstGenerateMixin._validate_project_completeness(
        harness,
        [{"path": "app/main.py"}, {"path": "app/svc.py"}],
        {"app/main.py": "x\n", "app/svc.py": "def todo():\n    pass\n"},
    )

    assert result["invalid_files"] == [("app/main.py", "syntax")]
    assert result["placeholder_files"] == [("app/svc.py", "TODO")]
    assert result["is_complete"] is False


@pytest.mark.asyncio
async def test_refactor_missing_graph(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: None))

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is False
    assert "依赖图不存在" in result["errors"][0]


@pytest.mark.asyncio
async def test_refactor_file_not_in_graph(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("other.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is False
    assert "不在依赖图中" in result["errors"][0]


@pytest.mark.asyncio
async def test_refactor_source_file_missing(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is False
    assert "不存在" in result["errors"][0]


@pytest.mark.asyncio
async def test_refactor_requires_backend_model(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    harness.model_assignment = None
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="model assignment is required for file refactor"):
        await harness.refactor_file("app/main.py", "拆分")


@pytest.mark.asyncio
async def test_refactor_parse_failure(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")

    async def fake_call_llm(**_kwargs):
        return "not json"

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is False
    assert "拆分方案解析失败" in result["errors"][0]


@pytest.mark.asyncio
async def test_refactor_no_new_files(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")

    async def fake_call_llm(**_kwargs):
        return json.dumps({"new_files": []})

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is False
    assert result["errors"] == ["拆分方案中没有新文件"]


@pytest.mark.asyncio
async def test_refactor_fenced_json_and_generation_errors(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")

    plan = {"new_files": [{"path": "app/part.py", "file_type": "utils"}]}

    async def fake_call_llm(**_kwargs):
        return "```json\n" + json.dumps(plan) + "\n```"

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)
    monkeypatch.setattr(module, "write_file_atomic", lambda *a, **k: True)

    class _BoomEngineer(_Engineer):
        async def generate_file(self, *_args, **_kwargs):
            raise RuntimeError("engineer boom")

    harness._select_engineer = lambda _path: _BoomEngineer()

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is False
    assert any("engineer boom" in error for error in result["errors"])


@pytest.mark.asyncio
async def test_refactor_empty_generated_content(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    (tmp_path / "app" / "main.py").write_text("a = 1\n", encoding="utf-8")

    async def fake_call_llm(**_kwargs):
        return json.dumps({"new_files": [{"path": "app/part.py"}]})

    async def fake_extract(*_args, **_kwargs):
        return ""

    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)
    monkeypatch.setattr("app.agent.utils.extract_engineer_content", fake_extract)

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is False
    assert any("内容为空" in error for error in result["errors"])


@pytest.mark.asyncio
async def test_refactor_partial_generation_keeps_old_file(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    graph = DependencyGraph()
    graph.add_file("app/main.py")
    monkeypatch.setattr(module.DependencyGraph, "load", classmethod(lambda *a, **k: graph))
    (tmp_path / "app").mkdir()
    old = tmp_path / "app" / "main.py"
    old.write_text("a = 1\n", encoding="utf-8")

    async def fake_call_llm(**_kwargs):
        return json.dumps(
            {"new_files": [{"path": "app/a.py"}, {"path": "app/b.py"}], "old_file_action": "delete"}
        )

    class _Partial(_Engineer):
        def __init__(self):
            super().__init__()
            self.count = 0

        async def generate_file(self, *_args, **_kwargs):
            self.count += 1
            if self.count == 1:
                raise RuntimeError("first fails")
            return "def b():\n    return 1\n"

    engineer = _Partial()
    harness._select_engineer = lambda _path: engineer
    monkeypatch.setattr("app.utils.call_llm", fake_call_llm)
    monkeypatch.setattr(module, "extract_engineer_content", lambda content, *a, **k: _async_echo(content))

    result = await harness.refactor_file("app/main.py", "拆分")

    assert result["success"] is False
    assert old.exists()
    assert "app/b.py" in result["new_files"]


# ---------------------------------------------------------------------------
# 模块级辅助函数
# ---------------------------------------------------------------------------


def test_sync_architecture_and_skipped_refinement():
    from app.agent.orchestrator_generation.spec_first_generate import (
        _skipped_refinement,
        sync_generation_architecture,
    )

    project_context = {}
    architecture = {"file_plan": [{"path": "a.py"}]}

    assert sync_generation_architecture(project_context, architecture) == [{"path": "a.py"}]
    assert project_context["architecture"] is architecture

    result = _skipped_refinement("")
    assert result.success is True
    assert result.final_content == ""
    assert result.remaining_issues[0].type == "review_skipped"


def test_language_mismatch_selection_skips_cached_and_keeps_allowed():
    from app.agent.orchestrator_generation.spec_first_generate import (
        _select_language_mismatch_files,
    )

    files = {
        "app/main.js": SimpleNamespace(generated_by="engineer"),
        "app/cached.js": SimpleNamespace(generated_by="cached"),
        "app/main.py": SimpleNamespace(generated_by="engineer"),
        "notes.md": SimpleNamespace(generated_by="engineer"),
    }

    selected = _select_language_mismatch_files(files, {".py"})

    assert selected == ["app/main.js"]


def test_dedup_rank_and_duplicate_selection():
    from app.agent.orchestrator_generation.spec_first_generate import (
        _dedup_keep_rank,
        _select_duplicate_files,
    )

    assert _dedup_keep_rank("src/a.py") == 0
    assert _dedup_keep_rank("app/a.py") == 1
    assert _dedup_keep_rank("pkg/a.py") == 3
    assert _dedup_keep_rank("a.py") == 4

    files = {
        "app/main.py": SimpleNamespace(generated_by="engineer"),
        "main.py": SimpleNamespace(generated_by="engineer"),
        "other/main.py": SimpleNamespace(generated_by="cached"),
        "src/dup.py": SimpleNamespace(generated_by="engineer"),
        "dup.py": SimpleNamespace(generated_by="engineer"),
    }
    contents = {
        "app/main.py": "same",
        "main.py": "same",
        "other/main.py": "same",
        "src/dup.py": "one",
        "dup.py": "two",
    }

    removals = _select_duplicate_files(files, contents)

    assert removals == {"main.py": "app/main.py"}


def test_is_adapter_owned_file_uses_registry(monkeypatch):
    from app.agent.orchestrator_generation.spec_first_generate import (
        _is_adapter_owned_file,
    )

    monkeypatch.setattr(
        module.LanguageAdapterRegistry,
        "scaffold_file",
        staticmethod(lambda *a, **k: "skeleton"),
    )

    assert _is_adapter_owned_file("a.py", "entry", {}) is True


@pytest.mark.asyncio
async def test_gather_with_limit_returns_exceptions():
    from app.agent.orchestrator_generation.spec_first_generate import gather_with_limit

    async def boom():
        raise RuntimeError("boom")

    async def ok():
        return "ok"

    results = await gather_with_limit([boom(), ok()], 1)

    assert isinstance(results[0], RuntimeError)
    assert results[1] == "ok"


def test_strip_output_dir_prefix_variants():
    harness = _Harness(Path("/tmp"))
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    harness._relative_output_dir = "out"
    assert SpecFirstGenerateMixin._strip_output_dir_prefix(harness, "out/app/a.py") == "app/a.py"
    assert SpecFirstGenerateMixin._strip_output_dir_prefix(harness, "other/a.py") == "other/a.py"

    harness._relative_output_dir = None
    assert SpecFirstGenerateMixin._strip_output_dir_prefix(harness, "out/a.py") == "out/a.py"


@pytest.mark.asyncio
async def test_infer_unknown_file_types_reports_stuck(monkeypatch):
    harness = _Harness(Path("/tmp"))

    class _Graph:
        nodes = {"a.xyz": SimpleNamespace(file_type="unknown")}

        def _enrich_unknown_file_type(self, *_args):
            return False

    with pytest.raises(RuntimeError, match="unknown file types were not inferred: a.xyz"):
        await harness._infer_unknown_file_types(_Graph(), ["a.xyz"], {}, "python")


@pytest.mark.asyncio
async def test_infer_unknown_file_types_updates_progressively():
    harness = _Harness(Path("/tmp"))

    class _Graph:
        def __init__(self):
            self.nodes = {
                "a.py": SimpleNamespace(file_type="unknown"),
                "b.py": SimpleNamespace(file_type="unknown"),
            }
            self.calls = 0

        def _enrich_unknown_file_type(self, path, _node):
            self.calls += 1
            if path == "a.py":
                self.nodes[path].file_type = "utils"
                return True
            self.nodes[path].file_type = "utils"
            return True

    await harness._infer_unknown_file_types(_Graph(), ["a.py", "b.py"], {}, "python")


def test_validate_content_syntax_python_and_unknown():
    harness = _Harness(Path("/tmp"))
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    assert asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.py", "def ok():\n    return 1\n")
    )
    assert not asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.py", "def broken(:\n")
    )
    assert asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.txt", "anything")
    )


def test_validate_content_syntax_typescript_and_js(monkeypatch):
    harness = _Harness(Path("/tmp"))
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    monkeypatch.setattr(module, "_shared_check_ts_source", lambda src, jsx=False: (True, ""))
    monkeypatch.setattr(module, "_shared_check_js_source", lambda src: (False, "bad"))

    assert SpecFirstGenerateMixin._check_ts_source(harness, "const a: number = 1", jsx=True) is True
    assert SpecFirstGenerateMixin._check_js_source(harness, "let a = 1") is False

    assert asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.tsx", "const a = <div />")
    )
    assert asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.jsx", "const a = <div />")
    )
    assert not asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.js", "let a = 1")
    )


def test_validate_content_syntax_vue_html_css(monkeypatch):
    harness = _Harness(Path("/tmp"))
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    monkeypatch.setattr(module, "vue_script_source", lambda _content: ("", True, True))
    monkeypatch.setattr(module, "html_structure_errors", lambda _content: ["bad"])
    monkeypatch.setattr(module, "css_structure_errors", lambda _content: [])
    monkeypatch.setattr(module, "strip_css_noise", lambda content: content)

    assert asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.vue", "<template></template>")
    )
    assert not asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.html", "<div>")
    )
    assert asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "a.css", "body { color: red; }")
    )
    long_chinese = "\n".join(["这是一个非常长的中文说明行"] * 5)
    assert not asyncio.run(
        SpecFirstGenerateMixin._validate_content_syntax(harness, "b.css", long_chinese)
    )


@pytest.mark.asyncio
async def test_quick_llm_check_requires_backend_model_and_swallows_errors(monkeypatch):
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    harness = _Harness(Path("/tmp"))
    harness.model_assignment = SimpleNamespace(backend_model=None)

    with pytest.raises(RuntimeError, match="model assignment is required for LLM check"):
        await SpecFirstGenerateMixin._quick_llm_check(harness, "prompt")

    harness.model_assignment = SimpleNamespace(backend_model="back")

    class _BrokenClient:
        def __init__(self, **_kwargs):
            pass

        async def call(self, *_args):
            raise RuntimeError("llm down")

    monkeypatch.setattr("app.agent.llm_client.LLMClient", _BrokenClient)

    assert await SpecFirstGenerateMixin._quick_llm_check(harness, "prompt") == ""


@pytest.mark.asyncio
async def test_validate_project_completeness_without_output_dir(monkeypatch):
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    harness = _Harness(Path("/tmp"))
    harness.output_dir = None
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.is_placeholder_content", lambda *a: (False, ""))

    result = await SpecFirstGenerateMixin._validate_project_completeness(
        harness, [{"path": "a.py"}], {}
    )

    assert result["missing_files"] == ["a.py"]


@pytest.mark.asyncio
async def test_validate_project_completeness_ignores_empty_package_entry(tmp_path, monkeypatch):
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    harness = _Harness(tmp_path)
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.is_placeholder_content", lambda *a: (False, ""))

    result = await SpecFirstGenerateMixin._validate_project_completeness(
        harness,
        [{"path": "pkg/__init__.py"}],
        {"pkg/__init__.py": ""},
    )

    assert result["missing_files"] == []
    assert result["empty_files"] == []
    assert result["is_complete"] is True


# ---------------------------------------------------------------------------
# 静态流程的完整性与沙箱收尾
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_flow_integrity_fixes_are_written(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    _FakeIntegrityValidator.passed = False
    _FakeIntegrityValidator.error_count = 1
    _FakeIntegrityValidator.issues = [
        SimpleNamespace(severity="error", message="missing package init"),
        SimpleNamespace(severity="warning", message="ignored"),
    ]
    _FakeIntegrityValidator.fixes = {"app/__init__.py": "# init\n"}

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert (tmp_path / "app" / "__init__.py").exists()
    assert "missing package init" in result["warnings"]
    assert "ignored" not in result["warnings"]


@pytest.mark.asyncio
async def test_static_flow_dependency_graph_missing_files(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    monkeypatch.setattr(
        DependencyGraph,
        "validate_completeness",
        lambda self: [{"type": "missing"}],
    )
    monkeypatch.setattr(
        DependencyGraph,
        "get_missing_files",
        lambda self: ["app/__init__.py"],
    )
    monkeypatch.setattr(
        DependencyGraph,
        "add_missing_files",
        lambda self, architecture: architecture,
    )

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert (tmp_path / "app" / "__init__.py").exists()


@pytest.mark.asyncio
async def test_static_flow_dependency_graph_missing_files_raises_for_unfilled(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    monkeypatch.setattr(
        DependencyGraph,
        "validate_completeness",
        lambda self: [{"type": "missing"}],
    )
    monkeypatch.setattr(
        DependencyGraph,
        "get_missing_files",
        lambda self: ["app/unknown.xyz"],
    )
    monkeypatch.setattr(
        DependencyGraph,
        "add_missing_files",
        lambda self, architecture: architecture,
    )

    with pytest.raises(RuntimeError, match="dependency graph missing files were not generated"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_cross_validation_applies_fixes(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.cross.fixed = {"app/main.py": "def fixed():\n    return 1\n"}
    harness.cross.issues = [{"message": "consistency"}]
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert "consistency" in result["warnings"]


@pytest.mark.asyncio
async def test_static_flow_cross_validation_failure_propagates(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    _FakeCrossValidator.raise_validate = RuntimeError("cross down")

    with pytest.raises(RuntimeError, match="cross down"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_sandbox_failure_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(
        "app.agent.utils.validate_in_sandbox",
        lambda **kwargs: (False, ["boom"]),
    )

    async def no_fix(*_args, **_kwargs):
        return []

    harness._fix_sandbox_errors = no_fix

    with pytest.raises(RuntimeError, match="sandbox validation failed: boom"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_sandbox_fix_then_passes(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    outcomes = iter([(False, ["boom"]), (True, [])])
    monkeypatch.setattr(
        "app.agent.utils.validate_in_sandbox",
        lambda **kwargs: next(outcomes, (True, [])),
    )

    async def fix(*_args, **_kwargs):
        return ["app/main.py"]

    harness._fix_sandbox_errors = fix

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_flow_cache_save_failure_is_tolerated(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.spec_cache = _FakeSpecCache(fail_save=True)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_flow_architecture_check_failure_warns(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    _FakeArchitectureInspector.passed = False
    _FakeArchitectureInspector.violations = ["a", "b"]

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert any("架构检查发现问题" in warning for warning in result["warnings"])


class _CtxStub:
    def __init__(self, files=None, contents=None):
        self.files = dict(files or {})
        self.contents = dict(contents or {})
        self.errors = []

    def get_file_content(self, path):
        return self.contents.get(path, "")

    def save_file_content(self, path, content, _model):
        self.files[path] = SimpleNamespace(file_type="entry", generated_by="engineer")
        self.contents[path] = content

    def add_error(self, error):
        self.errors.append(error)

    def update_file_validation(self, *_args, **_kwargs):
        pass

    def set_metric(self, *_args, **_kwargs):
        pass

    def get_metric(self, *_args, **_kwargs):
        return None

    def to_export_dict(self):
        return {}

    def get_summary(self):
        return {}


class _DynamicGraph:
    def __init__(self, nodes=None, missing=None, completeness=None):
        self.nodes = dict(nodes or {
            "app/main.py": SimpleNamespace(file_type="entry", description="entry", priority=3)
        })
        self.adjacency = {}
        self.missing = missing or []
        self.completeness = completeness or []

    def get_generation_layers(self):
        return [["app/main.py"]]

    def get_unknown_type_files(self):
        return []

    def validate_completeness(self):
        return self.completeness

    def get_missing_files(self):
        return self.missing

    def add_missing_files(self, architecture):
        return architecture

    def remove_node(self, _path):
        return True

    def get_context_for_file(self, *_args, **_kwargs):
        return ""

    def save(self, *_args, **_kwargs):
        pass


async def _run_dynamic(
    harness,
    monkeypatch,
    ctx=None,
    graph=None,
    after_patch=None,
    architecture=None,
    adapter=None,
    allow_plan_expansion=True,
):
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(module, "TopologyScheduler", _FakeScheduler)
    _FakeScheduler.failed = []
    if after_patch:
        after_patch()
    graph = graph or _DynamicGraph()
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


@pytest.mark.asyncio
async def test_dynamic_flow_removes_language_mismatch_file(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    target = tmp_path / "app" / "legacy.js"
    target.parent.mkdir(parents=True)
    target.write_text("let a = 1;\n", encoding="utf-8")
    ctx = _CtxStub(
        files={"app/legacy.js": SimpleNamespace(generated_by="engineer", file_type="entry")},
        contents={"app/legacy.js": "let a = 1;\n"},
    )

    result = await _run_dynamic(harness, monkeypatch, ctx=ctx)

    assert not target.exists()
    assert "app/legacy.js" not in ctx.files
    assert result["files_generated"] == 0


@pytest.mark.asyncio
async def test_dynamic_flow_renames_file_with_spaces(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    target = tmp_path / "app" / "bad name.py"
    target.parent.mkdir(parents=True)
    target.write_text("a = 1\n", encoding="utf-8")
    ctx = _CtxStub(
        files={"app/bad name.py": SimpleNamespace(generated_by="engineer", file_type="entry")},
        contents={"app/bad name.py": "a = 1\n"},
    )

    await _run_dynamic(harness, monkeypatch, ctx=ctx)

    assert (tmp_path / "app" / "badname.py").exists()
    assert "app/badname.py" in ctx.files
    assert "app/bad name.py" not in ctx.files


@pytest.mark.asyncio
async def test_dynamic_flow_removes_identical_duplicate(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    for name in ("app/main.py", "main.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("a = 1\n", encoding="utf-8")
    ctx = _CtxStub(
        files={
            "app/main.py": SimpleNamespace(generated_by="engineer", file_type="entry"),
            "main.py": SimpleNamespace(generated_by="engineer", file_type="entry"),
        },
        contents={"app/main.py": "a = 1\n", "main.py": "a = 1\n"},
    )

    await _run_dynamic(harness, monkeypatch, ctx=ctx)

    assert not (tmp_path / "main.py").exists()
    assert "main.py" not in ctx.files


@pytest.mark.asyncio
async def test_dynamic_flow_integrity_fixes_and_unfilled_missing_raises(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _FakeIntegrityValidator.passed = False
    _FakeIntegrityValidator.error_count = 1
    _FakeIntegrityValidator.issues = [SimpleNamespace(severity="error", message="missing init")]
    _FakeIntegrityValidator.fixes = {"app/__init__.py": "# init\n"}
    graph = _DynamicGraph(missing=["app/unknown.xyz"], completeness=[{"type": "missing"}])

    with pytest.raises(RuntimeError, match="dependency graph missing files were not generated"):
        await _run_dynamic(harness, monkeypatch, graph=graph)

    assert (tmp_path / "app" / "__init__.py").exists()


@pytest.mark.asyncio
async def test_dynamic_flow_adapter_owned_file_skips_review(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)

    result = await _run_dynamic(
        harness,
        monkeypatch,
        after_patch=lambda: monkeypatch.setattr(
            module, "_is_adapter_owned_file", lambda *a, **k: True
        ),
    )

    assert result["files_generated"] >= 1
    assert harness.refinement.calls == 0


@pytest.mark.asyncio
async def test_dynamic_flow_critical_cross_validation_uses_alternative(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"

    result = await _run_dynamic(harness, monkeypatch)

    assert result["files_generated"] >= 1
    assert harness.cross.calls


@pytest.mark.asyncio
async def test_dynamic_flow_critical_without_reviewer_model_fails_file(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"
    harness.model_assignment.reviewer_model = None

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(harness, monkeypatch)


@pytest.mark.asyncio
async def test_dynamic_flow_critical_cross_validation_error_fails_file(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"
    _FakeCrossValidator.raise_cross = RuntimeError("judge down")

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(harness, monkeypatch)


@pytest.mark.asyncio
async def test_dynamic_flow_critical_empty_alternative_falls_back_to_refine(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"
    harness._select_engineer_for_model = lambda _model: _Engineer(content="")

    result = await _run_dynamic(harness, monkeypatch)

    assert result["files_generated"] >= 1
    assert harness.refinement.calls >= 1


@pytest.mark.asyncio
async def test_dynamic_flow_quality_retry_succeeds(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    quality = iter(["leak", ""])

    result = await _run_dynamic(
        harness,
        monkeypatch,
        after_patch=lambda: monkeypatch.setattr(
            "app.agent.utils.validate_content_quality",
            lambda *a, **k: next(quality, ""),
        ),
    )

    assert result["files_generated"] >= 1
    assert harness.engineer.calls >= 2


@pytest.mark.asyncio
async def test_dynamic_flow_quality_retry_failure_marks_file_failed(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    harness.engineer.content = ""

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(
            harness,
            monkeypatch,
            after_patch=lambda: monkeypatch.setattr(
                "app.agent.utils.validate_content_quality",
                lambda *a, **k: "leak",
            ),
        )


@pytest.mark.asyncio
async def test_dynamic_flow_error_recovery_repairs_syntax(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    harness.syntax_ok = False

    class _Recovery:
        async def validate_and_fix(self, **kwargs):
            return True, "def fixed():\n    return 1\n"

    harness.error_recovery = _Recovery()

    result = await _run_dynamic(harness, monkeypatch)

    assert result["files_generated"] >= 1


@pytest.mark.asyncio
async def test_dynamic_flow_removes_stale_tmp_file(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    target = tmp_path / "app" / "main.py"
    target.parent.mkdir(parents=True)
    (tmp_path / "app" / "main.py.tmp").write_text("old", encoding="utf-8")

    result = await _run_dynamic(harness, monkeypatch)

    assert result["files_generated"] >= 1
    assert not (tmp_path / "app" / "main.py.tmp").exists()


# ---------------------------------------------------------------------------
# 静态流程剩余分支
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_static_flow_loads_dependency_graph_from_cache(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    cached = SimpleNamespace(
        requirement_hash="hash",
        specs={"openapi": {"paths": {}}},
        architecture={
            "language": "python",
            "file_plan": [{"path": "app/main.py", "file_type": "entry"}],
        },
        file_plan=[{"path": "app/main.py", "file_type": "entry"}],
        dependency_graph={"nodes": {"app/main.py": {}}, "adjacency": {}},
    )
    harness = _Harness(tmp_path)
    harness.spec_cache = _FakeSpecCache(cached=cached)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    loaded = []
    monkeypatch.setattr(
        DependencyGraph,
        "from_dict",
        classmethod(lambda cls, data, language_adapter=None: _cache_graph(loaded)),
    )

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert loaded


def _cache_graph(_loaded):
    from app.agent.dependency_graph import DependencyGraph

    graph = DependencyGraph()
    graph.add_file("app/main.py", file_type="entry")
    _loaded.append(True)
    return graph


@pytest.mark.asyncio
async def test_static_flow_string_tech_stack_and_constraint_prompt(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)

    async def design(requirement, complexity, callback=None):
        return {
            "language": "python",
            "project_type": "backend",
            "tech_stack": "FastAPI",
            "file_plan": [{"path": "app/main.py", "file_type": "entry", "description": "entry"}],
        }

    harness.architect.design_architecture = design
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    class _Parser:
        def parse_requirement(self, _requirement):
            return {}

        def get_constraints_summary(self):
            return {}

        def generate_prompt_fragment(self, *_args):
            return "constraints"

    monkeypatch.setattr(module, "GlobalConstraintParser", _Parser)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_flow_empty_decision_response_warns(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    class _Decision:
        def extract_from_architecture(self, *_args):
            return []

        def format_as_questions(self):
            return [{"id": "auth"}]

        def apply_user_choice(self, *_args):
            pass

        def get_all_choices(self):
            return {}

        def skip_remaining_decisions(self):
            pass

    async def empty(_questions):
        return {}

    harness.decision_callback = empty
    monkeypatch.setattr(module, "CriticalDecisionExtractor", _Decision)
    monkeypatch.setattr(module, "should_skip_user_decision", lambda *a, **k: False)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert any("user decision was empty" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_static_flow_blocked_by_unready_dependencies(tmp_path, monkeypatch):
    from app.agent.shared_context import SharedContext

    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(SharedContext, "are_dependencies_ready", lambda self, _path: False)

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_critical_alt_requires_reviewer_model(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"
    harness.model_assignment.reviewer_model = None

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_review_timeout_is_logged_and_reraised(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    async def boom(**_kwargs):
        raise RuntimeError("timeout")

    harness.refinement.refine = boom
    monkeypatch.setattr(
        "app.agent.cross_validator.is_review_timeout",
        lambda _exc: True,
    )

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_cross_validation_timeout_is_logged(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    harness.cross.critical = True
    harness._select_alternative_model = lambda _primary: "alt-model"
    _FakeCrossValidator.raise_cross = RuntimeError("timeout")
    monkeypatch.setattr(
        "app.agent.cross_validator.is_review_timeout",
        lambda _exc: True,
    )

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_quality_retry_still_bad_raises(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(
        "app.agent.utils.validate_content_quality",
        lambda *a, **k: "leak",
    )

    with pytest.raises(RuntimeError, match="content quality validation failed"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_cancelled_result_is_counted(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    async def cancelled(*_args, **_kwargs):
        return [asyncio.CancelledError()]

    monkeypatch.setattr(module, "gather_with_limit", cancelled)

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_unsuccessful_result_is_counted(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    async def unsuccessful(*_args, **_kwargs):
        return [{"success": False, "path": "app/main.py"}]

    monkeypatch.setattr(module, "gather_with_limit", unsuccessful)

    with pytest.raises(RuntimeError, match="file generation failed"):
        await harness.generate_with_spec_first("做一个后端服务")


@pytest.mark.asyncio
async def test_static_flow_symbol_table_issues_are_warned(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(
        "app.agent.symbol_table.remember_generated_file",
        lambda *a, **k: ["duplicate symbol"],
    )

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert "duplicate symbol" in result["warnings"]


@pytest.mark.asyncio
async def test_static_flow_forced_count_disables_expansion(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_FORCE_FILE_COUNT", "8")
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    _FakeIntegrityValidator.passed = False
    _FakeIntegrityValidator.error_count = 1
    _FakeIntegrityValidator.issues = [SimpleNamespace(severity="error", message="bad init")]
    _FakeIntegrityValidator.fixes = {"app/__init__.py": "# init\n"}

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert not (tmp_path / "app" / "__init__.py").exists()


@pytest.mark.asyncio
async def test_static_flow_missing_file_already_generated_is_skipped(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(
        DependencyGraph,
        "validate_completeness",
        lambda self: [{"type": "missing"}],
    )
    monkeypatch.setattr(
        DependencyGraph,
        "get_missing_files",
        lambda self: ["app/main.py"],
    )
    monkeypatch.setattr(
        DependencyGraph,
        "add_missing_files",
        lambda self, architecture: architecture,
    )

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_flow_skips_cross_validation_without_model_assignment(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    original_select = harness._select_engineer

    def select(_path):
        harness.model_assignment = None
        return original_select(_path)

    harness._select_engineer = select

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_flow_cross_validation_same_content_not_rewritten(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.cross.fixed = {"app/main.py": "def main():\n    return 1\n"}
    harness.cross.issues = [{"message": "same"}]
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True


@pytest.mark.asyncio
async def test_static_flow_saves_to_memory_when_enabled(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    harness.memory_enabled = True
    saved = []

    async def save(*args, **kwargs):
        saved.append(True)

    harness._save_to_memory = save
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert saved


# ---------------------------------------------------------------------------
# 收尾分支补充
# ---------------------------------------------------------------------------


class _SequenceEngineer(_Engineer):
    def __init__(self, contents):
        super().__init__()
        self.contents = list(contents)

    async def generate_file(self, *_args, **_kwargs):
        self.calls += 1
        if self.contents:
            return self.contents.pop(0)
        return ""


class _Tracker:
    def __init__(self):
        self.touches = 0

    def touch(self):
        self.touches += 1


@pytest.mark.asyncio
async def test_static_flow_cancel_before_first_layer_skips_all(tmp_path, monkeypatch):
    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)

    class _AlwaysCancel:
        def is_set(self):
            return True

    harness.cancel_event = _AlwaysCancel()

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert result["total_files_created"] == 0


@pytest.mark.asyncio
async def test_static_flow_unsuccessful_refinement_warns(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)

    class _FailedRefinement(_FakeRefinementLoop):
        async def refine(self, **kwargs):
            return _result(kwargs["initial_content"], success=False)

    result = await _run_dynamic(
        harness,
        monkeypatch,
        after_patch=lambda: setattr(harness, "refinement", _FailedRefinement()),
    )

    assert any("文件验证未完全通过" in warning for warning in result["warnings"])


@pytest.mark.asyncio
async def test_dynamic_flow_read_failure_regenerates(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    target = tmp_path / "app" / "main.py"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"\xff\xfe")

    result = await _run_dynamic(harness, monkeypatch)

    assert result["files_generated"] >= 1


@pytest.mark.asyncio
async def test_dynamic_flow_recovers_invalid_initial_content(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    recovered = []

    async def recover(*_args, **_kwargs):
        recovered.append(True)
        return "def recovered():\n    return 1\n"

    harness._recover_invalid_content = recover

    result = await _run_dynamic(
        harness,
        monkeypatch,
        after_patch=lambda: monkeypatch.setattr(
            module, "extract_engineer_content", lambda *a, **k: _async_none()
        ),
    )

    assert result["files_generated"] >= 1
    assert recovered


@pytest.mark.asyncio
async def test_dynamic_flow_retries_after_recover_failure(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    retried = []

    async def no_recover(*_args, **_kwargs):
        return None

    async def retry(*_args, **_kwargs):
        retried.append(True)
        return "def retried():\n    return 1\n"

    harness._recover_invalid_content = no_recover
    harness._retry_generate_file = retry

    result = await _run_dynamic(
        harness,
        monkeypatch,
        after_patch=lambda: monkeypatch.setattr(
            module, "extract_engineer_content", lambda *a, **k: _async_none()
        ),
    )

    assert result["files_generated"] >= 1
    assert retried


@pytest.mark.asyncio
async def test_dynamic_flow_all_recovery_attempts_fail(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)

    async def no_recover(*_args, **_kwargs):
        return None

    async def no_retry(*_args, **_kwargs):
        return None

    harness._recover_invalid_content = no_recover
    harness._retry_generate_file = no_retry

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(
            harness,
            monkeypatch,
            after_patch=lambda: monkeypatch.setattr(
                module, "extract_engineer_content", lambda *a, **k: _async_none()
            ),
        )


@pytest.mark.asyncio
async def test_dynamic_flow_critical_without_alternative_degrades(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)

    result = await _run_dynamic(
        harness,
        monkeypatch,
        after_patch=lambda: setattr(harness.cross, "critical", True),
    )

    assert result["files_generated"] >= 1
    assert any(event[0] == "cross_validation_skipped" for event in harness.progress_events)


@pytest.mark.asyncio
async def test_dynamic_flow_alternative_uses_edited_file_content(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    alt = _Engineer(content="from disk\n")
    alt.edited_files = ["app/main.py"]

    def select_alt(_primary):
        return "alt-model"

    def after_patch():
        harness.cross.critical = True
        harness._select_alternative_model = select_alt
        harness._select_engineer_for_model = lambda _model: alt

    result = await _run_dynamic(harness, monkeypatch, after_patch=after_patch)

    assert result["files_generated"] >= 1


@pytest.mark.asyncio
async def test_dynamic_flow_alternative_empty_refine_timeout(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    alt = _Engineer(content="")

    async def boom(**_kwargs):
        raise RuntimeError("timeout")

    def after_patch():
        harness.cross.critical = True
        harness._select_alternative_model = lambda _primary: "alt-model"
        harness._select_engineer_for_model = lambda _model: alt
        harness.refinement.refine = boom
        monkeypatch.setattr(
            "app.agent.cross_validator.is_review_timeout", lambda _exc: True
        )

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(harness, monkeypatch, after_patch=after_patch)


@pytest.mark.asyncio
async def test_dynamic_flow_non_critical_review_timeout(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)

    async def boom(**_kwargs):
        raise RuntimeError("timeout")

    def after_patch():
        harness.refinement.refine = boom
        monkeypatch.setattr(
            "app.agent.cross_validator.is_review_timeout", lambda _exc: True
        )

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(harness, monkeypatch, after_patch=after_patch)


@pytest.mark.asyncio
async def test_dynamic_flow_empty_quality_retry_falls_back(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    harness.engineer = _SequenceEngineer(["def ok():\n    return 1\n", ""])

    quality = iter(["leak", ""])

    result = await _run_dynamic(
        harness,
        monkeypatch,
        after_patch=lambda: monkeypatch.setattr(
            "app.agent.utils.validate_content_quality",
            lambda *a, **k: next(quality, ""),
        ),
    )

    assert result["files_generated"] >= 1


@pytest.mark.asyncio
async def test_dynamic_flow_quality_retry_fallback_failure_raises(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)

    async def no_retry(*_args, **_kwargs):
        return None

    harness._retry_generate_file = no_retry

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(
            harness,
            monkeypatch,
            after_patch=lambda: monkeypatch.setattr(
                "app.agent.utils.validate_content_quality",
                lambda *a, **k: "leak",
            ),
        )


@pytest.mark.asyncio
async def test_dynamic_flow_remaining_quality_after_successful_retry_raises(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    quality = iter(["leak", "", "still"])

    with pytest.raises(RuntimeError, match="file generation failed for 1 file"):
        await _run_dynamic(
            harness,
            monkeypatch,
            after_patch=lambda: monkeypatch.setattr(
                "app.agent.utils.validate_content_quality",
                lambda *a, **k: next(quality, ""),
            ),
        )


# ---------------------------------------------------------------------------
# 细分支补充
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dynamic_flow_without_adapter_skips_language_cleanup(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    ctx = _CtxStub(
        files={"app/legacy.js": SimpleNamespace(generated_by="engineer", file_type="entry")},
        contents={"app/legacy.js": "let a = 1;\n"},
    )

    result = await _run_dynamic(harness, monkeypatch, ctx=ctx, adapter=False)

    assert result["files_generated"] >= 1
    assert "app/legacy.js" in ctx.files


@pytest.mark.asyncio
async def test_dynamic_flow_skips_non_dict_file_plan_entries(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    architecture = {
        "language": "python",
        "file_plan": ["bad", {"path": "README"}, {"no_path": True}, {"path": "app/main.py"}],
    }
    ctx = _CtxStub(
        files={"app/legacy.js": SimpleNamespace(generated_by="engineer", file_type="entry")},
        contents={"app/legacy.js": "let a = 1;\n"},
    )

    await _run_dynamic(harness, monkeypatch, ctx=ctx, architecture=architecture)

    assert "app/legacy.js" not in ctx.files


@pytest.mark.asyncio
async def test_dynamic_flow_missing_file_already_generated_is_skipped(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    graph = _DynamicGraph(missing=["app/main.py"], completeness=[{"type": "missing"}])
    ctx = _CtxStub(
        files={"app/main.py": SimpleNamespace(generated_by="engineer", file_type="entry")},
        contents={"app/main.py": "a = 1\n"},
    )

    result = await _run_dynamic(harness, monkeypatch, ctx=ctx, graph=graph)

    assert result["files_generated"] >= 1


@pytest.mark.asyncio
async def test_dynamic_flow_integrity_fixes_skipped_when_not_expandable(tmp_path, monkeypatch):
    harness = _dynamic_harness(tmp_path)
    _FakeIntegrityValidator.passed = False
    _FakeIntegrityValidator.error_count = 1
    _FakeIntegrityValidator.issues = [SimpleNamespace(severity="error", message="bad init")]
    _FakeIntegrityValidator.fixes = {"app/__init__.py": "# init\n"}

    result = await _run_dynamic(harness, monkeypatch, allow_plan_expansion=False)

    assert result["files_generated"] >= 1
    assert not (tmp_path / "app" / "__init__.py").exists()


@pytest.mark.asyncio
async def test_static_flow_infers_unknown_file_types(tmp_path, monkeypatch):
    from app.agent.dependency_graph import DependencyGraph

    harness = _Harness(tmp_path)
    _patch_generation_collaborators(monkeypatch, harness)
    _fake_integrity(monkeypatch)
    monkeypatch.setattr(
        DependencyGraph,
        "get_unknown_type_files",
        lambda self: ["app/odd.xyz"],
    )
    calls = []

    async def infer(_graph, unknown_files, _architecture, _language):
        calls.append(list(unknown_files))

    harness._infer_unknown_file_types = infer

    result = await harness.generate_with_spec_first("做一个后端服务")

    assert result["success"] is True
    assert calls == [["app/odd.xyz"]]


@pytest.mark.asyncio
async def test_retry_generate_file_tracker_and_language_failure(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = lambda _prompt: _async_yes()
    monkeypatch.setattr(
        "app.agent.utils.validate_language_with_llm",
        lambda *a, **k: _async_tuple(False, "wrong"),
    )
    tracker = _Tracker()

    with pytest.raises(RuntimeError, match="file generation retry failed"):
        await harness._retry_generate_file(
            "app/main.py",
            "entry",
            {"architecture": {"language": "python"}},
            "",
            "",
            _Engineer(),
            None,
            heartbeat_tracker=tracker,
        )

    assert tracker.touches > 0


@pytest.mark.asyncio
async def test_recover_invalid_content_tracker_and_write_failure(monkeypatch):
    harness = _Harness(Path("/tmp"))
    harness._quick_llm_check = None
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.is_placeholder_content", lambda *a: (False, ""))
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: False)
    tracker = _Tracker()

    content = await harness._recover_invalid_content(
        "app/main.py",
        "entry",
        {"architecture": {"language": "python"}},
        "other",
        _Engineer(),
        heartbeat_tracker=tracker,
        persist=True,
    )

    assert content is None
    assert tracker.touches > 0


@pytest.mark.asyncio
async def test_fix_sandbox_errors_nested_import_and_no_match_second_round(monkeypatch, tmp_path):
    harness = _Harness(tmp_path)
    calls = []

    async def fake_call_llm(**_kwargs):
        calls.append(True)
        return {"choices": [{"message": {"content": "def main():\n    return 1\n"}}]}

    monkeypatch.setattr("app.utils.aicloud.llm_caller.call_llm", fake_call_llm)
    monkeypatch.setattr("app.agent.utils.is_valid_code_content", lambda *a: (True, ""))
    monkeypatch.setattr("app.agent.utils.write_file_atomic", lambda *a, **k: True)
    outcomes = iter([(False, ["no structured error"]), (False, ["still bad"])])
    monkeypatch.setattr(
        "app.agent.utils.validate_in_sandbox",
        lambda **kwargs: next(outcomes, (False, ["still bad"])),
    )

    fixed = await harness._fix_sandbox_errors(
        ["app/main.py: Import Error: NameError: missing"],
        {"app/main.py": "x = 1\n"},
        SimpleNamespace(save_file_content=lambda *a, **k: None),
        max_rounds=2,
    )

    assert fixed == []
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_quick_llm_check_returns_stripped_response(monkeypatch):
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    harness = _Harness(Path("/tmp"))

    class _Client:
        def __init__(self, **_kwargs):
            pass

        async def call(self, *_args):
            return "  YES  "

    monkeypatch.setattr("app.agent.llm_client.LLMClient", _Client)

    assert await SpecFirstGenerateMixin._quick_llm_check(harness, "prompt") == "YES"


def test_validate_content_syntax_js_logs_error(monkeypatch):
    harness = _Harness(Path("/tmp"))
    from app.agent.orchestrator_generation.spec_first_generate import (
        SpecFirstGenerateMixin,
    )

    monkeypatch.setattr(module, "_shared_check_js_source", lambda src: (False, "syntax"))

    assert SpecFirstGenerateMixin._check_js_source(harness, "let =") is False
