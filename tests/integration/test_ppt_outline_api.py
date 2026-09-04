import pytest
from datetime import datetime
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.main import app
from app.models.base import Base
from app.models.file import File
from app.schema.task_schema import TaskResponse
from app.utils.security import verify_token


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
async def test_text_and_material_outline_inputs_share_approval_flow(db, tmp_path):
    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[verify_token] = lambda: {"sub": "1"}
    try:
        material_path = tmp_path / "product-brief.txt"
        material_path.write_text("材料结论：试点转化率达到 35%。", encoding="utf-8")
        material = File(
            filename="product-brief.txt",
            file_path=str(material_path),
            file_size=material_path.stat().st_size,
            content_type="text/plain",
            user_id=1,
        )
        db.add(material)
        await db.commit()
        await db.refresh(material)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for payload in (
                {"topic": "季度业务汇报", "num_slides": 1},
                {"topic": "产品材料汇报", "material_file_ids": [material.id], "num_slides": 1},
            ):
                response = await client.post("/api/v1/pptx/outlines", json=payload)
                assert response.status_code == 201
                outline = response.json()
                slide = outline["slides"][0]
                slide.update({"title": "核心结论", "key_message": "业务持续增长"})

                update = await client.patch(
                    f"/api/v1/pptx/outlines/{outline['id']}",
                    json={"slides": [slide]},
                )
                assert update.status_code == 200
                approved = await client.post(f"/api/v1/pptx/outlines/{outline['id']}/approve")
                assert approved.status_code == 200
                assert approved.json()["status"] == "approved"

            material_outline = await client.post(
                "/api/v1/pptx/outlines",
                json={"topic": "材料复盘", "material_file_ids": [material.id], "num_slides": 1},
            )
            assert material_outline.status_code == 201
            material_slide = material_outline.json()["slides"][0]
            assert "试点转化率达到 35%" in material_slide["content_blocks"][0]["content"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generate_uses_requested_approved_outline_version(db, monkeypatch):
    captured = {}

    async def override_db():
        yield db

    async def fake_generate_task(req, token, db):
        captured.update(req.options)
        return TaskResponse(
            task_id="task-versioned",
            task_type="ppt_generation",
            status="pending",
            created_at=datetime.utcnow().isoformat(),
        )

    monkeypatch.setattr("app.api.v1.aiGeneratorPptx.generate_ppt_task", fake_generate_task)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[verify_token] = lambda: {"sub": "1"}
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            created = (await client.post(
                "/api/v1/pptx/outlines", json={"topic": "版本化汇报", "num_slides": 1}
            )).json()
            approved = (await client.post(f"/api/v1/pptx/outlines/{created['id']}/approve")).json()
            update = await client.patch(
                f"/api/v1/pptx/outlines/{created['id']}", json={"title": "尚未批准的新版本"}
            )
            assert update.json()["version"] == 2

            generated = await client.post(
                f"/api/v1/pptx/outlines/{created['id']}/generate",
                json={"quality_mode": "standard", "outline_version": approved["version"]},
            )

            assert generated.status_code == 200
            assert captured["outline_version"] == 1
            assert captured["approved_outline"]["title"] == "版本化汇报"
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generate_text_compatibility_endpoint_persists_editable_draft(db):
    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[verify_token] = lambda: {"sub": "1"}
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/generate-text",
                json={"topic": "兼容入口汇报", "num_slides": 2},
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["outline_id"]
            assert payload["outline_version"] == 1
            assert payload["status"] == "draft"

            persisted = await client.get(f"/api/v1/pptx/outlines/{payload['outline_id']}")
            assert persisted.status_code == 200
            assert persisted.json()["title"] == payload["title"]
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_generate_from_text_maps_to_approved_outline_task(db, monkeypatch):
    captured = {}

    async def override_db():
        yield db

    async def fake_generate_task(req, token, db):
        captured.update(req.options)
        return TaskResponse(
            task_id="task-legacy",
            task_type="ppt_generation",
            status="pending",
            created_at=datetime.utcnow().isoformat(),
        )

    monkeypatch.setattr("app.api.v1.aiGeneratorPptx.generate_ppt_task", fake_generate_task)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[verify_token] = lambda: {"sub": "1"}
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            generated = await client.post(
                "/api/v1/generate-from-text",
                json={"topic": "旧入口汇报", "num_slides": 2},
            )
            assert generated.status_code == 200
            assert captured["outline_version"] == 1
            assert captured["approved_outline"]["status"] == "approved"

            outline_id = captured["outline_id"]
            deleted = await client.delete(f"/api/v1/pptx/outlines/{outline_id}")
            assert deleted.status_code == 200
            assert deleted.json() == {"deleted": True}
            assert (await client.get(f"/api/v1/pptx/outlines/{outline_id}")).status_code == 404
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_template_recommendations_include_scenario_and_color_preview():
    app.dependency_overrides[verify_token] = lambda: {"sub": "1"}
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/pptx/templates",
                params={"scenario": "education"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["scenario"] == "education"
        assert len(payload["candidates"]) >= 3
        assert payload["candidates"][0]["id"] == "education"
        assert payload["candidates"][0]["preview"]["background"].startswith("#")
    finally:
        app.dependency_overrides.clear()
