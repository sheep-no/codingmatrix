"""Closed, categorized dependency declarations for generation plans."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Iterable, Mapping, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DependencyKind(str, Enum):
    STANDARD_LIBRARY = "standard_library"
    PROJECT_MODULE = "project_module"
    RUNTIME = "runtime"
    TEST = "test"
    FORBIDDEN = "forbidden"


class Dependency(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    kind: DependencyKind
    version: str = ""
    source: str = "plan"


class DependencyManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(default=1, ge=1)
    dependencies: Tuple[Dependency, ...] = ()
    digest: str = Field(default="", min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_digest(self) -> "DependencyManifest":
        payload = {"version": self.version, "dependencies": [item.model_dump(mode="json") for item in self.dependencies]}
        expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        if self.digest != expected:
            raise ValueError("dependency manifest digest does not match its contents")
        return self

    @classmethod
    def build(cls, dependencies: Iterable[Mapping[str, object] | Dependency], version: int = 1) -> "DependencyManifest":
        values = tuple(sorted((_coerce_dependency(item) for item in dependencies), key=lambda item: (item.kind.value, item.name)))
        names = set()
        for item in values:
            if item.name in names:
                raise ValueError(f"dependency declared more than once: {item.name}")
            names.add(item.name)
        if any(item.kind is DependencyKind.FORBIDDEN for item in values):
            forbidden = [item.name for item in values if item.kind is DependencyKind.FORBIDDEN]
            raise ValueError(f"forbidden dependencies declared: {forbidden}")
        payload = {"version": version, "dependencies": [item.model_dump(mode="json") for item in values]}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(version=version, dependencies=values, digest=digest)

    def names(self, *kinds: DependencyKind) -> Tuple[str, ...]:
        selected = set(kinds)
        return tuple(item.name for item in self.dependencies if not selected or item.kind in selected)

    def allows(self, name: str) -> bool:
        return any(item.name == name and item.kind is not DependencyKind.FORBIDDEN for item in self.dependencies)


def _coerce_dependency(item: Mapping[str, object] | Dependency) -> Dependency:
    if isinstance(item, Dependency):
        return item
    return Dependency(name=str(item.get("name", item.get("package", ""))), kind=item.get("kind", item.get("category", DependencyKind.RUNTIME.value)), version=str(item.get("version", "")), source=str(item.get("source", "plan")))
