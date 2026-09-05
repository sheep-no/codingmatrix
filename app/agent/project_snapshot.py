"""Immutable view of a project before a generation or incremental change."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field


class SnapshotFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    sha256: str = Field(min_length=64, max_length=64)
    size: int = Field(ge=0)


class ProjectSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    revision: str = Field(min_length=1)
    files: tuple[SnapshotFile, ...] = ()

    @classmethod
    def scan(cls, root: Path, *, revision: str = "working-tree") -> "ProjectSnapshot":
        files = []
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if not path.is_file() or any(part.startswith(".") for part in relative.parts):
                continue
            data = path.read_bytes()
            files.append(SnapshotFile(
                path=relative.as_posix(),
                sha256=hashlib.sha256(data).hexdigest(),
                size=len(data),
            ))
        return cls(revision=revision, files=tuple(files))

    def hashes(self) -> Mapping[str, str]:
        return {item.path: item.sha256 for item in self.files}


__all__ = ["ProjectSnapshot", "SnapshotFile"]
