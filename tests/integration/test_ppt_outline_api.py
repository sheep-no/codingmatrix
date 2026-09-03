import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.database import get_db
from app.main import app
from app.models.base import Base
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


@pytest.mark.asyncio
async def test_text_and_material_outline_inputs_share_approval_flow(db):
    async def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[verify_token] = lambda: {"sub": "1"}
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for payload in (
                {"topic": "季度业务汇报", "num_slides": 1},
                {"topic": "产品材料汇报", "material_file_ids": [101], "num_slides": 1},
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
    finally:
        app.dependency_overrides.clear()
