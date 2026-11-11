"""TraditionalGenerateMixin 主流程的分支覆盖测试。"""

import types

import pytest

from app.agent.orchestrator_generation import traditional_generate as tg
from app.agent.orchestrator_generation.traditional_generate import (
    TraditionalGenerateMixin,
)


class _FakeDepGraph:
    def __init__(self, language_adapter=None):
        self.language_adapter = language_adapter
        self.nodes = {}
        self.adjacency = {}
        self.generation_plan = None

    def build_from_architecture(self, _architecture):
        return None

    def get_generation_layers(self):
        return []

    def add_file(self, path, priority=3):
        self.nodes[path] = priority


class _FakeSharedContext:
    def __init__(self, _requirement, _output_dir):
        self.session_id = "generated-session"
        self.registered = []

    def register_file(self, path, file_type):
        self.registered.append((path, file_type))


class _FakeCommitter:
    def __init__(self, output_dir, shared_context, task_id):
        self.output_dir = output_dir
        self.shared_context = shared_context
        self.task_id = task_id


class _FakeEnvelope:
    def model_dump(self, mode="json"):
        return {"mode": mode}


class _FakeAssembler:
    def assemble(self, **_kwargs):
        return _FakeEnvelope()


class _FakeIntegrityValidator:
    def __init__(self, language_adapter=None):
        self.language_adapter = language_adapter

    def validate(self, _files):
        return types.SimpleNamespace(passed=False)

    def generate_fixes(self, _result, _files):
        return {"app/__init__.py": ""}


class _FakeAdapterRegistry:
    calls = []

    @classmethod
    def get_adapter(cls, language):
        cls.calls.append(language)
        return object()


class _Association:
    def __init__(self, skipped=False, enhanced="enhanced", domain="web"):
        self.skipped = skipped
        self.enhanced_requirement = enhanced
        self.domain_matched = domain


def _patch_collaborators(
    monkeypatch, *, integrity_passed=True, sandbox=(True, []), stub_complete=True
):
    monkeypatch.setattr(tg, "DependencyGraph", _FakeDepGraph)
    monkeypatch.setattr(tg, "get_embedding", _embedding)
    monkeypatch.setattr(
        "app.agent.profile_discovery.profile_context", lambda _dir: {"language": "python"}
    )
    monkeypatch.setattr("app.agent.context_assembler.ContextAssembler", _FakeAssembler)
    monkeypatch.setattr(
        "app.agent.orchestration.artifact_committer.ArtifactCommitter", _FakeCommitter
    )
    monkeypatch.setattr("app.agent.shared_context.SharedContext", _FakeSharedContext)
    monkeypatch.setattr(
        "app.agent.adapters.language_adapter.LanguageAdapterRegistry", _FakeAdapterRegistry
    )
    monkeypatch.setattr(
        "app.agent.integrity_validator.IntegrityValidator", _FakeIntegrityValidator
    )
    monkeypatch.setattr("app.agent.utils.validate_in_sandbox", lambda **_kwargs: sandbox)
    if stub_complete:
        monkeypatch.setattr(
            "app.agent.orchestrator_generation.spec_first_generate._require_project_complete",
            lambda _completeness: None,
        )


async def _embedding(_requirement):
    return [0.1, 0.2]


class _BaseOrchestrator(TraditionalGenerateMixin):
    def __init__(self, output_dir, *, incremental=False, spec_cache=None):
        self.output_dir = output_dir
        self.incremental = incremental
        self.spec_cache = spec_cache
        self.reviewer = None
        self.generated_files = []
        self.errors = []
        self.warnings = []
        self._generated_contents = {}
        self._association_result = _Association()
        self.require_approval = False
        self.approval_callback = None
        self.session_manager = None
        self.session_id = None
        self.api_contract_checker = None
        self.memory_enabled = False
        self.enable_validation = False
        self.feedback_learner = None
        self.model_assignment = None
        self.complexity = types.SimpleNamespace(
            level=types.SimpleNamespace(value="medium"), estimated_files=3
        )
        self.architect = types.SimpleNamespace(
            design_architecture=self._design,
            expand_file_plan=self._expand,
        )
        self.validator = types.SimpleNamespace(run_full_validation=self._validate)
        self.progress = []
        self.thinking = []
        self.cache_review_result = True
        self.cache_specs_calls = []
        self.learning_calls = []
        self.extracted_domain = []
        self.dynamic_results = {"success": True, "message": "ok"}
        self.react_result = None
        self.coverage_check = {"checked": False}
        self.feature_error = None
        self.completeness = {
            "total_planned": 1,
            "total_generated": 1,
            "missing_files": [],
            "empty_files": [],
            "invalid_files": [],
            "is_complete": True,
        }
        self.final_validation = {"is_valid": True}
        self.small_calls = []
        self.layer_calls = []
        self.incremental_calls = []
        self.snapshot_messages = []
        self.cost_summary = {"total": 1.5}
        self.error_recovery = None
        self.files_to_generate = []

    async def _initialize_components(self, _requirement):
        return None

    async def _generate_requirement_associations(self, _requirement, _level):
        return self._association_result

    async def _design(self, _requirement, _complexity, callback=None):
        return {
            "file_plan": [
                {"path": "main.py"},
                {"path": "util.py"},
                {"path": "app/__init__.py"},
            ],
            "project_type": "cli",
            "tech_stack": ["python", "pytest"],
            "language": "python",
        }

    async def _expand(self, architecture, _complexity, target_file_count=0, target_language=None):
        architecture = dict(architecture)
        architecture["file_plan"] = [
            {"path": f"mod{i}.py"} for i in range(target_file_count)
        ]
        return architecture

    async def _validate(self):
        return self.final_validation

    async def _handle_incremental_generation(self, requirement, file_plan, ctx, total):
        self.incremental_calls.append((requirement, file_plan, ctx, total))

    async def _generate_files_by_dep_layers(self, file_plan, ctx, total, graph):
        self.layer_calls.append((file_plan, ctx, total, graph))
        self._emit_files()

    async def _generate_files_small_project(self, file_plan, ctx, total):
        self.small_calls.append((file_plan, ctx, total))
        self._emit_files()

    def _emit_files(self):
        for entry in self.files_to_generate:
            path = self.output_dir / entry["path"]
            if entry.get("write", True):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("print('generated')\n", encoding="utf-8")
            self.generated_files.append(dict(entry))

    async def _run_dynamic_tests(self, _runner):
        return self.dynamic_results

    async def _try_react_auto_fix(self, _results):
        return self.react_result

    async def _save_to_memory(self, _requirement, _architecture):
        return None

    async def _cache_specs(self, requirement, architecture, file_plan, vector):
        self.cache_specs_calls.append((requirement, architecture, file_plan, vector))

    async def _record_learning_data(self, requirement, architecture, file_plan):
        self.learning_calls.append((requirement, architecture, file_plan))

    async def _git_save_snapshot(self, message):
        self.snapshot_messages.append(message)

    async def _extract_and_save_feature_list(self, requirement, files, domain=""):
        if self.feature_error:
            raise self.feature_error
        self.extracted_domain.append(domain)
        return None

    def _report_progress(self, step, current, total, callback=None, **kwargs):
        self.progress.append((step, current, total, kwargs))

    def _report_thinking(self, agent, message, **kwargs):
        self.thinking.append((agent, message))

    def _report_current_cost(self):
        return None

    def _report_final_metrics(self):
        return None

    def _validate_file_plan(self, file_plan):
        return file_plan

    def _estimate_generation_cost(self, _architecture, file_plan):
        return {
            "estimated_tokens": 100,
            "estimated_cost_usd": 0.3,
            "cost_level": "high",
            "suggestion": "split it",
            "estimated_files": len(file_plan),
        }

    async def _wait_for_approval(self, _key, timeout=300.0):
        return True

    async def _cache_review_gate(self, _cached):
        return self.cache_review_result

    async def _validate_project_completeness_traditional(self, _plan, _files):
        return self.completeness

    def _check_requirement_coverage(self, _requirement, _architecture, _plan):
        return self.coverage_check


def _cache(requirement="req", architecture=None):
    return types.SimpleNamespace(
        requirement=requirement,
        requirement_hash="hash-1",
        specs={"main.py": "spec"},
        architecture=architecture
        or {
            "file_plan": [{"path": "main.py"}],
            "project_type": "cli",
            "tech_stack": ["python"],
            "language": "python",
        },
        file_plan=[{"path": "main.py"}],
    )


class _SpecCache:
    def __init__(self, cached=None):
        self.cached = cached

    def lookup(self, _requirement, requirement_vector=None):
        self.vector = requirement_vector
        return self.cached


class TestCacheAndApproval:
    @pytest.mark.asyncio
    async def test_cache_hit_denied_high_cost_returns_early(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path, spec_cache=_SpecCache(_cache()))
        orchestrator.require_approval = True
        approved = []

        async def deny(key, timeout=300.0):
            approved.append(key)
            return False

        orchestrator._wait_for_approval = deny

        result = await orchestrator._generate_traditional("build a cli")

        assert result["success"] is False
        assert result["cancelled_by_user"] is True
        assert result["reason"] == "cost_too_high"
        assert approved == ["cost_estimation"]
        assert any(step == "cache_loaded" for step, *_ in orchestrator.progress)
        assert "用户拒绝高成本生成，已取消" in orchestrator.warnings
        assert orchestrator.small_calls == []

    @pytest.mark.asyncio
    async def test_cache_hit_blocked_by_review_regenerates(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path, spec_cache=_SpecCache(_cache()))
        orchestrator.reviewer = object()
        orchestrator.cache_review_result = False
        orchestrator._estimate_generation_cost = lambda a, f: {
            "estimated_tokens": 1,
            "estimated_cost_usd": 0.001,
            "cost_level": "low",
            "suggestion": "go",
        }

        result = await orchestrator._generate_traditional("build a cli")

        assert result["success"] is True
        assert "缓存命中但审查闸门拦截，重新生成" in orchestrator.warnings
        assert orchestrator.small_calls
        assert any(step == "cache_hit" for step, *_ in orchestrator.progress)

    @pytest.mark.asyncio
    async def test_embedding_failure_degrades_to_keyword_lookup(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        warnings = []

        async def broken(_requirement):
            raise RuntimeError("embedding offline")

        monkeypatch.setattr(tg, "get_embedding", broken)
        monkeypatch.setattr(tg.logger, "warning", lambda message: warnings.append(message))
        cache = _SpecCache(None)
        orchestrator = _BaseOrchestrator(tmp_path, spec_cache=cache)
        orchestrator._estimate_generation_cost = lambda a, f: {
            "estimated_tokens": 1,
            "estimated_cost_usd": 0.001,
            "cost_level": "low",
            "suggestion": "go",
        }

        await orchestrator._generate_traditional("build a cli")

        assert any("BCE Embedding 失败" in message for message in warnings)
        assert cache.vector is None


class TestFullGeneration:
    @pytest.mark.asyncio
    async def test_full_success_records_all_artifacts(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch, sandbox=(False, ["sandbox warning"]))
        orchestrator = _BaseOrchestrator(tmp_path, spec_cache=_SpecCache(None))
        orchestrator.incremental = False
        orchestrator.memory_enabled = True
        orchestrator.enable_validation = True
        orchestrator.feedback_learner = object()
        orchestrator.complexity = types.SimpleNamespace(
            level=types.SimpleNamespace(value="medium"), estimated_files=3
        )
        orchestrator.model_assignment = types.SimpleNamespace(
            architect_model="a",
            frontend_model="f",
            backend_model="b",
            reviewer_model="r",
        )
        orchestrator.dynamic_results = {"success": False, "summary": "1 failed"}
        orchestrator.react_result = {
            "fixed": True,
            "test_results": {"success": True, "message": "fixed"},
        }
        orchestrator.coverage_check = {
            "checked": True,
            "coverage_rate": 0.5,
            "uncovered": [{"item": "login"}, {"item": "logout"}],
        }
        orchestrator.feature_error = RuntimeError("extractor down")
        orchestrator.files_to_generate = [
            {"path": "main.py", "description": "entry", "success": True},
        ]
        orchestrator.error_recovery = types.SimpleNamespace(
            fix_history=[
                types.SimpleNamespace(
                    file_path="main.py", attempts=2, fix_applied=True, model_used="m"
                ),
                types.SimpleNamespace(file_path="util.py", attempts=1, fix_applied=False),
            ]
        )
        orchestrator.cost_tracker = types.SimpleNamespace(
            get_summary=lambda: orchestrator.cost_summary
        )

        result = await orchestrator._generate_traditional("build a cli")

        assert result["success"] is True
        assert result["total_files_created"] == 2
        assert result["complexity"] == "medium"
        assert result["models_used"]["architect"] == "a"
        assert result["test_results"]["success"] is True
        assert result["cost"] == {"total": 1.5}
        assert result["fix_attempts"][0]["model_used"] == "m"
        assert result["fix_attempts"][1]["model_used"] is None
        assert result["performance"]["files_generated"] == 2
        assert result["requirement_coverage"]["coverage_rate"] == 0.5
        assert any("sandbox warning" in w for w in orchestrator.warnings)
        assert any("动态测试失败" in w for w in orchestrator.warnings)
        assert any("ReAct 自动修复已尝试应用" in w for w in orchestrator.warnings)
        assert any("需求覆盖率" in w for w in orchestrator.warnings)
        assert orchestrator.cache_specs_calls
        assert orchestrator.learning_calls
        assert orchestrator.snapshot_messages == ["Agent 生成: enhanced"]
        assert "app/__init__.py" in result["files"][-1]["path"]

    @pytest.mark.asyncio
    async def test_expanded_plan_uses_layered_generation(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path, spec_cache=None)
        orchestrator.complexity = types.SimpleNamespace(
            level=types.SimpleNamespace(value="large"), estimated_files=12
        )
        orchestrator._estimate_generation_cost = lambda a, f: {
            "estimated_tokens": 1,
            "estimated_cost_usd": 0.001,
            "cost_level": "low",
            "suggestion": "go",
        }

        result = await orchestrator._generate_traditional("build a cli")

        assert result["success"] is True
        assert len(orchestrator.layer_calls) == 1
        assert len(orchestrator.layer_calls[0][0]) == 12

    @pytest.mark.asyncio
    async def test_incremental_resumes_session_and_reads_backend_contract(
        self, tmp_path, monkeypatch
    ):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path, incremental=True)
        orchestrator.session_id = "s1"
        resumed = types.SimpleNamespace()
        created = []

        async def resume(_session_id):
            return resumed

        async def create(**kwargs):
            created.append(kwargs)
            return types.SimpleNamespace()

        orchestrator.session_manager = types.SimpleNamespace(
            resume_session=resume, create_session=create
        )
        orchestrator.api_contract_checker = object()
        (tmp_path / "service.py").write_text(
            "from fastapi import APIRouter\n"
            "router = APIRouter()\n\n"
            "@router.get('/users')\n"
            "async def list_users():\n"
            "    return []\n",
            encoding="utf-8",
        )
        (tmp_path / "__pycache__").mkdir()
        orchestrator.files_to_generate = [
            {"path": "main.py", "description": "entry", "success": True}
        ]

        result = await orchestrator._generate_traditional("add a helper")

        assert result["success"] is True
        assert orchestrator._session_state is resumed
        assert created == []
        assert orchestrator.incremental_calls
        ctx = orchestrator.incremental_calls[0][2]
        assert "users" in ctx["api_contract"]
        assert orchestrator.snapshot_messages == ["Agent 增量修改: enhanced"]

    @pytest.mark.asyncio
    async def test_incremental_without_session_state_creates_one(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path, incremental=True)
        orchestrator.session_id = "s1"
        orchestrator._association_result = _Association(skipped=True, enhanced=None)
        created = []

        async def resume(_session_id):
            return None

        async def create(**kwargs):
            created.append(kwargs)
            return types.SimpleNamespace()

        orchestrator.session_manager = types.SimpleNamespace(
            resume_session=resume, create_session=create
        )

        await orchestrator._generate_traditional("add a helper")

        assert created[0]["session_id"] == "s1"
        assert created[0]["requirement"] == "add a helper"

    @pytest.mark.asyncio
    async def test_new_session_is_created_when_not_incremental(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.session_id = "fresh"
        created = []

        async def create(**kwargs):
            created.append(kwargs)
            return types.SimpleNamespace()

        orchestrator.session_manager = types.SimpleNamespace(create_session=create)

        await orchestrator._generate_traditional("build a cli")

        assert created[0]["session_id"] == "fresh"


class TestValidationState:
    @pytest.mark.asyncio
    async def test_invalid_validation_skips_dynamic_tests(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.enable_validation = True
        orchestrator.final_validation = {"is_valid": False}

        result = await orchestrator._generate_traditional("build a cli")

        assert result["success"] is False
        assert result["test_results"]["success"] is True
        assert orchestrator.warnings == []

    @pytest.mark.asyncio
    async def test_incomplete_project_raises(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch, stub_complete=False)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.completeness = {
            "total_planned": 2,
            "total_generated": 1,
            "missing_files": ["util.py"],
            "empty_files": [],
            "invalid_files": [],
            "is_complete": False,
        }

        with pytest.raises(RuntimeError, match="project completeness check failed"):
            await orchestrator._generate_traditional("build a cli")


class TestFilterAndCompletenessHelpers:
    def test_strict_paths_drop_unplanned_and_log(self, monkeypatch):
        messages = []
        monkeypatch.setattr(tg.logger, "info", lambda *a: messages.append(a))

        kept = tg._filter_planned_integrity_fixes(
            {"src\\__init__.py": "", "main.py": "x"},
            {"strict_file_paths": ["src/__init__.py"]},
        )

        assert kept == {"src\\__init__.py": ""}
        assert messages and "main.py" in messages[0][1]

    @pytest.mark.asyncio
    async def test_completeness_reports_missing_empty_and_invalid(self):
        mixin = object.__new__(TraditionalGenerateMixin)

        result = await mixin._validate_project_completeness_traditional(
            [{"path": "main.py"}, {"path": "util.py"}],
            {"main.py": "   ", "bad.py": "pass"},
        )

        assert result["missing_files"] == ["util.py"]
        assert result["empty_files"] == ["main.py"]
        assert [path for path, _ in result["invalid_files"]] == ["bad.py"]
        assert result["is_complete"] is False

    @pytest.mark.asyncio
    async def test_completeness_accepts_metadata_and_package_entries(self):
        mixin = object.__new__(TraditionalGenerateMixin)

        result = await mixin._validate_project_completeness_traditional(
            [{"path": "app/__init__.py"}, {"path": ".gitignore"}],
            {"app/__init__.py": "", ".gitignore": ""},
        )

        assert result["empty_files"] == []
        assert result["is_complete"] is True


class TestDegradedPaths:
    @pytest.mark.asyncio
    async def test_high_cost_approved_continues(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.require_approval = True

        result = await orchestrator._generate_traditional("build a cli")

        assert result["success"] is True
        assert any(step == "pause_for_cost_approval" for step, *_ in orchestrator.progress)

    @pytest.mark.asyncio
    async def test_incremental_contract_skips_pycache_and_empty(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path, incremental=True)
        orchestrator.session_id = "s1"
        orchestrator.api_contract_checker = object()

        async def resume(_session_id):
            return types.SimpleNamespace()

        orchestrator.session_manager = types.SimpleNamespace(resume_session=resume)
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.py").write_text("x = 1\n", encoding="utf-8")

        await orchestrator._generate_traditional("add a helper")

        ctx = orchestrator.incremental_calls[0][2]
        assert ctx["api_contract"] == ""

    @pytest.mark.asyncio
    async def test_incremental_contract_ignores_unreadable_file(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path, incremental=True)
        orchestrator.session_id = "s1"
        orchestrator.api_contract_checker = object()

        async def resume(_session_id):
            return types.SimpleNamespace()

        orchestrator.session_manager = types.SimpleNamespace(resume_session=resume)
        (tmp_path / "broken.py").write_text("x = 1\n", encoding="utf-8")
        debug_messages = []
        import pathlib

        original_read_text = pathlib.Path.read_text

        def read_text(path_obj, *args, **kwargs):
            if path_obj.name == "broken.py":
                raise OSError("permission denied")
            return original_read_text(path_obj, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "read_text", read_text)
        monkeypatch.setattr(tg.logger, "debug", lambda message: debug_messages.append(message))

        await orchestrator._generate_traditional("add a helper")

        assert any("传统生成读取文件失败" in message for message in debug_messages)

    @pytest.mark.asyncio
    async def test_plan_entries_without_path_or_already_known(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator._validate_file_plan = lambda plan: [
            {"path": ""},
            {"path": "main.py"},
            {"path": "main.py", "priority": 1},
        ]

        await orchestrator._generate_traditional("build a cli")

        assert orchestrator.dependency_graph_obj.nodes == {"main.py": 3}

    @pytest.mark.asyncio
    async def test_generation_plan_registers_planned_files(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)

        class Plan:
            files = [types.SimpleNamespace(path="planned.py", file_type="backend")]

            def model_dump(self, mode="json"):
                return {"files": [{"path": "planned.py"}], "mode": mode}

        class Graph(_FakeDepGraph):
            def __init__(self, language_adapter=None):
                super().__init__(language_adapter)
                self.generation_plan = Plan()

        monkeypatch.setattr(tg, "DependencyGraph", Graph)

        await orchestrator._generate_traditional("build a cli")

        assert ("planned.py", "backend") in orchestrator.shared_context.registered
        assert orchestrator.artifact_committer.task_id in {"fresh", "generated-session"}

    @pytest.mark.asyncio
    async def test_generated_file_missing_or_unreadable_is_skipped(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.files_to_generate = [
            {"path": "present.py", "description": "ok", "success": True},
        ]
        missing = {"path": "missing.py", "description": "gone", "success": False}
        orchestrator.generated_files.append(missing)

        import pathlib

        original_read_text = pathlib.Path.read_text
        debug_messages = []

        def read_text(path_obj, *args, **kwargs):
            if path_obj.name == "present.py":
                raise OSError("locked")
            return original_read_text(path_obj, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "read_text", read_text)
        monkeypatch.setattr(tg.logger, "debug", lambda *a: debug_messages.append(a))

        result = await orchestrator._generate_traditional("build a cli")

        assert result["success"] is True
        assert any("读取生成文件失败" in str(item) for item in debug_messages)

    @pytest.mark.asyncio
    async def test_generated_file_absent_on_disk_is_skipped(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.files_to_generate = [
            {"path": "", "description": "no path", "success": False, "write": False},
            {"path": "missing.py", "description": "gone", "success": False, "write": False},
            {"path": "present.py", "description": "ok", "success": True},
        ]

        result = await orchestrator._generate_traditional("build a cli")

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_integrity_pass_skips_fix_application(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)

        class PassingValidator(_FakeIntegrityValidator):
            def validate(self, _files):
                return types.SimpleNamespace(passed=True)

        monkeypatch.setattr("app.agent.integrity_validator.IntegrityValidator", PassingValidator)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.enable_validation = True
        applied = []
        orchestrator._apply_integrity_fixes = lambda fixes, files: applied.append(fixes)

        await orchestrator._generate_traditional("build a cli")

        assert applied == []

    @pytest.mark.asyncio
    async def test_dynamic_failure_without_react_fix_keeps_results(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.enable_validation = True
        orchestrator.dynamic_results = {"success": False, "summary": "1 failed"}
        orchestrator.react_result = None

        result = await orchestrator._generate_traditional("build a cli")

        assert result["test_results"] == {"success": False, "summary": "1 failed"}
        assert "ReAct 自动修复已尝试应用" not in orchestrator.warnings

    @pytest.mark.asyncio
    async def test_dynamic_failure_with_unfixed_react_keeps_results(self, tmp_path, monkeypatch):
        _patch_collaborators(monkeypatch)
        orchestrator = _BaseOrchestrator(tmp_path)
        orchestrator.enable_validation = True
        orchestrator.dynamic_results = {"success": False, "summary": "1 failed"}
        orchestrator.react_result = {"fixed": False}

        result = await orchestrator._generate_traditional("build a cli")

        assert result["test_results"]["success"] is False
        assert "ReAct 自动修复已尝试应用" not in orchestrator.warnings
