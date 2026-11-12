"""Additional branch coverage for aiGeneratorPptx uncovered paths."""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import aiGeneratorPptx as pptx
from app.db.database import get_db
from app.main import app
from app.utils.security import verify_token


USER_ID = "1"


class FakeDB:
    def __init__(self):
        self.execute = AsyncMock()
        self.scalar = AsyncMock(return_value=None)
        self.commit = AsyncMock()
        self.rollback = AsyncMock()


@pytest.fixture(autouse=True)
def _disable_limiter(monkeypatch):
    limiter = getattr(app.state, "limiter", None)
    if limiter is not None:
        monkeypatch.setattr(limiter, "enabled", False)
    from app.services.rate_limit_config import rate_limit_config

    monkeypatch.setattr(rate_limit_config, "_enabled", False)
    yield


@pytest.fixture
def client_api():
    app.dependency_overrides[verify_token] = lambda: {"sub": USER_ID, "role": "user"}
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def fake_db(client_api):
    db = FakeDB()
    app.dependency_overrides[get_db] = lambda: db
    yield db
    app.dependency_overrides.pop(get_db, None)


@pytest.fixture
def output_dir(tmp_path, monkeypatch):
    owners = tmp_path / ".owners"
    owners.mkdir()
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(pptx, "PPT_OWNER_DIR", owners)
    return tmp_path


def _owner(output, ppt_id, user_id=USER_ID):
    (output / ".owners" / f"{ppt_id}.json").write_text(
        json.dumps({"ppt_id": ppt_id, "user_id": str(user_id)})
    )


def _req(**kwargs):
    return pptx.PPTGenerationRequest(
        prompt=kwargs.pop("prompt", "主题"),
        slide_count=kwargs.pop("slide_count", 5),
        **kwargs,
    )


@pytest.mark.asyncio
async def test_approved_outline_endpoint_not_found(client_api, monkeypatch, fake_db):
    monkeypatch.setattr(
        pptx, "persist_get_ppt_outline",
        AsyncMock(side_effect=pptx.StateNotFoundError("x")),
    )
    resp = client_api.post("/api/v1/pptx/outlines/o1/generate", json={})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_outline_generate_text_uses_success_response(client_api, fake_db, monkeypatch):
    draft = SimpleNamespace(
        id="o1",
        version=2,
        status="approved",
        title="标题",
        slides=[],
    )
    monkeypatch.setattr(
        pptx, "persist_create_ppt_outline", AsyncMock(return_value=draft)
    )
    monkeypatch.setattr(
        pptx, "persist_approve_ppt_outline", AsyncMock(return_value=draft)
    )
    monkeypatch.setattr(
        pptx, "generate_ppt_from_approved_outline",
        AsyncMock(return_value={
            "task_id": "t1",
            "task_type": "ppt_generation",
            "status": "pending",
            "created_at": "2026-01-01",
        }),
    )
    resp = client_api.post("/api/v1/generate-from-text", json={"topic": "x"})
    assert resp.status_code == 200


def test_editorial_fit_truncates_long_text():
    value, size = pptx._fit_editorial_text("字" * 2000, 1.0, 0.3, 18)
    assert value.endswith("…")
    assert size == 8


def test_cropped_picture_wide_and_tall(tmp_path):
    from PIL import Image
    from pptx import Presentation

    wide = tmp_path / "wide.png"
    Image.new("RGB", (100, 20)).save(wide)
    tall = tmp_path / "tall.png"
    Image.new("RGB", (20, 100)).save(tall)
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    wide_pic = pptx._add_cropped_picture(slide, str(wide), 0, 0, 2, 2)
    tall_pic = pptx._add_cropped_picture(slide, str(tall), 2, 0, 2, 2)
    assert wide_pic.crop_left > 0
    assert tall_pic.crop_top > 0


def test_soften_rounded_rect_swallows_errors():
    class Shape:
        @property
        def adjustments(self):
            raise ValueError("bad")

    pptx._soften_rounded_rect(Shape())
    pptx._item_at([], 0) == ""
    assert pptx._item_at(["a"], 5) == ""


def test_render_default_unmapped_template_branches(tmp_path):
    from pptx import Presentation

    prs = Presentation()
    style = pptx.PPTStyle("unknown")
    for role, items in (
        ("evidence_story", ["a", "b", "c", "d"]),
        ("strategic_choice", ["a", "b"]),
        ("execution_roadmap", ["a", "b", "c"]),
        ("decision_close", ["a"]),
        ("other", ["a", "b", "c", "d"]),
    ):
        slide_data = {
            "slide_type": role,
            "title": "标题",
            "content": items,
            "evidence_sources": [{"title": "来源"}],
        }
        pptx._render_slide_default(prs, prs.slide_layouts[6], style, slide_data, 1, 3)
    assert len(prs.slides) == 5


def test_render_default_uses_local_image(tmp_path):
    from PIL import Image
    from pptx import Presentation

    image = tmp_path / "pic.png"
    Image.new("RGB", (40, 40)).save(image)
    prs = Presentation()
    slide_data = {
        "slide_type": "other",
        "title": "标题",
        "content": ["a", "b", "c"],
        "local_images": [str(image)],
    }
    pptx._render_slide_default(prs, prs.slide_layouts[6], pptx.PPTStyle("unknown"), slide_data, 1, 2)
    assert len(prs.slides) == 1


def test_render_default_creative_decision_and_signal():
    from pptx import Presentation

    prs = Presentation()
    style = pptx.PPTStyle("creative")
    for role, items in (
        ("decision_close", ["a", "b", "c", "d"]),
        ("other", ["a", "b", "c"]),
    ):
        slide_data = {
            "slide_type": role,
            "title": "标题",
            "content": items,
            "evidence_sources": [{"title": "来源"}],
        }
        pptx._render_slide_creative(prs, prs.slide_layouts[6], style, slide_data, 1, 2)
    assert len(prs.slides) == 2


def test_item_at_negative_and_edge():
    assert pptx._item_at(["a"], -1) == ""
    assert pptx._item_at(["a"], 0) == "a"


@pytest.mark.asyncio
async def test_generate_outline_skill_and_game_paths(monkeypatch):
    response = {"choices": [{"message": {"content": json.dumps({
        "title": "游戏 AI",
        "slides": [{"title": "页", "content": ["x"], "content_blocks": [{"content": "x"}]}],
    })}}]}
    monkeypatch.setattr(pptx, "call_llm", AsyncMock(return_value=response))
    monkeypatch.setattr(pptx, "_ensure_commercial_role_diversity", MagicMock())
    monkeypatch.setattr(pptx, "_ensure_content_diversity", MagicMock())
    req = _req(prompt="游戏 AI 应用", skills=["storytelling"], material_file_ids=[1])
    outline = await pptx.generate_ppt_outline(req, user_id=USER_ID)
    assert outline["title"] == "游戏 AI"


@pytest.mark.asyncio
async def test_generate_outline_non_dict_response_fallback(monkeypatch):
    monkeypatch.setattr(pptx, "call_llm", AsyncMock(return_value="not-json"))
    req = _req(prompt="普通主题", slide_count=3)
    outline = await pptx.generate_ppt_outline(req, user_id=USER_ID)
    assert outline["slides"]


@pytest.mark.asyncio
async def test_sync_generate_pdf_and_fallback(monkeypatch, client_api, output_dir):
    monkeypatch.setattr(
        pptx, "generate_ppt_outline",
        AsyncMock(return_value={"title": "T", "slides": [{"title": "x"}]}),
    )
    monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", AsyncMock())
    monkeypatch.setattr(pptx, "generate_html_ppt", AsyncMock())
    monkeypatch.setattr(pptx, "generate_markdown_ppt", AsyncMock())
    resp = client_api.post(
        "/api/v1/pptx/generate",
        json={"prompt": "同步", "slide_count": 5, "output_format": "pdf"},
    )
    assert resp.status_code == 200
    assert resp.json()["preview_url"] is None


def test_modify_endpoint_preview_paths(client_api, output_dir, monkeypatch):
    ppt_id = str(uuid.uuid4())
    _owner(output_dir, ppt_id)
    (output_dir / f"{ppt_id}.pptx").write_bytes(b"x")

    async def modify(**_kwargs):
        return {"success": True, "message": "ok", "preview_count": 1}

    monkeypatch.setattr("app.utils.pptx.visual_modifier.modify_ppt_visual", modify)
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", output_dir)
    resp = client_api.post(
        f"/api/v1/pptx/{ppt_id}/modify",
        json={"user_input": "改标题", "analyze_before_modify": True},
    )
    assert resp.status_code == 200


def test_update_task_missing_snapshot(client_api, output_dir, monkeypatch):
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", output_dir)
    resp = client_api.post(
        f"/api/v1/pptx/{uuid.uuid4()}/update",
        json={"prompt": "增量", "slide_count": 5},
    )
    assert resp.status_code == 404


def test_update_task_owner_mismatch(client_api, output_dir, monkeypatch):
    task_id = str(uuid.uuid4())
    _owner(output_dir, task_id)
    (output_dir / f"{task_id}_slides.json").write_text(
        json.dumps({"user_id": "2", "slides": []})
    )
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", output_dir)
    resp = client_api.post(
        f"/api/v1/pptx/{task_id}/update",
        json={"prompt": "增量", "slide_count": 5},
    )
    assert resp.status_code == 403


def test_update_task_formats_and_closure(client_api, output_dir, monkeypatch):
    from app.api.v1.aiGeneratorPptx import OutputFormat

    task_id = str(uuid.uuid4())
    _owner(output_dir, task_id)
    (output_dir / f"{task_id}_slides.json").write_text(
        json.dumps({"user_id": USER_ID, "slides": [{"title": "旧"}]})
    )
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", output_dir)
    captured = {}

    async def create_task(task_type, user_id, func, params=None):
        captured["func"] = func
        return str(uuid.uuid4())

    monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
    monkeypatch.setattr(pptx.task_manager, "update_progress", AsyncMock())
    monkeypatch.setattr(
        pptx, "generate_ppt_outline",
        AsyncMock(return_value={"title": "新", "slides": [{"title": "新"}]}),
    )
    monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", AsyncMock())
    monkeypatch.setattr(pptx, "generate_html_ppt", AsyncMock())
    monkeypatch.setattr(pptx, "generate_markdown_ppt", AsyncMock())

    for fmt in ("pptx", "html", "markdown"):
        resp = client_api.post(
            f"/api/v1/pptx/{task_id}/update",
            json={"prompt": "增量", "slide_count": 5, "output_format": fmt},
        )
        assert resp.status_code == 200
        result = __import__("asyncio").run(captured["func"]("child"))
        assert result["ppt_id"] == "child"


def test_analyze_endpoint_failure(client_api, output_dir, monkeypatch):
    ppt_id = str(uuid.uuid4())
    _owner(output_dir, ppt_id)
    (output_dir / f"{ppt_id}.pptx").write_bytes(b"x")

    async def boom(**_kwargs):
        raise RuntimeError("analyze")

    monkeypatch.setattr(
        "app.utils.pptx.visual_modifier.analyze_ppt_for_modification", boom
    )
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", output_dir)
    assert client_api.get(f"/api/v1/pptx/{ppt_id}/analyze").status_code == 500


def test_history_unreadable_owner_file(client_api, output_dir, monkeypatch):
    task_id = str(uuid.uuid4())
    _owner(output_dir, task_id)
    (output_dir / f"{task_id}_slides.json").write_text("{}")
    (output_dir / ".owners" / f"{task_id}.json").write_text("{bad")
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", output_dir)
    resp = client_api.get("/api/v1/pptx/history")
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_template_preview_unknown_alias(client_api, monkeypatch):
    from app.utils.pptx.templates.manager import TemplateManager

    monkeypatch.setattr(
        TemplateManager, "select_template",
        MagicMock(side_effect=KeyError("missing")),
    )
    assert client_api.get("/api/v1/pptx/templates/zzz/preview/1").status_code == 404


def test_custom_template_listing_skips_bad_files(client_api, monkeypatch, tmp_path):
    template_dir = tmp_path / "configs" / "ppt" / "custom_templates"
    template_dir.mkdir(parents=True)
    (template_dir / "custom_1_abc.json").write_text(json.dumps({"a": 1}))
    (template_dir / "custom_1_bad.json").write_text("{bad")
    (template_dir / "custom_2_other.json").write_text(json.dumps({"b": 2}))
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    resp = client_api.get("/api/v1/pptx/templates/custom")
    assert resp.status_code == 200
    ids = [item["template_id"] for item in resp.json()["templates"]]
    assert ids == ["custom_1_abc"]


def test_custom_template_listing_missing_dir(client_api, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    assert client_api.get("/api/v1/pptx/templates/custom").json() == {"templates": []}


@pytest.mark.asyncio
async def test_stream_upload_error_maps_generate_from_file(client_api, monkeypatch):
    async def broken(*_args, **_kwargs):
        raise RuntimeError("disk")

    monkeypatch.setattr(pptx, "_stream_upload_to_path", broken)
    files = {"file": ("a.txt", b"data", "text/plain")}
    resp = client_api.post("/api/v1/pptx/generate_from_file", files=files)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_parse_error_maps_generate_from_file(client_api, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        pptx, "_parse_uploaded_document", AsyncMock(side_effect=RuntimeError("parse"))
    )
    files = {"file": ("a.txt", b"data", "text/plain")}
    resp = client_api.post("/api/v1/pptx/generate_from_file", files=files)
    assert resp.status_code == 500


@pytest.mark.asyncio
async def test_empty_parse_maps_generate_from_file(client_api, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    monkeypatch.setattr(
        pptx, "_parse_uploaded_document", AsyncMock(return_value="   ")
    )
    files = {"file": ("a.txt", b"data", "text/plain")}
    resp = client_api.post("/api/v1/pptx/generate_from_file", files=files)
    assert resp.status_code == 400


def test_generate_from_file_closure_paths(client_api, monkeypatch, tmp_path):
    import asyncio

    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", tmp_path / "out")
    (tmp_path / "out").mkdir()
    monkeypatch.setattr(
        pptx, "_parse_uploaded_document", AsyncMock(return_value="正文")
    )
    captured = {}

    async def create_task(task_type, user_id, func, params=None):
        captured["func"] = func
        return str(uuid.uuid4())

    monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
    monkeypatch.setattr(pptx.task_manager, "update_progress", AsyncMock())
    monkeypatch.setattr(
        pptx, "generate_ppt_outline",
        AsyncMock(return_value={"title": "T", "slides": [{"title": "x"}]}),
    )
    monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", AsyncMock())
    monkeypatch.setattr(pptx, "generate_html_ppt", AsyncMock())
    monkeypatch.setattr(pptx, "generate_markdown_ppt", AsyncMock())
    files = {"file": ("a.txt", b"data", "text/plain")}
    for fmt in ("pptx", "html", "markdown"):
        resp = client_api.post(
            "/api/v1/pptx/generate_from_file",
            files=files,
            data={"output_format": fmt, "extra_prompt": "补充"},
        )
        assert resp.status_code == 200
        assert asyncio.run(captured["func"]("child"))["ppt_id"] == "child"


def test_generate_from_file_closure_failure_and_cancel(client_api, monkeypatch, tmp_path):
    import asyncio

    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", tmp_path / "out")
    (tmp_path / "out").mkdir()
    monkeypatch.setattr(
        pptx, "_parse_uploaded_document", AsyncMock(return_value="正文")
    )
    captured = {}

    async def create_task(task_type, user_id, func, params=None):
        captured["func"] = func
        return str(uuid.uuid4())

    monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
    monkeypatch.setattr(pptx.task_manager, "update_progress", AsyncMock())
    monkeypatch.setattr(
        pptx, "generate_ppt_outline", AsyncMock(side_effect=RuntimeError("llm"))
    )
    resp = client_api.post(
        "/api/v1/pptx/generate_from_file",
        files={"file": ("a.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 200
    assert asyncio.run(captured["func"]("child")) is None

    async def cancelled(*_args, **_kwargs):
        raise asyncio.CancelledError()

    monkeypatch.setattr(pptx, "generate_ppt_outline", cancelled)
    resp = client_api.post(
        "/api/v1/pptx/generate_from_file",
        files={"file": ("a.txt", b"data", "text/plain")},
    )
    assert resp.status_code == 200
    assert asyncio.run(captured["func"]("child2")) is None


def test_upload_custom_template_errors(client_api, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
    resp = client_api.post(
        "/api/v1/pptx/templates/upload",
        files={"file": ("bad.txt", b"x", "text/plain")},
        data={"name": "n"},
    )
    assert resp.status_code == 400

    async def broken(*_args, **_kwargs):
        raise RuntimeError("disk")

    monkeypatch.setattr(pptx, "_stream_upload_to_path", broken)
    resp = client_api.post(
        "/api/v1/pptx/templates/upload",
        files={"file": ("ok.pptx", b"x", "application/octet-stream")},
        data={"name": "n"},
    )
    assert resp.status_code == 500


def test_upload_custom_template_parse_error_keeps_file(client_api, monkeypatch, tmp_path):
    monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)

    class Parser:
        def parse_template_file(self, _path):
            raise RuntimeError("parse")

    monkeypatch.setattr("app.utils.pptx.custom_template.CustomTemplateParser", Parser)
    resp = client_api.post(
        "/api/v1/pptx/templates/upload",
        files={"file": ("ok.pptx", b"x", "application/octet-stream")},
        data={"name": "n"},
    )
    assert resp.status_code == 200
    assert resp.json()["config"] is None


def test_render_default_minimal_unknown_theme(tmp_path):
    from pptx import Presentation

    prs = Presentation()
    style = pptx.PPTStyle("modern")
    data = {"slide_type": "other", "title": "题", "content": ["a"]}
    pptx._render_slide_default(prs, prs.slide_layouts[6], style, data, 1, 2)
    assert len(prs.slides) == 1
