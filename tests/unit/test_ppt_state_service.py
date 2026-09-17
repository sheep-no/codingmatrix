import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.ppt_agent import PresentationOutline, SlideOutline
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
    _editable_agent_slides,
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


def test_editable_agent_slides_drop_cover_and_thanks():
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(type="title", title="AI 趋势"),
            SlideOutline(
                type="content",
                title="产业落地",
                bullets=["垂直行业模型进入规模化部署"],
                content_blocks=[{"type": "text", "content": "垂直行业模型进入规模化部署", "metadata": {}}],
            ),
            SlideOutline(type="end", title="感谢聆听", bullets=["谢谢观看"]),
        ],
    )
    slides = _editable_agent_slides(outline)
    assert [slide["title"] for slide in slides] == ["产业落地"]


def test_editable_agent_slides_rewrite_chart_captions():
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(type="title", title="AI 趋势"),
            SlideOutline(
                type="content",
                title="产业落地",
                bullets=["行业应用分布饼图，展示各垂直领域占比", "三年执行计划甘特图"],
                content_blocks=[
                    {"type": "text", "content": "行业应用分布饼图，展示各垂直领域占比", "metadata": {}},
                    {"type": "text", "content": "三年执行计划甘特图", "metadata": {}},
                    {"type": "text", "content": "列出客服场景", "metadata": {}},
                    {"type": "text", "content": "合规限制对特定行业的影响已经形成可量化判断", "metadata": {}},
                ],
            ),
            SlideOutline(type="end", title="谢谢观看", bullets=["感谢聆听"]),
        ],
    )
    slides = _editable_agent_slides(outline)
    texts = [block["content"] for block in slides[0]["content_blocks"]]
    assert [slide["title"] for slide in slides] == ["产业落地"]
    assert all("饼图" not in text and "甘特图" not in text for text in texts)
    assert all(len(text) >= 16 for text in texts)
    assert texts[3] == "合规限制对特定行业的影响已经形成可量化判断"
    assert all("已形成可执行判断" not in text for text in texts)


def test_editable_agent_slides_keep_complete_sentences():
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(
                type="content",
                title="产业落地",
                bullets=["展示生成式 AI 在客服与营销场景的 ROI 提升超过 35%"],
                content_blocks=[
                    {"type": "text", "content": "展示生成式 AI 在客服与营销场景的 ROI 提升超过 35%", "metadata": {}},
                    {"type": "text", "content": "垂直行业大模型在金融与医疗领域完成首轮验证", "metadata": {}},
                    {"type": "text", "content": "企业级应用已从单点工具转向智能体协同", "metadata": {}},
                    {"type": "text", "content": "数据质量将直接决定模型效果上限", "metadata": {}},
                ],
            ),
        ],
    )
    texts = [block["content"] for block in _editable_agent_slides(outline)[0]["content_blocks"]]
    assert texts[0] == "生成式 AI 在客服与营销场景的 ROI 提升超过 35%"
    assert all("已形成可执行判断" not in text for text in texts)


def test_editable_agent_slides_expand_short_labels_without_repeating_conclusion():
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(
                type="content",
                title="执行路线",
                key_message="分阶段验证是转型落地的唯一可行节奏",
                bullets=["第一阶段完成试点验证"],
                content_blocks=[
                    {"type": "text", "content": "各阶段核心任务列表", "metadata": {}},
                    {"type": "text", "content": "每阶段预期交付成果", "metadata": {}},
                    {"type": "text", "content": "关键时间节点安排", "metadata": {}},
                    {"type": "text", "content": "AI 转型专项工作组组织。", "metadata": {}},
                ],
            ),
        ],
    )
    slide = _editable_agent_slides(outline)[0]
    texts = [block["content"] for block in slide["content_blocks"]]
    assert all(len(text) >= 16 for text in texts)
    assert len(set(texts)) == len(texts)
    assert all(slide["key_message"] not in text for text in texts)


def test_editable_agent_slides_skip_redundant_claim_wrap():
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(
                type="content",
                title="执行路线图：阶段与交付",
                bullets=["第一阶段聚焦核心场景验证与试点。"],
                content_blocks=[
                    {"type": "text", "content": "第一阶段核心场景验证与试点成果", "metadata": {}},
                    {"type": "text", "content": "确认试点场景、负责人、用户名单和首个交付日期。", "metadata": {}},
                    {"type": "text", "content": "批准试点资源，并锁定两周后的结果评审窗口。", "metadata": {}},
                    {"type": "text", "content": "关键时间节点安排", "metadata": {}},
                ],
            ),
        ],
    )
    texts = [block["content"] for block in _editable_agent_slides(outline)[0]["content_blocks"]]
    assert not any(text.startswith("第一阶段聚焦核心场景验证与试点；关注第一阶段") for text in texts)
    assert all("先验证付费意愿" not in text for text in texts)
    assert texts[1] == "确认试点场景、负责人、用户名单和首个交付日期。"
    assert all(len(text) >= 16 for text in texts)


def test_editable_agent_slides_keep_comma_arguments():
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(
                type="content",
                title="机会判断",
                bullets=["市场窗口已经打开"],
                content_blocks=[
                    {"type": "text", "content": "先验证付费意愿，再扩大产品和运营投入。", "metadata": {}},
                    {"type": "text", "content": "智能库存管理前后库存周转天数。", "metadata": {}},
                    {"type": "text", "content": "高频、重复、可量化的环节形成首个机会窗口。", "metadata": {}},
                    {"type": "text", "content": "垂直行业大模型在金融与医疗领域完成首轮验证", "metadata": {}},
                ],
            ),
        ],
    )
    texts = [block["content"] for block in _editable_agent_slides(outline)[0]["content_blocks"]]
    assert texts[0] == "先验证付费意愿，再扩大产品和运营投入。"
    assert "已能用" not in "".join(texts)
    assert texts[1] != "智能库存管理前后库存周转天数。"
    assert texts[3] == "垂直行业大模型在金融与医疗领域完成首轮验证"


def test_editable_agent_slides_keep_model_key_message():
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(
                type="content",
                title="机会判断",
                key_message="AI 落地需要先验证付费意愿",
                bullets=["先验证付费意愿，再扩大产品和运营投入。"],
                content_blocks=[
                    {"type": "text", "content": "先验证付费意愿，再扩大产品和运营投入。", "metadata": {}},
                ],
            ),
        ],
    )
    slide = _editable_agent_slides(outline)[0]

    assert slide["key_message"] == "AI 落地需要先验证付费意愿"


def test_editable_agent_slides_replace_key_message_that_repeats_body():
    body = "等待和重复录入构成体验损耗的主要来源"
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(
                type="content",
                title="现状与机会",
                key_message=body,
                bullets=[body],
                content_blocks=[
                    {"type": "text", "content": body, "metadata": {}},
                    {"type": "text", "content": "高价值用户更关注结果确定性。", "metadata": {}},
                ],
            ),
        ],
    )
    slide = _editable_agent_slides(outline)[0]
    block_texts = [block["content"] for block in slide["content_blocks"]]

    assert slide["key_message"]
    assert slide["key_message"] != body
    assert all(slide["key_message"] not in text for text in block_texts)


def test_editable_agent_slides_fill_key_message_when_missing():
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(
                type="content",
                title="执行路线",
                bullets=[],
                content_blocks=[
                    {"type": "text", "content": "第一阶段完成端到端场景验证。", "metadata": {}},
                    {"type": "text", "content": "第二阶段沉淀可复用能力组件。", "metadata": {}},
                ],
            ),
        ],
    )
    slide = _editable_agent_slides(outline)[0]
    block_texts = [block["content"] for block in slide["content_blocks"]]

    assert slide["key_message"]
    assert all(slide["key_message"] not in text for text in block_texts)


def test_editable_agent_slides_keep_complete_sentence_and_distinct_conclusion():
    conclusion = "围绕 AI 明确汇报目标、核心判断与行动方向。"
    outline = PresentationOutline(
        title="AI",
        slides=[
            SlideOutline(
                type="content",
                title="AI：现状",
                key_message=conclusion,
                bullets=["用户期待从单点工具升级为端到端结果。"],
                content_blocks=[
                    {"type": "signal", "content": "用户期待从单点工具升级为端到端结果。", "metadata": {}},
                    {"type": "signal", "content": "高频、重复、可量化的环节形成首个机会窗口。", "metadata": {}},
                ],
            ),
        ],
    )
    slide = _editable_agent_slides(outline)[0]
    block_texts = [block["content"] for block in slide["content_blocks"]]

    assert block_texts[0] == "用户期待从单点工具升级为端到端结果。"
    assert slide["key_message"] == conclusion
    assert all(conclusion not in text for text in block_texts)


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
        db, "1", OutlineCreateRequest(topic="业务汇报", num_slides=6)
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
        OutlineCreateRequest(topic="客户经营复盘", num_slides=3, material_file_ids=[material.id]),
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
    draft = await create_ppt_outline(db, "1", OutlineCreateRequest(topic="业务汇报", num_slides=2))
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
    draft = await create_ppt_outline(db, "1", OutlineCreateRequest(topic="业务汇报", num_slides=2))
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
