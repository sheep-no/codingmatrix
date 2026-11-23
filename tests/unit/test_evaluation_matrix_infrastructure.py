"""基础设施失败不算跑满矩阵。"""

from types import SimpleNamespace

from app.agent.evaluation_matrix import (
    EvaluationCase,
    EvaluationRecord,
    build_report,
)
from tests.manual.run_core_evaluation_matrix import (
    _failed_record,
    _would_overwrite_completed,
    _would_overwrite_successful_detail,
)


def _passing(case_id: str) -> EvaluationRecord:
    return EvaluationRecord(
        case_id, True, True, True, True, True, True, True, True, 1, 1.0,
    )


def _infra(case_id: str) -> EvaluationRecord:
    return EvaluationRecord(
        case_id, False, False, False, False, False, False, False, False, 0, 0.02,
        evaluation_status="evaluation_infrastructure_failure",
    )


def test_matrix_is_incomplete_when_records_exist_but_infrastructure_failed():
    cases = [
        EvaluationCase("a", "python", "fastapi", "", ("main.py",)),
        EvaluationCase("b", "python", "fastapi", "", ("main.py",)),
    ]

    report = build_report([_passing("a"), _infra("b")], cases=cases)

    assert report.matrix_complete is False
    assert report.target_met is False
    assert report.core_summary.excluded == 1


def test_matrix_is_complete_when_every_case_completed():
    cases = [
        EvaluationCase("a", "python", "fastapi", "", ("main.py",)),
        EvaluationCase("b", "python", "fastapi", "", ("main.py",)),
    ]

    report = build_report([_passing("a"), _passing("b")], cases=cases)

    assert report.matrix_complete is True


def test_runner_exception_records_are_infrastructure_failures():
    """传输/运行器异常不得被当成质量失败计入通过率。"""
    record = _failed_record(SimpleNamespace(case_id="a", strategy="traditional", file_scale="single"), 0.01)

    assert record["evaluation_status"] == "evaluation_infrastructure_failure"


def test_failed_rerun_cannot_overwrite_completed_record():
    existing = {"evaluation_status": "completed", "case_id": "a"}
    failed = _failed_record(SimpleNamespace(case_id="a", strategy="traditional", file_scale="single"), 0.01)

    assert _would_overwrite_completed(existing, failed) is True
    assert _would_overwrite_completed(failed, failed) is False


def test_failed_rerun_cannot_overwrite_successful_detail():
    successful = {"success": True, "case_id": "a"}
    failed = {"success": False, "case_id": "a"}

    assert _would_overwrite_successful_detail(successful, failed) is True
    assert _would_overwrite_successful_detail(failed, successful) is False
