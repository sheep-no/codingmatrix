"""Recoverable filesystem transaction for incremental deletes and renames."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.agent.change_plan import ChangeAction, ChangePlan


class IncrementalFileTransaction:
    def __init__(self, root: Path, plan: ChangePlan, *, transaction_id: str) -> None:
        self.root = root
        self.plan = plan
        self.staging = root / ".orchestration-txn" / transaction_id
        self._staged: list[tuple[Path, Path]] = []
        self._closed = False

    def stage(self) -> None:
        self.staging.mkdir(parents=True, exist_ok=True)
        for change in self.plan.changes:
            source = change.previous_path if change.action is ChangeAction.RENAME else change.path
            if change.action not in {ChangeAction.DELETE, ChangeAction.RENAME} or not source:
                continue
            original = self.root / source
            if not original.is_file():
                raise FileNotFoundError(f"transaction source is absent: {source}")
            backup = self.staging / source
            backup.parent.mkdir(parents=True, exist_ok=True)
            original.replace(backup)
            self._staged.append((original, backup))

    def commit(self) -> None:
        if self._closed:
            return
        shutil.rmtree(self.staging, ignore_errors=True)
        self._closed = True

    def rollback(self) -> None:
        if self._closed:
            return
        for original, backup in reversed(self._staged):
            if backup.is_file():
                original.parent.mkdir(parents=True, exist_ok=True)
                backup.replace(original)
        shutil.rmtree(self.staging, ignore_errors=True)
        self._closed = True


__all__ = ["IncrementalFileTransaction"]
