import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.agent.ppt_agent import PresentationOutline, SlideOutline
from app.models.base import Base
from app.models.file import File
from app.models.ppt_state import PPTOutline
from app.models.task import Task
from app.schema.ppt_outline import (
    ContentBlock,
    OutlineCreateRequest,
    OutlineSlide,
    OutlineUpdateRequest,
)
from app.services import ppt_state_service as svc
from app.services.unified_state_service import StateNotFoundError, StateOwnershipError


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
def no_web_search(monkeypatch):
    async def no_sources(*args, **kwargs):
        return []

    monkeypatch.setattr(svc.FreeWebSearch, "search", no_sources)


def _slide(index=0, **overrides):
    data = {
        "id": f"slide-{index + 1}",
        "position": index,
        "slide_type": "key_points",
        "title": f"页面{index + 1}",
        "key_message": "结论足够具体以支撑决策",
        "content_blocks": [{"type": "text", "content": "这是一段足够长的正文内容用于展示判断", "metadata": {}}],
    }
    data.update(overrides)
    return data


def _outline(title="主题", slides=None):
    return PresentationOutline(
        title=title,
        slides=slides
        or [
            SlideOutline(
                type="content",
                title="内容页",
                key_message="这是一条完整结论",
                content_blocks=[
                    {"type": "text", "content": "一段足够长的正文内容用于说明本页判断", "metadata": {}}
                ],
            )
        ],
    )


# --------------------------- helpers ---------------------------

def test_user_id_invalid_raises():
    with pytest.raises(StateOwnershipError):
        svc._user_id("not-a-number")


def test_agent_slides_builds_asset_intent():
    outline = PresentationOutline(
        title="主题",
        slides=[
            SlideOutline(
                type="image",
                title="示意图",
                bullets=[""],
                image_keywords=[f"k{i}" for i in range(15)],
            )
        ],
    )

    slides = svc._agent_slides(outline)

    assert slides[0]["asset_intent"]["keywords"] == [f"k{i}" for i in range(12)]
    assert slides[0]["content_blocks"][0]["content"] == "主题"


def test_agent_slides_uses_bullets_when_no_content_blocks():
    outline = PresentationOutline(
        title="主题",
        slides=[SlideOutline(type="content", title="页", bullets=["要点一", "  ", "要点二"])],
    )

    blocks = svc._agent_slides(outline)[0]["content_blocks"]

    assert [block["content"] for block in blocks] == ["要点一", "要点二"]


def test_agent_slides_key_message_fallback_when_no_bullets():
    outline = PresentationOutline(
        title="主题",
        slides=[SlideOutline(type="content", title="页", key_message="关键结论")],
    )

    blocks = svc._agent_slides(outline)[0]["content_blocks"]

    assert blocks[0]["content"] == "关键结论"


def test_editable_slides_falls_back_to_blueprint_when_all_removed():
    outline = PresentationOutline(
        title="全部页", slides=[SlideOutline(type="title", title="封面")]
    )

    slides = svc._editable_agent_slides(outline)

    assert len(slides) == 5


def test_is_closing_slide_markers():
    assert svc._is_closing_slide({"slide_type": "closing"}) is True
    assert svc._is_closing_slide({"slide_type": "end"}) is True
    assert svc._is_closing_slide({"title": "感谢聆听"}) is True
    assert svc._is_closing_slide({"key_message": "谢谢观看"}) is True
    assert svc._is_closing_slide({"title": "正文"}) is False


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("", True),
        ("饼图", True),
        ("行业分布表", True),
        ("趋势图", True),
        ("组织图", True),
        ("短标签", True),
        ("第一，这是一个足够长的分句", False),
        ("这是一段没有标点但足够长的正文内容", True),
        ("完成", True),
    ],
)
def test_looks_like_visual_placeholder(text, expected):
    assert svc._looks_like_visual_placeholder(text) is expected


def test_strip_instruction_prefix_variants():
    assert svc._strip_instruction_prefix("列出：核心任务") == "核心任务"
    assert svc._strip_instruction_prefix("展示，结果") == "结果"
    assert svc._strip_instruction_prefix("普通文本") == "普通文本"


def test_noun_phrase_core_removes_visual_tokens():
    assert svc._noun_phrase_core("试点成果") == "试点成果"
    assert svc._noun_phrase_core("架构图") == "架构"
    assert svc._noun_phrase_core("饼图，数据") == "数据"


def test_is_redundant_core_for_empty_parts():
    assert svc._is_redundant_core("", "claim") is True
    assert svc._is_redundant_core("core", "") is True
    assert svc._is_redundant_core("阶段验证", "阶段验证成果") is True
    assert svc._is_redundant_core("完全不同内容", "阶段验证成果") is False


def test_expand_visual_placeholder_remainer_branches():
    assert svc._expand_visual_placeholder(
        "饼图：这是足够长的剩余内容用于说明本页判断", "标题", ""
    ).endswith("。")
    assert "已能用" in svc._expand_visual_placeholder(
        "饼图：短一些的说明文字", "标题", ""
    )
    assert "转成可验收结果" in svc._expand_visual_placeholder(
        "交付成果", "执行路线", ""
    )
    assert "可量化证据" in svc._expand_visual_placeholder("列出", "执行路线", "短")
    fallback = "这是一段足够长的兜底结论内容用于本页判断"
    assert svc._expand_visual_placeholder("列出", "执行路线", fallback) == fallback


def test_sanitize_editable_slides_strips_instruction_prefixes():
    slides = [
        {
            "id": "s1",
            "position": 0,
            "slide_type": "key_points",
            "title": "页面",
            "key_message": "列出：需要重写的结论内容",
            "content_blocks": [
                {"type": "text", "content": "展示：需要重写的正文内容足够长", "metadata": {}},
            ],
        }
    ]

    result = svc._sanitize_editable_slides(slides, "主题")

    assert not result[0]["key_message"].startswith("列出")
    assert not result[0]["content_blocks"][0]["content"].startswith("展示")
    assert result[0]["asset_intent"] is not None


def test_sanitize_editable_slides_empty_instruction_prefix_falls_back():
    slides = [
        {
            "id": "s1",
            "position": 0,
            "slide_type": "key_points",
            "title": "页面",
            "key_message": "列出：",
            "content_blocks": [{"type": "text", "content": "展示：", "metadata": {}}],
        }
    ]

    result = svc._sanitize_editable_slides(slides, "主题")

    assert result[0]["key_message"]
    assert result[0]["content_blocks"][0]["content"]


def test_stage_event_shape():
    assert svc._stage_event(0) == {
        "type": "stage",
        "stage": "analyzing",
        "label": "分析主题与受众",
        "index": 0,
    }


def test_preview_from_raw_agent_slide_filters_title_end():
    assert svc._preview_from_raw_agent_slide({"type": "title", "title": "封面"}, 0) is None
    assert svc._preview_from_raw_agent_slide({"type": "end", "title": "结束"}, 0) is None


def test_preview_from_raw_agent_slide_requires_title():
    assert svc._preview_from_raw_agent_slide({"title": ""}, 0) is None


def test_preview_from_raw_agent_slide_filters_closing():
    assert svc._preview_from_raw_agent_slide(
        {"title": "感谢聆听", "bullets": ["谢谢"]}, 0
    ) is None


def test_preview_from_raw_agent_slide_empty_conversion(monkeypatch):
    monkeypatch.setattr(svc, "_agent_slides", lambda outline: [])

    assert svc._preview_from_raw_agent_slide({"title": "某页"}, 0) is None


def test_preview_from_raw_agent_slide_builds_preview():
    preview = svc._preview_from_raw_agent_slide(
        {
            "type": "content",
            "title": "内容",
            "key_message": "结论",
            "bullets": ["要点一", " ", "要点二"],
            "image_keywords": ["a", "b"],
            "notes": "备注",
            "narrative_role": "opportunity_map",
        },
        3,
    )

    assert preview["id"] == "slide-4"
    assert preview["position"] == 3


def test_attach_evidence_limits_and_extends():
    slides = [{"evidence_sources": []}, {}]

    svc._attach_evidence(slides, [{"a": 1}, {"b": 2}, {"c": 3}])

    assert slides[0]["evidence_sources"] == [{"a": 1}]
    assert slides[1]["evidence_sources"] == [{"b": 2}]


def test_apply_material_evidence_no_slides():
    slides = []
    svc._apply_material_evidence(slides, [{"id": 1, "filename": "f", "content": "x"}])
    assert slides == []


def test_apply_material_evidence_prepends_source_and_block():
    slides = [
        {"slide_type": "cover", "content_blocks": [], "evidence_sources": [{"old": True}]},
        {"slide_type": "key_points", "content_blocks": [{"type": "text", "content": "x", "metadata": {}}]},
    ]

    svc._apply_material_evidence(slides, [{"id": 7, "filename": "brief.txt", "content": "  资料   内容 "}])

    assert slides[1]["evidence_sources"][0]["material_file_id"] == 7
    assert slides[1]["content_blocks"][0]["content"] == "资料 内容"
    assert slides[0]["evidence_sources"] == [{"old": True}]


def test_apply_material_evidence_skips_empty_content_blocks():
    slides = [{"slide_type": "key_points", "content_blocks": [], "evidence_sources": []}]

    svc._apply_material_evidence(
        slides, [{"id": 1, "filename": "a.txt", "content": "内容"}]
    )

    assert slides[0]["content_blocks"] == []
    assert slides[0]["evidence_sources"][0]["material_file_id"] == 1


# --------------------------- materials ---------------------------

@pytest.mark.asyncio
async def test_load_materials_skips_empty_ids(db):
    assert await svc._load_materials(db, 1, []) == []


@pytest.mark.asyncio
async def test_load_materials_parse_error_raises(db, tmp_path, monkeypatch):
    path = tmp_path / "broken.bin"
    path.write_bytes(b"x")
    material = File(
        filename="broken.bin", file_path=str(path), file_size=1, content_type="application/octet-stream", user_id=1
    )
    db.add(material)
    await db.commit()
    await db.refresh(material)

    def boom(path):
        raise RuntimeError("cannot parse")

    monkeypatch.setattr(svc, "parse_document", boom)

    with pytest.raises(ValueError, match="无法解析素材文件"):
        await svc._load_materials(db, 1, [material.id])


@pytest.mark.asyncio
async def test_load_materials_empty_text_raises(db, tmp_path, monkeypatch):
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")
    material = File(filename="empty.txt", file_path=str(path), file_size=0, content_type="text/plain", user_id=1)
    db.add(material)
    await db.commit()
    await db.refresh(material)
    monkeypatch.setattr(svc, "parse_document", lambda path: "   ")

    with pytest.raises(ValueError, match="没有可提取的文本"):
        await svc._load_materials(db, 1, [material.id])


@pytest.mark.asyncio
async def test_load_materials_uses_cache(db, tmp_path):
    path = tmp_path / "cached.txt"
    path.write_text("ignored", encoding="utf-8")
    material = File(filename="cached.txt", file_path=str(path), file_size=1, content_type="text/plain", user_id=1)
    material.update_parse_cache("缓存内容")
    db.add(material)
    await db.commit()
    await db.refresh(material)

    result = await svc._load_materials(db, 1, [material.id, material.id])

    assert result == [{"id": material.id, "filename": "cached.txt", "content": "缓存内容"}]


# --------------------------- persistence ---------------------------

@pytest.mark.asyncio
async def test_get_ppt_outline_missing(db):
    with pytest.raises(StateNotFoundError):
        await svc.get_ppt_outline(db, "1", "missing")


@pytest.mark.asyncio
async def test_update_outline_without_request_fields(db):
    draft = await svc.create_ppt_outline(db, "1", OutlineCreateRequest(topic="主题", num_slides=2))

    updated = await svc.update_ppt_outline(db, "1", draft.id, OutlineUpdateRequest())

    assert updated.version == draft.version + 1
    assert updated.status == "draft"


@pytest.mark.asyncio
async def test_persist_new_outline_defaults_slide_limit(db):
    request = OutlineCreateRequest(topic="主题")
    draft = await svc._persist_new_outline(db, 1, request, "主题", [_slide(0)])

    assert draft.slide_limit == 2


@pytest.mark.asyncio
async def test_build_outline_slides_without_num_slides(db):
    request = OutlineCreateRequest(topic="主题")
    title, slides = await svc._build_outline_slides(request, [])

    assert title == "主题"
    assert slides


@pytest.mark.asyncio
async def test_create_ppt_outline_swallows_search_error(db, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("search down")

    monkeypatch.setattr(svc.FreeWebSearch, "search", boom)

    draft = await svc.create_ppt_outline(db, "1", OutlineCreateRequest(topic="主题", num_slides=2))

    assert draft.slides


@pytest.mark.asyncio
async def test_create_ppt_outline_with_agent(db, monkeypatch):
    class _Agent:
        def __init__(self, model=None):
            self.model = model

        async def generate_outline(self, topic, description, num_slides, api_key_token):
            return _outline(title="生成标题")

    monkeypatch.setattr(svc, "PPTAgent", _Agent)

    draft = await svc.create_ppt_outline(
        db,
        "1",
        OutlineCreateRequest(topic="主题", num_slides=1, api_key_token="token", model="m"),
    )

    assert draft.title == "生成标题"


# --------------------------- revise / approve ---------------------------

@pytest.mark.asyncio
async def test_revise_slide_requires_approved_base(db):
    draft = await svc.create_ppt_outline(db, "1", OutlineCreateRequest(topic="主题", num_slides=3))
    slide = OutlineSlide(**_slide(0))

    with pytest.raises(ValueError, match="请先批准基准大纲"):
        await svc.revise_ppt_slide(db, "1", draft.id, draft.version, slide.id, slide)


@pytest.mark.asyncio
async def test_revise_slide_missing_target(db):
    draft = await svc.create_ppt_outline(db, "1", OutlineCreateRequest(topic="主题", num_slides=2))
    await svc.approve_ppt_outline(db, "1", draft.id)
    slide = OutlineSlide(**_slide(0, id="missing"))

    with pytest.raises(StateNotFoundError, match="目标页面不存在"):
        await svc.revise_ppt_slide(db, "1", draft.id, 1, "missing", slide)


@pytest.mark.asyncio
async def test_revise_slide_requires_title_and_content(db):
    draft = await svc.create_ppt_outline(db, "1", OutlineCreateRequest(topic="主题", num_slides=2))
    await svc.approve_ppt_outline(db, "1", draft.id)
    slide = OutlineSlide(
        id=draft.slides[0].id,
        position=0,
        title="",
        key_message="结论",
        content_blocks=[ContentBlock(content="正文")],
    )

    with pytest.raises(ValueError, match="请填写页面标题"):
        await svc.revise_ppt_slide(db, "1", draft.id, 1, slide.id, slide)


@pytest.mark.asyncio
async def test_revise_slide_creates_new_version(db):
    draft = await svc.create_ppt_outline(db, "1", OutlineCreateRequest(topic="主题", num_slides=3))
    await svc.approve_ppt_outline(db, "1", draft.id)
    slide = OutlineSlide(
        id=draft.slides[0].id,
        position=0,
        title="新标题",
        key_message="新结论足够具体",
        content_blocks=[ContentBlock(content="新的正文内容足够长")],
    )

    revised = await svc.revise_ppt_slide(db, "1", draft.id, 1, slide.id, slide)

    assert revised.version == 2
    assert revised.status == "approved"
    assert revised.slides[0].title == "新标题"
    assert revised.slides[1].title == draft.slides[1].title


@pytest.mark.asyncio
async def test_approve_outline_marks_approved(db):
    draft = await svc.create_ppt_outline(db, "1", OutlineCreateRequest(topic="主题", num_slides=2))

    approved = await svc.approve_ppt_outline(db, "1", draft.id)

    assert approved.status == "approved"
    assert approved.approved_at


# --------------------------- quality report ---------------------------

@pytest.mark.asyncio
async def test_save_quality_report_missing_task(db):
    with pytest.raises(StateNotFoundError, match="任务不存在"):
        await svc.save_ppt_quality_report(
            db, "missing", 1, "outline", 1, "standard", "modern", "1",
            90, {}, [], {},
        )


@pytest.mark.asyncio
async def test_save_quality_report_clamps_score(db):
    from app.services.unified_state_service import create_task

    task = await create_task(db, 1, "ppt_generation")
    report = await svc.save_ppt_quality_report(
        db, task.task_id, 1, "outline", 2, "standard", "modern", "1",
        250, {"s": 1}, [{"issue": 1}], {"s": 1}, degraded_stage="stage",
    )

    assert report.overall_score == 100
    assert report.degraded_stage == "stage"
    assert task.outline_id == "outline"
    assert task.outline_version == 2


@pytest.mark.asyncio
async def test_get_quality_report_missing(db):
    with pytest.raises(StateNotFoundError, match="质量报告不存在"):
        await svc.get_ppt_quality_report(db, "missing", 1)


@pytest.mark.asyncio
async def test_get_quality_report_latest_version(db):
    from app.services.unified_state_service import create_task

    task = await create_task(db, 1, "ppt_generation")
    first = await svc.save_ppt_quality_report(
        db, task.task_id, 1, "outline", 1, "standard", "modern", "1",
        80, {}, [], {},
    )
    first.version = 0
    await db.commit()
    await svc.save_ppt_quality_report(
        db, task.task_id, 1, "outline", 2, "refined", "modern", "1",
        90, {}, [], {},
    )

    latest = await svc.get_ppt_quality_report(db, task.task_id, 1)

    assert latest.overall_score == 90


# --------------------------- stream ---------------------------

@pytest.mark.asyncio
async def test_stream_outline_without_api_key_emits_slides_and_done(db):
    events = [
        event
        async for event in svc.stream_ppt_outline(
            db, "1", OutlineCreateRequest(topic="主题", num_slides=2)
        )
    ]

    types = [event["type"] for event in events]
    assert types[0] == "stage"
    assert "slide" in types
    assert types[-2] == "stage"
    assert events[-1]["type"] == "done"


@pytest.mark.asyncio
async def test_stream_outline_retry_slide_and_complete(db, monkeypatch):
    first_outline = _outline(title="流式标题")

    class _Agent:
        def __init__(self, model=None):
            pass

        async def stream_outline(self, **kwargs):
            yield {"type": "slide", "slide": {"type": "content", "title": "预览页", "bullets": ["要点"]}}
            yield {"type": "retry", "attempt": 2}
            yield {"type": "slide", "slide": {"type": "title", "title": "封面"}}
            yield {"type": "slide", "slide": {"type": "content", "title": "第二页", "bullets": ["要点"]}}
            yield {"type": "unknown"}
            yield {"type": "complete", "outline": first_outline}

    monkeypatch.setattr(svc, "PPTAgent", _Agent)

    events = [
        event
        async for event in svc.stream_ppt_outline(
            db, "1", OutlineCreateRequest(topic="主题", num_slides=2, api_key_token="token")
        )
    ]

    types = [event["type"] for event in events]
    assert "retry" in types
    assert events[-1]["type"] == "done"
    assert events[-1]["draft"]["title"] == "流式标题"
    # preview index resets after retry, so the second content preview reuses index 0
    previews = [event for event in events if event["type"] == "slide"]
    assert previews[0]["index"] == 0
    assert previews[1]["index"] == 0


@pytest.mark.asyncio
async def test_stream_outline_complete_without_outline_falls_back(db, monkeypatch):
    class _Agent:
        def __init__(self, model=None):
            pass

        async def stream_outline(self, **kwargs):
            yield {"type": "complete", "outline": "not-an-outline"}

        async def generate_outline(self, **kwargs):
            return _outline(title="回退标题")

    monkeypatch.setattr(svc, "PPTAgent", _Agent)

    events = [
        event
        async for event in svc.stream_ppt_outline(
            db, "1", OutlineCreateRequest(topic="主题", num_slides=2, api_key_token="token")
        )
    ]

    assert events[-1]["type"] == "done"
    assert events[-1]["draft"]["title"] == "回退标题"


@pytest.mark.asyncio
async def test_stream_outline_swallows_search_error(db, monkeypatch):
    async def boom(*args, **kwargs):
        raise RuntimeError("search down")

    monkeypatch.setattr(svc.FreeWebSearch, "search", boom)

    events = [
        event
        async for event in svc.stream_ppt_outline(
            db, "1", OutlineCreateRequest(topic="主题", num_slides=1)
        )
    ]

    assert events[-1]["type"] == "done"
