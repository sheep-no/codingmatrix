"""Recoverable filesystem transaction for incremental file changes."""

from __future__ import annotations

import shutil
from pathlib import Path

from app.agent.change_plan import ChangeAction, ChangePlan

from .plan import normalize_plan_path


class IncrementalFileTransaction:
    def __init__(self, root: Path, plan: ChangePlan, *, transaction_id: str) -> None:
        self.root = root
        self.plan = plan
        self.staging = root / ".orchestration-txn" / transaction_id
        self._backups: list[tuple[Path, Path]] = []
        self._created_targets: list[Path] = []
        self._closed = False

    def stage(self) -> None:
        if self._closed:
            raise RuntimeError("incremental file transaction is closed")
        if self._backups or self._created_targets:
            raise RuntimeError("incremental file transaction is already staged")
        self.staging.mkdir(parents=True, exist_ok=True)
        try:
            for change in self.plan.changes:
                target_path = normalize_plan_path(change.path)
                target = self.root / target_path
                if change.action is ChangeAction.ADD:
                    if target.exists():
                        raise FileExistsError(f"transaction add target already exists: {target_path}")
                    self._created_targets.append(target)
                    continue

                source_path = (
                    normalize_plan_path(change.previous_path)
                    if change.action is ChangeAction.RENAME and change.previous_path
                    else target_path
                )
                source = self.root / source_path
                if not source.is_file():
                    raise FileNotFoundError(f"transaction source is absent: {source_path}")
                backup = self.staging / source_path
                backup.parent.mkdir(parents=True, exist_ok=True)
                if change.action is ChangeAction.MODIFY:
                    shutil.copy2(source, backup)
                else:
                    source.replace(backup)
                self._backups.append((source, backup))

                if change.action is ChangeAction.RENAME:
                    if target.exists():
                        raise FileExistsError(f"transaction rename target already exists: {target_path}")
                    self._created_targets.append(target)
        except Exception:
            self.rollback()
            raise

    def commit(self) -> None:
        if self._closed:
            return
        shutil.rmtree(self.staging, ignore_errors=True)
        self._closed = True

    def rollback(self) -> None:
        if self._closed:
            return
        for target in reversed(self._created_targets):
            if target.is_file() or target.is_symlink():
                target.unlink()
        for original, backup in reversed(self._backups):
            if backup.is_file():
                original.parent.mkdir(parents=True, exist_ok=True)
                backup.replace(original)
        shutil.rmtree(self.staging, ignore_errors=True)
        self._closed = True


__all__ = ["IncrementalFileTransaction"]
