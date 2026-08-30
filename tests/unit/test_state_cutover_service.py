from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.unified_state import StateReconciliationRecord
from app.services.state_cutover_service import (
    CutoverError,
    ReadCutoverController,
    ReconciliationReport,
    activate_modules_in_order,
    build_reconciliation_report,
)


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_report_requires_all_resources_and_no_open_differences(db):
    for resource_type in ("session", "message", "task", "event", "checkpoint", "artifact"):
        db.add(StateReconciliationRecord(
            module="aicloud",
            resource_type=resource_type,
            resource_id=f"{resource_type}-1",
            status="resolved",
            expected_json={},
            actual_json={},
            difference_json={},
            created_at=datetime.utcnow(),
        ))
    await db.flush()

    report = await build_reconciliation_report(db, "aicloud")

    assert report.ready_for_cutover is True
    assert report.open_records == 0
    assert report.missing_resource_types == ()


def test_cutover_requires_order_and_supports_rollback():
    controller = ReadCutoverController()
    ready = type("Report", (), {"module": "agent", "ready_for_cutover": True})()

    with pytest.raises(CutoverError, match="顺序"):
        controller.enable("agent", ready)
    controller.enable("aicloud", type("Report", (), {"module": "aicloud", "ready_for_cutover": True})())
    controller.enable("girlai", type("Report", (), {"module": "girlai", "ready_for_cutover": True})())
    controller.enable("agent", ready)
    assert controller.source("agent") == "unified"
    controller.rollback("agent")
    assert controller.source("agent") == "legacy"


def test_cutover_uses_deterministic_user_cohort():
    controller = ReadCutoverController(("aicloud",))
    report = ReconciliationReport("aicloud", 6, 0, ("artifact",), (), True)
    controller.enable("aicloud", report, rollout_percentage=0)
    assert controller.source_for_user("aicloud", 1) == "legacy"
    controller.enable("aicloud", report, rollout_percentage=100)
    assert controller.source_for_user("aicloud", 1) == "unified"


def test_activate_modules_in_order():
    controller = ReadCutoverController()
    reports = {
        module: ReconciliationReport(module, 6, 0, (), (), True)
        for module in controller.module_order
    }

    snapshot = activate_modules_in_order(controller, reports, rollout_percentage=25)

    assert all(source == "unified" for source in snapshot.values())
    assert controller.rollout_snapshot() == {module: 25 for module in controller.module_order}
