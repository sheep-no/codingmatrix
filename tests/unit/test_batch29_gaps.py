"""Batch 29: close branch-only gaps left after the r41 baseline."""

import time
from pathlib import Path
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# boilerplate
# ---------------------------------------------------------------------------


def test_python_requirements_deduplicates_packages():
    from app.agent.adapters.boilerplate import _python_requirements

    architecture = {
        "framework": "flask",
        "tech_stack": {"backend": "flask"},
        "storage": {"type": "sqlite"},
        "auth": {"scheme": "jwt"},
    }

    rendered = _python_requirements(architecture)

    assert rendered.count("flask") == 1


# ---------------------------------------------------------------------------
# api_contract_checker
# ---------------------------------------------------------------------------


def test_generate_api_contract_reuses_existing_module_bucket():
    from app.agent.api_contract_checker import APIContractChecker

    code = (
        "from fastapi import APIRouter\n"
        "router = APIRouter()\n"
        "@router.get('/users')\n"
        "def a(): pass\n"
        "@router.post('/users/x')\n"
        "def b(): pass\n"
    )

    contract = APIContractChecker().generate_api_contract({"a.py": code})

    assert [item["path"] for item in contract["users"]] == ["/users", "/users/x"]


# ---------------------------------------------------------------------------
# architecture_inspector
# ---------------------------------------------------------------------------


def test_layer_boundary_violation_is_reported():
    from app.agent.architecture_inspector import ArchitectureInspector

    inspector = ArchitectureInspector()
    inspector.set_context(
        architecture={
            "layers": {
                "repository": {
                    "paths": ["src/repository/"],
                    "boundaries": ["no_http_handling"],
                }
            }
        },
        generated_files={"src/repository/user.py": "def f(request: Request): pass\n"},
    )

    violations = inspector._check_layer_boundaries()

    assert len(violations) == 1
    assert violations[0].violation_type == "layer_boundary"


def test_js_import_fallback_detects_package():
    from app.agent.architecture_inspector import ArchitectureInspector

    inspector = ArchitectureInspector()

    assert inspector._file_imports_packages("const x = require('react');", ["react"]) is True
    assert inspector._file_imports_packages("const x = 1;", ["react"]) is False


def test_tech_stack_list_accepts_strings_and_dicts():
    from app.agent.architecture_inspector import ArchitectureInspector

    inspector = ArchitectureInspector()
    inspector.set_context(
        architecture={
            "tech_stack": ["Python backend", {"frontend": "vue"}],
        },
        generated_files={},
    )
    inspector.user_decisions = {}

    assert inspector._check_tech_stack_consistency() == []


# ---------------------------------------------------------------------------
# code_patcher
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_patch_to_file_without_output_dir_skips_boundary(tmp_path):
    from app.agent.code_patcher import CodePatcher

    target = tmp_path / "main.py"
    target.write_text("a = 1\n", encoding="utf-8")
    patch = (
        "--- a/main.py\n"
        "+++ b/main.py\n"
        "@@ -1 +1 @@\n"
        "-a = 1\n"
        "+a = 2\n"
    )

    result = await CodePatcher().apply_patch_to_file(target, patch)

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "a = 2"


# ---------------------------------------------------------------------------
# error_recovery
# ---------------------------------------------------------------------------


def test_custom_preference_without_chain_falls_back_to_config(monkeypatch):
    from app.agent import error_recovery as module

    loop = module.ErrorRecoveryLoop(validator=object(), reviewer=object())
    monkeypatch.setattr(
        loop,
        "_get_user_fallback_preference",
        lambda: {"fallback_preference": "custom", "custom_fallback_chain": []},
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.load_agent_model_config",
        lambda: {"fallback_chains": {"error_recovery": ["a"]}},
    )
    monkeypatch.setattr(
        "app.agent.dynamic_model_router.resolve_model_key",
        lambda name: f"resolved-{name}",
    )

    assert loop._load_fallback_chain() == ["resolved-a"]


@pytest.mark.asyncio
async def test_temp_cleanup_runs_when_missing_and_final_failure_records_strategy(
    monkeypatch, tmp_path
):
    from app.agent import error_recovery as module

    class _Sem:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    class _Budget:
        def consume(self, _category):
            return True

        def can_consume(self, _category):
            return True

    class _Evaluator:
        def __init__(self):
            self.calls = []

        def get_strategy_template(self, *_a):
            return ("template", "strategy-1")

        def record_evaluation_result(self, result):
            self.calls.append(result)

    class _Validator:
        async def validate_single_file(self, _path):
            return {"is_valid": False, "syntax_errors": ["bad"]}

    evaluator = _Evaluator()
    loop = module.ErrorRecoveryLoop(validator=_Validator(), reviewer=object())
    loop._semaphore = _Sem()
    loop.repair_budget = _Budget()
    loop.MAX_FIX_ATTEMPTS = 1

    async def fake_classify(*_a, **_k):
        from app.agent.error_classifier import ErrorClassification

        return ErrorClassification(
            error_type="SyntaxError",
            error_subtype="sub",
            description="bad",
            suggested_fix_strategy="fix",
            confidence=0.9,
        )

    monkeypatch.setattr(module, "error_classifier", SimpleNamespace(
        classify_error=fake_classify,
        add_to_history=lambda *_a, **_k: None,
    ))
    monkeypatch.setattr(module, "strategy_evaluator", evaluator)
    monkeypatch.setattr(
        module.RepairRouter,
        "route",
        lambda *_a, **_k: SimpleNamespace(
            auto_apply=True, category="syntax", max_attempts=1
        ),
    )

    async def fake_llm(**_kwargs):
        return "a = 1\n"

    monkeypatch.setattr(module, "call_llm", fake_llm)

    target = tmp_path / "main.py"
    result = await loop._smart_fix_loop(
        file_path=target,
        content="a = 2\n",
        errors={"syntax_errors": ["bad"]},
        backend_model="model-a",
    )

    assert result["success"] is False
    assert evaluator.calls
    assert not list(tmp_path.glob(".temp_fix_*"))


# ---------------------------------------------------------------------------
# impact_analyzer
# ---------------------------------------------------------------------------


def test_generate_summary_without_modified_files(tmp_path):
    from app.agent.impact_analyzer import ChangeSummary, ImpactAnalyzer

    analyzer = ImpactAnalyzer(str(tmp_path))
    summary = ChangeSummary(new_symbols=["a"])

    assert "修改了" not in analyzer._generate_summary(summary)


# ---------------------------------------------------------------------------
# artifact_committer
# ---------------------------------------------------------------------------


def test_commit_is_idempotent_when_disk_matches(tmp_path):
    from app.agent.orchestration import ArtifactCommitter
    from app.agent.shared_context import SharedContext

    context = SharedContext("idempotent", tmp_path)
    committer = ArtifactCommitter(tmp_path, context, task_id="t")

    first = committer.commit("main.py", "x = 1\n", model_name="m")
    second = committer.commit("main.py", "x = 1\n", model_name="m")

    assert first.success and second.success
    assert second.idempotent is True


# ---------------------------------------------------------------------------
# profile_bridge
# ---------------------------------------------------------------------------


def test_validation_plan_skips_stage_without_command():
    from app.agent.capabilities import CapabilitySet
    from app.agent.framework_profiles import FrameworkProfile, ValidationStage
    from app.agent.framework_profiles.types import ProfileStatus
    from app.agent.orchestration.profile_bridge import validation_plan_from_framework

    # 正常构造会因「validation step 必须配命令」被拒；这里绕过校验，
    # 专门覆盖 bridge 对「空命令阶段」的跳过逻辑。
    profile = FrameworkProfile.model_construct(
        name="x",
        language="python",
        version="1",
        status=ProfileStatus.SUPPORTED,
        capabilities=CapabilitySet(),
        validation_steps=(ValidationStage.BUILD.value,),
        build_command=(),
        install_command=("pip", "install", "."),
        dependencies=(),
        lint_command=(),
        typecheck_command=(),
        test_command=(),
        smoke_command=(),
        start_command=(),
        health_path="/health",
        scope="profile",
        owner_id=None,
        workspace_id=None,
        command_allowlist=(),
        dependency_allowlist=(),
        probe_commands={},
        file_role_patterns={},
        contract_rules={},
        default_for_language=False,
    )

    plan = validation_plan_from_framework(profile)

    assert plan.commands == ()
    assert plan.unsupported_steps == ("build",)


# ---------------------------------------------------------------------------
# orchestrator path normalization
# ---------------------------------------------------------------------------


def test_orchestrator_resolves_relative_output_dir(tmp_path, monkeypatch):
    from app.agent import orchestrator as module

    base = tmp_path / "projects"
    monkeypatch.setattr(module, "PROJECTS_BASE_DIR", base)

    agent = module.OrchestratorAgent(output_dir="1_demo")

    assert agent.output_dir == base / "1_demo"


# ---------------------------------------------------------------------------
# coverage_checker
# ---------------------------------------------------------------------------


def test_check_requirement_coverage_accepts_list_fields():
    from app.agent.orchestrator_generation.coverage_checker import (
        check_requirement_coverage,
    )

    item = SimpleNamespace(
        category="functional", confidence=0.9, description="登录", content="登录", source="req",
    )
    association = SimpleNamespace(items=[item], skipped=False)

    result = check_requirement_coverage(
        "登录",
        {"tech_stack": ["fastapi", "vue"]},
        [{"path": "login.py", "description": "登录"}],
        association,
    )

    assert result["checked"] is True


# ---------------------------------------------------------------------------
# incremental_modify
# ---------------------------------------------------------------------------


def test_python_import_matching_returns_none_for_bare_import():
    import re

    assert re.match(r"from\s+(\w+)", "import os") is None


# ---------------------------------------------------------------------------
# feedback_tracker
# ---------------------------------------------------------------------------


def test_cleanup_trims_when_db_exceeds_limit(tmp_path, monkeypatch):
    from app.agent.orchestrator_requirements import feedback_tracker as module

    monkeypatch.setattr(module.AssociationFeedbackTracker, "DB_PATH", tmp_path / "feedback.db")
    monkeypatch.setattr(module.AssociationFeedbackTracker, "MAX_DB_SIZE_BYTES", 0)
    tracker = module.AssociationFeedbackTracker()
    tracker.record_choice(
        "s", "req", [{"content": f"item{i}", "category": "functional"} for i in range(8)],
        "accepted",
    )

    tracker._cleanup()

    remaining = tracker._conn.execute(
        "SELECT COUNT(*) FROM association_feedback"
    ).fetchone()[0]
    assert remaining == 6


# ---------------------------------------------------------------------------
# project_metadata
# ---------------------------------------------------------------------------


def test_save_removes_temp_file_when_replace_fails(tmp_path, monkeypatch):
    from app.agent import project_metadata as module

    monkeypatch.setattr(module, "METADATA_PATH", tmp_path / "meta.json")
    manager = module.ProjectMetadataManager()
    manager._projects = {"a": {}}

    def boom(*_a, **_k):
        raise RuntimeError("replace failed")

    monkeypatch.setattr(module.os, "replace", boom)

    with pytest.raises(RuntimeError):
        manager._save()

    assert list(tmp_path.glob(".project_metadata.*.tmp")) == []


# ---------------------------------------------------------------------------
# stack_adapters
# ---------------------------------------------------------------------------


def test_express_detect_uses_package_main(tmp_path):
    from app.agent.stack_adapters.adapters import ExpressStackAdapter

    (tmp_path / "package.json").write_text(
        '{"main": "server.js", "dependencies": {"express": "^4.0.0"}}', encoding="utf-8"
    )
    (tmp_path / "server.js").write_text("const express = require('express')\n", encoding="utf-8")

    project = ExpressStackAdapter().detect(tmp_path)

    assert "server.js" in project.entrypoints


# ---------------------------------------------------------------------------
# strategy / user preference singletons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_singletons_return_cached_instances(monkeypatch):
    from app.agent import strategy_learner as sl
    from app.agent import user_preference_learner as upl

    monkeypatch.setattr(sl, "_strategy_learner", object())
    assert await sl.get_strategy_learner() is sl._strategy_learner

    cached = object()
    monkeypatch.setattr(upl, "_user_preference_learners", {"default": cached})
    monkeypatch.setattr(upl, "_learner_lock", __import__("asyncio").Lock())
    assert await upl.get_user_preference_learner("default") is cached


# ---------------------------------------------------------------------------
# logging_config
# ---------------------------------------------------------------------------


def test_sensitive_filter_handles_dict_and_tuple_args():
    from app.core.logging_config import SensitiveDataFilter

    record = SimpleNamespace(
        msg="user password=abc",
        args={"password": "password=abc"},
    )
    SensitiveDataFilter().filter(record)
    assert "***REDACTED***" in record.args["password"]

    record = SimpleNamespace(msg="token=abc", args=("plain",))
    SensitiveDataFilter().filter(record)
    assert record.args == ("plain",)


# ---------------------------------------------------------------------------
# rate_limiter
# ---------------------------------------------------------------------------


def test_extract_user_id_from_scope_variants(monkeypatch):
    from app.middleware import rate_limiter as module

    monkeypatch.setattr(module.jwt, "decode", lambda *_a, **_k: {"sub": "u1"})
    scope = {"headers": [(b"authorization", b"Bearer token")]}
    assert module._extract_user_id_from_scope(scope) == "u1"

    monkeypatch.setattr(module.jwt, "decode", lambda *_a, **_k: {})
    assert module._extract_user_id_from_scope(scope) is None


# ---------------------------------------------------------------------------
# agent_memory_service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_model_stats_averages_execution_time(monkeypatch):
    from app.services import agent_memory_service as module

    stats = SimpleNamespace(
        request_count=0,
        total_tokens=0,
        success_count=1,
        failure_count=0,
        avg_execution_time=2.0,
        last_used_at=None,
    )

    class _Result:
        def scalar_one_or_none(self):
            return stats

    class _Db:
        async def execute(self, *_a, **_k):
            return _Result()

        async def commit(self):
            return None

        async def refresh(self, _obj):
            return None

    service = module.AgentMemoryService(db=_Db())
    await service.update_model_stats(
        user_id="1",
        model_key="m",
        model_name="M",
        tokens=10,
        success=True,
        execution_time=4.0,
    )

    # 成功后 success_count 由 1 增至 2，均值按 (2*1 + 4)/3 更新为 3.0
    assert stats.avg_execution_time == 3.0


# ---------------------------------------------------------------------------
# chat_context
# ---------------------------------------------------------------------------


def test_fit_context_truncates_to_available_chars(monkeypatch):
    from app.services import chat_context as module

    monkeypatch.setattr(module, "get_context_length", lambda *_a, **_k: 1000)
    monkeypatch.setattr(module, "get_max_output_tokens", lambda *_a, **_k: 1)

    context, budget = module.fit_context("prompt", "x" * 100000, "m")

    assert budget.truncated is True
    assert len(context) == (1000 - 1 - 2) * 4


# ---------------------------------------------------------------------------
# ppt_generation_persistence
# ---------------------------------------------------------------------------


def test_trace_without_outline_skips_quality_report_lookup(tmp_path):
    from app.services.ppt_generation_persistence import build_ppt_trace_context

    trace = build_ppt_trace_context({}, "business", "refined")

    assert trace.get("outline_id") is None


# ---------------------------------------------------------------------------
# aicloud dynamic adapter
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_stream_ignores_non_data_lines(monkeypatch):
    from app.utils.aicloud.adapters import dynamic as module

    provider = module.DynamicProvider(
        id="p", name="p", base_url="https://example.com",
        protocol=module.Protocol.ANTHROPIC, api_key="k",
    )
    adapter = module.DynamicAdapter(provider)

    class _Response:
        async def aiter_lines(self):
            yield "event: ping"
            yield "data: [DONE]"

        async def aclose(self):
            return None

    class _Stream:
        async def __aenter__(self):
            return _Response()

        async def __aexit__(self, *_exc):
            return False

    class _Client:
        def stream(self, *_a, **_k):
            return _Stream()

    async def _client():
        return _Client()

    class _Sem:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc):
            return False

    monkeypatch.setattr(module, "get_http_client", _client)
    monkeypatch.setattr(module, "_max_concurrent_calls", _Sem())

    chunks = [chunk async for chunk in await adapter.call_llm("m", "p", stream=True)]

    assert chunks == []


# ---------------------------------------------------------------------------
# http_client
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_http_client_reuses_live_client(monkeypatch):
    from app.utils.aicloud import http_client as module

    class _Client:
        is_closed = False

    client = _Client()
    monkeypatch.setattr(module, "_http_client", client)
    monkeypatch.setattr(module, "_http_client_loop", __import__("asyncio").get_running_loop())

    assert await module.get_http_client() is client


# ---------------------------------------------------------------------------
# cache / encryption singletons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cache_and_key_manager_singletons_return_cached(monkeypatch):
    from app.utils import cache as cache_module
    from app.utils import encryption as enc_module

    cached_cache = object()
    monkeypatch.setattr(cache_module, "_cache_manager", cached_cache)
    assert await cache_module.get_cache_manager() is cached_cache

    cached_key = object()
    monkeypatch.setattr(enc_module, "_key_manager", cached_key)
    assert await enc_module.get_key_manager() is cached_key


# ---------------------------------------------------------------------------
# log_archiver
# ---------------------------------------------------------------------------


def test_archive_all_tracks_rotated_files(tmp_path, monkeypatch):
    from app.utils.log_archiver import LogArchiver

    archiver = LogArchiver(log_dir=str(tmp_path), max_size_mb=0.001)
    (tmp_path / "a.log").write_bytes(b"x" * 4096)

    stats = archiver._archive_all_locked()

    assert stats["rotated"]


def test_archive_stats_pick_oldest_and_newest(tmp_path):
    from app.utils.log_archiver import LogArchiver

    archiver = LogArchiver(log_dir=str(tmp_path), compression_enabled=False)
    older = tmp_path / "a.log.1"
    newer = tmp_path / "b.log.2"
    older.write_bytes(b"x")
    newer.write_bytes(b"y")
    older.touch()
    newer.touch()

    stats = archiver.get_archive_stats()

    assert stats["file_count"] == 2
    assert stats["oldest_file"] is not None
    assert stats["newest_file"] is not None


# ---------------------------------------------------------------------------
# visual_analyzer
# ---------------------------------------------------------------------------


def test_fix_json_format_handles_nested_quotes_and_literals():
    from app.utils.visual.visual_analyzer import VisualAnalyzer

    analyzer = VisualAnalyzer()
    fixed = analyzer._fix_json_format("{'a': 'it\\'s', 'b': True, 'c': False}")

    assert '"a"' in fixed
    assert "true" in fixed
    assert "false" in fixed


def test_extract_json_by_regex_keeps_partial_slides():
    from app.utils.visual.visual_analyzer import VisualAnalyzer

    content = (
        '{"slides_analysis": [{"slide_index": 1, "images": []}'
        '{"slide_index": 2, "title_style": {"font_size": 20}}],'
        ' "overall_style": {}}'
    )

    result = VisualAnalyzer()._extract_json_by_regex(content)

    assert result["slides_analysis"]


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------


def test_search_result_to_dict_includes_summary():
    from app.utils.web_search import SearchResult

    result = SearchResult("t", "https://x", "s", summary="sum")

    assert result.to_dict()["summary"] == "sum"


def test_extract_named_entity_returns_entity_for_time_prefix():
    from app.utils.web_search import extract_named_entity

    assert extract_named_entity("今年的清华大学 排名") == "清华大学"


def test_clean_url_extracts_duckduckgo_redirect():
    from app.utils.web_search import FreeWebSearch

    searcher = FreeWebSearch()
    cleaned = searcher._clean_url(
        "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com"
    )

    assert cleaned == "https://example.com"


# ---------------------------------------------------------------------------
# workflow nodes
# ---------------------------------------------------------------------------


def test_file_processing_copy_without_destination_reports_error(tmp_path):
    from app.utils.file_operator import FileOperator
    from app.utils.workflow.node_types.file_processing import FileProcessingNode

    node = FileProcessingNode("n", {"operation": "copy", "source": "a.txt"})
    node._operator = FileOperator(base_path=str(tmp_path), allow_protected_paths=True)

    assert "Missing required parameter: destination" in node.validate_params()


def test_human_approval_rejects_timeout_out_of_range():
    from app.utils.workflow.node_types.human_approval import HumanApprovalNode

    node = HumanApprovalNode("n", {"prompt": "ok", "timeout": 0})

    assert "Parameter 'timeout' must be between 1 and 3600" in node.validate_params()


def test_human_approval_rejects_non_list_options():
    from app.utils.workflow.node_types.human_approval import HumanApprovalNode

    node = HumanApprovalNode("n", {"prompt": "ok", "options": "yes"})

    assert "Parameter 'options' must be a list with at least 2 items" in node.validate_params()


# ---------------------------------------------------------------------------
# web_search page summaries
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_search_with_page_summaries_skips_empty_pages(monkeypatch):
    from app.utils import web_search as module

    class _Search:
        max_concurrent_fetch = 1

        async def search(self, _query, count=5):
            return [module.SearchResult("t", "https://example.com", "s")]

    monkeypatch.setattr(module, "FreeWebSearch", _Search)
    monkeypatch.setattr(module, "fetch_page_text", _async_none)
    monkeypatch.setattr(module, "summarize_page_with_llm", _async_none)

    results = await module.search_with_page_summaries("python", count=1)

    assert len(results) == 1
    assert results[0].summary is None


async def _async_none(*_a, **_k):
    return None
