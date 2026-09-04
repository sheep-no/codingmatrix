import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.base import Base
from app.models.file import File
from app.models.ppt_state import PPTOutline
from app.services.ppt_state_service import (
    approve_ppt_outline,
    create_ppt_outline,
    delete_ppt_outline,
    get_ppt_outline,
    save_ppt_quality_report,
    update_ppt_outline,
)
from app.services.unified_state_service import create_task
from app.services.unified_state_service import create_artifact, save_checkpoint
from app.schema.ppt_outline import OutlineCreateRequest, OutlineUpdateRequest
from app.services.unified_state_service import StateNotFoundError


@pytest.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest.fixture(autouse=True)
def disable_outline_web_search(monkeypatch):
    async def no_sources(*args, **kwargs):
        return []

    monkeypatch.setattr("app.services.ppt_state_service.FreeWebSearch.search", no_sources)


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
async def test_outline_scenario_is_detected_unless_user_selects_one(db):
    detected = await create_ppt_outline(
        db,
        "1",
        OutlineCreateRequest(topic="论文研究实验方法", num_slides=1),
    )
    selected = await create_ppt_outline(
        db,
        "1",
        OutlineCreateRequest(topic="论文研究实验方法", scenario="business", num_slides=1),
    )

    assert detected.scenario == "academic"
    assert selected.scenario == "business"


@pytest.mark.asyncio
async def test_delete_outline_removes_all_owned_versions(db):
    draft = await create_ppt_outline(db, "1", OutlineCreateRequest(topic="待删除大纲", num_slides=1))
    await update_ppt_outline(db, "1", draft.id, OutlineUpdateRequest(title="第二版"))

    await delete_ppt_outline(db, "1", draft.id)

    assert (await db.scalars(select(PPTOutline).where(PPTOutline.outline_id == draft.id))).all() == []
    with pytest.raises(StateNotFoundError):
        await get_ppt_outline(db, "1", draft.id)


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
async def test_material_content_is_parsed_into_owned_outline(db, tmp_path, monkeypatch):
    async def no_sources(*args, **kwargs):
        return []

    monkeypatch.setattr("app.services.ppt_state_service.FreeWebSearch.search", no_sources)
    material_path = tmp_path / "brief.txt"
    material_path.write_text("客户续约率达到 92%，重点推进华东区域。", encoding="utf-8")
    material = File(
        filename="brief.txt",
        file_path=str(material_path),
        file_size=material_path.stat().st_size,
        content_type="text/plain",
        user_id=1,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    draft = await create_ppt_outline(
        db,
        "1",
        OutlineCreateRequest(topic="客户经营复盘", num_slides=2, material_file_ids=[material.id]),
    )

    sourced_slide = next(slide for slide in draft.slides if slide.evidence_sources)
    assert "客户续约率达到 92%" in sourced_slide.content_blocks[0].content
    assert sourced_slide.evidence_sources[0]["material_file_id"] == material.id
    assert material.parsed_content == "客户续约率达到 92%，重点推进华东区域。"


@pytest.mark.asyncio
async def test_material_ids_are_scoped_to_outline_owner(db, tmp_path):
    material_path = tmp_path / "private.txt"
    material_path.write_text("仅属于其他用户的材料", encoding="utf-8")
    material = File(
        filename="private.txt",
        file_path=str(material_path),
        file_size=material_path.stat().st_size,
        content_type="text/plain",
        user_id=2,
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    with pytest.raises(StateNotFoundError, match="素材文件不存在"):
        await create_ppt_outline(
            db,
            "1",
            OutlineCreateRequest(topic="客户经营复盘", num_slides=1, material_file_ids=[material.id]),
        )


@pytest.mark.asyncio
async def test_approval_rejects_blank_content_blocks(db):
    draft = await create_ppt_outline(db, "1", OutlineCreateRequest(topic="业务汇报", num_slides=1))
    invalid_slide = draft.slides[0].model_copy(
        update={"content_blocks": [{"type": "text", "content": "   ", "metadata": {}}]}
    )
    await update_ppt_outline(
        db,
        "1",
        draft.id,
        OutlineUpdateRequest(slides=[invalid_slide]),
    )

    with pytest.raises(ValueError, match="大纲包含未完成页面"):
        await approve_ppt_outline(db, "1", draft.id)


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
