"""Immutable file-plan policies for Orchestrator Core."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from pathlib import PurePosixPath
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from .models import utc_now


class PlanPolicy(str, Enum):
    STRICT = "strict"
    EXTENSIBLE = "extensible"


class PlanFileOrigin(str, Enum):
    REQUESTED = "requested"
    PLANNED = "planned"
    EXTENSION = "extension"


class PlanIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    path: Optional[str] = None


class FilePlanValidationError(ValueError):
    """Structured collection of errors that prevented plan freezing."""

    def __init__(self, issues: Sequence[PlanIssue]) -> None:
        self.issues = tuple(issues)
        summary = "; ".join(f"{issue.code}: {issue.message}" for issue in self.issues)
        super().__init__(summary)


class PlannedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    role: str = ""
    language: str = ""
    file_type: str = ""
    priority: int = Field(default=3, ge=1, le=5)
    dependencies: Tuple[str, ...] = ()
    imports: Tuple[str, ...] = ()
    origin: PlanFileOrigin = PlanFileOrigin.PLANNED
    source: Optional[str] = None
    reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_extension_provenance(self) -> "PlannedFile":
        if self.origin is PlanFileOrigin.EXTENSION and not self.source:
            raise ValueError("extension file requires source")
        if self.origin is PlanFileOrigin.EXTENSION and not self.reason:
            raise ValueError("extension file requires reason")
        return self


class GenerationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int = Field(ge=1)
    policy: PlanPolicy
    requested_paths: Tuple[str, ...] = ()
    files: Tuple[PlannedFile, ...] = Field(min_length=1)
    digest: str = Field(min_length=64, max_length=64)
    frozen_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_frozen_plan(self) -> "GenerationPlan":
        planned_paths = [item.path for item in self.files]
        if len(set(planned_paths)) != len(planned_paths):
            raise ValueError("generation plan file paths must be unique")
        if len(set(self.requested_paths)) != len(self.requested_paths):
            raise ValueError("requested_paths must be unique")
        if self.policy is PlanPolicy.STRICT:
            if set(planned_paths) != set(self.requested_paths):
                raise ValueError("strict plan files must equal requested_paths")
        for item in self.files:
            missing = set(item.dependencies) - set(planned_paths)
            if missing:
                raise ValueError(f"file {item.path} has missing dependencies: {sorted(missing)}")
        expected_digest = _plan_digest(
            self.version,
            self.policy,
            self.requested_paths,
            self.files,
        )
        if self.digest != expected_digest:
            raise ValueError("generation plan digest does not match its contents")
        return self


_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")


def normalize_plan_path(path: str) -> str:
    """Return one safe, relative POSIX representation for a planned file."""
    if not isinstance(path, str):
        raise ValueError("file path must be a string")
    candidate = path.strip().replace("\\", "/")
    if not candidate:
        raise ValueError("file path must be non-empty")
    if "\x00" in candidate:
        raise ValueError("file path contains a null byte")
    if candidate.startswith("/") or _WINDOWS_DRIVE.match(candidate):
        raise ValueError("file path must be relative")
    if any(character.isspace() for character in candidate):
        raise ValueError("file path cannot contain whitespace")

    parts = []
    for part in candidate.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise ValueError("file path cannot contain parent traversal")
        if part in {".env", ".git"}:
            raise ValueError("file path targets a protected project file")
        if "," in part or ";" in part:
            raise ValueError("file path contains an unsupported separator")
        parts.append(part)

    if not parts:
        raise ValueError("file path must identify a file")
    normalized = PurePosixPath(*parts).as_posix()
    if normalized.endswith("/"):
        raise ValueError("file path must identify a file")
    return normalized


def build_file_plan(
    file_entries: Sequence[Mapping[str, Any]],
    *,
    requested_paths: Optional[Iterable[str]] = None,
    version: int = 1,
) -> GenerationPlan:
    """Validate and freeze a strict or extensible file plan."""
    issues = []
    normalized_requested = _normalize_requested_paths(requested_paths, issues)
    policy = PlanPolicy.STRICT if requested_paths is not None else PlanPolicy.EXTENSIBLE
    files = []
    seen_paths = set()

    for index, entry in enumerate(file_entries):
        if not isinstance(entry, Mapping):
            issues.append(PlanIssue(
                code="plan.invalid_file",
                message=f"file entry {index} must be an object",
            ))
            continue

        raw_path = entry.get("path")
        try:
            path = normalize_plan_path(raw_path)
        except ValueError as exc:
            issues.append(PlanIssue(
                code="plan.invalid_path",
                message=str(exc),
                path=str(raw_path) if raw_path is not None else None,
            ))
            continue
        if path in seen_paths:
            issues.append(PlanIssue(
                code="plan.duplicate_file",
                message="normalized file path appears more than once",
                path=path,
            ))
            continue
        seen_paths.add(path)

        dependencies = _normalize_dependencies(entry, path, issues)
        if dependencies is None:
            continue

        origin = entry.get("origin", PlanFileOrigin.PLANNED.value)
        if policy is PlanPolicy.STRICT and path in normalized_requested:
            origin = PlanFileOrigin.REQUESTED.value
        raw_imports = entry.get("imports", ())
        if isinstance(raw_imports, str):
            raw_imports = (raw_imports,)
        try:
            files.append(PlannedFile(
                path=path,
                role=str(entry.get("role") or entry.get("description") or ""),
                language=str(entry.get("language") or ""),
                file_type=str(entry.get("file_type") or ""),
                priority=entry.get("priority", 3),
                dependencies=dependencies,
                imports=tuple(str(value) for value in raw_imports),
                origin=origin,
                source=entry.get("source"),
                reason=entry.get("reason"),
            ))
        except (TypeError, ValidationError, ValueError) as exc:
            issues.append(PlanIssue(
                code="plan.invalid_file",
                message=str(exc),
                path=path,
            ))

    planned_paths = {item.path for item in files}
    if policy is PlanPolicy.STRICT:
        for path in sorted(planned_paths - normalized_requested):
            issues.append(PlanIssue(
                code="plan.unexpected_file",
                message="file is outside the strict requested scope",
                path=path,
            ))
        for path in sorted(normalized_requested - planned_paths):
            issues.append(PlanIssue(
                code="plan.missing_requested_file",
                message="requested file is missing from the plan",
                path=path,
            ))

    for item in files:
        for dependency in item.dependencies:
            if dependency not in planned_paths:
                issues.append(PlanIssue(
                    code="plan.missing_dependency",
                    message=f"dependency {dependency} is missing from the plan",
                    path=item.path,
                ))

    if not files:
        issues.append(PlanIssue(
            code="plan.empty",
            message="file plan must contain at least one valid file",
        ))
    if issues:
        raise FilePlanValidationError(issues)

    ordered_files = tuple(sorted(files, key=lambda item: item.path))
    ordered_requested = tuple(sorted(normalized_requested))
    digest = _plan_digest(version, policy, ordered_requested, ordered_files)
    return GenerationPlan(
        version=version,
        policy=policy,
        requested_paths=ordered_requested,
        files=ordered_files,
        digest=digest,
    )


def _normalize_requested_paths(
    requested_paths: Optional[Iterable[str]],
    issues: list[PlanIssue],
) -> set[str]:
    if requested_paths is None:
        return set()
    normalized = set()
    for raw_path in requested_paths:
        try:
            path = normalize_plan_path(raw_path)
        except ValueError as exc:
            issues.append(PlanIssue(
                code="plan.invalid_requested_path",
                message=str(exc),
                path=str(raw_path),
            ))
            continue
        if path in normalized:
            issues.append(PlanIssue(
                code="plan.duplicate_requested_path",
                message="requested path appears more than once after normalization",
                path=path,
            ))
        normalized.add(path)
    if not normalized:
        issues.append(PlanIssue(
            code="plan.empty_requested_scope",
            message="strict plan requires at least one requested file",
        ))
    return normalized


def _normalize_dependencies(
    entry: Mapping[str, Any],
    file_path: str,
    issues: list[PlanIssue],
) -> Optional[Tuple[str, ...]]:
    raw_dependencies = entry.get("dependencies", entry.get("depends_on", ()))
    if isinstance(raw_dependencies, str):
        raw_dependencies = (raw_dependencies,)
    try:
        values = list(raw_dependencies)
    except TypeError:
        issues.append(PlanIssue(
            code="plan.invalid_dependencies",
            message="dependencies must be a sequence of file paths",
            path=file_path,
        ))
        return None

    normalized = []
    for raw_dependency in values:
        try:
            dependency = normalize_plan_path(raw_dependency)
        except ValueError as exc:
            issues.append(PlanIssue(
                code="plan.invalid_dependency_path",
                message=str(exc),
                path=file_path,
            ))
            continue
        if dependency == file_path:
            issues.append(PlanIssue(
                code="plan.self_dependency",
                message="file cannot depend on itself",
                path=file_path,
            ))
            continue
        if dependency not in normalized:
            normalized.append(dependency)
    return tuple(sorted(normalized))


def _plan_digest(
    version: int,
    policy: PlanPolicy,
    requested_paths: Tuple[str, ...],
    files: Tuple[PlannedFile, ...],
) -> str:
    payload = {
        "version": version,
        "policy": policy.value,
        "requested_paths": requested_paths,
        "files": [item.model_dump(mode="json") for item in files],
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
