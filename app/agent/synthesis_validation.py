"""Layered validation and candidate selection for constrained synthesis."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Awaitable, Callable, Iterable, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.agent.code_synthesis_contracts import ChangePlanIR, GenerationStrategy
from app.agent.orchestration.artifact_committer import (
    ArtifactCompletionEvent,
    ArtifactConsistencyResult,
    check_artifact_success_gate,
)
from app.agent.orchestration.plan import GenerationPlan, normalize_plan_path
from app.agent.stack_adapters import StackAdapter
from app.agent.toolchain import ToolchainAction
from app.agent.validation_coordinator import (
    ValidationCoordinator,
    ValidationPlan,
)
from app.agent.validation_report import ValidationCategory, ValidationFinding


class ValidationLevel(str, Enum):
    V0 = "v0_protocol"
    V1 = "v1_file"
    V2 = "v2_module"
    V3 = "v3_tests"
    V4 = "v4_contract"
    V5 = "v5_smoke"
    V6 = "v6_delivery"

    @property
    def index(self) -> int:
        return _VALIDATION_LEVELS.index(self)


_VALIDATION_LEVELS = tuple(ValidationLevel)

_ACTIONS_BY_LEVEL = {
    ValidationLevel.V2: frozenset({
        ToolchainAction.INSTALL,
        ToolchainAction.LINT,
        ToolchainAction.TYPECHECK,
        ToolchainAction.BUILD,
    }),
    ValidationLevel.V3: frozenset({ToolchainAction.TEST}),
    ValidationLevel.V5: frozenset({
        ToolchainAction.START,
        ToolchainAction.SMOKE,
        ToolchainAction.HEALTH,
    }),
}

_UNSUPPORTED_STEPS_BY_LEVEL = {
    ValidationLevel.V2: frozenset({"syntax", "install", "lint", "typecheck", "build"}),
    ValidationLevel.V3: frozenset({"test", "tests", "unit_tests", "command_test"}),
    ValidationLevel.V4: frozenset({"api_contract", "schema_contract", "consumer_contract"}),
    ValidationLevel.V5: frozenset({"start", "smoke", "smoke_test", "health", "headless_startup"}),
}


class LayerStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNSUPPORTED = "unsupported"
    BUDGET_EXHAUSTED = "budget_exhausted"


class CandidateFailure(str, Enum):
    VALIDATION_FAILED = "validation_failed"
    VALIDATION_UNSUPPORTED = "validation_unsupported"
    TASK_CANDIDATE_BUDGET_EXHAUSTED = "task_candidate_budget_exhausted"
    STRATEGY_CANDIDATE_BUDGET_EXHAUSTED = "strategy_candidate_budget_exhausted"


class CandidateArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    content: str

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        return normalize_plan_path(value)


class SynthesisCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    strategy: GenerationStrategy
    artifacts: tuple[CandidateArtifact, ...]
    changed_lines: int = Field(default=0, ge=0)
    model_calls: int = Field(default=0, ge=0)
    context_hash: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_unique_paths(self) -> "SynthesisCandidate":
        paths = tuple(item.path for item in self.artifacts)
        if len(paths) != len(set(paths)):
            raise ValueError("candidate artifact paths must be unique")
        return self

    @property
    def artifact_map(self) -> Mapping[str, str]:
        return {item.path: item.content for item in self.artifacts}


class MinimalDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: ValidationLevel
    category: ValidationCategory
    code: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=800)
    file_path: str | None = None
    context_hash: str = Field(min_length=64, max_length=64)


class ValidationLayerResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    level: ValidationLevel
    status: LayerStatus
    diagnostics: tuple[MinimalDiagnostic, ...] = ()
    elapsed_ms: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_diagnostics(self) -> "ValidationLayerResult":
        if self.status is LayerStatus.PASSED and self.diagnostics:
            raise ValueError("passed validation layer cannot contain diagnostics")
        if self.status is not LayerStatus.PASSED and not self.diagnostics:
            raise ValueError("non-passing validation layer requires diagnostics")
        if any(item.level is not self.level for item in self.diagnostics):
            raise ValueError("diagnostic level must match validation layer")
        return self

    @property
    def passed(self) -> bool:
        return self.status is LayerStatus.PASSED


class CandidateValidationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate: SynthesisCandidate
    layers: tuple[ValidationLayerResult, ...]
    failure: CandidateFailure | None = None

    @model_validator(mode="after")
    def validate_sequence(self) -> "CandidateValidationResult":
        indexes = tuple(item.level.index for item in self.layers)
        if indexes != tuple(range(len(indexes))):
            raise ValueError("candidate validation layers must form a V0-based prefix")
        if self.success and self.failure is not None:
            raise ValueError("successful candidate cannot contain a failure classification")
        if not self.success:
            if self.failure is None:
                raise ValueError("non-passing candidate requires a failure classification")
            if not self.layers or self.layers[-1].passed:
                raise ValueError("non-passing candidate must end at a failed layer")
            if any(not layer.passed for layer in self.layers[:-1]):
                raise ValueError("validation must stop after the first non-passing layer")
        return self

    @property
    def success(self) -> bool:
        return len(self.layers) == len(_VALIDATION_LEVELS) and all(
            layer.passed for layer in self.layers
        )

    @property
    def highest_passed_level(self) -> int:
        passed = [layer.level.index for layer in self.layers if layer.passed]
        return max(passed, default=-1)

    @property
    def diagnostics(self) -> tuple[MinimalDiagnostic, ...]:
        return tuple(item for layer in self.layers for item in layer.diagnostics)


class CandidateSelectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    winner: CandidateValidationResult | None
    ranked: tuple[CandidateValidationResult, ...]


class RepairFeedback(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    candidate_id: str = Field(min_length=1)
    strategy: GenerationStrategy
    diagnostics: tuple[MinimalDiagnostic, ...]
    related_context: tuple[str, ...] = ()


@dataclass(frozen=True)
class CandidateBudget:
    task_limit: int = 6
    strategy_limit: int = 3

    def __post_init__(self) -> None:
        if self.task_limit < 1 or self.strategy_limit < 1:
            raise ValueError("candidate limits must be positive")


@dataclass
class CandidateBudgetTracker:
    budget: CandidateBudget
    total_used: int = 0
    used_by_strategy: dict[GenerationStrategy, int] = field(
        default_factory=lambda: defaultdict(int)
    )

    def consume(self, strategy: GenerationStrategy) -> CandidateFailure | None:
        if self.total_used >= self.budget.task_limit:
            return CandidateFailure.TASK_CANDIDATE_BUDGET_EXHAUSTED
        if self.used_by_strategy[strategy] >= self.budget.strategy_limit:
            return CandidateFailure.STRATEGY_CANDIDATE_BUDGET_EXHAUSTED
        self.total_used += 1
        self.used_by_strategy[strategy] += 1
        return None


@dataclass(frozen=True)
class ValidationContext:
    change_plan: ChangePlanIR
    workspace: Path
    satisfied_preconditions: frozenset[str] = frozenset()


LayerHandler = Callable[
    [SynthesisCandidate, ValidationContext],
    Awaitable[ValidationLayerResult],
]


class CandidateValidationRouter:
    """Run validation as a strict V0-V6 prefix under candidate budgets."""

    def __init__(
        self,
        handlers: Mapping[ValidationLevel, LayerHandler],
        *,
        budget: CandidateBudget | None = None,
    ) -> None:
        self.handlers = dict(handlers)
        self.budget_tracker = CandidateBudgetTracker(budget or CandidateBudget())

    async def validate(
        self,
        candidate: SynthesisCandidate,
        context: ValidationContext,
    ) -> CandidateValidationResult:
        exhausted = self.budget_tracker.consume(candidate.strategy)
        if exhausted is not None:
            diagnostic = _diagnostic(
                ValidationLevel.V0,
                ValidationCategory.UNKNOWN,
                exhausted.value,
                "candidate generation budget exhausted",
                candidate.context_hash,
            )
            layer = ValidationLayerResult(
                level=ValidationLevel.V0,
                status=LayerStatus.BUDGET_EXHAUSTED,
                diagnostics=(diagnostic,),
            )
            return CandidateValidationResult(
                candidate=candidate,
                layers=(layer,),
                failure=exhausted,
            )

        layers: list[ValidationLayerResult] = []
        for level in _VALIDATION_LEVELS:
            started = monotonic()
            if level is ValidationLevel.V0:
                result = self._validate_v0(candidate, context)
            else:
                handler = self.handlers.get(level)
                if handler is None:
                    result = _unsupported_layer(level, candidate.context_hash)
                else:
                    try:
                        result = await handler(candidate, context)
                    except Exception as exc:
                        result = ValidationLayerResult(
                            level=level,
                            status=LayerStatus.FAILED,
                            diagnostics=(_diagnostic(
                                level,
                                ValidationCategory.UNKNOWN,
                                "validation_handler_failed",
                                str(exc),
                                candidate.context_hash,
                            ),),
                        )
            if result.level is not level:
                raise ValueError(f"validation handler for {level.value} returned {result.level.value}")
            if result.elapsed_ms == 0:
                result = result.model_copy(
                    update={"elapsed_ms": max(0, int((monotonic() - started) * 1000))}
                )
            layers.append(result)
            if not result.passed:
                failure = (
                    CandidateFailure.VALIDATION_UNSUPPORTED
                    if result.status is LayerStatus.UNSUPPORTED
                    else CandidateFailure.VALIDATION_FAILED
                )
                return CandidateValidationResult(
                    candidate=candidate,
                    layers=tuple(layers),
                    failure=failure,
                )
        return CandidateValidationResult(candidate=candidate, layers=tuple(layers))

    @staticmethod
    def _validate_v0(
        candidate: SynthesisCandidate,
        context: ValidationContext,
    ) -> ValidationLayerResult:
        expected = {
            artifact.path
            for artifact in context.change_plan.artifacts
            if artifact.operation in {"create", "modify"}
        }
        actual = set(candidate.artifact_map)
        diagnostics: list[MinimalDiagnostic] = []
        if actual != expected:
            diagnostics.append(_diagnostic(
                ValidationLevel.V0,
                ValidationCategory.TYPE,
                "candidate_artifact_set_mismatch",
                f"candidate artifacts differ from change plan: missing={sorted(expected - actual)}, extra={sorted(actual - expected)}",
                candidate.context_hash,
            ))
        for artifact in context.change_plan.artifacts:
            try:
                normalize_plan_path(artifact.path)
            except (TypeError, ValueError) as exc:
                diagnostics.append(_diagnostic(
                    ValidationLevel.V0,
                    ValidationCategory.TYPE,
                    "artifact_path_invalid",
                    str(exc),
                    candidate.context_hash,
                    artifact.path,
                ))
            missing = set(artifact.preconditions) - context.satisfied_preconditions
            if missing:
                diagnostics.append(_diagnostic(
                    ValidationLevel.V0,
                    ValidationCategory.UNKNOWN,
                    "artifact_precondition_failed",
                    f"unsatisfied preconditions: {sorted(missing)}",
                    candidate.context_hash,
                    artifact.path,
                ))
        for path, content in candidate.artifact_map.items():
            if not content.strip():
                diagnostics.append(_diagnostic(
                    ValidationLevel.V0,
                    ValidationCategory.SYNTAX,
                    "candidate_content_empty",
                    "candidate artifact content is empty",
                    candidate.context_hash,
                    path,
                ))
        return ValidationLayerResult(
            level=ValidationLevel.V0,
            status=LayerStatus.FAILED if diagnostics else LayerStatus.PASSED,
            diagnostics=tuple(diagnostics),
        )


def rank_candidates(
    results: Iterable[CandidateValidationResult],
) -> CandidateSelectionResult:
    ranked = tuple(sorted(results, key=_candidate_rank_key))
    winner = next((result for result in ranked if result.success), None)
    return CandidateSelectionResult(winner=winner, ranked=ranked)


def build_repair_feedback(
    result: CandidateValidationResult,
    related_context: Sequence[str] = (),
    *,
    max_diagnostics: int = 5,
    context_budget_chars: int = 2_000,
) -> RepairFeedback:
    if max_diagnostics < 1 or context_budget_chars < 0:
        raise ValueError("feedback limits are invalid")
    remaining = context_budget_chars
    snippets = []
    for item in related_context:
        if remaining <= 0:
            break
        clipped = str(item)[:remaining]
        if clipped:
            snippets.append(clipped)
            remaining -= len(clipped)
    return RepairFeedback(
        candidate_id=result.candidate.candidate_id,
        strategy=result.candidate.strategy,
        diagnostics=result.diagnostics[:max_diagnostics],
        related_context=tuple(snippets),
    )


def stack_file_handler(adapter: StackAdapter) -> LayerHandler:
    async def validate(
        candidate: SynthesisCandidate,
        context: ValidationContext,
    ) -> ValidationLayerResult:
        diagnostics = []
        for artifact in candidate.artifacts:
            try:
                adapter.extract_symbols(Path(artifact.path), artifact.content)
            except Exception as exc:
                diagnostics.append(_diagnostic(
                    ValidationLevel.V1,
                    ValidationCategory.SYNTAX,
                    "file_parse_failed",
                    str(exc),
                    candidate.context_hash,
                    artifact.path,
                ))
        return ValidationLayerResult(
            level=ValidationLevel.V1,
            status=LayerStatus.FAILED if diagnostics else LayerStatus.PASSED,
            diagnostics=tuple(diagnostics),
        )

    return validate


def coordinator_handler(
    level: ValidationLevel,
    coordinator: ValidationCoordinator,
    plan: ValidationPlan,
) -> LayerHandler:
    scoped_plan = validation_plan_for_level(plan, level)

    async def validate(
        candidate: SynthesisCandidate,
        context: ValidationContext,
    ) -> ValidationLayerResult:
        results = await coordinator.execute(scoped_plan, context.workspace)
        report = coordinator.to_report(scoped_plan, results, context_hash=candidate.context_hash)
        diagnostics = tuple(
            _finding_diagnostic(level, finding) for finding in report.findings
        )
        return ValidationLayerResult(
            level=level,
            status=LayerStatus.FAILED if diagnostics else LayerStatus.PASSED,
            diagnostics=diagnostics,
        )

    return validate


def validation_plan_for_level(
    plan: ValidationPlan,
    level: ValidationLevel,
) -> ValidationPlan:
    """Restrict a coordinator plan to the commands owned by one DAG level."""
    actions = _ACTIONS_BY_LEVEL.get(level, frozenset())
    step_names = _UNSUPPORTED_STEPS_BY_LEVEL.get(level, frozenset())
    return ValidationPlan(
        commands=tuple(command for command in plan.commands if command.action in actions),
        unsupported_steps=tuple(
            step for step in plan.unsupported_steps if step in step_names
        ),
    )


def delivery_gate_handler(
    plan: GenerationPlan,
    manifest: Mapping[str, Mapping[str, object]],
    completion_events: Iterable[ArtifactCompletionEvent],
    *,
    preserved_paths: Iterable[str] = (),
) -> LayerHandler:
    events = tuple(completion_events)
    preserved = tuple(preserved_paths)

    async def validate(
        candidate: SynthesisCandidate,
        context: ValidationContext,
    ) -> ValidationLayerResult:
        result = check_artifact_success_gate(
            plan,
            manifest,
            events,
            context.workspace,
            preserved_paths=preserved,
        )
        return delivery_gate_result(result, candidate.context_hash)

    return validate


def delivery_gate_result(
    result: ArtifactConsistencyResult,
    context_hash: str,
) -> ValidationLayerResult:
    if result.success:
        return ValidationLayerResult(level=ValidationLevel.V6, status=LayerStatus.PASSED)
    diagnostic = result.diagnostic
    assert diagnostic is not None
    return ValidationLayerResult(
        level=ValidationLevel.V6,
        status=LayerStatus.FAILED,
        diagnostics=(_diagnostic(
            ValidationLevel.V6,
            ValidationCategory.FRAMEWORK,
            diagnostic.code,
            diagnostic.message,
            context_hash,
            diagnostic.path,
        ),),
    )


def _candidate_rank_key(result: CandidateValidationResult) -> tuple[object, ...]:
    hard_failures = sum(
        layer.status in {LayerStatus.FAILED, LayerStatus.BUDGET_EXHAUSTED}
        for layer in result.layers
    )
    return (
        0 if result.success else 1,
        -result.highest_passed_level,
        hard_failures,
        len(result.diagnostics),
        len(result.candidate.artifacts),
        result.candidate.changed_lines,
        result.candidate.model_calls,
        result.candidate.candidate_id,
    )


def _unsupported_layer(level: ValidationLevel, context_hash: str) -> ValidationLayerResult:
    return ValidationLayerResult(
        level=level,
        status=LayerStatus.UNSUPPORTED,
        diagnostics=(_diagnostic(
            level,
            ValidationCategory.UNKNOWN,
            "validation_layer_unsupported",
            f"validation handler is unavailable for {level.value}",
            context_hash,
        ),),
    )


def _finding_diagnostic(
    level: ValidationLevel,
    finding: ValidationFinding,
) -> MinimalDiagnostic:
    return _diagnostic(
        level,
        finding.category,
        finding.code or "validation_failed",
        finding.message,
        finding.context_hash,
        finding.file_path,
    )


def _diagnostic(
    level: ValidationLevel,
    category: ValidationCategory,
    code: str,
    message: str,
    context_hash: str,
    file_path: str | None = None,
) -> MinimalDiagnostic:
    normalized_message = str(message).strip() or code
    return MinimalDiagnostic(
        level=level,
        category=category,
        code=str(code)[:128],
        message=normalized_message[:800],
        file_path=file_path,
        context_hash=context_hash,
    )


def candidate_context_hash(*values: object) -> str:
    payload = json.dumps(values, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


__all__ = [
    "CandidateArtifact",
    "CandidateBudget",
    "CandidateBudgetTracker",
    "CandidateFailure",
    "CandidateSelectionResult",
    "CandidateValidationResult",
    "CandidateValidationRouter",
    "LayerHandler",
    "LayerStatus",
    "MinimalDiagnostic",
    "RepairFeedback",
    "SynthesisCandidate",
    "ValidationContext",
    "ValidationLayerResult",
    "ValidationLevel",
    "build_repair_feedback",
    "candidate_context_hash",
    "coordinator_handler",
    "delivery_gate_handler",
    "delivery_gate_result",
    "rank_candidates",
    "stack_file_handler",
    "validation_plan_for_level",
]
