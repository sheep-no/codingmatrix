"""Endpoint and helper branch coverage for aiGeneratorPptx."""

import json
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1 import aiGeneratorPptx as pptx
from app.db.database import get_db
from app.main import app
from app.schema.ppt_outline import (
    AssetIntent,
    ContentBlock,
    OutlineDraft,
    OutlineSlide,
)
from app.utils.security import verify_token, verify_token_ws


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


def _task_response(task_id="t1"):
    return {
        "task_id": task_id,
        "task_type": "ppt_generation",
        "status": "pending",
        "created_at": "2026-01-01T00:00:00",
    }


def _quality_report():
    return SimpleNamespace(
        overall_score=1,
        slide_scores={},
        issues=[],
        reflow_attempts={},
        manual_review_slides=[],
    )


def _draft(status="draft"):
    return OutlineDraft(
        id="outline-1",
        user_id=USER_ID,
        version=1,
        status=status,
        title="标题",
        scenario="general",
        template_id="modern",
        slide_limit=10,
        slides=[
            OutlineSlide(
                id="s1",
                position=0,
                content_blocks=[ContentBlock(content="内容")],
                asset_intent=AssetIntent(keywords=["a"]),
            )
        ],
        created_at="2026-01-01T00:00:00",
    )


class TestOutlineEndpoints:
    def test_create_outline_ok(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx, "persist_create_ppt_outline", AsyncMock(return_value=_draft())
        )
        resp = client.post("/api/v1/pptx/outlines", json={"topic": "主题"})
        assert resp.status_code == 201

    @pytest.mark.parametrize(
        ("error", "status"),
        [
            (pptx.StateNotFoundError("x"), 404),
            (ValueError("bad"), 422),
            (pptx.LLMCallError("auth"), 401),
        ],
    )
    def test_create_outline_errors(self, client, fake_db, monkeypatch, error, status):
        monkeypatch.setattr(
            pptx, "persist_create_ppt_outline", AsyncMock(side_effect=error)
        )
        resp = client.post("/api/v1/pptx/outlines", json={"topic": "主题"})
        assert resp.status_code == status

    @pytest.mark.asyncio
    async def test_create_outline_sse_events(self, client, monkeypatch):
        async def ok_stream(*_args):
            yield {"type": "progress", "progress": 10}

        async def missing_stream(*_args):
            if False:
                yield {}
            raise pptx.StateNotFoundError("missing")

        async def value_stream(*_args):
            if False:
                yield {}
            raise ValueError("bad")

        async def llm_stream(*_args):
            if False:
                yield {}
            raise pptx.LLMCallError("auth")

        async def crash_stream(*_args):
            if False:
                yield {}
            raise RuntimeError("boom")

        for stream in (ok_stream, missing_stream, value_stream, llm_stream, crash_stream):
            monkeypatch.setattr(pptx, "persist_stream_ppt_outline", stream)
            response = client.post(
                "/api/v1/pptx/outlines",
                json={"topic": "主题"},
                headers={"accept": "text/event-stream"},
            )
            assert response.status_code == 200
            assert "data:" in response.text

    def test_get_update_delete_approve_outline(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx, "persist_get_ppt_outline", AsyncMock(return_value=_draft())
        )
        assert client.get("/api/v1/pptx/outlines/o1").status_code == 200
        monkeypatch.setattr(
            pptx, "persist_update_ppt_outline", AsyncMock(return_value=_draft())
        )
        assert client.patch("/api/v1/pptx/outlines/o1", json={"title": "新"}).status_code == 200
        monkeypatch.setattr(pptx, "persist_delete_ppt_outline", AsyncMock())
        assert client.delete("/api/v1/pptx/outlines/o1").status_code == 200
        monkeypatch.setattr(
            pptx, "persist_approve_ppt_outline", AsyncMock(return_value=_draft("approved"))
        )
        assert client.post("/api/v1/pptx/outlines/o1/approve").status_code == 200

    def test_outline_endpoint_error_mappings(self, client, fake_db, monkeypatch):
        for name, method, path, error, expected in (
            ("persist_get_ppt_outline", client.get, "/api/v1/pptx/outlines/o1", pptx.StateNotFoundError("x"), 404),
            ("persist_update_ppt_outline", client.patch, "/api/v1/pptx/outlines/o1", pptx.StateOwnershipError("x"), 404),
            ("persist_delete_ppt_outline", client.delete, "/api/v1/pptx/outlines/o1", pptx.StateNotFoundError("x"), 404),
            ("persist_approve_ppt_outline", client.post, "/api/v1/pptx/outlines/o1/approve", ValueError("bad"), 422),
        ):
            monkeypatch.setattr(pptx, name, AsyncMock(side_effect=error))
            kwargs = {"json": {"title": "x"}} if method.__name__ == "patch" else {}
            assert method(path, **kwargs).status_code == expected

    def test_generate_from_approved_outline(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx, "persist_get_ppt_outline", AsyncMock(return_value=_draft("approved"))
        )
        fake_generate = AsyncMock(return_value=_task_response("t1"))
        monkeypatch.setattr(pptx, "generate_ppt_task", fake_generate)
        resp = client.post("/api/v1/pptx/outlines/o1/generate", json={})
        assert resp.status_code == 200
        assert resp.json()["task_id"] == "t1"
        request = fake_generate.call_args.args[0]
        assert request.slide_count == 2

    def test_generate_from_unapproved_outline(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx, "persist_get_ppt_outline", AsyncMock(return_value=_draft("draft"))
        )
        resp = client.post("/api/v1/pptx/outlines/o1/generate", json={})
        assert resp.status_code == 409

    def test_regenerate_slide_success(self, client, fake_db, monkeypatch):
        revised = _draft("approved")
        monkeypatch.setattr(pptx, "revise_ppt_slide", AsyncMock(return_value=revised))
        monkeypatch.setattr(
            pptx, "generate_ppt_from_approved_outline",
            AsyncMock(return_value=_task_response("t1")),
        )
        body = {"outline_version": 1, "slide": _draft().slides[0].model_dump(mode="json")}
        resp = client.post("/api/v1/pptx/outlines/o1/slides/s1/regenerate", json=body)
        assert resp.status_code == 200

    def test_regenerate_slide_error_mappings(self, client, fake_db, monkeypatch):
        body = {"outline_version": 1, "slide": _draft().slides[0].model_dump(mode="json")}
        for error, status in (
            (pptx.StateNotFoundError("x"), 404),
            (ValueError("bad"), 422),
        ):
            monkeypatch.setattr(pptx, "revise_ppt_slide", AsyncMock(side_effect=error))
            resp = client.post("/api/v1/pptx/outlines/o1/slides/s1/regenerate", json=body)
            assert resp.status_code == status

    def test_regenerate_slide_integrity_conflict(self, client, fake_db, monkeypatch):
        from sqlalchemy.exc import IntegrityError

        monkeypatch.setattr(
            pptx, "revise_ppt_slide",
            AsyncMock(side_effect=IntegrityError("x", {}, Exception())),
        )
        body = {"outline_version": 1, "slide": _draft().slides[0].model_dump(mode="json")}
        resp = client.post("/api/v1/pptx/outlines/o1/slides/s1/regenerate", json=body)
        assert resp.status_code == 409
        fake_db.rollback.assert_awaited()

    def test_regenerate_slide_export_failure(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(pptx, "revise_ppt_slide", AsyncMock(return_value=_draft("approved")))
        monkeypatch.setattr(
            pptx, "generate_ppt_from_approved_outline",
            AsyncMock(side_effect=RuntimeError("export")),
        )
        body = {"outline_version": 1, "slide": _draft().slides[0].model_dump(mode="json")}
        resp = client.post("/api/v1/pptx/outlines/o1/slides/s1/regenerate", json=body)
        assert resp.status_code == 503

    def test_quality_report(self, client, fake_db, monkeypatch):
        report = SimpleNamespace(
            id="r1", task_id="t1", outline_id="o1", outline_version=1,
            quality_mode="standard", overall_score=90, slide_scores_json=[],
            issues_json=[], reflow_attempts_json=[], degraded_stage=None,
            status="completed",
        )
        monkeypatch.setattr(
            pptx, "persist_get_ppt_quality_report", AsyncMock(return_value=report)
        )
        resp = client.get("/api/v1/pptx/t1/quality-report")
        assert resp.status_code == 200
        assert resp.json()["overall_score"] == 90

    def test_quality_report_not_found(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx, "persist_get_ppt_quality_report",
            AsyncMock(side_effect=pptx.StateNotFoundError("x")),
        )
        assert client.get("/api/v1/pptx/t1/quality-report").status_code == 404


class TestTaskEndpoints:
    def _patch_task_creation(self, monkeypatch):
        captured = {}

        async def create_task(task_type, user_id, func, params=None):
            captured["func"] = func
            captured["task_type"] = task_type
            return str(uuid.uuid4())

        monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
        return captured

    def test_generate_task_pending_and_closure(self, client, fake_db, output, monkeypatch):
        captured = self._patch_task_creation(monkeypatch)

        async def outline(_req, user_id=None):
            return {"title": "标题", "slides": [{"title": "页", "content": ["a"]}]}

        async def render(filepath, *_args, **_kwargs):
            filepath.write_text("pptx")

        async def html(filepath, *_args):
            filepath.write_text("<html>")

        async def quality(slides, mode):
            return slides, {"score": 1}

        monkeypatch.setattr(pptx, "generate_ppt_outline", outline)
        monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", render)
        monkeypatch.setattr(pptx, "generate_html_ppt", html)
        monkeypatch.setattr(pptx, "run_quality_pipeline", quality)
        monkeypatch.setattr(pptx, "serialize_quality_report", lambda report: {})
        monkeypatch.setattr(pptx, "save_ppt_stage_checkpoint", AsyncMock())
        monkeypatch.setattr(pptx, "persist_ppt_generation_result", AsyncMock())

        resp = client.post(
            "/api/v1/pptx/generate_task",
            json={"prompt": "生成季度复盘", "slide_count": 5},
        )
        assert resp.status_code == 200
        result = __import__("asyncio").run(captured["func"]("t1"))
        assert result["ppt_id"] == "t1"
        assert (Path(output) / "t1.pptx").exists()

    def test_generate_task_uses_approved_outline_and_pdf(self, client, fake_db, output, monkeypatch):
        captured = self._patch_task_creation(monkeypatch)

        async def render(filepath, *_args, **_kwargs):
            filepath.write_text("pptx")

        monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", render)
        monkeypatch.setattr(pptx, "run_quality_pipeline", AsyncMock(return_value=([], {})))
        monkeypatch.setattr(pptx, "serialize_quality_report", lambda report: {})
        monkeypatch.setattr(
            "app.services.ppt_quality_orchestrator.review_rendered_deck", AsyncMock()
        )
        monkeypatch.setattr(pptx, "save_ppt_stage_checkpoint", AsyncMock())
        monkeypatch.setattr(pptx, "persist_ppt_generation_result", AsyncMock())
        monkeypatch.setattr(pptx, "_convert_pptx_to_pdf", AsyncMock())
        resp = client.post(
            "/api/v1/pptx/generate_task",
            json={
                "prompt": "季度复盘",
                "slide_count": 5,
                "output_format": "pdf",
                "options": {
                    "approved_outline": {"title": "已批准", "slides": []},
                    "quality_mode": "refined",
                },
            },
        )
        assert resp.status_code == 200
        result = __import__("asyncio").run(captured["func"]("t2"))
        assert result["preview_url"] is None

    def test_generate_task_failure_and_cancel_paths(self, client, fake_db, output, monkeypatch):
        captured = self._patch_task_creation(monkeypatch)
        monkeypatch.setattr(
            pptx, "generate_ppt_outline", AsyncMock(side_effect=RuntimeError("llm down"))
        )
        monkeypatch.setattr(pptx, "save_ppt_stage_checkpoint", AsyncMock())
        resp = client.post(
            "/api/v1/pptx/generate_task", json={"prompt": "失败", "slide_count": 5}
        )
        assert resp.status_code == 200
        assert __import__("asyncio").run(captured["func"]("t3")) is None

    def test_generate_task_celery_dispatch(self, client, fake_db, output, monkeypatch):
        monkeypatch.setenv("PPT_USE_CELERY", "true")
        fake_record = SimpleNamespace(
            outline_id=None, outline_version=None, quality_mode=None
        )
        fake_db.scalar.return_value = fake_record
        monkeypatch.setattr(
            "app.services.ppt_dispatch_service.dispatch_ppt_to_celery",
            AsyncMock(return_value=("t1", "c1")),
        )
        resp = client.post(
            "/api/v1/pptx/generate_task",
            json={"prompt": "celery", "slide_count": 5, "options": {"outline_id": "o1", "outline_version": 2}},
        )
        assert resp.status_code == 200
        assert resp.json()["celery_task_id"] == "c1"
        fake_db.commit.assert_awaited()

    def test_generate_task_records_outline_metadata(self, client, fake_db, output, monkeypatch):
        self._patch_task_creation(monkeypatch)
        fake_record = SimpleNamespace(
            outline_id=None, outline_version=None, quality_mode=None
        )
        fake_db.scalar.return_value = fake_record
        resp = client.post(
            "/api/v1/pptx/generate_task",
            json={
                "prompt": "普通",
                "slide_count": 5,
                "options": {"outline_id": "o1", "outline_version": 3, "quality_mode": "refined"},
            },
        )
        assert resp.status_code == 200
        assert fake_record.outline_id == "o1"
        fake_db.commit.assert_awaited()

    def test_sync_generate_formats(self, client, output, monkeypatch):
        monkeypatch.setattr(
            pptx, "generate_ppt_outline",
            AsyncMock(return_value={"title": "T", "slides": [{"title": "x"}]}),
        )
        monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", AsyncMock())
        monkeypatch.setattr(pptx, "generate_html_ppt", AsyncMock())
        monkeypatch.setattr(pptx, "generate_markdown_ppt", AsyncMock())
        for fmt in ("pptx", "html", "markdown"):
            resp = client.post(
                "/api/v1/pptx/generate",
                json={"prompt": "同步", "slide_count": 5, "output_format": fmt},
            )
            assert resp.status_code == 200
            assert resp.json()["output_format"] == fmt

    def test_sync_generate_failure(self, client, output, monkeypatch):
        monkeypatch.setattr(
            pptx, "generate_ppt_outline", AsyncMock(side_effect=RuntimeError("boom"))
        )
        resp = client.post(
            "/api/v1/pptx/generate", json={"prompt": "同步", "slide_count": 5}
        )
        assert resp.status_code == 500

    def test_download_preview_slides(self, client, output):
        ppt_id = str(uuid.uuid4())
        _owner(output, ppt_id)
        (output / f"{ppt_id}.md").write_text("# 标题")
        response = client.get(f"/api/v1/pptx/download/{ppt_id}?format=markdown")
        assert response.status_code == 200
        assert "text/markdown" in response.headers["content-type"]

        response = client.get(f"/api/v1/pptx/preview/{ppt_id}?format=markdown")
        assert response.status_code == 200
        assert "<pre>" in response.text

        (output / f"{ppt_id}.html").write_text("<html>ok</html>")
        response = client.get(f"/api/v1/pptx/preview/{ppt_id}?format=html")
        assert response.status_code == 200
        assert response.text == "<html>ok</html>"

        (output / f"{ppt_id}.pptx").write_bytes(b"pptx")
        response = client.get(f"/api/v1/pptx/preview/{ppt_id}?format=pptx")
        assert response.status_code == 200
        assert "slides-container" in response.text

        (output / f"{ppt_id}_slides.json").write_text(
            json.dumps({"slides": [{"title": "x"}]})
        )
        response = client.get(f"/api/v1/pptx/{ppt_id}/slides")
        assert response.status_code == 200
        assert response.json()["slides"][0]["title"] == "x"

    def test_download_preview_error_paths(self, client, output):
        ppt_id = str(uuid.uuid4())
        _owner(output, ppt_id)
        assert client.get(f"/api/v1/pptx/download/{ppt_id}").status_code == 404
        assert client.get(f"/api/v1/pptx/download/{ppt_id}?format=exe").status_code == 400
        assert client.get(f"/api/v1/pptx/preview/{ppt_id}?format=exe").status_code == 400
        assert client.get(f"/api/v1/pptx/preview/{ppt_id}").status_code == 404
        assert client.get(f"/api/v1/pptx/{ppt_id}/slides").status_code == 404

    def test_slides_legacy_list_format(self, client, output):
        ppt_id = str(uuid.uuid4())
        _owner(output, ppt_id)
        (output / f"{ppt_id}_slides.json").write_text(json.dumps([{"title": "旧"}]))
        response = client.get(f"/api/v1/pptx/{ppt_id}/slides")
        assert response.json()["slides"][0]["title"] == "旧"


class TestCancelEndpoint:
    def test_cancel_running_by_owner(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx.task_manager, "get_task_info_async",
            AsyncMock(return_value={"user_id": USER_ID, "status": "running"}),
        )
        monkeypatch.setattr(pptx.task_manager, "cancel_task", AsyncMock(return_value=True))
        resp = client.delete(f"/api/v1/pptx/{uuid.uuid4()}/cancel")
        assert resp.json()["status"] == "cancelled"

    def test_cancel_forbidden_and_finished(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx.task_manager, "get_task_info_async",
            AsyncMock(return_value={"user_id": "2", "status": "running"}),
        )
        assert client.delete(f"/api/v1/pptx/{uuid.uuid4()}/cancel").status_code == 403
        monkeypatch.setattr(
            pptx.task_manager, "get_task_info_async",
            AsyncMock(return_value={"user_id": USER_ID, "status": "success"}),
        )
        assert client.delete(f"/api/v1/pptx/{uuid.uuid4()}/cancel").json()["status"] == "already_finished"

    def test_cancel_not_running(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx.task_manager, "get_task_info_async",
            AsyncMock(return_value={"user_id": USER_ID, "status": "running"}),
        )
        monkeypatch.setattr(pptx.task_manager, "cancel_task", AsyncMock(return_value=False))
        assert client.delete(f"/api/v1/pptx/{uuid.uuid4()}/cancel").json()["status"] == "not_running"

    def test_cancel_sql_record_paths(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(pptx.task_manager, "get_task_info_async", AsyncMock(return_value=None))
        monkeypatch.setattr(
            pptx, "get_owned_task",
            AsyncMock(return_value=SimpleNamespace(status="running", celery_task_id="c1", progress=10)),
        )
        monkeypatch.setattr(pptx, "transition_task", AsyncMock())
        monkeypatch.setattr(pptx.celery_app.control, "revoke", MagicMock())
        resp = client.delete(f"/api/v1/pptx/{uuid.uuid4()}/cancel")
        assert resp.json()["status"] == "cancelled"

    def test_cancel_sql_record_finished(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(pptx.task_manager, "get_task_info_async", AsyncMock(return_value=None))
        monkeypatch.setattr(
            pptx, "get_owned_task",
            AsyncMock(return_value=SimpleNamespace(status="failed", celery_task_id=None, progress=0)),
        )
        resp = client.delete(f"/api/v1/pptx/{uuid.uuid4()}/cancel")
        assert resp.json()["status"] == "already_finished"

    def test_cancel_sql_record_not_running(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(pptx.task_manager, "get_task_info_async", AsyncMock(return_value=None))
        monkeypatch.setattr(
            pptx, "get_owned_task",
            AsyncMock(return_value=SimpleNamespace(status="running", celery_task_id=None, progress=0)),
        )
        resp = client.delete(f"/api/v1/pptx/{uuid.uuid4()}/cancel")
        assert resp.json()["status"] == "not_running"

    def test_cancel_missing(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(pptx.task_manager, "get_task_info_async", AsyncMock(return_value=None))
        monkeypatch.setattr(pptx, "get_owned_task", AsyncMock(side_effect=Exception("missing")))
        assert client.delete(f"/api/v1/pptx/{uuid.uuid4()}/cancel").status_code == 404


class TestUpdateEndpoint:
    def test_update_task_closure_all_formats(self, client, fake_db, output, monkeypatch):
        task_id = str(uuid.uuid4())
        _owner(output, task_id)
        (output / f"{task_id}_slides.json").write_text(
            json.dumps({"user_id": USER_ID, "slides": [{"title": "旧"}]})
        )
        captured = {}

        async def create_task(task_type, user_id, func, params=None):
            captured["func"] = func
            return str(uuid.uuid4())

        monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
        monkeypatch.setattr(
            pptx, "generate_ppt_outline",
            AsyncMock(return_value={"title": "新", "slides": [{"title": "新页"}]}),
        )
        monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", AsyncMock())
        monkeypatch.setattr(pptx, "generate_html_ppt", AsyncMock())
        monkeypatch.setattr(pptx, "generate_markdown_ppt", AsyncMock())

        for fmt in ("pptx", "html", "markdown"):
            resp = client.post(
                f"/api/v1/pptx/{task_id}/update",
                json={"prompt": "增量", "slide_count": 5, "output_format": fmt},
            )
            assert resp.status_code == 200
            result = __import__("asyncio").run(captured["func"](task_id))
            assert result["ppt_id"] == task_id
            assert result["preview_url"] is not None

    def test_update_task_empty_outline(self, client, fake_db, output, monkeypatch):
        task_id = str(uuid.uuid4())
        _owner(output, task_id)
        (output / f"{task_id}_slides.json").write_text(json.dumps([]))
        captured = {}

        async def create_task(task_type, user_id, func, params=None):
            captured["func"] = func
            return str(uuid.uuid4())

        monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
        monkeypatch.setattr(
            pptx, "generate_ppt_outline",
            AsyncMock(return_value={"title": "新", "slides": []}),
        )
        resp = client.post(
            f"/api/v1/pptx/{task_id}/update", json={"prompt": "增量", "slide_count": 5}
        )
        assert resp.status_code == 200
        assert __import__("asyncio").run(captured["func"](task_id)) is None

    def test_update_task_foreign_owner(self, client, fake_db, output):
        task_id = str(uuid.uuid4())
        _owner(output, task_id)
        (output / f"{task_id}_slides.json").write_text(
            json.dumps({"user_id": "2", "slides": []})
        )
        resp = client.post(
            f"/api/v1/pptx/{task_id}/update", json={"prompt": "增量", "slide_count": 5}
        )
        assert resp.status_code == 403

    def test_update_task_failure(self, client, fake_db, output, monkeypatch):
        task_id = str(uuid.uuid4())
        _owner(output, task_id)
        (output / f"{task_id}_slides.json").write_text(json.dumps({"slides": []}))
        captured = {}

        async def create_task(task_type, user_id, func, params=None):
            captured["func"] = func
            return str(uuid.uuid4())

        monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
        monkeypatch.setattr(
            pptx, "generate_ppt_outline", AsyncMock(side_effect=RuntimeError("llm"))
        )
        client.post(
            f"/api/v1/pptx/{task_id}/update", json={"prompt": "增量", "slide_count": 5}
        )
        assert __import__("asyncio").run(captured["func"](task_id)) is None


class TestTemplatesAndUploads:
    def test_template_preview_validation(self, client):
        assert client.get("/api/v1/pptx/templates/business/preview/0").status_code == 422
        assert client.get("/api/v1/pptx/templates/business/preview/4").status_code == 422

    def test_template_preview_missing_template(self, client):
        assert client.get("/api/v1/pptx/templates/zzz/preview/1").status_code == 404

    def test_template_preview_missing_file(self, client, monkeypatch):
        monkeypatch.setattr(
            "app.utils.pptx.templates.manager.TemplateManager.select_template",
            lambda self, value: value,
        )
        monkeypatch.setattr(
            "app.services.ppt_template_samples.ensure_template_sample", AsyncMock()
        )
        monkeypatch.setattr(
            "app.services.ppt_template_samples._paths",
            lambda _id: {"png_dir": Path("/nonexistent")},
        )
        assert client.get("/api/v1/pptx/templates/business/preview/1").status_code == 404

    def test_template_preview_serves_png(self, client, tmp_path, monkeypatch):
        png = tmp_path / "slide-1.png"
        png.write_bytes(b"png")
        monkeypatch.setattr(
            "app.utils.pptx.templates.manager.TemplateManager.select_template",
            lambda self, value: value,
        )
        monkeypatch.setattr(
            "app.services.ppt_template_samples.ensure_template_sample", AsyncMock()
        )
        monkeypatch.setattr(
            "app.services.ppt_template_samples._paths",
            lambda _id: {"png_dir": tmp_path},
        )
        response = client.get("/api/v1/pptx/templates/business/preview/1")
        assert response.status_code == 200
        assert response.headers["content-type"] == "image/png"

    def test_templates_sample_failure_and_category(self, client, monkeypatch):
        async def boom(_id):
            raise RuntimeError("render")

        monkeypatch.setattr("app.services.ppt_template_samples.ensure_template_sample", boom)
        response = client.get("/api/v1/pptx/templates?category=business")
        assert response.status_code == 200
        assert all(t["sample"]["status"] == "unavailable" for t in response.json()["templates"])

    def test_templates_scenario_recommendation(self, client):
        response = client.get("/api/v1/pptx/templates?scenario=education")
        assert response.status_code == 200
        assert "templates" in response.json()

    def test_history_legacy_and_bad_records(self, client, output):
        owned = str(uuid.uuid4())
        _owner(output, owned)
        (output / f"{owned}_slides.json").write_text(json.dumps([{"title": "旧标题"}]))
        bad = str(uuid.uuid4())
        _owner(output, bad)
        (output / f"{bad}_slides.json").write_text("{not json")
        orphan = str(uuid.uuid4())
        (output / f"{orphan}_slides.json").write_text(json.dumps([]))
        foreign = str(uuid.uuid4())
        _owner(output, foreign, "2")
        (output / f"{foreign}_slides.json").write_text(json.dumps({"slides": []}))
        response = client.get("/api/v1/pptx/history")
        assert response.status_code == 200
        assert response.json()["total"] == 1

    def test_history_dict_and_empty_slides(self, client, output):
        first = str(uuid.uuid4())
        _owner(output, first)
        (output / f"{first}_slides.json").write_text(
            json.dumps({"user_id": USER_ID, "title": "标题", "slides": []})
        )
        (output / f"{first}.pptx").write_bytes(b"x")
        second = str(uuid.uuid4())
        _owner(output, second)
        (output / f"{second}_slides.json").write_text(
            json.dumps({"user_id": USER_ID, "slides": []})
        )
        response = client.get("/api/v1/pptx/history")
        records = response.json()["records"]
        assert {r["status"] for r in records} == {"completed", "failed"}

    def test_output_dir_missing(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr(pptx, "PPT_OUTPUT_DIR", tmp_path / "missing")
        assert client.get("/api/v1/pptx/history").json()["total"] == 0
        assert client.get("/api/v1/pptx/history/stats").json()["total"] == 0

    def test_delete_history_errors_and_cleanup(self, client, output):
        task_id = str(uuid.uuid4())
        _owner(output, task_id)
        (output / f"{task_id}_slides.json").write_text("{bad json")
        for ext in ("pptx", "html", "md", "pdf"):
            (output / f"{task_id}.{ext}").write_text("x")
        response = client.delete(f"/api/v1/pptx/history/{task_id}")
        assert response.status_code == 200
        assert not (output / f"{task_id}.pdf").exists()

        foreign = str(uuid.uuid4())
        _owner(output, foreign)
        (output / f"{foreign}_slides.json").write_text(
            json.dumps({"user_id": "2"})
        )
        assert client.delete(f"/api/v1/pptx/history/{foreign}").status_code == 403

    def test_stats_ignores_bad_owner_files(self, client, output):
        (_owner_dir := output / ".owners").mkdir(exist_ok=True)
        (_owner_dir / "broken.json").write_text("{bad")
        ppt_id = str(uuid.uuid4())
        (_owner_dir / f"{ppt_id}.json").write_text(json.dumps({"user_id": USER_ID}))
        (output / f"{ppt_id}_slides.json").write_text("{}")
        response = client.get("/api/v1/pptx/history/stats")
        assert response.json()["total"] == 1

    def test_prevent_text_overflow_warns(self, monkeypatch):
        layout = SimpleNamespace(
            needs_overflow_warning=True,
            overflow_message="too long",
            lines=["a"],
        )
        warnings = []
        monkeypatch.setattr(
            pptx, "prevent_text_overflow_v2", lambda *a, **k: layout
        )
        monkeypatch.setattr(pptx.logger, "warning", warnings.append)
        assert pptx.prevent_text_overflow("x") == ["a"]
        assert warnings

    def test_generate_from_text_task_success_and_failure(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx, "persist_create_ppt_outline", AsyncMock(return_value=_draft())
        )
        monkeypatch.setattr(
            pptx, "persist_approve_ppt_outline", AsyncMock(return_value=_draft("approved"))
        )
        monkeypatch.setattr(
            pptx, "generate_ppt_from_approved_outline",
            AsyncMock(return_value=_task_response("t1")),
        )
        response = client.post("/api/v1/generate-from-text", json={"topic": "主题"})
        assert response.status_code == 200

        monkeypatch.setattr(
            pptx, "persist_create_ppt_outline", AsyncMock(side_effect=RuntimeError("x"))
        )
        response = client.post("/api/v1/generate-from-text", json={"topic": "主题"})
        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_stream_upload_limit(self):
        class Upload:
            def __init__(self):
                self.calls = 0

            async def read(self, _size):
                self.calls += 1
                return b"x" * 8 if self.calls == 1 else b""

        with pytest.raises(HTTPException):
            await pptx._stream_upload_to_path(Upload(), Path("/tmp/opencode/ppt-upload-test.bin"), 4)

    def test_generate_from_file_success(self, client, fake_db, output, monkeypatch):
        import asyncio

        monkeypatch.setattr(
            pptx, "_parse_uploaded_document", AsyncMock(return_value="文件正文")
        )
        captured = {}

        async def create_task(task_type, user_id, func, params=None):
            captured["func"] = func
            return str(uuid.uuid4())

        monkeypatch.setattr(pptx.task_manager, "create_task", create_task)
        monkeypatch.setattr(
            pptx, "generate_ppt_outline",
            AsyncMock(return_value={"title": "T", "slides": [{"title": "x"}]}),
        )
        monkeypatch.setattr(pptx, "generate_pptx_file_enhanced", AsyncMock())
        monkeypatch.setattr(pptx, "generate_html_ppt", AsyncMock())
        monkeypatch.setattr(pptx, "generate_markdown_ppt", AsyncMock())
        response = client.post(
            "/api/v1/pptx/generate_from_file",
            files={"file": ("notes.txt", b"hello", "text/plain")},
            data={"template": "modern", "slide_count": "5", "output_format": "html"},
        )
        assert response.status_code == 200
        result = asyncio.run(captured["func"]("file-task"))
        assert result["source_file"] == "notes.txt"

    def test_generate_from_file_validation_and_parse_errors(self, client, fake_db, monkeypatch):
        response = client.post(
            "/api/v1/pptx/generate_from_file",
            files={"file": ("bad.exe", b"x", "application/octet-stream")},
            data={"slide_count": "5"},
        )
        assert response.status_code == 400

        monkeypatch.setattr(pptx, "_parse_uploaded_document", AsyncMock(return_value="  "))
        response = client.post(
            "/api/v1/pptx/generate_from_file",
            files={"file": ("notes.txt", b"x", "text/plain")},
            data={"slide_count": "5"},
        )
        assert response.status_code == 400

        monkeypatch.setattr(
            pptx, "_parse_uploaded_document", AsyncMock(side_effect=RuntimeError("x"))
        )
        response = client.post(
            "/api/v1/pptx/generate_from_file",
            files={"file": ("notes.txt", b"x", "text/plain")},
            data={"slide_count": "5"},
        )
        assert response.status_code == 500

    def test_generate_from_file_stream_failure(self, client, fake_db, monkeypatch):
        monkeypatch.setattr(
            pptx, "_stream_upload_to_path", AsyncMock(side_effect=RuntimeError("disk"))
        )
        response = client.post(
            "/api/v1/pptx/generate_from_file",
            files={"file": ("notes.txt", b"x", "text/plain")},
            data={"slide_count": "5"},
        )
        assert response.status_code == 500

    def test_upload_custom_template_parse_failure(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
        response = client.post(
            "/api/v1/pptx/templates/upload",
            files={"file": ("tpl.pptx", b"not-a-pptx", "application/octet-stream")},
            data={"name": "模板"},
        )
        assert response.status_code == 200
        assert response.json()["config"] is None

    def test_upload_custom_template_wrong_type(self, client):
        response = client.post(
            "/api/v1/pptx/templates/upload",
            files={"file": ("tpl.txt", b"x", "text/plain")},
            data={"name": "模板"},
        )
        assert response.status_code == 400

    def test_custom_template_listing(self, client, monkeypatch, tmp_path):
        monkeypatch.setattr(pptx, "BASE_DIR", tmp_path)
        directory = tmp_path / "configs" / "ppt" / "custom_templates"
        directory.mkdir(parents=True)
        (directory / f"custom_{USER_ID}_abc.json").write_text(json.dumps({"name": "我的"}))
        (directory / "custom_2_other.json").write_text(json.dumps({"name": "别人"}))
        (directory / "broken.json").write_text("{bad")
        response = client.get("/api/v1/pptx/templates/custom")
        assert response.status_code == 200
        assert len(response.json()["templates"]) == 1

    def test_download_pdf_paths(self, client, output, monkeypatch):
        ppt_id = str(uuid.uuid4())
        _owner(output, ppt_id)
        assert client.get(f"/api/v1/pptx/download/{ppt_id}/pdf").status_code == 404

        (output / f"{ppt_id}.pptx").write_bytes(b"x")

        async def missing(_src, _dst):
            raise FileNotFoundError

        monkeypatch.setattr(pptx, "_convert_pptx_to_pdf", missing)
        assert client.get(f"/api/v1/pptx/download/{ppt_id}/pdf").status_code == 501

        async def fail(_src, _dst):
            raise RuntimeError("boom")

        monkeypatch.setattr(pptx, "_convert_pptx_to_pdf", fail)
        assert client.get(f"/api/v1/pptx/download/{ppt_id}/pdf").status_code == 500

        async def no_file(_src, _dst):
            return None

        monkeypatch.setattr(pptx, "_convert_pptx_to_pdf", no_file)
        assert client.get(f"/api/v1/pptx/download/{ppt_id}/pdf").status_code == 500

        async def creates(_src, dst):
            dst.write_text("pdf")

        monkeypatch.setattr(pptx, "_convert_pptx_to_pdf", creates)
        response = client.get(f"/api/v1/pptx/download/{ppt_id}/pdf")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    @pytest.mark.asyncio
    async def test_convert_pptx_to_pdf_uses_cache_and_subprocess(self, tmp_path, monkeypatch):
        src = tmp_path / "deck.pptx"
        dst = tmp_path / "deck.pdf"
        src.write_bytes(b"x")
        dst.write_bytes(b"pdf")
        await pptx._convert_pptx_to_pdf(src, dst)

        dst.unlink()
        calls = {}

        def fake_run(args, **kwargs):
            calls["args"] = args
            src.with_suffix(".pdf").write_bytes(b"generated")
            return SimpleNamespace(returncode=0, stderr="")

        monkeypatch.setattr("subprocess.run", fake_run)
        await pptx._convert_pptx_to_pdf(src, dst)
        assert dst.exists()
        assert calls["args"][0] == "libreoffice"

    @pytest.mark.asyncio
    async def test_convert_pptx_to_pdf_failures(self, tmp_path, monkeypatch):
        src = tmp_path / "deck.pptx"
        dst = tmp_path / "deck.pdf"
        src.write_bytes(b"x")

        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=1, stderr="bad"),
        )
        with pytest.raises(RuntimeError):
            await pptx._convert_pptx_to_pdf(src, dst)

        monkeypatch.setattr(
            "subprocess.run",
            lambda *a, **k: SimpleNamespace(returncode=0, stderr=""),
        )
        with pytest.raises(RuntimeError):
            await pptx._convert_pptx_to_pdf(src, dst)
