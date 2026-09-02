"""Fixed, machine-readable matrix for multilingual CRUD evaluations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from statistics import quantiles
from collections import Counter
from typing import Iterable, Tuple


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

    @property
    def success(self) -> bool:
        return all((
            self.plan_consistent, self.interfaces_consistent, self.dependency_closure,
            self.files_complete, self.compile_passed, self.tests_passed,
            self.startup_passed, self.persistence_passed,
        ))


@dataclass(frozen=True)
class EvaluationSummary:
    total: int
    successful: int
    success_rate: float
    p95_seconds: float


@dataclass(frozen=True)
class EvaluationReport:
    summary: EvaluationSummary
    missing_case_ids: Tuple[str, ...]
    invalid_case_ids: Tuple[str, ...]
    failure_categories: Tuple[Tuple[str, int], ...]


FIXED_CRUD_CASES: Tuple[EvaluationCase, ...] = (
    EvaluationCase("python-fastapi-crud", "python", "fastapi", "Create a CRUD todo API with SQLite persistence.", ("app/main.py", "app/models.py", "app/schemas.py", "app/crud.py", "tests/test_crud.py")),
    EvaluationCase("python-flask-crud", "python", "flask", "Create a CRUD todo API with SQLite persistence.", ("app.py", "models.py", "crud.py", "tests/test_crud.py")),
    EvaluationCase("typescript-express-crud", "typescript", "express", "Create a CRUD todo API with SQLite persistence.", ("src/app.ts", "src/routes/todos.ts", "src/db.ts", "tests/todos.test.ts")),
    EvaluationCase("typescript-nestjs-crud", "typescript", "nestjs", "Create a CRUD todo API with SQLite persistence.", ("src/main.ts", "src/todos/todos.controller.ts", "src/todos/todos.service.ts", "test/todos.e2e-spec.ts")),
    EvaluationCase("go-http-crud", "go", "net/http", "Create a CRUD todo API with SQLite persistence.", ("cmd/server/main.go", "internal/todos/handler.go", "internal/todos/store.go", "internal/todos/handler_test.go")),
    EvaluationCase("java-spring-boot-crud", "java", "spring-boot", "Create a CRUD todo API with SQLite persistence.", ("src/main/java/com/example/Application.java", "src/main/java/com/example/TodoController.java", "src/main/java/com/example/TodoRepository.java", "src/test/java/com/example/TodoControllerTest.java")),
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


def summarize(records: Iterable[EvaluationRecord]) -> EvaluationSummary:
    values = list(records)
    if not values:
        return EvaluationSummary(0, 0, 0.0, 0.0)
    elapsed = sorted(record.elapsed_seconds for record in values)
    if len(elapsed) == 1:
        p95 = elapsed[0]
    else:
        p95 = quantiles(elapsed, n=100, method="inclusive")[94]
    successful = sum(record.success for record in values)
    return EvaluationSummary(len(values), successful, successful / len(values), p95)


def build_report(
    records: Iterable[EvaluationRecord],
    *,
    cases: Iterable[EvaluationCase] = FIXED_CRUD_CASES,
) -> EvaluationReport:
    values = list(records)
    expected = {case.case_id for case in cases}
    actual = {record.case_id for record in values}
    missing = tuple(sorted(expected - actual))
    duplicate_ids = {case_id for case_id, count in Counter(record.case_id for record in values).items() if count > 1}
    invalid = tuple(sorted({
        record.case_id for record in values
        if record.case_id not in expected or record.case_id in duplicate_ids
        or record.elapsed_seconds < 0 or record.token_count < 0
    }))
    categories = {
        "plan": sum(not record.plan_consistent for record in values),
        "interface": sum(not record.interfaces_consistent for record in values),
        "dependency": sum(not record.dependency_closure for record in values),
        "artifact": sum(not record.files_complete for record in values),
        "compile": sum(not record.compile_passed for record in values),
        "test": sum(not record.tests_passed for record in values),
        "startup": sum(not record.startup_passed for record in values),
        "persistence": sum(not record.persistence_passed for record in values),
    }
    return EvaluationReport(
        summary=summarize(values),
        missing_case_ids=missing,
        invalid_case_ids=invalid,
        failure_categories=tuple((name, count) for name, count in categories.items() if count),
    )


__all__ = ["ApplicationDomain", "EvaluationCase", "EvaluationRecord", "EvaluationSummary", "EvaluationReport", "EvaluationRegistry", "FIXED_CRUD_CASES", "summarize", "build_report"]
