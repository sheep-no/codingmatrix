"""Immutable view of a project before a generation or incremental change."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Mapping

from pydantic import BaseModel, ConfigDict, Field


def is_python_bytecode_cache(path: Path) -> bool:
    """Identify interpreter cache files without hiding other directory contents."""
    return path.parent.name == "__pycache__" and path.suffix == ".pyc"


def is_runtime_artifact(path: Path) -> bool:
    """Ignore files created by local validation while tracking source changes."""
    if is_python_bytecode_cache(path):
        return True
    name = path.name.lower()
    return name.endswith((
        ".db", ".sqlite", ".sqlite3", ".db-wal", ".db-shm",
        ".sqlite-wal", ".sqlite-shm", ".sqlite3-wal", ".sqlite3-shm",
        ".db-journal", ".sqlite-journal", ".sqlite3-journal",
    ))


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
            if is_runtime_artifact(relative):
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


__all__ = ["ProjectSnapshot", "SnapshotFile", "is_python_bytecode_cache", "is_runtime_artifact"]
