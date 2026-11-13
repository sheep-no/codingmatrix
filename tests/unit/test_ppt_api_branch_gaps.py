"""Close remaining branch gaps in aiGeneratorPptx endpoint and renderer paths."""

import asyncio
import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pptx import Presentation

from app.api.v1 import aiGeneratorPptx as pptx
from app.db.database import get_db
from app.main import app
from app.utils.security import verify_token
from app.utils.visual.image_manager import ImageAsset, ImageSource
from app.utils.visual.visual_analyzer import ImageDecision, ImageType, SlideVisualDecision


USER_ID = "1"


class FakeDB:
    def __init__(self):
        self.execute = AsyncMock()
        self.scalar = AsyncMock(return_value=None)
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.add = MagicMock()


@pytest.fixture(autouse=True)
def _disable_limiter(monkeypatch):
    limiter = getattr(app.state, "limiter", None)
    if limiter is not None:
        monkeypatch.setattr(limiter, "enabled", False)
    from app.services.rate_limit_config import rate_limit_config

    monkeypatch.setattr(rate_limit_config, "_enabled", False)
    yield


@pytest.fixture
def client():
    app.dependency_overrides[verify_token] = lambda: {"sub": USER_ID, "role": "user"}
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def fake_db(client):
    db = FakeDB()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def direct_db():
    """Client-free DB for tests that await endpoints directly.

    Starting TestClient spawns a portal thread, which makes coverage tracing
    unreliable for closures created in the main test thread.
    """
    return FakeDB()


@pytest.fixture
def output(tmp_path, monkeypatch):
    owners = tmp_path / ".owners"
    owners.mkdir()
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pptx, "PPT_OWNER_DIR", owners)
    return tmp_path


def _owner(output, ppt_id, user_id=USER_ID):
    (output / ".owners" / f"{ppt_id}.json").write_text(
        json.dumps({"ppt_id": ppt_id, "user_id": str(user_id)})
    )


def _request(template="business", language="zh-CN", **kwargs):
    return pptx.PPTGenerationRequest(
        prompt=kwargs.pop("prompt", "季度复盘"),
        template=template,
        language=language,
        slide_count=kwargs.pop("slide_count", 5),
        **kwargs,
    )


def _capture_task(monkeypatch):
    captured = {}

    async def create_task(task_type, user_id, func, params=None):
        captured["func"] = func
        return str(uuid.uuid4())

    monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
    return captured


def _patch_outline_render(monkeypatch, slides=None):
    slides = slides if slides is not None else [{"title": "页", "content": ["a"]}]
    monkeypatch.setattr(
        pptx, "generate_ppt_outline",
        AsyncMock(return_value={"title": "标题", "slides": slides}),
    )
    monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", AsyncMock())
    monkeypatch.setattr(pptx, "generate_html_ppt", AsyncMock())
    monkeypatch.setattr(pptx, "generate_markdown_ppt", AsyncMock())
    monkeypatch.setattr(pptx, "run_quality_pipeline", AsyncMock(return_value=(slides, {})))
    monkeypatch.setattr(pptx, "serialize_quality_report", lambda report: {})
    monkeypatch.setattr(pptx, "save_ppt_stage_checkpoint", AsyncMock())
    monkeypatch.setattr(pptx, "persist_ppt_generation_result", AsyncMock())


def test_approve_outline_not_found_maps_404(client, fake_db, monkeypatch):
    monkeypatch.setattr(
        pptx, "persist_approve_ppt_outline",
        AsyncMock(side_effect=pptx.StateNotFoundError("missing")),
    )
    resp = client.post("/api/v1/pptx/outlines/o1/approve")
    assert resp.status_code == 404


def test_fit_editorial_text_empty_value_reaches_fallback_return():
    value, size = pptx._fit_editorial_text("", 1.0, 0.01, 18)
    assert value == ""
    assert size == 8


def test_cropped_picture_equal_ratio_skips_crop(tmp_path):
    from PIL import Image

    square = tmp_path / "square.png"
    Image.new("RGB", (50, 50)).save(square)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    picture = pptx._add_cropped_picture(slide, str(square), 0, 0, 2, 2)
    assert picture.crop_left == 0
    assert picture.crop_top == 0


def test_render_modern_directly_delegates_variant():
    prs = Presentation()
    slide_data = {
        "title": "变体",
        "narrative_role": "opportunity_map",
        "content": ["a", "b", "c", "d"],
        "layout_variant": 2,
    }
    slide = pptx._render_slide_modern(
        prs, prs.slide_layouts[6], pptx.PPTStyle("modern"), slide_data, 1, 4
    )
    assert slide is not None
    assert len(prs.slides) == 1


def test_creative_decision_close_without_fourth_item():
    prs = Presentation()
    slide_data = {
        "title": "收束",
        "narrative_role": "decision_close",
        "content": ["a", "b"],
    }
    pptx._render_slide_creative(
        prs, prs.slide_layouts[6], pptx.PPTStyle("creative"), slide_data, 1, 2
    )
    assert len(prs.slides) == 1


def test_default_evidence_story_without_fourth_item():
    prs = Presentation()
    style = pptx.PPTStyle("modern")
    style.template_name = "unknown"
    slide_data = {
        "title": "证据",
        "narrative_role": "evidence_story",
        "content": ["a", "b"],
        "evidence_sources": [{"title": "公开报告"}],
    }
    pptx._render_slide_default(prs, prs.slide_layouts[6], style, slide_data, 1, 2)
    assert len(prs.slides) == 1


@pytest.mark.asyncio
async def test_read_material_text_empty_parse_does_not_cache(monkeypatch):
    record = SimpleNamespace(
        filename="a.pdf",
        file_path="/tmp/a.pdf",
        parsed_content=None,
        is_parse_cache_valid=lambda: False,
        update_parse_cache=MagicMock(),
    )
    monkeypatch.setattr(
        "app.utils.aicloud.knowledge_processor.parse_document",
        lambda _path: "   ",
    )
    assert await pptx._read_material_text(record) == ""
    record.update_parse_cache.assert_not_called()


@pytest.mark.asyncio
async def test_build_material_context_skips_query_errors():
    db = SimpleNamespace(execute=AsyncMock(side_effect=RuntimeError("db down")))
    assert await pptx._build_material_context(db, USER_ID, [7]) == ""


@pytest.mark.asyncio
async def test_build_material_context_degrades_on_read_error(monkeypatch):
    record = SimpleNamespace(filename="a.pdf", conversation_id=None)
    result = SimpleNamespace(scalar_one_or_none=lambda: record)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    monkeypatch.setattr(
        pptx, "_read_material_text", AsyncMock(side_effect=RuntimeError("bad"))
    )
    context = await pptx._build_material_context(db, USER_ID, [7])
    assert "- a.pdf" in context


@pytest.mark.asyncio
async def test_build_material_context_empty_content_uses_filename(monkeypatch):
    record = SimpleNamespace(filename="empty.pdf", conversation_id=None)
    result = SimpleNamespace(scalar_one_or_none=lambda: record)
    db = SimpleNamespace(execute=AsyncMock(return_value=result))
    monkeypatch.setattr(pptx, "_read_material_text", AsyncMock(return_value=""))
    context = await pptx._build_material_context(db, USER_ID, [7])
    assert "- empty.pdf" in context


@pytest.mark.asyncio
async def test_outline_dict_response_without_choices_uses_string(monkeypatch):
    monkeypatch.setattr(pptx, "call_llm", AsyncMock(return_value={}))
    outline = await pptx.generate_ppt_outline(_request(), user_id=USER_ID)
    assert outline == {}


@pytest.mark.asyncio
async def test_outline_list_payload_skips_diversity(monkeypatch):
    monkeypatch.setattr(pptx, "call_llm", AsyncMock(return_value="[]"))
    diversity = MagicMock()
    monkeypatch.setattr(pptx, "_ensure_commercial_role_diversity", diversity)
    outline = await pptx.generate_ppt_outline(_request(), user_id=USER_ID)
    assert outline == []
    diversity.assert_not_called()


@pytest.mark.asyncio
async def test_render_uses_style_fallback_when_tokens_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        pptx.TemplateManager, "resolve_design_tokens",
        MagicMock(side_effect=KeyError("missing")),
    )
    filepath = tmp_path / "tokens.pptx"
    outline = {"title": "T", "slides": [{"title": "页", "content": ["a"]}]}
    await pptx.generate_pptx_file_enhanced(filepath, outline, _request())
    assert filepath.exists()


@pytest.mark.asyncio
async def test_render_uses_visual_plan_image(tmp_path, monkeypatch):
    image_path = tmp_path / "visual.png"
    from PIL import Image

    Image.new("RGB", (40, 40)).save(image_path)
    decision = SlideVisualDecision(
        slide_index=0,
        title="页",
        content_summary="a",
        images=[ImageDecision(image_type=ImageType.ILLUSTRATION)],
    )
    plan = SimpleNamespace(slides=[decision])
    monkeypatch.setattr(
        pptx.visual_analyzer, "analyze_ppt_content", AsyncMock(return_value=plan)
    )
    monkeypatch.setattr(
        pptx.image_manager, "get_image_for_slide",
        AsyncMock(return_value=ImageAsset(source=ImageSource.GENERATED, local_path=str(image_path))),
    )
    filepath = tmp_path / "visual.pptx"
    outline = {
        "title": "T",
        "slides": [{
            "title": "页",
            "content": ["a"],
            "narrative_role": "opportunity_map",
        }],
    }
    await pptx.generate_pptx_file_enhanced(
        filepath, outline, _request(api_key_token="token")
    )
    assert filepath.exists()


@pytest.mark.asyncio
async def test_render_swallows_visual_plan_image_failure(tmp_path, monkeypatch):
    decision = SlideVisualDecision(
        slide_index=0,
        title="页",
        content_summary="a",
        images=[ImageDecision(image_type=ImageType.ILLUSTRATION)],
    )
    monkeypatch.setattr(
        pptx.visual_analyzer, "analyze_ppt_content",
        AsyncMock(return_value=SimpleNamespace(slides=[decision])),
    )
    monkeypatch.setattr(
        pptx.image_manager, "get_image_for_slide",
        AsyncMock(side_effect=RuntimeError("image down")),
    )
    filepath = tmp_path / "fallback.pptx"
    outline = {
        "title": "T",
        "slides": [{
            "title": "页",
            "content": ["a"],
            "narrative_role": "opportunity_map",
        }],
    }
    await pptx.generate_pptx_file_enhanced(
        filepath, outline, _request(api_key_token="token")
    )
    assert filepath.exists()


def test_celery_dispatch_without_outline_options(client, fake_db, output, monkeypatch):
    monkeypatch.setenv("PPT_USE_CELERY", "true")
    monkeypatch.setattr(
        "app.services.ppt_dispatch_service.dispatch_ppt_to_celery",
        AsyncMock(return_value=("t1", "c1")),
    )
    resp = client.post(
        "/api/v1/pptx/generate_task", json={"prompt": "celery", "slide_count": 5}
    )
    assert resp.status_code == 200
    fake_db.scalar.assert_not_awaited()


def test_celery_dispatch_outline_record_missing(client, fake_db, output, monkeypatch):
    monkeypatch.setenv("PPT_USE_CELERY", "true")
    fake_db.scalar.return_value = None
    monkeypatch.setattr(
        "app.services.ppt_dispatch_service.dispatch_ppt_to_celery",
        AsyncMock(return_value=("t1", "c1")),
    )
    resp = client.post(
        "/api/v1/pptx/generate_task",
        json={
            "prompt": "celery",
            "slide_count": 5,
            "options": {"outline_id": "o1", "outline_version": 1},
        },
    )
    assert resp.status_code == 200
    fake_db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_generate_task_skips_material_regex_when_ids_present(direct_db, output, monkeypatch):
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)
    seen = {}

    async def build(_db, _user, ids, _session=None):
        seen["ids"] = ids
        return ""

    monkeypatch.setattr(pptx, "_build_material_context", build)
    req = pptx.PPTGenerationRequest(
        prompt="主题", slide_count=5, material_file_ids=[3]
    )
    await pptx.generate_ppt_task(req, token={"sub": USER_ID}, db=direct_db)
    await captured["func"]("t1")
    assert seen["ids"] == [3]


@pytest.mark.asyncio
async def test_generate_task_parses_legacy_material_prompt(direct_db, output, monkeypatch):
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)
    seen = {}

    async def build(_db, _user, ids, _session=None):
        seen["ids"] = ids
        return ""

    monkeypatch.setattr(pptx, "_build_material_context", build)
    req = pptx.PPTGenerationRequest(
        prompt="主题 <material>[1, 2]</material>", slide_count=5
    )
    await pptx.generate_ppt_task(req, token={"sub": USER_ID}, db=direct_db)
    await captured["func"]("t1")
    assert seen["ids"] == [1, 2]


@pytest.mark.asyncio
async def test_build_generation_context_joins_history_and_material(monkeypatch, direct_db):
    monkeypatch.setattr(
        pptx, "compress_conversation_history",
        AsyncMock(return_value="历史摘要"),
    )
    monkeypatch.setattr(
        pptx, "_build_material_context", AsyncMock(return_value="[参考素材]\n正文")
    )
    context = await pptx._build_generation_context(direct_db, USER_ID, 9, [1], "s1")
    assert "[对话历史]" in context
    assert "历史摘要" in context
    assert "[参考素材]" in context


@pytest.mark.asyncio
async def test_build_generation_context_without_sources_returns_empty(direct_db, monkeypatch):
    monkeypatch.setattr(pptx, "_build_material_context", AsyncMock(return_value=""))
    assert await pptx._build_generation_context(direct_db, USER_ID, None, [], None) == ""


@pytest.mark.asyncio
async def test_build_generation_context_empty_history_still_adds_material(direct_db, monkeypatch):
    monkeypatch.setattr(
        pptx, "compress_conversation_history", AsyncMock(return_value="")
    )
    monkeypatch.setattr(
        pptx, "_build_material_context", AsyncMock(return_value="素材")
    )
    assert await pptx._build_generation_context(direct_db, USER_ID, 9, [], None) == "素材"


@pytest.mark.asyncio
async def test_build_generation_context_swallows_history_failure(direct_db, monkeypatch):
    monkeypatch.setattr(
        pptx, "compress_conversation_history",
        AsyncMock(side_effect=RuntimeError("history down")),
    )
    monkeypatch.setattr(pptx, "_build_material_context", AsyncMock(return_value="素材"))
    assert await pptx._build_generation_context(direct_db, USER_ID, 9, [], None) == "素材"


@pytest.mark.asyncio
async def test_generate_task_appends_context_to_topic(direct_db, output, monkeypatch):
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)
    monkeypatch.setattr(
        pptx, "_build_generation_context", AsyncMock(return_value="[素材]\n正文")
    )
    seen = {}

    async def outline(req, user_id=None):
        seen["topic"] = req.topic
        return {"title": "T", "slides": [{"title": "页", "content": ["a"]}]}

    monkeypatch.setattr(pptx, "generate_ppt_outline", outline)
    req = pptx.PPTGenerationRequest(prompt="主题", slide_count=5)
    await pptx.generate_ppt_task(req, token={"sub": USER_ID}, db=direct_db)
    await captured["func"]("t1")
    assert seen["topic"].startswith("主题")
    assert "[素材]" in seen["topic"]


@pytest.mark.asyncio
async def test_generate_task_skips_topic_rewrite_without_context(direct_db, output, monkeypatch):
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)
    monkeypatch.setattr(
        pptx, "_build_generation_context", AsyncMock(return_value="")
    )
    seen = {}

    async def outline(req, user_id=None):
        seen["topic"] = req.topic
        return {"title": "T", "slides": [{"title": "页", "content": ["a"]}]}

    monkeypatch.setattr(pptx, "generate_ppt_outline", outline)
    req = pptx.PPTGenerationRequest(prompt="主题", slide_count=5)
    await pptx.generate_ppt_task(req, token={"sub": USER_ID}, db=direct_db)
    await captured["func"]("t1")
    assert seen["topic"] == "主题"


@pytest.mark.asyncio
async def test_generate_task_markdown_output(direct_db, output, monkeypatch):
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)
    req = pptx.PPTGenerationRequest(
        prompt="主题", slide_count=5, output_format="markdown"
    )
    await pptx.generate_ppt_task(req, token={"sub": USER_ID}, db=direct_db)
    result = await captured["func"]("t1")
    assert result["filename"].endswith(".md")
    pptx.generate_markdown_ppt.assert_awaited()


@pytest.mark.asyncio
async def test_generate_task_html_falls_back_to_pptx(direct_db, output, monkeypatch):
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)
    req = pptx.PPTGenerationRequest(prompt="主题", slide_count=5, output_format="html")
    await pptx.generate_ppt_task(req, token={"sub": USER_ID}, db=direct_db)
    result = await captured["func"]("t1")
    assert result["filename"].endswith(".html")
    pptx.generate_pptx_file_enhanced.assert_awaited()


@pytest.mark.asyncio
async def test_generate_task_cancel_cleans_partial_file(direct_db, output, monkeypatch):
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)

    async def render(filepath, *_args, **_kwargs):
        filepath.write_text("partial")

    async def cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", render)
    monkeypatch.setattr(pptx, "generate_html_ppt", cancelled)
    req = pptx.PPTGenerationRequest(prompt="主题", slide_count=5)
    await pptx.generate_ppt_task(req, token={"sub": USER_ID}, db=direct_db)
    assert await captured["func"]("t1") is None
    assert not (output / "t1.pptx").exists()


@pytest.mark.asyncio
async def test_generate_task_cancel_before_file_created(direct_db, output, monkeypatch):
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)

    async def cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(pptx, "generate_ppt_outline", cancelled)
    req = pptx.PPTGenerationRequest(prompt="主题", slide_count=5)
    await pptx.generate_ppt_task(req, token={"sub": USER_ID}, db=direct_db)
    assert await captured["func"]("t1") is None


def test_sync_generate_reraises_http_exception(client, output, monkeypatch):
    monkeypatch.setattr(
        pptx, "generate_ppt_outline",
        AsyncMock(side_effect=HTTPException(status_code=409, detail="bad")),
    )
    resp = client.post("/api/v1/pptx/generate", json={"prompt": "同步", "slide_count": 5})
    assert resp.status_code == 409


def test_update_task_missing_snapshot_with_owner(client, fake_db, output):
    task_id = str(uuid.uuid4())
    _owner(output, task_id)
    resp = client.post(
        f"/api/v1/pptx/{task_id}/update", json={"prompt": "增量", "slide_count": 5}
    )
    assert resp.status_code == 404


def test_modify_missing_pptx_returns_404(client, output):
    task_id = str(uuid.uuid4())
    _owner(output, task_id)
    resp = client.post(
        f"/api/v1/pptx/{task_id}/modify", json={"user_input": "改标题"}
    )
    assert resp.status_code == 404


def test_analyze_missing_pptx_returns_404(client, output):
    task_id = str(uuid.uuid4())
    _owner(output, task_id)
    assert client.get(f"/api/v1/pptx/{task_id}/analyze").status_code == 404


def test_history_skips_records_owned_by_other_user(client, output):
    task_id = str(uuid.uuid4())
    _owner(output, task_id)
    (output / f"{task_id}_slides.json").write_text(
        json.dumps({"user_id": "2", "slides": [{"title": "别人的"}]})
    )
    resp = client.get("/api/v1/pptx/history")
    assert resp.status_code == 200
    assert resp.json()["records"] == []


def test_delete_history_missing_snapshot_returns_404(client, output):
    task_id = str(uuid.uuid4())
    _owner(output, task_id)
    assert client.delete(f"/api/v1/pptx/history/{task_id}").status_code == 404


def test_generate_text_empty_draft_returns_500(client, fake_db, monkeypatch):
    monkeypatch.setattr(
        pptx, "persist_create_ppt_outline",
        AsyncMock(return_value=SimpleNamespace(slides=[])),
    )
    assert client.post("/api/v1/generate-text", json={"topic": "x"}).status_code == 500


def test_generate_text_reraises_http_exception(client, fake_db, monkeypatch):
    monkeypatch.setattr(
        pptx, "persist_create_ppt_outline",
        AsyncMock(side_effect=HTTPException(status_code=409, detail="conflict")),
    )
    assert client.post("/api/v1/generate-text", json={"topic": "x"}).status_code == 409


def test_generate_from_file_reraises_upload_http_exception(client, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)

    async def too_large(*_args, **_kwargs):
        raise HTTPException(status_code=400, detail="too large")

    monkeypatch.setattr(pptx, "_stream_upload_to_path", too_large)
    resp = client.post(
        "/api/v1/pptx/generate_from_file",
        files={"file": ("a.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 400


def test_generate_from_file_truncates_long_content(client, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", tmp_path / "out")
    (tmp_path / "out").mkdir()
    monkeypatch.setattr(pptx, "_parse_uploaded_document", AsyncMock(return_value="x" * 30005))
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)
    seen = {}

    async def outline(req, user_id=None):
        seen["topic"] = req.topic
        return {"title": "T", "slides": [{"title": "页", "content": ["a"]}]}

    monkeypatch.setattr(pptx, "generate_ppt_outline", outline)
    resp = client.post(
        "/api/v1/pptx/generate_from_file",
        files={"file": ("a.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 200
    asyncio.run(captured["func"]("t1"))
    assert "已截断至 30000 字符" in seen["topic"]


def test_generate_from_file_finally_handles_missing_temp(client, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", tmp_path / "out")
    (tmp_path / "out").mkdir()

    async def no_write(*_args, **_kwargs):
        return 0

    monkeypatch.setattr(pptx, "_stream_upload_to_path", no_write)
    monkeypatch.setattr(pptx, "_parse_uploaded_document", AsyncMock(return_value="text"))
    captured = _capture_task(monkeypatch)
    _patch_outline_render(monkeypatch)
    resp = client.post(
        "/api/v1/pptx/generate_from_file",
        files={"file": ("a.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 200
    assert asyncio.run(captured["func"]("t1"))["ppt_id"] == "t1"


def test_upload_custom_template_reraises_http_exception(client, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)

    async def too_large(*_args, **_kwargs):
        raise HTTPException(status_code=400, detail="too large")

    monkeypatch.setattr(pptx, "_stream_upload_to_path", too_large)
    resp = client.post(
        "/api/v1/pptx/templates/upload",
        files={"file": ("ok.pptx", b"x", "application/octet-stream")},
        data={"name": "n"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_convert_pptx_to_pdf_moves_generated_file(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    target_dir = tmp_path / "target"
    source_dir.mkdir()
    target_dir.mkdir()
    src = source_dir / "deck.pptx"
    dst = target_dir / "deck.pdf"
    src.write_bytes(b"x")

    def fake_run(_args, **_kwargs):
        src.with_suffix(".pdf").write_bytes(b"generated")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    await pptx._convert_pptx_to_pdf(src, dst)
    assert dst.read_bytes() == b"generated"


class FakeSessionContext:
    def __init__(self, db=None):
        self.db = db or SimpleNamespace(execute=AsyncMock(), commit=AsyncMock())

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_exc):
        return False


def _auth_ws(monkeypatch):
    monkeypatch.setattr(
        pptx, "verify_token_ws",
        AsyncMock(return_value=(True, {"sub": USER_ID}, 1000, "")),
    )
    monkeypatch.setattr(pptx, "_verify_ppt_owner", lambda *_args: None)


def _patch_ws_events(monkeypatch):
    async def replay(*_args, **_kwargs):
        return []

    monkeypatch.setattr("app.services.task_event_service.replay_task_events", replay)
    monkeypatch.setattr(pptx, "async_session", lambda: FakeSessionContext())


def _patch_ws_manager(monkeypatch, infos):
    manager = MagicMock()
    manager.get_task_info_async = AsyncMock(side_effect=list(infos))
    monkeypatch.setattr("app.utils.task_manager.task_manager", manager)
    return manager


def test_websocket_no_checkpoint_marks_snapshot_sent(client, monkeypatch):
    _auth_ws(monkeypatch)
    _patch_ws_events(monkeypatch)
    monkeypatch.setattr(
        "app.services.task_checkpoint_service.get_latest_checkpoint",
        AsyncMock(return_value=None),
    )
    _patch_ws_manager(
        monkeypatch,
        [{"status": "success", "progress": 100, "progress_message": "done", "result": {}}],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(
        f"/api/v1/ws/ppt/{task_id}?token=x&after_sequence=5"
    ) as ws:
        assert ws.receive_json()["type"] == "completed"


def test_websocket_unchanged_progress_and_non_ping_message(client, monkeypatch):
    _auth_ws(monkeypatch)
    _patch_ws_events(monkeypatch)
    _patch_ws_manager(
        monkeypatch,
        [
            {"status": "running", "progress": 10, "progress_message": "working"},
            {"status": "running", "progress": 10, "progress_message": "working"},
            {"status": "success", "progress": 100, "progress_message": "done", "result": {}},
        ],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        assert ws.receive_json()["type"] == "progress"
        ws.send_text("hello")
        assert ws.receive_json()["type"] == "completed"


def test_websocket_receive_timeout_continues(client, monkeypatch):
    _auth_ws(monkeypatch)
    _patch_ws_events(monkeypatch)
    _patch_ws_manager(
        monkeypatch,
        [
            {"status": "running", "progress": 10, "progress_message": "working"},
            {"status": "running", "progress": 10, "progress_message": "working"},
            {"status": "success", "progress": 100, "progress_message": "done", "result": {}},
        ],
    )
    task_id = str(uuid.uuid4())
    with client.websocket_connect(f"/api/v1/ws/ppt/{task_id}?token=x") as ws:
        assert ws.receive_json()["type"] == "progress"
        assert ws.receive_json()["type"] == "completed"
