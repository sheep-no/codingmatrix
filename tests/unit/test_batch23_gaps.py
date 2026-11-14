"""Batch 23 coverage gaps: metrics, prompt cache, contracts and graph helpers."""

import asyncio
from pathlib import Path

import pytest

from app.agent import shared_context as shared_context_module
from app.agent.file_contract import FileContract
from app.agent.retrieval.models import RetrievalChunk, RetrievalRequest
from app.agent.retrieval.service import CallableRetriever, RetrievalService
from app.agent.shared_context import SharedContext
from app.core.config import Settings
from app.services import prometheus_metrics as metrics_module
from app.services.image_history_refs import resolve_reference
from app.utils.prompt_builder import PromptBuilder, PromptContext, ordered_json_dumps
from app.utils.pptx.design_tokens import DesignTokens


def test_database_connections_and_celery_task_are_recorded():
    registry = metrics_module.get_prometheus_metrics().get_registry()
    saved = (dict(registry._counters), dict(registry._gauges))
    try:
        registry._counters.clear()
        registry._gauges.clear()

        metrics_module.PrometheusMetrics().set_database_connections(3, 7)
        metrics_module.PrometheusMetrics().record_celery_task("sync", "ok")

        active = registry._gauges['database_connections_active{state="active"}']
        idle = registry._gauges['database_connections_active{state="idle"}']
        assert active.value == 3
        assert idle.value == 7
        celery = registry._counters['celery_tasks_total{status="ok",task="sync"}']
        assert celery.value == 1
    finally:
        registry._counters.clear()
        registry._gauges.clear()
        registry._counters.update(saved[0])
        registry._gauges.update(saved[1])


def test_format_labels_empty_returns_blank():
    assert metrics_module._format_labels({}) == ""


def test_resolve_reference_rejects_parent_directory(tmp_path: Path):
    assert resolve_reference("..", tmp_path) is None
    assert resolve_reference("nested", tmp_path) == (tmp_path / "nested").resolve()


def test_static_prefix_includes_spec_and_project_context():
    builder = PromptBuilder()
    prefix = builder.build_messages(
        PromptContext(
            system_instructions="sys",
            spec_cache_content="spec body",
            project_context="project body",
        )
    )[0]["content"]

    assert "## 项目规范" in prefix
    assert "## 项目上下文" in prefix


def test_static_prefix_without_system_instructions_starts_with_tools():
    prefix = PromptBuilder().build_messages(
        PromptContext(tool_definitions="run_tests()")
    )[0]["content"]

    assert prefix.startswith("## 可用工具")


def test_ordered_json_dumps_recurses_into_lists():
    payload = {"b": 1, "a": [{"z": 2, "y": 3}]}
    dumped = ordered_json_dumps(payload)
    assert dumped == ordered_json_dumps({"a": [{"y": 3, "z": 2}], "b": 1})


def test_design_tokens_as_dict_round_trips_fields():
    tokens = DesignTokens(
        version="1.0",
        colors={"primary": "#000"},
        typography={},
        spacing={},
        shapes={},
        image={},
        chart={},
    )
    assert tokens.as_dict()["version"] == "1.0"
    assert tokens.as_dict()["colors"] == {"primary": "#000"}


def test_file_contract_swallows_path_resolution_errors():
    contract = FileContract(operation="read", file_path="bad\x00name.py")
    assert contract.validate_path() is False


@pytest.mark.parametrize(
    ("validator", "value"),
    [
        ("validate_db_pool_size", 0),
        ("validate_db_pool_size", 101),
        ("validate_db_max_overflow", -1),
        ("validate_generated_asset_retention_days", 0),
    ],
)
def test_settings_numeric_validators_reject_out_of_range(validator, value):
    with pytest.raises(ValueError):
        getattr(Settings, validator)(value)


def test_phase_status_and_review_helpers(tmp_path: Path):
    context = SharedContext("req", tmp_path)
    context.start_phase("coding", total_files=2)
    context.save_file_content("a.py", "x = 1\n", "m")

    assert context.get_phase_status() == {"coding": "in_progress"}

    context.update_file_review("a.py", ["lint"])
    context.update_file_review("missing.py", ["ignored"])
    assert context.files["a.py"].review_issues == ["lint"]

    context.increment_fix_attempts("a.py")
    context.increment_fix_attempts("missing.py")
    assert context.files["a.py"].fix_attempts == 1

    assert context.get_dependencies_for("a.py") == []
    context.dependencies["a.py"] = ["b.py"]
    assert context.get_dependencies_for("a.py") == ["b.py"]
    assert context.get_dependents_of("b.py") == ["a.py"]


def test_complete_phase_unknown_phase_only_logs(tmp_path: Path):
    context = SharedContext("req", tmp_path)
    context.complete_phase("missing", ["boom"])
    assert context.phases == {}


def test_resaving_same_content_keeps_validation(tmp_path: Path):
    context = SharedContext("req", tmp_path)
    context.save_file_content("a.py", "x = 1\n", "m")
    context.update_file_validation("a.py", True)

    context.save_file_content("a.py", "x = 1\n", "m2")

    assert context.files["a.py"].validation_passed is True


def test_generation_order_handles_cycles_and_unregistered_files(tmp_path: Path):
    context = SharedContext("req", tmp_path)
    context.dependencies["a.py"] = ["b.py"]
    context.dependencies["b.py"] = ["a.py"]
    context.files["orphan.py"] = shared_context_module.FileArtifact(
        path="orphan.py", content="", file_type="utils", generated_by="", generation_order=3
    )

    order = context.get_generation_order()

    assert set(order) == {"a.py", "b.py", "orphan.py"}
    assert order.index("orphan.py") == len(order) - 1


def test_generated_files_summary_joins_multiple_artifacts(tmp_path: Path):
    context = SharedContext("req", tmp_path)
    context.save_file_content("a.py", "print(1)\n", "m")
    context.save_file_content("b.py", "print(2)\n", "m")
    context.register_file("empty.py", "utils")

    summary = context.get_generated_files_summary()

    assert summary.count("## ") == 2


def test_callable_retriever_rejects_empty_source_type():
    with pytest.raises(ValueError):
        CallableRetriever("", lambda _request: [])


def test_retrieval_keeps_best_score_and_drops_unusable_items():
    async def high(_request):
        return [RetrievalChunk("same", "src", "1", score=0.9)]

    async def low(_request):
        return [RetrievalChunk("same", "src", "2", score=0.1)]

    result = asyncio.run(
        RetrievalService([CallableRetriever("src", high), CallableRetriever("src", low)])
        .retrieve(RetrievalRequest("q"))
    )
    assert len(result.chunks) == 1
    assert result.chunks[0].score == 0.9


def test_retrieval_normalizes_dicts_and_rejects_unknown_items():
    async def items(_request):
        return [{"content": "keep me", "id": 7}, {"content": ""}, 42]

    result = asyncio.run(
        RetrievalService([CallableRetriever("src", items)]).retrieve(RetrievalRequest("q"))
    )
    assert len(result.chunks) == 1
    assert result.chunks[0].source_id == "7"
