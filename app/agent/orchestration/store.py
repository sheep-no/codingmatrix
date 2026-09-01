"""Checkpoint storage contract and atomic JSON implementation."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Optional, Protocol

from .models import OrchestrationState


CURRENT_ORCHESTRATION_SCHEMA_VERSION = 1


class OrchestrationStore(Protocol):
    async def save(self, state: OrchestrationState) -> None: ...

    async def load_latest(self, task_id: str) -> Optional[OrchestrationState]: ...


class OrchestrationCheckpointStore:
    """Persist one versioned orchestration state snapshot per task."""

    def __init__(self, directory: Path) -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def path_for(self, task_id: str) -> Path:
        if not task_id or Path(task_id).name != task_id:
            raise ValueError("task_id must be a simple non-empty file name")
        return self.directory / f"{task_id}.json"

    async def save(self, state: OrchestrationState) -> None:
        target = self.path_for(state.task_id)
        payload = {
            "schema_version": CURRENT_ORCHESTRATION_SCHEMA_VERSION,
            "state": state.model_dump(mode="json"),
        }
        fd, temporary_name = tempfile.mkstemp(
            prefix=f".{state.task_id}.", suffix=".tmp", dir=self.directory
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, target)

    async def load_latest(self, task_id: str) -> Optional[OrchestrationState]:
        path = self.path_for(task_id)
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        version = payload.get("schema_version")
        if version != CURRENT_ORCHESTRATION_SCHEMA_VERSION:
            raise ValueError(f"unsupported orchestration checkpoint schema version: {version}")
        state_payload = payload.get("state")
        if not isinstance(state_payload, dict):
            raise ValueError("orchestration checkpoint must contain a state object")
        return OrchestrationState.model_validate(state_payload)
