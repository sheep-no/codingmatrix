"""Project-level immutable generation plan and its consistency gate."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Iterable, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .dependency_manifest import DependencyManifest
from .interface_registry import InterfaceRegistry


class PlanFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    role: str = ""
    language: str = ""
    file_type: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    dependencies: Tuple[str, ...] = ()
    imports: Tuple[str, ...] = ()


class GenerationPlan(BaseModel):
    """The single project-level source of truth consumed by later stages."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(default=1, ge=1)
    policy: str = "extensible"
    language: str = ""
    framework: str = ""
    runtime: str = ""
    requested_paths: Tuple[str, ...] = ()
    files: Tuple[PlanFile, ...] = Field(min_length=1)
    interfaces: InterfaceRegistry = Field(default_factory=InterfaceRegistry.build)
    dependencies: DependencyManifest = Field(default_factory=DependencyManifest.build)
    digest: str = Field(min_length=64, max_length=64)

    @model_validator(mode="after")
    def validate_digest(self) -> "GenerationPlan":
        payload = {"version": self.version, "policy": self.policy, "language": self.language, "framework": self.framework, "runtime": self.runtime, "requested_paths": self.requested_paths, "files": [item.model_dump(mode="json") for item in self.files], "interfaces": self.interfaces.model_dump(mode="json"), "dependencies": self.dependencies.model_dump(mode="json")}
        expected = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        if self.digest != expected:
            raise ValueError("generation plan digest does not match its contents")
        return self

    @classmethod
    def build(cls, files: Iterable[Mapping[str, object] | PlanFile], *, language: str = "", framework: str = "", runtime: str = "", requested_paths: Optional[Iterable[str]] = None, policy: str = "extensible", version: int = 1, interfaces: Optional[InterfaceRegistry] = None, dependencies: Optional[DependencyManifest] = None) -> "GenerationPlan":
        normalized = tuple(sorted((_coerce_file(item) for item in files), key=lambda item: item.path))
        paths = {item.path for item in normalized}
        if len(paths) != len(normalized):
            raise ValueError("generation plan file paths must be unique")
        missing = {dependency for item in normalized for dependency in item.dependencies if dependency not in paths}
        if missing:
            raise ValueError(f"generation plan has missing file dependencies: {sorted(missing)}")
        requested = tuple(sorted({_normalize_path(path) for path in (requested_paths or ())}))
        if policy == "strict" and set(requested) != paths:
            raise ValueError("strict generation plan files must equal requested_paths")
        registry = interfaces or InterfaceRegistry.build(())
        manifest = dependencies or DependencyManifest.build(())
        payload = {"version": version, "policy": policy, "language": language, "framework": framework, "runtime": runtime, "requested_paths": requested, "files": [item.model_dump(mode="json") for item in normalized], "interfaces": registry.model_dump(mode="json"), "dependencies": manifest.model_dump(mode="json")}
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
        return cls(version=version, policy=policy, language=language, framework=framework, runtime=runtime, requested_paths=requested, files=normalized, interfaces=registry, dependencies=manifest, digest=digest)

    @classmethod
    def from_architecture(cls, architecture: Mapping[str, object], **kwargs: object) -> "GenerationPlan":
        files = architecture.get("file_plan", ())
        project = architecture.get("project_spec", {})
        project = project if isinstance(project, Mapping) else {}
        interface_data = architecture.get("interfaces", architecture.get("interface_registry", ()))
        dependency_data = architecture.get("dependencies", architecture.get("dependency_manifest", ()))
        interfaces = interface_data if isinstance(interface_data, InterfaceRegistry) else InterfaceRegistry.build(interface_data or ())
        dependencies = dependency_data if isinstance(dependency_data, DependencyManifest) else DependencyManifest.build(dependency_data or ())
        return cls.build(files, language=str(project.get("language", architecture.get("language", ""))), framework=str(project.get("framework", architecture.get("framework", ""))), runtime=str(project.get("runtime", architecture.get("runtime", ""))), interfaces=interfaces, dependencies=dependencies, **kwargs)

    def file_entries(self) -> Tuple[Mapping[str, object], ...]:
        """Return a compatibility projection with mutable collection fields."""
        return tuple({
            "path": item.path,
            "description": item.role,
            "language": item.language,
            "file_type": item.file_type,
            "priority": item.priority,
            "dependencies": list(item.dependencies),
            "imports": list(item.imports),
        } for item in self.files)


def _coerce_file(item: Mapping[str, object] | PlanFile) -> PlanFile:
    if isinstance(item, PlanFile):
        return item
    raw = item.get("dependencies", item.get("depends_on", ()))
    if isinstance(raw, str):
        raw = (raw,)
    imports = item.get("imports", ())
    if isinstance(imports, str):
        imports = (imports,)
    return PlanFile(path=_normalize_path(str(item.get("path", ""))), role=str(item.get("role", item.get("description", ""))), language=str(item.get("language", "")), file_type=str(item.get("file_type", "")), priority=item.get("priority", 3), dependencies=tuple(_normalize_path(str(value)) for value in raw or ()), imports=tuple(str(value) for value in imports or ()))


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def _normalize_path(path: str) -> str:
    candidate = path.strip().replace("\\", "/")
    if not candidate or candidate.startswith("/") or _WINDOWS_DRIVE.match(candidate):
        raise ValueError("plan paths must be relative and non-empty")
    parts = []
    for part in candidate.split("/"):
        if part in ("", "."):
            continue
        if part == ".." or any(char.isspace() for char in part):
            raise ValueError("plan paths cannot contain traversal or whitespace")
        parts.append(part)
    if not parts:
        raise ValueError("plan paths must identify a file")
    return PurePosixPath(*parts).as_posix()
