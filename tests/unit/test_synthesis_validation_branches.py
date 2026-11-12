"""Branch coverage for layered validation and candidate selection."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.agent.code_synthesis_contracts import (
    ArtifactSpec,
    ChangePlanIR,
    GenerationStrategy,
    ProjectModel,
)
from app.agent.orchestration.artifact_committer import ArtifactConsistencyResult
from app.agent.orchestration.plan import build_file_plan
from app.agent.synthesis_validation import (
    CandidateArtifact,
    CandidateBudget,
    CandidateBudgetTracker,
    CandidateFailure,
    CandidateSelectionResult,
    CandidateValidationResult,
    CandidateValidationRouter,
    LayerStatus,
    MinimalDiagnostic,
    SynthesisCandidate,
    ValidationContext,
    ValidationLayerResult,
    ValidationLevel,
    build_repair_feedback,
    candidate_context_hash,
    coordinator_handler,
    delivery_gate_handler,
    delivery_gate_result,
    rank_candidates,
    stack_file_handler,
    validate_model_operation_v0,
    validation_plan_for_level,
)
from app.agent.synthesis_protocol import ModelOperation, ModelOperationKind
from app.agent.toolchain import CommandSpec, ToolchainAction
from app.agent.validation_coordinator import ValidationPlan
from app.agent.validation_report import ValidationCategory, ValidationFinding, ValidationReport


HASH = "b" * 64


def _plan(*paths: str, dependencies: dict[str, tuple[str, ...]] | None = None) -> ChangePlanIR:
    project = ProjectModel(language="python", framework="fastapi")
    artifacts = [
        ArtifactSpec(
            path=path,
            role="source",
            owner="test",
            operation="create",
            strategy=GenerationStrategy.LLM,
            validation_profile="test",
            source="test",
            depends_on=(dependencies or {}).get(path, ()),
        )
        for path in paths
    ]
    return ChangePlanIR.build(project, artifacts)


def _candidate(
    candidate_id: str = "candidate-a",
    *,
    paths: tuple[str, ...] = ("main.py",),
    strategy: GenerationStrategy = GenerationStrategy.LLM,
    content: str = "value = 1\n",
) -> SynthesisCandidate:
    return SynthesisCandidate(
        candidate_id=candidate_id,
        strategy=strategy,
        artifacts=tuple(
            CandidateArtifact(path=path, content=content) for path in paths
        ),
        context_hash=HASH,
    )


def _diag(level: ValidationLevel = ValidationLevel.V0, code: str = "failed") -> MinimalDiagnostic:
    return MinimalDiagnostic(
        level=level,
        category=ValidationCategory.UNKNOWN,
        code=code,
        message="failed",
        context_hash=HASH,
    )


def _layer(
    level: ValidationLevel,
    status: LayerStatus = LayerStatus.PASSED,
    **kwargs,
) -> ValidationLayerResult:
    diagnostics = kwargs.pop("diagnostics", ())
    if status is not LayerStatus.PASSED and not diagnostics:
        diagnostics = (_diag(level),)
    return ValidationLayerResult(
        level=level, status=status, diagnostics=diagnostics, **kwargs
    )


# ---------------------------------------------------------------------------
# Pydantic contract validators
# ---------------------------------------------------------------------------


def test_layer_result_rejects_passed_with_diagnostics() -> None:
    with pytest.raises(ValidationError, match="cannot contain diagnostics"):
        ValidationLayerResult(
            level=ValidationLevel.V0,
            status=LayerStatus.PASSED,
            diagnostics=(_diag(),),
        )


def test_layer_result_rejects_non_passing_without_diagnostics() -> None:
    with pytest.raises(ValidationError, match="requires diagnostics"):
        ValidationLayerResult(
            level=ValidationLevel.V0,
            status=LayerStatus.FAILED,
            diagnostics=(),
        )


def test_layer_result_rejects_mismatched_diagnostic_level() -> None:
    with pytest.raises(ValidationError, match="must match"):
        ValidationLayerResult(
            level=ValidationLevel.V1,
            status=LayerStatus.FAILED,
            diagnostics=(_diag(ValidationLevel.V0),),
        )


def test_candidate_result_rejects_non_prefix_layers() -> None:
    with pytest.raises(ValidationError, match="V0-based prefix"):
        CandidateValidationResult(
            candidate=_candidate(),
            layers=(_layer(ValidationLevel.V1),),
        )


def test_candidate_result_rejects_success_with_failure_classification() -> None:
    layers = tuple(_layer(level) for level in ValidationLevel)
    with pytest.raises(ValidationError, match="cannot contain a failure"):
        CandidateValidationResult(
            candidate=_candidate(),
            layers=layers,
            failure=CandidateFailure.VALIDATION_FAILED,
        )


def test_candidate_result_requires_failure_classification() -> None:
    with pytest.raises(ValidationError, match="requires a failure classification"):
        CandidateValidationResult(
            candidate=_candidate(),
            layers=(_layer(ValidationLevel.V0),),
            failure=None,
        )


def test_candidate_result_requires_failed_final_layer() -> None:
    with pytest.raises(ValidationError, match="must end at a failed layer"):
        CandidateValidationResult(
            candidate=_candidate(),
            layers=(_layer(ValidationLevel.V0), _layer(ValidationLevel.V1)),
            failure=CandidateFailure.VALIDATION_FAILED,
        )


def test_candidate_result_stops_after_first_failure() -> None:
    with pytest.raises(ValidationError, match="stop after the first non-passing"):
        CandidateValidationResult(
            candidate=_candidate(),
            layers=(
                _layer(ValidationLevel.V0, LayerStatus.FAILED),
                _layer(ValidationLevel.V1, LayerStatus.FAILED),
            ),
            failure=CandidateFailure.VALIDATION_FAILED,
        )


def test_candidate_budget_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError, match="must be positive"):
        CandidateBudget(task_limit=0)
    with pytest.raises(ValueError, match="must be positive"):
        CandidateBudget(strategy_limit=0)


def test_budget_tracker_returns_none_until_strategy_limit() -> None:
    tracker = CandidateBudgetTracker(CandidateBudget(task_limit=5, strategy_limit=1))
    assert tracker.consume(GenerationStrategy.LLM) is None
    assert (
        tracker.consume(GenerationStrategy.LLM)
        is CandidateFailure.STRATEGY_CANDIDATE_BUDGET_EXHAUSTED
    )


# ---------------------------------------------------------------------------
# V0 operation validation edge cases
# ---------------------------------------------------------------------------


def test_patch_touching_only_its_target_is_accepted_and_skips_dev_null() -> None:
    plan = _plan("main.py")
    context = ValidationContext(change_plan=plan, workspace=Path("."))
    operation = ModelOperation(
        operation=ModelOperationKind.PATCH,
        target_path="main.py",
        allowed_paths=("main.py",),
        patch=(
            "--- a/main.py\n"
            "+++ b/main.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
            "--- /dev/null\n"
            "+++ plain/file.txt\n"
        ),
    )

    result = validate_model_operation_v0(operation, context, context_hash=HASH)

    codes = {diagnostic.code for diagnostic in result.diagnostics}
    assert "patch_scope_exceeded" in codes


def test_patch_dev_null_and_unprefixed_paths_are_normalized() -> None:
    plan = _plan("main.py")
    context = ValidationContext(change_plan=plan, workspace=Path("."))
    operation = ModelOperation(
        operation=ModelOperationKind.PATCH,
        target_path="main.py",
        allowed_paths=("main.py",),
        patch="--- /dev/null\n+++ main.py\n@@ -1 +1 @@\n-old\n+new\n",
    )

    result = validate_model_operation_v0(operation, context, context_hash=HASH)

    assert result.passed is True


def test_v0_accepts_operation_without_target_path() -> None:
    plan = _plan("main.py")
    context = ValidationContext(change_plan=plan, workspace=Path("."))
    operation = ModelOperation(
        operation=ModelOperationKind.PLAN,
    )

    result = validate_model_operation_v0(operation, context, context_hash=HASH)

    assert result.passed is True


# ---------------------------------------------------------------------------
# Router edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_router_rejects_handler_for_a_different_level(tmp_path) -> None:
    async def wrong_level(candidate, context):
        return _layer(ValidationLevel.V0)

    router = CandidateValidationRouter({ValidationLevel.V1: wrong_level})

    with pytest.raises(ValueError, match="returned v0_protocol"):
        await router.validate(
            _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
        )


@pytest.mark.asyncio
async def test_router_preserves_handler_elapsed_time(tmp_path) -> None:
    layers = tuple(_layer(level, elapsed_ms=7) for level in ValidationLevel)

    async def handler(candidate, context, level):
        return layers[level.index]

    handlers = {level: (lambda c, ctx, lvl=level: handler(c, ctx, lvl))
                for level in tuple(ValidationLevel)[1:]}
    router = CandidateValidationRouter(handlers)

    result = await router.validate(
        _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    )

    assert result.success
    assert all(layer.elapsed_ms == 7 for layer in result.layers[1:])


@pytest.mark.asyncio
async def test_router_flags_empty_candidate_content(tmp_path) -> None:
    result = await CandidateValidationRouter({}).validate(
        _candidate(content="   \n"),
        ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path),
    )

    assert result.diagnostics[0].code == "candidate_content_empty"


# ---------------------------------------------------------------------------
# Ranking and repair feedback
# ---------------------------------------------------------------------------


def test_rank_candidates_without_success_has_no_winner() -> None:
    failed = CandidateValidationResult(
        candidate=_candidate(),
        layers=(_layer(ValidationLevel.V0, LayerStatus.FAILED),),
        failure=CandidateFailure.VALIDATION_FAILED,
    )

    selection = rank_candidates((failed,))

    assert isinstance(selection, CandidateSelectionResult)
    assert selection.winner is None
    assert selection.ranked == (failed,)


def test_repair_feedback_rejects_invalid_limits() -> None:
    result = CandidateValidationResult(
        candidate=_candidate(),
        layers=(_layer(ValidationLevel.V0, LayerStatus.FAILED),),
        failure=CandidateFailure.VALIDATION_FAILED,
    )

    with pytest.raises(ValueError, match="feedback limits are invalid"):
        build_repair_feedback(result, max_diagnostics=0)
    with pytest.raises(ValueError, match="feedback limits are invalid"):
        build_repair_feedback(result, context_budget_chars=-1)


def test_repair_feedback_skips_empty_and_stops_at_budget() -> None:
    result = CandidateValidationResult(
        candidate=_candidate(),
        layers=(_layer(ValidationLevel.V0, LayerStatus.FAILED),),
        failure=CandidateFailure.VALIDATION_FAILED,
    )

    feedback = build_repair_feedback(
        result, ("", "abc", "ignored"), context_budget_chars=3
    )

    assert feedback.related_context == ("abc",)


# ---------------------------------------------------------------------------
# Handler factories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stack_file_handler_passes_when_all_artifacts_parse(tmp_path) -> None:
    class Adapter:
        def extract_symbols(self, path: Path, content: str):
            return object()

    result = await stack_file_handler(Adapter())(
        _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    )

    assert result.status is LayerStatus.PASSED


class _StubCoordinator:
    def __init__(self, findings):
        self.findings = findings
        self.executed = None

    async def execute(self, plan, workspace):
        self.executed = (plan, workspace)
        return ()

    def to_report(self, plan, results, *, context_hash):
        return ValidationReport.create(self.findings)


@pytest.mark.asyncio
async def test_coordinator_handler_reports_pass_and_failure(tmp_path) -> None:
    plan = ValidationPlan(
        commands=(CommandSpec(action=ToolchainAction.BUILD, command=("make",)),),
        unsupported_steps=("schema_contract",),
    )
    passing = coordinator_handler(
        ValidationLevel.V2, _StubCoordinator(()), plan
    )
    failing_finding = ValidationFinding(
        category=ValidationCategory.TYPE,
        message="contract broken",
        file_path="main.py",
        context_hash=HASH,
    )
    failing = coordinator_handler(
        ValidationLevel.V4, _StubCoordinator((failing_finding,)), plan
    )
    context = ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)

    passed_result = await passing(_candidate(), context)
    failed_result = await failing(_candidate(), context)

    assert passed_result.status is LayerStatus.PASSED
    assert failed_result.status is LayerStatus.FAILED
    assert failed_result.diagnostics[0].code == "validation_failed"
    assert failed_result.diagnostics[0].file_path == "main.py"


@pytest.mark.asyncio
async def test_coordinator_handler_uses_finding_code_when_present(tmp_path) -> None:
    finding = ValidationFinding(
        category=ValidationCategory.SYNTAX,
        message="bad syntax",
        code="E001",
        context_hash=HASH,
    )
    handler = coordinator_handler(
        ValidationLevel.V3,
        _StubCoordinator((finding,)),
        ValidationPlan(commands=(), unsupported_steps=()),
    )

    result = await handler(
        _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    )

    assert result.diagnostics[0].code == "E001"


@pytest.mark.asyncio
async def test_delivery_gate_handler_passes_on_empty_plan(tmp_path) -> None:
    plan = build_file_plan([], requested_paths=[], allow_empty=True)
    handler = delivery_gate_handler(plan, {}, ())

    result = await handler(
        _candidate(paths=()), ValidationContext(change_plan=_plan(), workspace=tmp_path)
    )

    assert result.level is ValidationLevel.V6
    assert result.status is LayerStatus.PASSED


@pytest.mark.asyncio
async def test_delivery_gate_handler_forwards_preserved_paths(tmp_path) -> None:
    plan = build_file_plan([], requested_paths=[], allow_empty=True)
    handler = delivery_gate_handler(plan, {}, (), preserved_paths=("keep.txt",))

    result = await handler(
        _candidate(paths=()), ValidationContext(change_plan=_plan(), workspace=tmp_path)
    )

    assert result.status is LayerStatus.FAILED
    assert result.diagnostics[0].code == "artifact_consistency_failed"


def test_delivery_gate_result_passes_when_consistent() -> None:
    result = delivery_gate_result(
        ArtifactConsistencyResult(
            success=True,
            planned_paths=(),
            manifest_paths=(),
            completed_paths=(),
            disk_paths=(),
        ),
        HASH,
    )

    assert result.status is LayerStatus.PASSED


def test_validation_plan_for_unknown_level_is_empty() -> None:
    plan = ValidationPlan(
        commands=(CommandSpec(action=ToolchainAction.BUILD, command=("make",)),),
        unsupported_steps=("schema_contract",),
    )

    scoped = validation_plan_for_level(plan, ValidationLevel.V0)

    assert scoped.commands == ()
    assert scoped.unsupported_steps == ()


def test_candidate_context_hash_handles_unserializable_values() -> None:
    value = object()

    assert candidate_context_hash(value) == candidate_context_hash(value)
