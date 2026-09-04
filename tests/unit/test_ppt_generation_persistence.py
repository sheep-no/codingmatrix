from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.ppt_state import PPTQualityReport
from app.models.unified_state import Artifact, Checkpoint
from app.services.ppt_generation_persistence import (
    build_ppt_trace_context,
    persist_ppt_generation_result,
    save_ppt_stage_checkpoint,
    serialize_quality_report,
)
from app.services.unified_state_service import StateOwnershipError, create_task
from app.tasks.ppt_tasks import _generate_ppt
from app.utils.pptx.quality import QualityIssue, QualityReport


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def _quality_report() -> QualityReport:
    return QualityReport(
        issues=[
            QualityIssue(
                "text_overflow",
                "slide-1",
                "high",
                "文本溢出",
                ("body",),
                "reduce_text_or_switch_layout",
            ),
            QualityIssue(
                "vision_review_unavailable",
                "slide-2",
                "medium",
                "视觉复审不可用",
            ),
        ],
        slide_scores={"slide-1": 80.0, "slide-2": 90.0},
        reflow_attempts={"slide-1": 2},
        manual_review_slides=["slide-1"],
    )


def test_trace_and_quality_report_serialization_preserve_versions_and_diagnostics():
    trace = build_ppt_trace_context(
        {
            "outline_id": "outline-1",
            "outline_version": 4,
            "planner_version": "planner-2",
            "template_version": "template-3",
        },
        "business",
        "refined",
    )
    quality = serialize_quality_report(_quality_report())

    assert trace == {
        "outline_id": "outline-1",
        "outline_version": 4,
        "quality_mode": "refined",
        "planner_version": "planner-2",
        "template_id": "business",
        "template_version": "template-3",
        "quality_stage": "planning",
    }
    assert quality["overall_score"] == 85.0
    assert quality["issues"][0]["fix_action"] == "reduce_text_or_switch_layout"
    assert quality["reflow_attempts"] == {"slide-1": 2}
    assert quality["manual_review_slides"] == ["slide-1"]
    assert quality["degraded_stage"] == "vision_review_unavailable"


@pytest.mark.asyncio
async def test_generation_result_persists_traceable_artifact_graph_and_checkpoints(db, tmp_path: Path):
    task = await create_task(db, 1, "ppt_generation", task_id="ppt-1")
    output = tmp_path / "ppt-1.pptx"
    output.write_bytes(b"ppt-version-1")
    trace = build_ppt_trace_context(
        {"outline_id": "outline-1", "outline_version": 2},
        "business",
        "refined",
    )
    slides = [{"id": "slide-1", "layout": "hero", "render_metadata": {"token_version": "1.0"}}]

    await save_ppt_stage_checkpoint(db, task.task_id, 1, 1, "planning", trace, {"slides": slides})
    await save_ppt_stage_checkpoint(db, task.task_id, 1, 2, "rule_qa", trace)
    artifact_ids = await persist_ppt_generation_result(
        db,
        task.task_id,
        1,
        output,
        "pptx",
        {"filename": output.name, "preview_url": "/api/v1/pptx/preview/ppt-1"},
        trace,
        slides,
        _quality_report(),
    )

    artifacts = (await db.scalars(select(Artifact).where(Artifact.task_id == task.task_id))).all()
    checkpoints = (
        await db.scalars(select(Checkpoint).where(Checkpoint.task_id == task.task_id).order_by(Checkpoint.revision))
    ).all()
    report = await db.scalar(select(PPTQualityReport).where(PPTQualityReport.task_id == task.task_id))

    assert {artifact.artifact_type for artifact in artifacts} == {
        "pptx",
        "preview",
        "layout_metadata",
        "quality_report",
    }
    assert [checkpoint.step for checkpoint in checkpoints] == ["planning", "rule_qa", "completed"]
    assert checkpoints[-1].artifact_ref == artifact_ids["output"]
    assert checkpoints[-1].state_json["quality"]["issues"][0]["fix_action"]
    assert checkpoints[-1].state_json["quality_stage"] == "completed"
    primary = next(artifact for artifact in artifacts if artifact.artifact_type == "pptx")
    children = [artifact for artifact in artifacts if artifact.parent_artifact_id == primary.id]
    assert {artifact.artifact_type for artifact in children} == {"preview", "layout_metadata", "quality_report"}
    assert len(primary.content_hash) == 64
    assert primary.metadata_json["outline_version"] == 2
    assert primary.metadata_json["quality_report_version"] == 1
    assert report.issues_json[0]["fix_action"] == "reduce_text_or_switch_layout"
    assert report.reflow_attempts_json == {"slide-1": 2}
    assert report.degraded_stage == "vision_review_unavailable"
    assert task.quality_report_artifact_id == artifact_ids["quality_report"]


@pytest.mark.asyncio
async def test_generation_result_is_idempotent_and_enforces_task_ownership(db, tmp_path: Path):
    task = await create_task(db, 1, "ppt_generation", task_id="ppt-2")
    output = tmp_path / "ppt-2.md"
    output.write_text("first", encoding="utf-8")
    trace = build_ppt_trace_context(
        {"outline_id": "outline-2", "outline_version": 1},
        "minimal",
    )
    result = {"filename": output.name, "preview_url": None}

    first_ids = await persist_ppt_generation_result(
        db, task.task_id, 1, output, "md", result, trace, [], _quality_report()
    )
    output.write_text("second", encoding="utf-8")
    second_ids = await persist_ppt_generation_result(
        db, task.task_id, 1, output, "md", result, trace, [], QualityReport()
    )

    artifacts = (await db.scalars(select(Artifact).where(Artifact.task_id == task.task_id))).all()
    reports = (await db.scalars(select(PPTQualityReport).where(PPTQualityReport.task_id == task.task_id))).all()
    assert first_ids == second_ids
    assert len(artifacts) == 3
    assert len(reports) == 1
    assert reports[0].issues_json == []
    assert reports[0].overall_score == 100

    with pytest.raises(StateOwnershipError):
        await persist_ppt_generation_result(
            db, task.task_id, 2, output, "md", result, trace, [], QualityReport()
        )


@pytest.mark.asyncio
async def test_celery_pipeline_persists_approved_outline_result(monkeypatch, tmp_path: Path):
    database_path = tmp_path / "celery-ppt.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        await create_task(session, 1, "ppt_generation", task_id="celery-ppt-1")
        await session.commit()

    monkeypatch.setattr("app.db.database.async_session", factory)
    monkeypatch.setattr("app.api.v1.aiGeneratorPptx.PPT_OUTPUT_DIR", tmp_path / "outputs")

    class Progress:
        async def update(self, *args, **kwargs):
            return None

    result = await _generate_ppt(
        "celery-ppt-1",
        1,
        {
            "topic": "季度复盘",
            "template": "minimal",
            "slide_count": 1,
            "output_format": "markdown",
            "options": {
                "outline_id": "outline-celery",
                "outline_version": 5,
                "quality_mode": "standard",
                "approved_outline": {
                    "title": "季度复盘",
                    "slides": [
                        {
                            "id": "slide-1",
                            "position": 0,
                            "slide_type": "key_points",
                            "title": "经营结论",
                            "key_message": "收入保持增长",
                            "content_blocks": [
                                {"type": "text", "content": "收入同比增长 20%", "metadata": {}}
                            ],
                        }
                    ],
                },
            },
        },
        Progress(),
    )

    async with factory() as session:
        artifacts = (
            await session.scalars(select(Artifact).where(Artifact.task_id == "celery-ppt-1"))
        ).all()
        checkpoints = (
            await session.scalars(
                select(Checkpoint)
                .where(Checkpoint.task_id == "celery-ppt-1")
                .order_by(Checkpoint.revision)
            )
        ).all()
        report = await session.scalar(
            select(PPTQualityReport).where(PPTQualityReport.task_id == "celery-ppt-1")
        )

    assert result["filename"] == "celery-ppt-1.md"
    assert result["preview_url"] is None
    assert {artifact.artifact_type for artifact in artifacts} == {"md", "layout_metadata", "quality_report"}
    assert [checkpoint.step for checkpoint in checkpoints] == ["planning", "rule_qa", "completed"]
    assert report.outline_id == "outline-celery"
    assert report.outline_version == 5
    assert (tmp_path / "outputs" / result["filename"]).is_file()
    await engine.dispose()
