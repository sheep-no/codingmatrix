"""Versioned JSON checkpoints for graph state recovery."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

from .models import State
from .migrations import migrate_state_payload


CURRENT_SCHEMA_VERSION = 1


class CheckpointStore:
    """Persist one state snapshot per task using an atomic file replacement."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        if not task_id or Path(task_id).name != task_id:
            raise ValueError("task_id must be a simple non-empty file name")
        return self.directory / f"{task_id}.json"

    def save(self, state: State) -> Path:
        target = self.path_for(state.task_id)
        payload = {
            "schema_version": CURRENT_SCHEMA_VERSION,
            "state": state.to_dict(),
        }
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{state.task_id}.", suffix=".tmp", dir=self.directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
        except Exception:
            raise
        return target

    def load(self, task_id: str) -> Optional[State]:
        path = self.path_for(task_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return State.from_dict(migrate_state_payload(payload))
