"""Coverage gaps for validation, IR projection, state graph, and context assembly."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from app.agent.state import GraphDefinitionError, State, StateDelta, StateGraphBuilder


def _delta(state, status="generated"):
    return StateDelta(expected_revision=state.revision, status=status)


# ------------------------------------------------- validation coordinator


@pytest.mark.asyncio
async def test_validation_execute_records_missing_command():
    from app.agent.validation_coordinator import ValidationCoordinator

    class Runner:
        async def run(self, command, workspace):
            raise FileNotFoundError("missing")

    coordinator = ValidationCoordinator(runner=Runner())
    action = SimpleNamespace(action="lint")
    plan = SimpleNamespace(commands=(action,))
    results = await coordinator.execute(plan, Path("/tmp"))
    assert results[0].returncode == 127


def test_validation_report_skips_passed_and_names_unsupported():
    from app.agent.toolchain import ToolchainAction
    from app.agent.validation_coordinator import (
        CommandSpec,
        ValidationCoordinator,
        ValidationResult,
    )

    coordinator = ValidationCoordinator(runner=SimpleNamespace())
    plan = SimpleNamespace(commands=(), unsupported_steps=("weird",))
    command = CommandSpec(action=ToolchainAction.LINT, command=("ruff",))
    passed = ValidationResult(command, 0, "", "")
    failed = ValidationResult(command, 2, "", "boom")
    report = coordinator.to_report(plan, (passed, failed), context_hash="0" * 64)
    messages = [finding.message for finding in report.findings]
    assert any("unsupported validation step" in m for m in messages)
    assert any("boom" in m for m in messages)
    assert len(report.findings) == 2


# ---------------------------------------------------- ir projection


def test_ir_projection_rejects_empty_plan():
    from app.agent.code_synthesis_contracts import ChangePlanIR, ProjectModel
    from app.agent.orchestration.ir_projection import project_change_plan

    plan = ChangePlanIR.build(ProjectModel(language="python"), [])
    with pytest.raises(ValueError, match="no generatable artifacts"):
        project_change_plan(plan)


# ------------------------------------------------ code synthesis contracts


def test_http_contract_validates_lifecycle_fields():
    from app.agent.code_synthesis_contracts import HttpContract

    with pytest.raises(ValueError, match="unsupported contract source"):
        HttpContract(method="GET", path="/x", source="bogus")
    with pytest.raises(ValueError, match="unsupported contract status"):
        HttpContract(method="GET", path="/x", status="bogus")
    with pytest.raises(ValueError, match="cannot be frozen"):
        HttpContract(method="GET", path="/x", status="frozen")
    assert HttpContract(method="GET", path="/x", status="frozen", source="architect").is_authoritative


def test_change_plan_rejects_duplicate_and_missing_dependency():
    from pydantic import ValidationError

    from app.agent.code_synthesis_contracts import (
        ArtifactSpec,
        ChangePlanIR,
        GenerationStrategy,
        ProjectModel,
    )

    project = ProjectModel(language="python")

    def artifact(path, depends_on=()):
        return ArtifactSpec(
            path=path,
            role="module",
            owner="o",
            operation="create",
            strategy=GenerationStrategy.TEMPLATE,
            depends_on=depends_on,
            validation_profile="python",
            source="stack",
        )

    duplicate = (artifact("a.py"), artifact("a.py"))
    with pytest.raises(ValidationError, match="must be unique"):
        ChangePlanIR.build(project, duplicate)

    missing = (artifact("a.py", ("ghost.py",)),)
    with pytest.raises(ValidationError, match="missing artifact dependencies"):
        ChangePlanIR.build(project, missing)


def test_change_plan_artifact_lookup_raises_key_error():
    from app.agent.code_synthesis_contracts import (
        ArtifactSpec,
        ChangePlanIR,
        GenerationStrategy,
        ProjectModel,
    )

    artifact = ArtifactSpec(
        path="a.py",
        role="module",
        owner="o",
        operation="create",
        strategy=GenerationStrategy.TEMPLATE,
        validation_profile="python",
        source="stack",
    )
    plan = ChangePlanIR.build(ProjectModel(language="python"), [artifact])
    assert plan.artifact("a.py").path == "a.py"
    with pytest.raises(KeyError):
        plan.artifact("missing.py")


# ------------------------------------------------------- state graph


@pytest.mark.asyncio
async def test_state_graph_unknown_start_node():
    graph = StateGraphBuilder().add_node("a", lambda s: _delta(s)).compile()
    with pytest.raises(GraphDefinitionError, match="unknown start node"):
        await graph.run(State("s", "t"), "missing")


@pytest.mark.asyncio
async def test_state_graph_async_conditional_selector():
    def node(state):
        return _delta(state, "generated")

    async def choose(state):
        return "done"

    graph = (
        StateGraphBuilder()
        .add_node("start", node)
        .add_node("done", lambda s: _delta(s, "completed"))
        .add_conditional_edges("start", choose, {"done": "done"})
        .compile()
    )
    assert (await graph.run(State("s", "t"), "start")).status == "completed"


def test_state_graph_builder_rejects_bad_nodes_and_targets():
    builder = StateGraphBuilder()
    with pytest.raises(GraphDefinitionError, match="invalid or duplicate node"):
        builder.add_node("", lambda s: _delta(s))
    builder.add_node("a", lambda s: _delta(s))
    with pytest.raises(GraphDefinitionError, match="invalid or duplicate node"):
        builder.add_node("a", lambda s: _delta(s))
    builder.add_edge("a", "ghost")
    with pytest.raises(GraphDefinitionError, match="unknown target nodes"):
        builder.compile()


# ------------------------------------------------------- go adapter


def test_go_adapter_package_and_module_helpers():
    from app.agent.adapters.go import GoLanguageAdapter

    adapter = GoLanguageAdapter()
    assert adapter.get_package_init_file("pkg") == ""
    assert adapter.is_project_module("") is False
    assert adapter.is_project_module("example.com/internal/x") is True
    assert adapter.is_project_module("example.com/web/x") is False


# ------------------------------------------------- image metrics


def test_image_metrics_records_property():
    from app.services.image_metrics_service import ImageGenerationMetric, ImageGenerationMetrics

    metrics = ImageGenerationMetrics()
    metric = ImageGenerationMetric(
        user_id=1,
        generation_type="single",
        profile=None,
        cache_hit=False,
        total_duration_ms=1,
        retry_count=0,
        image_count=1,
        output_bytes=10,
        status="ok",
    )
    metrics.record(metric)
    assert metrics.records == (metric,)
    assert metrics.summary()["requests"] == 1


# ------------------------------------------------ composition pool


def test_composition_pool_avoids_repeat_and_recent():
    from app.utils.pptx.composition_pool import select_layout_variants

    sequence = select_layout_variants("topic", count=6)
    assert all(left != right for left, right in zip(sequence, sequence[1:]))
    recent = select_layout_variants("topic", count=4)
    shifted = select_layout_variants("topic", count=4, recent_variants=tuple(recent[:1]))
    assert shifted


# ------------------------------------------------ context assembler


def test_context_assembler_rejects_non_positive_capacity():
    from app.agent.context_assembler import ContextAssembler

    with pytest.raises(ValueError, match="max_chars must be positive"):
        ContextAssembler(max_chars=0)


def test_context_assembler_stops_and_skips_blank_content():
    from app.agent.context_assembler import ContextAssembler

    assembler = ContextAssembler(max_chars=5)
    envelope = assembler.assemble(
        task_id="t",
        stage="s",
        items=[
            {"source": "memory", "source_id": "m1", "content": "   ", "priority": 100},
            {"source": "requirement", "source_id": "r1", "content": "abcdef", "priority": 90},
            {"source": "memory", "source_id": "m2", "content": "later", "priority": 10},
        ],
    )
    assert [item.source_id for item in envelope.items] == ["r1"]
    assert envelope.items[0].content == "abcde"

    empty = ContextAssembler(max_chars=5).assemble(
        task_id="t",
        stage="s",
        items=[{"source": "memory", "source_id": "m1", "content": "x" * 10, "priority": 1}],
    )
    assert empty.items[0].content == "xxxxx"

    over = ContextAssembler(max_chars=1).assemble(
        task_id="t", stage="s",
        items=[{"source": "memory", "source_id": "a", "content": "ab", "priority": 2}],
    )
    assert over.items[0].content == "a"


def test_context_assembler_coerces_context_items():
    from app.agent.context_assembler import ContextAssembler, ContextItem, ContextSource

    assembler = ContextAssembler()
    item = ContextItem(
        source=ContextSource.MEMORY,
        source_id="m",
        content="hi",
        priority=10,
        content_hash="0" * 64,
    )
    assert assembler._coerce(item) is item
    coerced = assembler._coerce(
        {"source": "memory", "source_id": "m2", "content": "yo", "priority": "20"}
    )
    assert coerced.priority == 20


def test_validation_plan_deduplicates_repeated_commands(tmp_path):
    from app.agent.toolchain import detect_toolchain
    from app.agent.validation_coordinator import ValidationCoordinator

    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")
    profile = {"capability_policy": {"validation_steps": ["syntax", "syntax"]}}
    plan = ValidationCoordinator().build_plan(profile, detect_toolchain(tmp_path))
    assert len(plan.commands) == 1


def test_composition_pool_swaps_when_cycle_boundary_repeats(monkeypatch):
    import random as random_module

    import app.utils.pptx.composition_pool as module

    class BoundaryRandom(random_module.Random):
        calls = 0

        def shuffle(self, values):
            type(self).calls += 1
            if type(self).calls >= 2:
                values[:] = [10] + [value for value in values if value != 10]

    monkeypatch.setattr(module.random, "Random", BoundaryRandom)
    sequence = module.select_layout_variants("t", 22)
    assert sequence[10] == 10
    assert sequence[11] == 0
    assert all(left != right for left, right in zip(sequence, sequence[1:]))


def test_composition_pool_empty_and_recent_filter():
    from app.utils.pptx.composition_pool import select_layout_variants

    assert select_layout_variants("t", 0) == []
    variants = select_layout_variants("t", 5, recent_variants=(0, 99))
    assert len(variants) == 5
    assert variants[0] != 0
