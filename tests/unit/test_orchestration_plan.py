"""Tests for strict and extensible Orchestrator Core file plans."""

import pytest
from pydantic import ValidationError

from app.agent.orchestration import (
    FilePlanValidationError,
    GenerationPlan,
    PlanFileOrigin,
    PlanPolicy,
    build_file_plan,
    normalize_plan_path,
)


@pytest.mark.parametrize(
    ("raw_path", "expected"),
    [
        ("./src//main.py", "src/main.py"),
        (r"src\services\todo.ts", "src/services/todo.ts"),
        ("服务/订单.go", "服务/订单.go"),
        ("src/main.rs", "src/main.rs"),
        ("app/src/main/java/Todo.java", "app/src/main/java/Todo.java"),
    ],
)
def test_normalize_plan_path_has_one_canonical_representation(
    raw_path: str,
    expected: str,
) -> None:
    assert normalize_plan_path(raw_path) == expected


@pytest.mark.parametrize(
    "path",
    [
        "",
        "../main.py",
        "src/../main.py",
        "/etc/passwd",
        r"C:\temp\main.py",
        "src/my file.py",
        ".env",
        ".git/config",
    ],
)
def test_normalize_plan_path_rejects_unsafe_paths(path: str) -> None:
    with pytest.raises(ValueError):
        normalize_plan_path(path)


def test_explicit_requested_paths_create_exact_strict_plan() -> None:
    plan = build_file_plan(
        [
            {
                "path": "./src//service.py",
                "dependencies": [r"src\model.py"],
                "description": "service",
                "language": "python",
            },
            {"path": "src/model.py", "description": "model", "language": "python"},
        ],
        requested_paths=[r"src\service.py", "./src/model.py"],
        version=3,
    )

    assert plan.policy is PlanPolicy.STRICT
    assert plan.version == 3
    assert plan.requested_paths == ("src/model.py", "src/service.py")
    assert tuple(item.path for item in plan.files) == plan.requested_paths
    assert all(item.origin is PlanFileOrigin.REQUESTED for item in plan.files)
    assert plan.files[1].dependencies == ("src/model.py",)


def test_strict_plan_reports_files_outside_and_missing_from_scope() -> None:
    with pytest.raises(FilePlanValidationError) as raised:
        build_file_plan(
            [{"path": "main.py"}, {"path": "README.md"}],
            requested_paths=["main.py", "tests/test_main.py"],
        )

    issues = {(issue.code, issue.path) for issue in raised.value.issues}
    assert ("plan.unexpected_file", "README.md") in issues
    assert ("plan.missing_requested_file", "tests/test_main.py") in issues


def test_strict_plan_reports_missing_dependency() -> None:
    with pytest.raises(FilePlanValidationError) as raised:
        build_file_plan(
            [{"path": "service.py", "dependencies": ["model.py"]}],
            requested_paths=["service.py"],
        )

    assert any(issue.code == "plan.missing_dependency" for issue in raised.value.issues)


def test_extensible_plan_records_extension_source_and_reason() -> None:
    plan = build_file_plan(
        [
            {"path": "main.py"},
            {
                "path": "requirements.txt",
                "origin": "extension",
                "source": "architecture_completeness",
                "reason": "runtime dependency manifest",
            },
        ]
    )

    extension = next(item for item in plan.files if item.origin is PlanFileOrigin.EXTENSION)
    assert plan.policy is PlanPolicy.EXTENSIBLE
    assert extension.source == "architecture_completeness"
    assert extension.reason == "runtime dependency manifest"


def test_single_import_string_remains_one_import_item() -> None:
    plan = build_file_plan([{"path": "main.py", "imports": "package.module"}])

    assert plan.files[0].imports == ("package.module",)


@pytest.mark.parametrize("missing_field", ["source", "reason"])
def test_extensible_plan_rejects_incomplete_extension_provenance(
    missing_field: str,
) -> None:
    extension = {
        "path": "requirements.txt",
        "origin": "extension",
        "source": "architecture_completeness",
        "reason": "runtime dependency manifest",
    }
    extension.pop(missing_field)

    with pytest.raises(FilePlanValidationError) as raised:
        build_file_plan([{"path": "main.py"}, extension])

    assert any(issue.code == "plan.invalid_file" for issue in raised.value.issues)


def test_normalized_duplicate_paths_are_rejected() -> None:
    with pytest.raises(FilePlanValidationError) as raised:
        build_file_plan([{"path": "./src/main.py"}, {"path": r"src\main.py"}])

    assert any(issue.code == "plan.duplicate_file" for issue in raised.value.issues)


def test_frozen_plan_digest_is_stable_for_equivalent_input_order() -> None:
    first = build_file_plan(
        [
            {"path": "service.py", "dependencies": ["model.py"]},
            {"path": "model.py"},
        ],
        version=2,
    )
    second = build_file_plan(
        [
            {"path": "./model.py"},
            {"path": "./service.py", "dependencies": [r"model.py"]},
        ],
        version=2,
    )

    assert first.digest == second.digest
    assert first.files == second.files


def test_new_plan_version_has_distinct_digest() -> None:
    first = build_file_plan([{"path": "main.py"}], version=1)
    second = build_file_plan([{"path": "main.py"}], version=2)

    assert first.version == 1
    assert second.version == 2
    assert first.digest != second.digest


def test_plan_is_immutable_and_json_round_trip_validates_digest() -> None:
    plan = build_file_plan([{"path": "main.py"}])

    with pytest.raises(ValidationError, match="frozen"):
        plan.version = 2

    restored = GenerationPlan.model_validate_json(plan.model_dump_json())
    assert restored == plan

    payload = plan.model_dump(mode="json")
    payload["digest"] = "0" * 64
    with pytest.raises(ValidationError, match="digest does not match"):
        GenerationPlan.model_validate(payload)
