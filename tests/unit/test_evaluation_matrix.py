from app.agent.evaluation_matrix import ApplicationDomain, EvaluationCase, EvaluationRegistry, FIXED_CRUD_CASES, EvaluationRecord, build_report, summarize


def test_fixed_matrix_contains_six_required_stacks():
    assert len(FIXED_CRUD_CASES) == 6
    assert {(case.language, case.framework) for case in FIXED_CRUD_CASES} == {
        ("python", "fastapi"), ("python", "flask"), ("typescript", "express"),
        ("typescript", "nestjs"), ("go", "net/http"), ("java", "spring-boot"),
    }


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
