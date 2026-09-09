from app.agent.evaluation_matrix import (
    ApplicationDomain, EvaluationCase, EvaluationRegistry, FIXED_CRUD_CASES,
    FIXED_EVALUATION_MATRIX, EvaluationRecord, build_report, summarize,
)


def test_fixed_matrix_contains_six_required_stacks():
    assert len(FIXED_CRUD_CASES) == 6
    assert {(case.language, case.framework) for case in FIXED_CRUD_CASES} == {
        ("python", "fastapi"), ("python", "flask"), ("typescript", "express"),
        ("typescript", "nestjs"), ("go", "net/http"), ("java", "spring-boot"),
    }


def test_expanded_matrix_covers_languages_scales_and_strategies():
    assert len(FIXED_EVALUATION_MATRIX) == 24
    assert {case.language for case in FIXED_EVALUATION_MATRIX} == {"python", "typescript", "go", "java"}
    assert {case.file_scale for case in FIXED_EVALUATION_MATRIX} == {"single", "small", "modular"}
    assert {case.strategy for case in FIXED_EVALUATION_MATRIX} == {"traditional", "spec_first"}
    assert len({case.case_id for case in FIXED_EVALUATION_MATRIX}) == 24
    go_modular = next(case for case in FIXED_EVALUATION_MATRIX if case.case_id == "go-modular-traditional")
    assert "go.sum" in go_modular.required_files


def test_summary_calculates_success_rate_and_p95():
    records = [EvaluationRecord("a", True, True, True, True, True, True, True, True, 10, 1.0),
               EvaluationRecord("b", True, True, True, True, True, True, True, False, 12, 2.0)]

    summary = summarize(records)

    assert summary.successful == 1
    assert summary.success_rate == 0.5
    assert summary.p95_seconds == 1.95


def test_empty_summary_is_safe():
    assert summarize([]).total == 0


def test_report_identifies_missing_cases_and_failure_categories():
    record = EvaluationRecord("python-fastapi-crud", True, True, True, True, True, True, False, True, 10, 1.0)

    report = build_report([record])

    assert "go-http-crud" in report.missing_case_ids
    assert report.failure_categories == (("startup", 1),)
    assert report.matrix_complete is False
    assert report.target_met is False


def test_report_rejects_invalid_measurements():
    record = EvaluationRecord("unknown", True, True, True, True, True, True, True, True, -1, -0.5)

    report = build_report([record])

    assert report.invalid_case_ids == ("unknown",)


def test_report_rejects_duplicate_case_records():
    record = EvaluationRecord("python-fastapi-crud", True, True, True, True, True, True, True, True, 1, 1.0)

    report = build_report([record, record])

    assert report.invalid_case_ids == ("python-fastapi-crud",)


def test_registry_accepts_non_web_workspace_cases():
    registry = EvaluationRegistry(cases=[])
    registry.register_case(EvaluationCase(
        "pygame-gomoku", "python", "pygame", "Build a Gomoku game.",
        ("main.py", "tests/test_rules.py"), domain=ApplicationDomain.GAME,
    ))

    assert registry.cases[0].domain is ApplicationDomain.GAME
    assert registry.build_report([]).missing_case_ids == ("pygame-gomoku",)


def test_report_requires_complete_matrix_before_target_is_met():
    records = [
        EvaluationRecord(
            case.case_id, True, True, True, True, True, True, True, True, 1, 1.0
        )
        for case in FIXED_CRUD_CASES
    ]

    report = build_report(records)

    assert report.matrix_complete is True
    assert report.summary.success_rate == 1.0
    assert report.target_success_rate == 0.9
    assert report.target_met is True


def test_report_rejects_invalid_target_rate():
    import pytest

    with pytest.raises(ValueError, match="target_success_rate"):
        build_report([], target_success_rate=1.1)


def test_report_tracks_database_profile_failures():
    record = EvaluationRecord(
        "python-fastapi-crud", True, True, True, True, True, True, True, True, 10, 1.0,
        database_status="unsupported",
        database_diagnostics=("database profile not found",),
    )

    report = build_report([record])

    assert report.summary.successful == 0
    assert report.failure_categories[-1] == ("database", 1)


def test_report_aggregates_stage_rates_calls_and_p95_per_strategy():
    records = [
        EvaluationRecord(
            case.case_id, True, True, True, True, True, True, True, True,
            token_count=index + 1, elapsed_seconds=float(index + 1),
            model_call_count=index + 2,
            strategy=case.strategy, file_scale=case.file_scale,
            first_passed=index > 0, candidate_passed=True, repaired_passed=True,
        )
        for index, case in enumerate(FIXED_EVALUATION_MATRIX[:2])
    ]

    report = build_report(records, cases=FIXED_EVALUATION_MATRIX[:2])

    assert report.matrix_complete is True
    assert [(item.strategy, item.first_success_rate) for item in report.strategy_summaries] == [
        ("spec_first", 1.0), ("traditional", 0.0)
    ]
    assert report.strategy_summaries[0].average_model_calls == 3
    assert report.strategy_summaries[1].p95_seconds == 1.0


def test_report_separates_core_engineering_and_quality_layers():
    records = [
        EvaluationRecord(
            "a", True, True, True, True, True, True, True, True, 1, 1.0,
            first_passed=False, candidate_passed=True, repaired_passed=True,
        ),
        EvaluationRecord(
            "b", True, True, True, True, False, False, False, False, 1, 2.0,
            first_passed=False, candidate_passed=False, repaired_passed=False,
        ),
    ]

    report = build_report(records, cases=[
        EvaluationCase("a", "python", "fastapi", "", ("main.py",)),
        EvaluationCase("b", "python", "fastapi", "", ("main.py",)),
    ])

    assert report.core_summary.passed == 2
    assert report.engineering_summary.passed == 1
    assert report.quality_summary.passed == 1
    assert report.target_met is False


def test_infrastructure_failures_are_excluded_from_layer_rates():
    records = [
        EvaluationRecord(
            "a", False, False, False, False, False, False, False, False, 0, 1.0,
            evaluation_status="evaluation_infrastructure_failure",
        )
    ]

    report = build_report(records, cases=[
        EvaluationCase("a", "python", "fastapi", "", ("main.py",)),
    ])

    assert report.core_summary.total == 0
    assert report.core_summary.excluded == 1
    assert report.quality_summary.pass_rate == 0.0
    assert report.failure_categories == (("evaluation_infrastructure_failure", 1),)
