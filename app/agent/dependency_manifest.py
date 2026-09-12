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
    def build(cls, dependencies: Iterable[Mapping[str, object] | Dependency | str] | Mapping[str, object], version: int = 1) -> "DependencyManifest":
        entries = _normalize_dependencies(dependencies)
        values = tuple(sorted((_coerce_dependency(item) for item in entries), key=lambda item: (item.kind.value, item.name)))
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


def _normalize_dependencies(
    dependencies: Iterable[Mapping[str, object] | Dependency | str] | Mapping[str, object],
) -> Tuple[Mapping[str, object] | Dependency | str, ...]:
    if dependencies is None or isinstance(dependencies, str):
        return ()
    if not isinstance(dependencies, Mapping):
        return tuple(dependencies)
    if "name" in dependencies or "package" in dependencies:
        return (dependencies,)
    if "dependencies" in dependencies:
        nested = dependencies.get("dependencies", ())
        return tuple(nested) if not isinstance(nested, str) else (nested,)

    entries = []
    valid_kinds = {kind.value for kind in DependencyKind}
    if dependencies and all(
        isinstance(version, str) and name not in valid_kinds
        for name, version in dependencies.items()
    ):
        return tuple(
            {"name": name, "version": version, "kind": DependencyKind.RUNTIME.value}
            for name, version in dependencies.items()
        )
    for category, raw_items in dependencies.items():
        items = (raw_items,) if isinstance(raw_items, (str, Mapping, Dependency)) else tuple(raw_items or ())
        for item in items:
            if isinstance(item, str):
                entries.append({
                    "name": item,
                    "kind": category if category in valid_kinds else DependencyKind.RUNTIME.value,
                })
            else:
                entries.append(item)
    return tuple(entries)


def _coerce_dependency(item: Mapping[str, object] | Dependency | str) -> Dependency:
    if isinstance(item, Dependency):
        return item
    if isinstance(item, str):
        return Dependency(name=item, kind=DependencyKind.RUNTIME)
    return Dependency(name=str(item.get("name", item.get("package", ""))), kind=item.get("kind", item.get("category", DependencyKind.RUNTIME.value)), version=str(item.get("version", "")), source=str(item.get("source", "plan")))
