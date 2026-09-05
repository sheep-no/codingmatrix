"""Dynamic file changes for feature and incremental generation."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .project_snapshot import ProjectSnapshot


class ChangeAction(str, Enum):
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


class FileChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    action: ChangeAction
    owner: str = ""
    reason: str = ""
    dependencies: tuple[str, ...] = ()
    previous_path: str | None = None


class ChangePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_revision: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    changes: tuple[FileChange, ...] = ()
    digest: str = Field(min_length=64, max_length=64)

    @classmethod
    def build(
        cls,
        snapshot: ProjectSnapshot,
        changes: Iterable[Mapping[str, object] | FileChange],
        *,
        version: int = 1,
    ) -> "ChangePlan":
        normalized = tuple(
            item if isinstance(item, FileChange) else FileChange(
                path=str(item["path"]),
                action=ChangeAction(str(item.get("action", "modify"))),
                owner=str(item.get("owner", "")),
                reason=str(item.get("reason", "")),
                dependencies=tuple(str(value) for value in item.get("dependencies", ())),
                previous_path=str(item["previous_path"]) if item.get("previous_path") else None,
            )
            for item in changes
        )
        paths = [item.path for item in normalized]
        if len(paths) != len(set(paths)):
            raise ValueError("change plan paths must be unique")
        known = set(snapshot.hashes())
        for item in normalized:
            if item.action is ChangeAction.MODIFY and item.path not in known:
                raise ValueError(f"modified file is absent from snapshot: {item.path}")
            if item.action is ChangeAction.DELETE and item.path not in known:
                raise ValueError(f"deleted file is absent from snapshot: {item.path}")
            if item.action is ChangeAction.RENAME and item.previous_path not in known:
                raise ValueError(f"renamed source is absent from snapshot: {item.previous_path}")
        payload = {
            "base_revision": snapshot.revision,
            "version": version,
            "changes": [item.model_dump(mode="json") for item in normalized],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(base_revision=snapshot.revision, version=version, changes=normalized, digest=digest)

    @property
    def affected_files(self) -> tuple[str, ...]:
        return tuple(sorted({item.path for item in self.changes} | {
            item.previous_path for item in self.changes if item.previous_path
        }))

    def verify_untouched(self, snapshot: ProjectSnapshot, current: ProjectSnapshot) -> tuple[str, ...]:
        """Return files whose content changed outside the declared change scope."""
        before = snapshot.hashes()
        after = current.hashes()
        affected = set(self.affected_files)
        return tuple(sorted(
            path for path in set(before) | set(after)
            if path not in affected and before.get(path) != after.get(path)
        ))


__all__ = ["ChangeAction", "ChangePlan", "FileChange"]
