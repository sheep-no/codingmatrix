from pathlib import Path

import pytest

from app.agent.code_synthesis_contracts import (
    ArtifactSpec,
    ChangePlanIR,
    GenerationStrategy,
    ProjectModel,
)
from app.agent.contract_index import ContractIndex
from app.agent.orchestration.artifact_committer import (
    ArtifactConsistencyResult,
    ArtifactDiagnostic,
)
from app.agent.synthesis_validation import (
    CandidateArtifact,
    CandidateBudget,
    CandidateFailure,
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
    delivery_gate_result,
    rank_candidates,
    stack_file_handler,
    validation_plan_for_level,
    validate_model_operation_v0,
)
from app.agent.synthesis_protocol import ModelOperation, ModelOperationKind
from app.agent.toolchain import CommandSpec, ToolchainAction
from app.agent.validation_coordinator import ValidationPlan
from app.agent.validation_report import ValidationCategory


HASH = "a" * 64


def _plan(
    *paths: str,
    preconditions: tuple[str, ...] = (),
    dependencies: dict[str, tuple[str, ...]] | None = None,
) -> ChangePlanIR:
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
            preconditions=preconditions,
            depends_on=(dependencies or {}).get(path, ()),
        )
        for path in paths
    ]
    return ChangePlanIR.build(project, artifacts)


def test_v0_accepts_scoped_operation_with_declared_dependency_and_contract() -> None:
    plan = _plan("models.py", "routes.py", dependencies={"routes.py": ("models.py",)})
    context = ValidationContext(change_plan=plan, workspace=Path("."))
    operation = ModelOperation(
        operation=ModelOperationKind.FILE_SLOT,
        target_path="routes.py",
        allowed_paths=("models.py", "routes.py"),
        depends_on=("models.py",),
        contract_refs=("todo.read",),
        content="def read():\n    return []\n",
    )
    index = ContractIndex.build(
        [{"name": "todo.read", "kind": "api", "owner": "routes"}]
    )

    result = validate_model_operation_v0(
        operation, context, contract_index=index, context_hash=HASH
    )

    assert result.passed is True


def test_v0_rejects_plan_scope_dependency_contract_and_patch_violations() -> None:
    plan = _plan("routes.py", "models.py")
    context = ValidationContext(change_plan=plan, workspace=Path("."))
    operation = ModelOperation(
        operation=ModelOperationKind.PATCH,
        target_path="routes.py",
        allowed_paths=("routes.py", "models.py"),
        depends_on=("models.py",),
        contract_refs=("missing",),
        patch=(
            "--- a/routes.py\n"
            "+++ b/models.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        ),
    )

    result = validate_model_operation_v0(
        operation,
        context,
        contract_index=ContractIndex.build([]),
        context_hash=HASH,
    )
    codes = {diagnostic.code for diagnostic in result.diagnostics}

    assert result.passed is False
    assert codes == {"operation_dependency_undeclared", "operation_contract_missing", "patch_scope_exceeded"}


def test_v0_rejects_target_outside_frozen_plan() -> None:
    plan = _plan("routes.py")
    context = ValidationContext(change_plan=plan, workspace=Path("."))
    operation = ModelOperation(
        operation=ModelOperationKind.FILE_SLOT,
        target_path="extra.py",
        allowed_paths=("extra.py",),
        content="value = 1\n",
    )

    result = validate_model_operation_v0(operation, context, context_hash=HASH)

    assert result.diagnostics[0].code == "operation_path_outside_plan"


def _candidate(
    candidate_id: str = "candidate-a",
    *,
    paths: tuple[str, ...] = ("main.py",),
    strategy: GenerationStrategy = GenerationStrategy.LLM,
    changed_lines: int = 1,
    model_calls: int = 1,
) -> SynthesisCandidate:
    return SynthesisCandidate(
        candidate_id=candidate_id,
        strategy=strategy,
        artifacts=tuple(CandidateArtifact(path=path, content="value = 1\n") for path in paths),
        changed_lines=changed_lines,
        model_calls=model_calls,
        context_hash=HASH,
    )


def _layer(
    level: ValidationLevel,
    status: LayerStatus = LayerStatus.PASSED,
) -> ValidationLayerResult:
    diagnostics = ()
    if status is not LayerStatus.PASSED:
        diagnostics = (MinimalDiagnostic(
            level=level,
            category=ValidationCategory.UNKNOWN,
            code="failed",
            message="failed",
            context_hash=HASH,
        ),)
    return ValidationLayerResult(level=level, status=status, diagnostics=diagnostics)


def _result(
    candidate: SynthesisCandidate,
    passed_through: ValidationLevel,
    *,
    success: bool = False,
) -> CandidateValidationResult:
    layers = [_layer(level) for level in ValidationLevel if level.index <= passed_through.index]
    failure = None
    if not success:
        failed_level = ValidationLevel(passed_through.value)
        layers[-1] = _layer(failed_level, LayerStatus.FAILED)
        failure = CandidateFailure.VALIDATION_FAILED
    return CandidateValidationResult(
        candidate=candidate,
        layers=tuple(layers),
        failure=failure,
    )


def _passing_handlers():
    handlers = {}
    for level in tuple(ValidationLevel)[1:]:
        async def handler(candidate, context, current=level):
            return _layer(current)
        handlers[level] = handler
    return handlers


@pytest.mark.asyncio
async def test_router_runs_v0_to_v6_as_an_ordered_prefix(tmp_path) -> None:
    calls = []
    handlers = {}
    for level in tuple(ValidationLevel)[1:]:
        async def handler(candidate, context, current=level):
            calls.append(current)
            return _layer(current)
        handlers[level] = handler

    result = await CandidateValidationRouter(handlers).validate(
        _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    )

    assert result.success
    assert tuple(item.level for item in result.layers) == tuple(ValidationLevel)
    assert calls == list(tuple(ValidationLevel)[1:])


@pytest.mark.asyncio
async def test_v0_rejects_artifact_set_and_precondition_mismatch(tmp_path) -> None:
    context = ValidationContext(
        change_plan=_plan("main.py", "service.py", preconditions=("contract-ready",)),
        workspace=tmp_path,
    )

    result = await CandidateValidationRouter(_passing_handlers()).validate(
        _candidate(paths=("main.py",)), context
    )

    assert result.failure is CandidateFailure.VALIDATION_FAILED
    assert tuple(item.code for item in result.diagnostics) == (
        "candidate_artifact_set_mismatch",
        "artifact_precondition_failed",
        "artifact_precondition_failed",
    )


@pytest.mark.asyncio
async def test_router_stops_after_first_failed_layer(tmp_path) -> None:
    calls = []
    handlers = _passing_handlers()

    async def fail_module(candidate, context):
        calls.append(ValidationLevel.V2)
        return _layer(ValidationLevel.V2, LayerStatus.FAILED)

    async def should_not_run(candidate, context):
        calls.append(ValidationLevel.V3)
        return _layer(ValidationLevel.V3)

    handlers[ValidationLevel.V2] = fail_module
    handlers[ValidationLevel.V3] = should_not_run

    result = await CandidateValidationRouter(handlers).validate(
        _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    )

    assert result.failure is CandidateFailure.VALIDATION_FAILED
    assert result.layers[-1].level is ValidationLevel.V2
    assert calls == [ValidationLevel.V2]


@pytest.mark.asyncio
async def test_missing_layer_is_explicitly_unsupported(tmp_path) -> None:
    result = await CandidateValidationRouter({}).validate(
        _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    )

    assert result.failure is CandidateFailure.VALIDATION_UNSUPPORTED
    assert result.layers[-1].level is ValidationLevel.V1
    assert result.diagnostics[0].code == "validation_layer_unsupported"


@pytest.mark.asyncio
async def test_handler_exception_becomes_structured_layer_failure(tmp_path) -> None:
    handlers = _passing_handlers()

    async def fail(candidate, context):
        raise RuntimeError("runner unavailable")

    handlers[ValidationLevel.V2] = fail
    result = await CandidateValidationRouter(handlers).validate(
        _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    )

    assert result.layers[-1].level is ValidationLevel.V2
    assert result.diagnostics[0].code == "validation_handler_failed"


@pytest.mark.asyncio
async def test_candidate_budget_distinguishes_strategy_and_task_limits(tmp_path) -> None:
    context = ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    strategy_router = CandidateValidationRouter(
        _passing_handlers(), budget=CandidateBudget(task_limit=3, strategy_limit=1)
    )
    assert (await strategy_router.validate(_candidate("one"), context)).success
    strategy_result = await strategy_router.validate(_candidate("two"), context)
    assert strategy_result.failure is CandidateFailure.STRATEGY_CANDIDATE_BUDGET_EXHAUSTED

    task_router = CandidateValidationRouter(
        _passing_handlers(), budget=CandidateBudget(task_limit=1, strategy_limit=2)
    )
    assert (await task_router.validate(_candidate("one"), context)).success
    task_result = await task_router.validate(
        _candidate("two", strategy=GenerationStrategy.PATCH), context
    )
    assert task_result.failure is CandidateFailure.TASK_CANDIDATE_BUDGET_EXHAUSTED


def test_candidate_ranking_prefers_validation_then_smaller_cheaper_change() -> None:
    partial = _result(_candidate("partial"), ValidationLevel.V4)
    expensive = _result(
        _candidate("expensive", changed_lines=20, model_calls=3),
        ValidationLevel.V6,
        success=True,
    )
    efficient = _result(
        _candidate("efficient", changed_lines=3, model_calls=1),
        ValidationLevel.V6,
        success=True,
    )

    selection = rank_candidates((partial, expensive, efficient))

    assert selection.winner is not None
    assert selection.winner.candidate.candidate_id == "efficient"
    assert [item.candidate.candidate_id for item in selection.ranked] == [
        "efficient", "expensive", "partial",
    ]


def test_repair_feedback_keeps_strategy_and_clips_diagnostics_and_context() -> None:
    candidate = _candidate(strategy=GenerationStrategy.PATCH)
    layers = [_layer(ValidationLevel.V0)]
    diagnostics = tuple(MinimalDiagnostic(
        level=ValidationLevel.V1,
        category=ValidationCategory.SYNTAX,
        code=f"error-{index}",
        message="x" * 800,
        file_path="main.py",
        context_hash=HASH,
    ) for index in range(7))
    layers.append(ValidationLayerResult(
        level=ValidationLevel.V1,
        status=LayerStatus.FAILED,
        diagnostics=diagnostics,
    ))
    result = CandidateValidationResult(
        candidate=candidate,
        layers=tuple(layers),
        failure=CandidateFailure.VALIDATION_FAILED,
    )

    feedback = build_repair_feedback(
        result, ("a" * 80, "b" * 80), max_diagnostics=3, context_budget_chars=100
    )

    assert feedback.strategy is GenerationStrategy.PATCH
    assert len(feedback.diagnostics) == 3
    assert sum(map(len, feedback.related_context)) == 100


@pytest.mark.asyncio
async def test_stack_file_handler_converts_adapter_parse_failure_to_v1(tmp_path) -> None:
    class BrokenAdapter:
        def extract_symbols(self, path: Path, content: str):
            raise ValueError("parse failed")

    result = await stack_file_handler(BrokenAdapter())(
        _candidate(), ValidationContext(change_plan=_plan("main.py"), workspace=tmp_path)
    )

    assert result.status is LayerStatus.FAILED
    assert result.diagnostics[0].level is ValidationLevel.V1
    assert result.diagnostics[0].code == "file_parse_failed"


def test_delivery_gate_result_preserves_existing_v6_diagnostic() -> None:
    consistency = ArtifactConsistencyResult(
        success=False,
        planned_paths=("main.py",),
        manifest_paths=(),
        completed_paths=(),
        disk_paths=(),
        diagnostic=ArtifactDiagnostic(
            code="artifact_consistency_failed",
            message="manifest mismatch",
            path="main.py",
        ),
    )

    result = delivery_gate_result(consistency, HASH)

    assert result.level is ValidationLevel.V6
    assert result.status is LayerStatus.FAILED
    assert result.diagnostics[0].code == "artifact_consistency_failed"


def test_validation_plan_is_partitioned_by_v2_v3_and_v5_actions() -> None:
    plan = ValidationPlan(
        commands=(
            CommandSpec(action=ToolchainAction.BUILD, command=("go", "build", "./...")),
            CommandSpec(action=ToolchainAction.TEST, command=("go", "test", "./...")),
            CommandSpec(action=ToolchainAction.SMOKE, command=("go", "run", ".")),
        ),
        unsupported_steps=("schema_contract", "headless_startup"),
    )

    assert tuple(command.action for command in validation_plan_for_level(
        plan, ValidationLevel.V2
    ).commands) == (ToolchainAction.BUILD,)
    assert tuple(command.action for command in validation_plan_for_level(
        plan, ValidationLevel.V3
    ).commands) == (ToolchainAction.TEST,)
    smoke = validation_plan_for_level(plan, ValidationLevel.V5)
    assert tuple(command.action for command in smoke.commands) == (ToolchainAction.SMOKE,)
    assert smoke.unsupported_steps == ("headless_startup",)
    assert validation_plan_for_level(
        plan, ValidationLevel.V4
    ).unsupported_steps == ("schema_contract",)


def test_candidate_contracts_are_strict_and_hash_is_stable() -> None:
    with pytest.raises(ValueError, match="unique"):
        _candidate(paths=("main.py", "main.py"))
    with pytest.raises(ValueError):
        CandidateArtifact(path="../main.py", content="value = 1")

    assert candidate_context_hash({"b": 2, "a": 1}) == candidate_context_hash({"a": 1, "b": 2})


@pytest.mark.asyncio
async def test_v0_reports_unsafe_change_plan_path(tmp_path) -> None:
    project = ProjectModel(language="python")
    unsafe_plan = ChangePlanIR.build(project, [ArtifactSpec(
        path="../main.py",
        role="source",
        owner="test",
        operation="delete",
        strategy=GenerationStrategy.PATCH,
        validation_profile="test",
        source="test",
    )])
    candidate = _candidate(paths=(), strategy=GenerationStrategy.PATCH)

    result = await CandidateValidationRouter(_passing_handlers()).validate(
        candidate, ValidationContext(change_plan=unsafe_plan, workspace=tmp_path)
    )

    assert result.diagnostics[0].code == "artifact_path_invalid"
