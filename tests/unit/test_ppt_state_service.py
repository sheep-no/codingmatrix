import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.ppt_state import PPTOutline
from app.services.ppt_state_service import (
    approve_ppt_outline,
    create_ppt_outline,
    get_ppt_outline,
    save_ppt_quality_report,
    update_ppt_outline,
)
from app.services.unified_state_service import create_task
from app.services.unified_state_service import create_artifact, save_checkpoint
from app.schema.ppt_outline import OutlineCreateRequest, OutlineUpdateRequest


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_outline_versions_are_persisted_and_latest_is_retrievable(db):
    draft = await create_ppt_outline(db, "1", OutlineCreateRequest(topic="业务汇报", num_slides=2))
    updated = await update_ppt_outline(
        db,
        "1",
        draft.id,
        OutlineUpdateRequest(title="更新后的业务汇报"),
    )

    latest = await get_ppt_outline(db, "1", draft.id)
    version_one = await get_ppt_outline(db, "1", draft.id, version=1)

    assert updated.version == 2
    assert latest.title == "更新后的业务汇报"
    assert version_one.title == "业务汇报"
    assert len((await db.scalars(select(PPTOutline))).all()) == 2


@pytest.mark.asyncio
async def test_persisted_outline_keeps_commercial_metadata(db, monkeypatch):
    async def no_sources(*args, **kwargs):
        return []

    monkeypatch.setattr("app.services.ppt_state_service.FreeWebSearch.search", no_sources)
    draft = await create_ppt_outline(
        db, "1", OutlineCreateRequest(topic="业务汇报", num_slides=5)
    )

    assert draft.slides[0].content_blocks[3].metadata["roi"] == "≥3.0"
    assert draft.slides[2].content_blocks[1].metadata["timeframe"] == "4-6 周"
    assert draft.slides[3].content_blocks[2].metadata["gate"] == "降低 25%"
    assert draft.slides[4].content_blocks[2].metadata["deadline"] == "今日"


@pytest.mark.asyncio
async def test_approved_outline_can_be_used_for_quality_report_traceability(db):
    draft = await create_ppt_outline(db, "1", OutlineCreateRequest(topic="业务汇报", num_slides=1))
    approved = await approve_ppt_outline(db, "1", draft.id)
    task = await create_task(db, 1, "ppt_generation")
    await save_checkpoint(
        db,
        task.task_id,
        1,
        1,
        "outline",
        {"outline_id": approved.id, "outline_version": approved.version},
        "outline-checkpoint-1",
    )
    artifact = await create_artifact(
        db,
        1,
        "pptx",
        "pptx_output/example.pptx",
        task_id=task.task_id,
        metadata={"outline_version": approved.version},
    )
    report = await save_ppt_quality_report(
        db,
        task.task_id,
        1,
        approved.id,
        approved.version,
        "standard",
        approved.template_id,
        "template-v1",
        92,
        {approved.slides[0].id: 92},
        [],
        {approved.slides[0].id: 0},
    )

    assert report.outline_id == approved.id
    assert task.outline_id == approved.id
    assert task.outline_version == approved.version
    assert task.quality_mode == "standard"
    assert artifact.task_id == task.task_id
