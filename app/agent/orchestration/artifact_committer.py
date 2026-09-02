"""Verified artifact persistence and orchestration success gating."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agent.shared_context import SharedContext
from app.agent.utils import write_file_atomic

from .plan import GenerationPlan, normalize_plan_path


ARTIFACT_COMMIT_FAILED = "artifact_commit_failed"
ARTIFACT_CONSISTENCY_FAILED = "artifact_consistency_failed"


class ArtifactDiagnostic(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    path: Optional[str] = None
    details: Dict[str, Any] = Field(default_factory=dict)


class ArtifactCompletionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str = Field(min_length=1)
    event_type: str = "file_completed"
    path: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    size_bytes: int = Field(ge=1)


class ArtifactCommitResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    path: Optional[str] = None
    content_hash: Optional[str] = None
    size_bytes: int = Field(default=0, ge=0)
    idempotent: bool = False
    completion_event: Optional[ArtifactCompletionEvent] = None
    diagnostic: Optional[ArtifactDiagnostic] = None


class ArtifactConsistencyResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    success: bool
    planned_paths: Tuple[str, ...]
    manifest_paths: Tuple[str, ...]
    completed_paths: Tuple[str, ...]
    disk_paths: Tuple[str, ...]
    diagnostic: Optional[ArtifactDiagnostic] = None

    @model_validator(mode="after")
    def validate_diagnostic(self) -> "ArtifactConsistencyResult":
        if self.success and self.diagnostic is not None:
            raise ValueError("successful consistency result cannot contain a diagnostic")
        if not self.success and self.diagnostic is None:
            raise ValueError("failed consistency result requires a diagnostic")
        return self


Writer = Callable[[Path, str, str], bool]
Reader = Callable[[Path], bytes]


class ArtifactCommitter:
    """Write one generated file and register it only after disk verification."""

    def __init__(
        self,
        output_dir: Path,
        shared_context: SharedContext,
        *,
        task_id: str,
        max_file_bytes: int = 5 * 1024 * 1024,
        writer: Writer = write_file_atomic,
        reader: Reader = Path.read_bytes,
    ) -> None:
        if max_file_bytes < 1:
            raise ValueError("max_file_bytes must be positive")
        self.output_dir = output_dir
        self.shared_context = shared_context
        self.task_id = task_id
        self.max_file_bytes = max_file_bytes
        self._writer = writer
        self._reader = reader

    def commit(self, file_path: str, content: str, *, model_name: str) -> ArtifactCommitResult:
        try:
            normalized_path = normalize_plan_path(file_path)
        except (TypeError, ValueError) as exc:
            return self._failure(None, f"invalid artifact path: {exc}")

        if not isinstance(content, str) or not content.strip():
            return self._failure(normalized_path, "artifact content must be non-empty")

        encoded = content.encode("utf-8")
        size_bytes = len(encoded)
        if size_bytes > self.max_file_bytes:
            return self._failure(
                normalized_path,
                "artifact exceeds the configured size limit",
                details={"size_bytes": size_bytes, "max_file_bytes": self.max_file_bytes},
            )

        content_hash = hashlib.sha256(encoded).hexdigest()
        full_path = self.output_dir / normalized_path
        existing = self.shared_context.get_artifact_manifest().get(normalized_path)
        if existing and existing.get("content_hash") == content_hash:
            disk_result = self._read_and_hash(full_path, normalized_path)
            if isinstance(disk_result, ArtifactCommitResult):
                return disk_result
            disk_bytes, disk_hash = disk_result
            if disk_bytes == encoded and disk_hash == content_hash:
                return ArtifactCommitResult(
                    success=True,
                    path=normalized_path,
                    content_hash=content_hash,
                    size_bytes=size_bytes,
                    idempotent=True,
                )

        try:
            written = self._writer(self.output_dir, normalized_path, content)
        except Exception as exc:
            return self._failure(normalized_path, f"atomic artifact write raised an error: {exc}")
        if not written:
            return self._failure(normalized_path, "atomic artifact write failed")

        disk_result = self._read_and_hash(full_path, normalized_path)
        if isinstance(disk_result, ArtifactCommitResult):
            return disk_result
        disk_bytes, disk_hash = disk_result
        if disk_bytes != encoded or disk_hash != content_hash:
            return self._consistency_failure(
                normalized_path,
                "artifact content changed between generation and disk verification",
                details={"expected_hash": content_hash, "disk_hash": disk_hash},
            )

        self.shared_context.save_file_content(normalized_path, content, model_name)
        manifest_entry = self.shared_context.get_artifact_manifest().get(normalized_path)
        if manifest_entry is None or manifest_entry.get("content_hash") != disk_hash:
            return self._consistency_failure(
                normalized_path,
                "artifact manifest hash does not match the verified disk hash",
                details={
                    "manifest_hash": manifest_entry.get("content_hash") if manifest_entry else None,
                    "disk_hash": disk_hash,
                },
            )

        event_digest = hashlib.sha256(
            f"{self.task_id}\0{normalized_path}\0{content_hash}".encode("utf-8")
        ).hexdigest()
        completion_event = ArtifactCompletionEvent(
            event_id=f"{self.task_id}:file_completed:{event_digest}",
            path=normalized_path,
            content_hash=content_hash,
            size_bytes=size_bytes,
        )
        return ArtifactCommitResult(
            success=True,
            path=normalized_path,
            content_hash=content_hash,
            size_bytes=size_bytes,
            completion_event=completion_event,
        )

    def _read_and_hash(
        self,
        full_path: Path,
        normalized_path: str,
    ) -> tuple[bytes, str] | ArtifactCommitResult:
        try:
            disk_bytes = self._reader(full_path)
        except Exception as exc:
            return self._failure(normalized_path, f"artifact disk read failed: {exc}")
        if not disk_bytes or not disk_bytes.strip():
            return self._failure(normalized_path, "artifact disk content is empty")
        return disk_bytes, hashlib.sha256(disk_bytes).hexdigest()

    @staticmethod
    def _failure(
        path: Optional[str],
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> ArtifactCommitResult:
        return ArtifactCommitResult(
            success=False,
            path=path,
            diagnostic=ArtifactDiagnostic(
                code=ARTIFACT_COMMIT_FAILED,
                message=message,
                path=path,
                details=details or {},
            ),
        )

    @staticmethod
    def _consistency_failure(
        path: str,
        message: str,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> ArtifactCommitResult:
        return ArtifactCommitResult(
            success=False,
            path=path,
            diagnostic=ArtifactDiagnostic(
                code=ARTIFACT_CONSISTENCY_FAILED,
                message=message,
                path=path,
                details=details or {},
            ),
        )


def check_artifact_success_gate(
    plan: GenerationPlan,
    manifest: Mapping[str, Mapping[str, Any]],
    completion_events: Iterable[ArtifactCompletionEvent],
    output_dir: Path,
    *,
    allowed_validation_statuses: Iterable[str] = ("valid",),
) -> ArtifactConsistencyResult:
    """Verify plan, completion events, manifest, validation, and disk agree."""
    planned_paths = tuple(sorted(item.path for item in plan.files))
    manifest_paths = tuple(sorted(manifest))
    completed_events = tuple(completion_events)
    completed_paths = tuple(sorted(event.path for event in completed_events))
    try:
        disk_paths = _business_disk_paths(output_dir)
    except OSError as exc:
        return _gate_failure(
            planned_paths,
            manifest_paths,
            completed_paths,
            (),
            "unable to enumerate artifact files on disk",
            details={"error": str(exc)},
        )

    expected = set(planned_paths)
    sets = {
        "manifest": set(manifest_paths),
        "completed_events": set(completed_paths),
        "disk": set(disk_paths),
    }
    differences = {
        name: {
            "missing": sorted(expected - paths),
            "extra": sorted(paths - expected),
        }
        for name, paths in sets.items()
        if paths != expected
    }
    duplicate_events = sorted({path for path in completed_paths if completed_paths.count(path) > 1})
    if differences or duplicate_events:
        return _gate_failure(
            planned_paths,
            manifest_paths,
            completed_paths,
            disk_paths,
            "artifact file sets do not match the frozen generation plan",
            details={"differences": differences, "duplicate_events": duplicate_events},
        )

    allowed_statuses = set(allowed_validation_statuses)
    for event in completed_events:
        entry = manifest[event.path]
        artifact_path = output_dir / event.path
        if artifact_path.is_symlink():
            return _gate_failure(
                planned_paths,
                manifest_paths,
                completed_paths,
                disk_paths,
                "artifact path cannot be a symbolic link",
                path=event.path,
            )
        try:
            disk_bytes = artifact_path.read_bytes()
        except OSError as exc:
            return _gate_failure(
                planned_paths,
                manifest_paths,
                completed_paths,
                disk_paths,
                "unable to read artifact file from disk",
                path=event.path,
                details={"error": str(exc)},
            )
        disk_hash = hashlib.sha256(disk_bytes).hexdigest()
        manifest_hash = entry.get("content_hash")
        if not disk_bytes.strip() or event.content_hash != disk_hash or manifest_hash != disk_hash:
            return _gate_failure(
                planned_paths,
                manifest_paths,
                completed_paths,
                disk_paths,
                "artifact hashes are inconsistent",
                path=event.path,
                details={
                    "event_hash": event.content_hash,
                    "manifest_hash": manifest_hash,
                    "disk_hash": disk_hash,
                },
            )
        if entry.get("status") not in allowed_statuses or not entry.get("validation_passed", False):
            return _gate_failure(
                planned_paths,
                manifest_paths,
                completed_paths,
                disk_paths,
                "artifact validation has not reached an allowed terminal state",
                path=event.path,
                details={"status": entry.get("status")},
            )

    return ArtifactConsistencyResult(
        success=True,
        planned_paths=planned_paths,
        manifest_paths=manifest_paths,
        completed_paths=completed_paths,
        disk_paths=disk_paths,
    )


def _business_disk_paths(output_dir: Path) -> Tuple[str, ...]:
    if not output_dir.exists():
        return ()
    paths = []
    for path in output_dir.rglob("*"):
        relative = path.relative_to(output_dir)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if path.is_file():
            paths.append(relative.as_posix())
    return tuple(sorted(paths))


def _gate_failure(
    planned_paths: Tuple[str, ...],
    manifest_paths: Tuple[str, ...],
    completed_paths: Tuple[str, ...],
    disk_paths: Tuple[str, ...],
    message: str,
    *,
    path: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> ArtifactConsistencyResult:
    return ArtifactConsistencyResult(
        success=False,
        planned_paths=planned_paths,
        manifest_paths=manifest_paths,
        completed_paths=completed_paths,
        disk_paths=disk_paths,
        diagnostic=ArtifactDiagnostic(
            code=ARTIFACT_CONSISTENCY_FAILED,
            message=message,
            path=path,
            details=details or {},
        ),
    )
