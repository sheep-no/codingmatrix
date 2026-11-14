"""state_cutover_service 报告、顺序与灰度补测。"""

import pytest

from app.services.state_cutover_service import (
    DEFAULT_MODULE_ORDER,
    CutoverError,
    ReadCutoverController,
    ReconciliationReport,
    activate_modules_in_order,
    build_reconciliation_report,
)


def _report(module: str, *, ready: bool = True, missing=()) -> ReconciliationReport:
    return ReconciliationReport(
        module=module,
        total_records=4,
        open_records=0 if ready else 1,
        covered_resource_types=("session",),
        missing_resource_types=tuple(missing),
        ready_for_cutover=ready,
    )


class _Scalars:
    def __init__(self, records):
        self._records = records

    def all(self):
        return self._records


class _DB:
    def __init__(self, records):
        self._records = records

    async def scalars(self, _query):
        return _Scalars(self._records)


async def test_build_report_counts_open_and_missing():
    records = [
        type("R", (), {"resource_type": "session", "status": "open"})(),
        type("R", (), {"resource_type": "session", "status": "done"})(),
        type("R", (), {"resource_type": "message", "status": "retryable"})(),
    ]

    report = await build_reconciliation_report(_DB(records), "agent", ("session", "message", "task"))

    assert report.total_records == 3
    assert report.open_records == 2
    assert report.covered_resource_types == ("message", "session")
    assert report.missing_resource_types == ("task",)
    assert report.ready_for_cutover is False


def test_report_to_dict():
    payload = _report("agent").to_dict()
    assert payload["module"] == "agent"
    assert payload["covered_resource_types"] == ["session"]


def test_controller_source_and_snapshot():
    controller = ReadCutoverController()
    assert controller.source("agent") == "legacy"
    assert controller.snapshot() == {module: "legacy" for module in DEFAULT_MODULE_ORDER}
    assert controller.rollout_snapshot() == {module: 0 for module in DEFAULT_MODULE_ORDER}


def test_controller_rejects_unknown_module():
    with pytest.raises(CutoverError):
        ReadCutoverController().source("unknown")


def test_enable_requires_matching_report_module():
    controller = ReadCutoverController()

    with pytest.raises(CutoverError, match="不一致"):
        controller.enable("aicloud", _report("agent"))


def test_enable_requires_ready_report():
    controller = ReadCutoverController()

    with pytest.raises(CutoverError, match="门禁"):
        controller.enable("aicloud", _report("aicloud", ready=False))


def test_enable_enforces_module_order():
    controller = ReadCutoverController()

    with pytest.raises(CutoverError, match="顺序"):
        controller.enable("girlai", _report("girlai"))


def test_enable_validates_rollout_percentage():
    controller = ReadCutoverController()

    with pytest.raises(CutoverError, match="灰度"):
        controller.enable("aicloud", _report("aicloud"), rollout_percentage=101)


def test_enable_and_rollback():
    controller = ReadCutoverController()
    assert controller.enable("aicloud", _report("aicloud"), rollout_percentage=50) == "unified"
    assert controller.source("aicloud") == "unified"
    assert controller.rollout_snapshot()["aicloud"] == 50

    assert controller.rollback("aicloud") == "legacy"
    assert controller.source("aicloud") == "legacy"


def test_source_for_user_cohorts():
    controller = ReadCutoverController()

    assert controller.source_for_user("agent", 1) == "legacy"

    controller.enable("aicloud", _report("aicloud"), 100)
    controller.enable("girlai", _report("girlai"), 100)
    controller.enable("agent", _report("agent"), 100)
    assert controller.source_for_user("agent", 1) == "unified"

    controller.enable("workflow", _report("workflow"), 0)
    assert controller.source_for_user("workflow", 1) == "legacy"


def test_activate_modules_in_order():
    controller = ReadCutoverController()
    reports = {module: _report(module) for module in DEFAULT_MODULE_ORDER}

    snapshot = activate_modules_in_order(controller, reports)

    assert all(value == "unified" for value in snapshot.values())


def test_activate_requires_all_reports():
    controller = ReadCutoverController()

    with pytest.raises(CutoverError, match="缺少"):
        activate_modules_in_order(controller, {})
