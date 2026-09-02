import pytest

from app.agent.repair_router import RepairBudget, RepairRouter
from app.agent.validation_report import ValidationCategory, ValidationReport


def test_validation_report_classifies_findings_and_is_reproducible():
    report = ValidationReport.create().with_finding(
        "database.py 未导出符号 SessionLocal",
        file_path="api.py",
    )

    assert report.passed is False
    assert report.findings[0].category is ValidationCategory.EXPORT
    assert report.findings[0].scope == "cloud_syntax"
    assert len(report.report_hash) == 64
    assert report.model_validate(report.model_dump()).report_hash == report.report_hash


@pytest.mark.parametrize(
    ("message", "category"),
    [
        ("unknown dependency sqlalchemy_utils", "dependency"),
        ("调用 update_todo 缺少必需参数 todo_update", "signature"),
        ("fixture 生命周期错误", "fixture"),
        ("业务字段缺失: title", "schema"),
        ("async/sync 调用不匹配", "async"),
    ],
)
def test_repair_router_uses_explicit_safe_categories(message, category):
    route = RepairRouter.route(error_message=message)

    assert route.category == category
    assert route.auto_apply is True


def test_report_repair_authorization_enforces_category_and_total_budget():
    report = ValidationReport.create().with_finding(
        "模块 sqlalchemy_utils 当前运行时不可导入",
        file_path="database.py",
    )
    budget = RepairBudget(per_category_limit=3, total_limit=1)
    route, evidence = report.authorize_repair(
        report.findings[0], "from sqlalchemy_utils import helper", budget
    )

    assert route.category == "import"
    assert evidence is not None
    assert evidence.attempt == 1
    _, blocked = report.authorize_repair(report.findings[0], "retry", budget)
    assert blocked is None
