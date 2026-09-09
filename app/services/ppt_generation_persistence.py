"""Shared persistence helpers for PPT generation checkpoints and artifacts."""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ppt_state import PPTQualityReport
from app.models.unified_state import Artifact
from app.services.ppt_state_service import save_ppt_quality_report
from app.services.unified_state_service import create_artifact, get_owned_task, save_checkpoint
from app.utils.pptx.templates.manager import TemplateManager


PLANNER_VERSION = "1.0"
TEMPLATE_VERSION = "1.0"


def build_ppt_trace_context(
    options: Mapping[str, Any] | None,
    template_id: str,
    quality_mode: str = "standard",
    quality_stage: str = "planning",
) -> dict[str, Any]:
    """Build the version metadata shared by checkpoints and artifacts."""
    values = dict(options or {})
    template_version = values.get("template_version")
    if not template_version:
        config = TemplateManager().get_config(template_id)
        template_version = config.version if config else TEMPLATE_VERSION
    return {
        "outline_id": values.get("outline_id"),
        "outline_version": values.get("outline_version"),
        "quality_mode": values.get("quality_mode") or quality_mode,
        "planner_version": values.get("planner_version") or PLANNER_VERSION,
        "template_id": template_id,
        "template_version": template_version,
        "quality_stage": quality_stage,
    }


def serialize_quality_report(report: Any) -> dict[str, Any]:
    """Convert the in-memory quality report into JSON-safe state."""
    issues = [asdict(issue) if is_dataclass(issue) else dict(issue) for issue in report.issues]
    degraded_stage = next(
        (
            "vision_review_unavailable"
            for issue in issues
            if issue.get("issue_type") == "vision_review_unavailable"
        ),
        None,
    )
    return {
        "overall_score": report.overall_score,
        "slide_scores": dict(report.slide_scores),
        "issues": issues,
        "reflow_attempts": dict(report.reflow_attempts),
        "manual_review_slides": list(report.manual_review_slides),
        "degraded_stage": degraded_stage,
    }


async def save_ppt_stage_checkpoint(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    revision: int,
    stage: str,
    trace: Mapping[str, Any],
    state: Mapping[str, Any] | None = None,
    *,
    artifact_ref: str | None = None,
) -> None:
    payload = {**dict(trace), **dict(state or {}), "quality_stage": stage}
    await save_checkpoint(
        db,
        task_id,
        int(user_id),
        revision,
        stage,
        payload,
        f"{task_id}:ppt:{stage}:{revision}",
        input_ref=trace.get("outline_id"),
        artifact_ref=artifact_ref,
    )


async def _upsert_artifact(
    db: AsyncSession,
    user_id: int,
    task_id: str,
    artifact_type: str,
    storage_uri: str,
    metadata: Mapping[str, Any],
    *,
    parent_artifact_id: str | None = None,
    content_hash: str | None = None,
) -> Artifact:
    artifact = await db.scalar(
        select(Artifact).where(
            Artifact.task_id == task_id,
            Artifact.artifact_type == artifact_type,
            Artifact.version == 1,
        )
    )
    if artifact:
        artifact.storage_uri = storage_uri
        artifact.metadata_json = dict(metadata)
        artifact.parent_artifact_id = parent_artifact_id
        artifact.content_hash = content_hash
        return artifact
    return await create_artifact(
        db,
        int(user_id),
        artifact_type,
        storage_uri,
        task_id=task_id,
        content_hash=content_hash,
        parent_artifact_id=parent_artifact_id,
        metadata=dict(metadata),
    )


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


async def persist_ppt_generation_result(
    db: AsyncSession,
    task_id: str,
    user_id: int,
    filepath: Path,
    artifact_type: str,
    result: Mapping[str, Any],
    trace: Mapping[str, Any],
    slides: list[dict[str, Any]],
    quality_report: Any,
) -> dict[str, str | None]:
    """Persist final output, layout metadata, preview, and quality report."""
    task = await get_owned_task(db, task_id, int(user_id))
    quality = serialize_quality_report(quality_report)
    completed_trace = {**dict(trace), "quality_stage": "completed"}
    content_hash = await asyncio.to_thread(_file_sha256, filepath)
    primary = await _upsert_artifact(
        db,
        user_id,
        task_id,
        artifact_type,
        str(filepath),
        completed_trace,
        content_hash=content_hash,
    )
    layout = await _upsert_artifact(
        db,
        user_id,
        task_id,
        "layout_metadata",
        f"layout://{task_id}/1",
        {
            **completed_trace,
            "slides": [
                {
                    "slide_id": slide.get("id", f"slide-{index + 1}"),
                    "layout": slide.get("layout"),
                    "render_metadata": slide.get("render_metadata", {}),
                }
                for index, slide in enumerate(slides)
            ],
        },
        parent_artifact_id=primary.id,
    )
    preview = None
    if result.get("preview_url"):
        preview = await _upsert_artifact(
            db,
            user_id,
            task_id,
            "preview",
            str(result["preview_url"]),
            completed_trace,
            parent_artifact_id=primary.id,
        )

    report_row = None
    quality_artifact = None
    if completed_trace.get("outline_id") and completed_trace.get("outline_version"):
        report_row = await db.scalar(
            select(PPTQualityReport).where(
                PPTQualityReport.task_id == task_id,
                PPTQualityReport.user_id == int(user_id),
                PPTQualityReport.version == 1,
            )
        )
        if report_row is None:
            report_row = await save_ppt_quality_report(
                db,
                task_id,
                int(user_id),
                str(completed_trace["outline_id"]),
                int(completed_trace["outline_version"]),
                str(completed_trace["quality_mode"]),
                str(completed_trace["template_id"]),
                str(completed_trace["template_version"]),
                int(quality["overall_score"]),
                quality["slide_scores"],
                quality["issues"],
                quality["reflow_attempts"],
                quality["degraded_stage"],
            )
        else:
            report_row.outline_id = str(completed_trace["outline_id"])
            report_row.outline_version = int(completed_trace["outline_version"])
            report_row.quality_mode = str(completed_trace["quality_mode"])
            report_row.template_id = str(completed_trace["template_id"])
            report_row.template_version = str(completed_trace["template_version"])
            report_row.overall_score = max(0, min(100, int(quality["overall_score"])))
            report_row.slide_scores_json = quality["slide_scores"]
            report_row.issues_json = quality["issues"]
            report_row.reflow_attempts_json = quality["reflow_attempts"]
            report_row.degraded_stage = quality["degraded_stage"]
        quality_metadata = {
            **completed_trace,
            "quality_report_id": report_row.id,
            "quality_report_version": report_row.version,
            "manual_review_slides": quality["manual_review_slides"],
        }
        quality_artifact = await _upsert_artifact(
            db,
            user_id,
            task_id,
            "quality_report",
            f"quality://{task_id}/{report_row.version}",
            quality_metadata,
            parent_artifact_id=primary.id,
        )
        task.quality_report_artifact_id = quality_artifact.id
        completed_trace.update(
            {
                "quality_report_id": report_row.id,
                "quality_report_version": report_row.version,
            }
        )

    artifact_ids = {
        "output": primary.id,
        "preview": preview.id if preview else None,
        "layout_metadata": layout.id,
        "quality_report": quality_artifact.id if quality_artifact else None,
    }
    primary.metadata_json = {**completed_trace, "artifact_ids": artifact_ids}
    await save_ppt_stage_checkpoint(
        db,
        task_id,
        user_id,
        3,
        "completed",
        completed_trace,
        {"result": dict(result), "quality": quality, "artifact_ids": artifact_ids},
        artifact_ref=primary.id,
    )
    await db.commit()
    return artifact_ids


__all__ = [
    "PLANNER_VERSION",
    "TEMPLATE_VERSION",
    "build_ppt_trace_context",
    "persist_ppt_generation_result",
    "save_ppt_stage_checkpoint",
    "serialize_quality_report",
]
