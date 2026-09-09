"""Fixed, machine-readable matrix for multilingual CRUD evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import mean, quantiles
from collections import Counter
from typing import Callable, Iterable, Tuple

from .code_synthesis_contracts import HttpContract


class ApplicationDomain(str, Enum):
    WEB = "web"
    WINDOWS = "windows"
    ANDROID = "android"
    SCRAPER = "scraper"
    GAME = "game"
    CLI = "cli"


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    language: str
    framework: str
    request: str
    required_files: Tuple[str, ...]
    domain: ApplicationDomain = ApplicationDomain.WEB
    database: str = "sqlite"
    file_scale: str = "small"
    strategy: str = "baseline"
    contract_version: int = 1
    contract_instructions: Tuple[str, ...] = ()
    http_contracts: Tuple[HttpContract, ...] = ()


@dataclass(frozen=True)
class EvaluationRecord:
    case_id: str
    plan_consistent: bool
    interfaces_consistent: bool
    dependency_closure: bool
    files_complete: bool
    compile_passed: bool
    tests_passed: bool
    startup_passed: bool
    persistence_passed: bool
    token_count: int
    elapsed_seconds: float
    database_status: str = "supported"
    database_diagnostics: Tuple[str, ...] = ()
    model_call_count: int = 0
    strategy: str = "baseline"
    file_scale: str = "small"
    first_passed: bool | None = None
    candidate_passed: bool | None = None
    repaired_passed: bool | None = None
    evaluation_status: str = "completed"

    @property
    def success(self) -> bool:
        return all((
            self.plan_consistent, self.interfaces_consistent, self.dependency_closure,
            self.files_complete, self.compile_passed, self.tests_passed,
            self.startup_passed, self.persistence_passed,
            self.database_status == "supported",
        ))

    @property
    def core_passed(self) -> bool:
        """Report the orchestration contract result independently of project quality."""
        return all((self.plan_consistent, self.dependency_closure, self.files_complete))

    @property
    def engineering_passed(self) -> bool:
        """Report language/framework validation independently of model-stage outcomes."""
        return all((
            self.compile_passed,
            self.tests_passed,
            self.startup_passed,
            self.persistence_passed,
            self.database_status == "supported",
        ))

    def stage_success(self, stage: str) -> bool:
        """Return an explicit stage result, falling back to final status for old records."""
        value = {
            "first": self.first_passed,
            "candidate": self.candidate_passed,
            "repaired": self.repaired_passed,
        }[stage]
        return self.success if value is None else value


@dataclass(frozen=True)
class EvaluationSummary:
    total: int
    successful: int
    success_rate: float
    p95_seconds: float


@dataclass(frozen=True)
class LayerSummary:
    total: int
    passed: int
    pass_rate: float
    p95_seconds: float
    excluded: int = 0


@dataclass(frozen=True)
class StrategySummary:
    strategy: str
    total: int
    first_success_rate: float
    candidate_success_rate: float
    repaired_success_rate: float
    average_model_calls: float
    p95_seconds: float


@dataclass(frozen=True)
class EvaluationReport:
    summary: EvaluationSummary
    missing_case_ids: Tuple[str, ...]
    invalid_case_ids: Tuple[str, ...]
    failure_categories: Tuple[Tuple[str, int], ...]
    matrix_complete: bool
    target_success_rate: float
    target_met: bool
    strategy_summaries: Tuple[StrategySummary, ...] = ()
    core_summary: LayerSummary | None = None
    engineering_summary: LayerSummary | None = None
    quality_summary: LayerSummary | None = None


_FIXTURE_CONTRACTS: dict[tuple[str, str], Tuple[str, ...]] = {
    ("python", "fastapi"): (
        "Bind SQLAlchemy metadata to a real SQLite engine before serving requests.",
        "Every FastAPI database dependency must yield a usable session and close it after the request.",
        "Generated pytest tests must be collected by pytest and use fastapi.testclient.TestClient(app).",
        "Use the documented TestClient response API, including response.json().",
    ),
}


FIXED_CRUD_CASES: Tuple[EvaluationCase, ...] = (
    EvaluationCase("python-fastapi-crud", "python", "fastapi", "Create a CRUD todo API with SQLite persistence.", ("app/main.py", "app/models.py", "app/schemas.py", "app/crud.py", "tests/test_crud.py"), contract_instructions=_FIXTURE_CONTRACTS[("python", "fastapi")]),
    EvaluationCase("python-flask-crud", "python", "flask", "Create a CRUD todo API with SQLite persistence.", ("app.py", "models.py", "crud.py", "tests/test_crud.py")),
    EvaluationCase("typescript-express-crud", "typescript", "express", "Create a CRUD todo API with SQLite persistence.", ("src/app.ts", "src/routes/todos.ts", "src/db.ts", "tests/todos.test.ts")),
    EvaluationCase("typescript-nestjs-crud", "typescript", "nestjs", "Create a CRUD todo API with SQLite persistence.", ("src/main.ts", "src/todos/todos.controller.ts", "src/todos/todos.service.ts", "test/todos.e2e-spec.ts")),
    EvaluationCase("go-http-crud", "go", "net/http", "Create a CRUD todo API with SQLite persistence.", ("go.mod", "go.sum", "cmd/server/main.go", "internal/todos/handler.go", "internal/todos/store.go", "internal/todos/handler_test.go")),
     EvaluationCase("java-spring-boot-crud", "java", "spring-boot", "Create a CRUD todo API with SQLite persistence.", ("pom.xml", "src/main/java/com/example/Application.java", "src/main/java/com/example/Todo.java", "src/main/java/com/example/TodoController.java", "src/main/java/com/example/TodoRepository.java", "src/test/java/com/example/TodoControllerTest.java")),
)


_SCALE_FILES = {
    "single": {
        "python": ("main.py",),
        "typescript": ("src/index.ts",),
        "go": ("main.go",),
        "java": ("src/main/java/com/example/Application.java",),
    },
    "small": {
        "python": ("app/main.py", "app/models.py", "app/schemas.py", "tests/test_crud.py"),
        "typescript": ("src/app.ts", "src/routes/todos.ts", "tests/todos.test.ts"),
        "go": ("cmd/server/main.go", "internal/todos/store.go", "internal/todos/handler_test.go"),
        "java": ("pom.xml", "src/main/java/com/example/Application.java", "src/test/java/com/example/TodoControllerTest.java"),
    },
    "modular": {
        "python": ("app/main.py", "app/models.py", "app/schemas.py", "app/crud.py", "app/repository.py", "tests/test_crud.py"),
        "typescript": ("src/app.ts", "src/routes/todos.ts", "src/services/todos.ts", "src/repositories/todos.ts", "tests/todos.test.ts"),
        "go": ("go.mod", "go.sum", "cmd/server/main.go", "internal/todos/store.go", "internal/todos/service.go", "internal/todos/handler.go", "internal/todos/handler_test.go"),
        "java": ("pom.xml", "src/main/java/com/example/Application.java", "src/main/java/com/example/Todo.java", "src/main/java/com/example/TodoRepository.java", "src/main/java/com/example/TodoService.java", "src/test/java/com/example/TodoControllerTest.java"),
    },
}

_FRAMEWORKS = {"python": "fastapi", "typescript": "express", "go": "net/http", "java": "spring-boot"}


FIXED_EVALUATION_MATRIX: Tuple[EvaluationCase, ...] = tuple(
    EvaluationCase(
        case_id=f"{language}-{scale}-{strategy}",
        language=language,
        framework=_FRAMEWORKS[language],
        request="Create a CRUD todo API with SQLite persistence.",
        required_files=files,
        file_scale=scale,
        strategy=strategy,
        contract_instructions=_FIXTURE_CONTRACTS.get((language, _FRAMEWORKS[language]), ()),
    )
    for language in ("python", "typescript", "go", "java")
    for scale, language_files in _SCALE_FILES.items()
    for strategy in ("traditional", "spec_first")
    for files in (language_files[language],)
)


class EvaluationRegistry:
    """Runtime registry for baseline and workspace-specific evaluation cases."""

    def __init__(self, cases: Iterable[EvaluationCase] = FIXED_CRUD_CASES) -> None:
        self._cases: dict[str, EvaluationCase] = {}
        for case in cases:
            self.register_case(case)

    def register_case(self, case: EvaluationCase) -> None:
        if case.case_id in self._cases:
            raise ValueError(f"duplicate evaluation case: {case.case_id}")
        self._cases[case.case_id] = case

    @property
    def cases(self) -> Tuple[EvaluationCase, ...]:
        return tuple(self._cases.values())

    def build_report(self, records: Iterable[EvaluationRecord]) -> EvaluationReport:
        return build_report(records, cases=self.cases)


def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    return values[0] if len(values) == 1 else quantiles(values, n=100, method="inclusive")[94]


def summarize(records: Iterable[EvaluationRecord]) -> EvaluationSummary:
    values = list(records)
    if not values:
        return EvaluationSummary(0, 0, 0.0, 0.0)
    p95 = _p95(sorted(record.elapsed_seconds for record in values))
    successful = sum(record.success for record in values)
    return EvaluationSummary(len(values), successful, successful / len(values), p95)


def summarize_layer(
    records: Iterable[EvaluationRecord],
    passed: Callable[[EvaluationRecord], bool],
) -> LayerSummary:
    all_values = list(records)
    values = [record for record in all_values if record.evaluation_status != "evaluation_infrastructure_failure"]
    excluded = sum(
        record.evaluation_status == "evaluation_infrastructure_failure"
        for record in all_values
    )
    if not values:
        return LayerSummary(0, 0, 0.0, 0.0, excluded)
    successful = sum(bool(passed(record)) for record in values)
    return LayerSummary(
        total=len(values),
        passed=successful,
        pass_rate=successful / len(values),
        p95_seconds=_p95(sorted(record.elapsed_seconds for record in values)),
        excluded=excluded,
    )


def build_report(
    records: Iterable[EvaluationRecord],
    *,
    cases: Iterable[EvaluationCase] = FIXED_CRUD_CASES,
    target_success_rate: float = 0.9,
) -> EvaluationReport:
    if not 0 <= target_success_rate <= 1:
        raise ValueError("target_success_rate must be between 0 and 1")
    values = list(records)
    expected = {case.case_id for case in cases}
    actual = {record.case_id for record in values}
    missing = tuple(sorted(expected - actual))
    duplicate_ids = {case_id for case_id, count in Counter(record.case_id for record in values).items() if count > 1}
    invalid = tuple(sorted({
        record.case_id for record in values
        if record.case_id not in expected or record.case_id in duplicate_ids
        or record.elapsed_seconds < 0 or record.token_count < 0
        or record.model_call_count < 0
        or record.database_status not in {"supported", "experimental", "unsupported"}
        or record.evaluation_status not in {"completed", "evaluation_infrastructure_failure"}
    }))
    categories = {
        "evaluation_infrastructure_failure": sum(
            record.evaluation_status == "evaluation_infrastructure_failure"
            for record in values
        ),
    }
    completed_values = [
        record
        for record in values
        if record.evaluation_status != "evaluation_infrastructure_failure"
    ]
    categories.update({
        "plan": sum(not record.plan_consistent for record in completed_values),
        "interface": sum(not record.interfaces_consistent for record in completed_values),
        "dependency": sum(not record.dependency_closure for record in completed_values),
        "artifact": sum(not record.files_complete for record in completed_values),
        "compile": sum(not record.compile_passed for record in completed_values),
        "test": sum(not record.tests_passed for record in completed_values),
        "startup": sum(not record.startup_passed for record in completed_values),
        "persistence": sum(not record.persistence_passed for record in completed_values),
        "database": sum(record.database_status != "supported" for record in completed_values),
    })
    summary = summarize(values)
    core_summary = summarize_layer(values, lambda record: record.core_passed)
    engineering_summary = summarize_layer(values, lambda record: record.engineering_passed)
    quality_summary = summarize_layer(values, lambda record: record.stage_success("repaired"))
    matrix_complete = not missing and not invalid and len(values) == len(expected)
    strategy_summaries = tuple(
        _summarize_strategy(strategy, [record for record in values if record.strategy == strategy])
        for strategy in sorted({record.strategy for record in values})
    )
    return EvaluationReport(
        summary=summary,
        missing_case_ids=missing,
        invalid_case_ids=invalid,
        failure_categories=tuple((name, count) for name, count in categories.items() if count),
        matrix_complete=matrix_complete,
        target_success_rate=target_success_rate,
        target_met=matrix_complete and quality_summary.pass_rate >= target_success_rate,
        strategy_summaries=strategy_summaries,
        core_summary=core_summary,
        engineering_summary=engineering_summary,
        quality_summary=quality_summary,
    )


def _summarize_strategy(strategy: str, records: list[EvaluationRecord]) -> StrategySummary:
    if not records:
        return StrategySummary(strategy, 0, 0.0, 0.0, 0.0, 0.0, 0.0)
    p95 = _p95(sorted(record.elapsed_seconds for record in records))
    return StrategySummary(
        strategy=strategy,
        total=len(records),
        first_success_rate=sum(record.stage_success("first") for record in records) / len(records),
        candidate_success_rate=sum(record.stage_success("candidate") for record in records) / len(records),
        repaired_success_rate=sum(record.stage_success("repaired") for record in records) / len(records),
        average_model_calls=mean(record.model_call_count for record in records),
        p95_seconds=p95,
    )


__all__ = ["ApplicationDomain", "EvaluationCase", "EvaluationRecord", "EvaluationSummary", "LayerSummary", "StrategySummary", "EvaluationReport", "EvaluationRegistry", "FIXED_CRUD_CASES", "FIXED_EVALUATION_MATRIX", "summarize", "summarize_layer", "build_report"]
