"""Module-level reconciliation reports and guarded read cutover controls."""

from dataclasses import dataclass
import hashlib
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.unified_state import StateReconciliationRecord


DEFAULT_RESOURCE_TYPES = ("session", "message", "task", "event", "checkpoint", "artifact")
DEFAULT_MODULE_ORDER = ("aicloud", "girlai", "agent", "workflow")


@dataclass(frozen=True)
class ReconciliationReport:
    module: str
    total_records: int
    open_records: int
    covered_resource_types: tuple[str, ...]
    missing_resource_types: tuple[str, ...]
    ready_for_cutover: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "module": self.module,
            "total_records": self.total_records,
            "open_records": self.open_records,
            "covered_resource_types": list(self.covered_resource_types),
            "missing_resource_types": list(self.missing_resource_types),
            "ready_for_cutover": self.ready_for_cutover,
        }


async def build_reconciliation_report(
    db: AsyncSession,
    module: str,
    required_resource_types: tuple[str, ...] = DEFAULT_RESOURCE_TYPES,
) -> ReconciliationReport:
    """Build a cutover gate report from all reconciliation records for a module."""
    records = list((await db.scalars(
        select(StateReconciliationRecord)
        .where(StateReconciliationRecord.module == module)
        .order_by(StateReconciliationRecord.resource_type.asc())
    )).all())
    covered = tuple(sorted({record.resource_type for record in records}))
    missing = tuple(item for item in required_resource_types if item not in covered)
    open_count = sum(record.status in {"open", "retryable"} for record in records)
    return ReconciliationReport(
        module=module,
        total_records=len(records),
        open_records=open_count,
        covered_resource_types=covered,
        missing_resource_types=missing,
        ready_for_cutover=bool(records) and open_count == 0 and not missing,
    )


class CutoverError(ValueError):
    """Raised when a module cannot change its read source."""


class ReadCutoverController:
    """In-memory controller for staged unified-read activation and rollback."""

    def __init__(self, module_order: tuple[str, ...] = DEFAULT_MODULE_ORDER):
        self.module_order = module_order
        self._sources = {module: "legacy" for module in module_order}
        self._rollout_percentages = {module: 0 for module in module_order}

    def source(self, module: str) -> str:
        self._validate_module(module)
        return self._sources[module]

    def source_for_user(self, module: str, user_id: int) -> str:
        """Return the read source for a deterministic user rollout cohort."""
        self._validate_module(module)
        if self._sources[module] != "unified":
            return "legacy"
        percentage = self._rollout_percentages[module]
        bucket = int(hashlib.sha256(f"{module}:{int(user_id)}".encode()).hexdigest()[:8], 16) % 100
        return "unified" if bucket < percentage else "legacy"

    def enable(
        self,
        module: str,
        report: ReconciliationReport,
        rollout_percentage: int = 100,
    ) -> str:
        self._validate_module(module)
        if report.module != module:
            raise CutoverError("核对报告模块与切换模块不一致")
        if not report.ready_for_cutover:
            raise CutoverError("核对报告未通过读切换门禁")
        position = self.module_order.index(module)
        previous = self.module_order[:position]
        if any(self._sources[item] != "unified" for item in previous):
            raise CutoverError("必须按模块顺序执行读切换")
        if rollout_percentage < 0 or rollout_percentage > 100:
            raise CutoverError("灰度比例必须在 0 到 100 之间")
        self._sources[module] = "unified"
        self._rollout_percentages[module] = rollout_percentage
        return "unified"

    def rollback(self, module: str) -> str:
        self._validate_module(module)
        self._sources[module] = "legacy"
        self._rollout_percentages[module] = 0
        return "legacy"

    def snapshot(self) -> dict[str, str]:
        return dict(self._sources)

    def rollout_snapshot(self) -> dict[str, int]:
        return dict(self._rollout_percentages)

    def _validate_module(self, module: str) -> None:
        if module not in self._sources:
            raise CutoverError(f"未知迁移模块: {module}")


def activate_modules_in_order(
    controller: ReadCutoverController,
    reports: dict[str, ReconciliationReport],
    rollout_percentage: int = 100,
) -> dict[str, str]:
    """Activate the four migration modules in the designed order."""
    for module in controller.module_order:
        report = reports.get(module)
        if report is None:
            raise CutoverError(f"缺少模块核对报告: {module}")
        controller.enable(module, report, rollout_percentage=rollout_percentage)
    return controller.snapshot()


__all__ = [
    "CutoverError",
    "ReadCutoverController",
    "ReconciliationReport",
    "activate_modules_in_order",
    "build_reconciliation_report",
]
