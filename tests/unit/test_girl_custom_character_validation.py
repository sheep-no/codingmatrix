"""自定义角色创建需校验输入，非法值返回 400 而非 500（GIR3）。

原实现直接 `int(float(body.get("temperature", 0.8)) * 100)` 与
`int(body.get("max_tokens", 180))`，非数字输入抛 ValueError/TypeError → 500；
model 也无白名单。
"""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.v1.GirlAi import create_custom_character
from app.models.chat_history import CustomCharacter


@pytest.fixture
async def session():
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(CustomCharacter.__table__.create)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as db:
        yield db
    await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"name": "x", "temperature": "hot"},
        {"name": "x", "temperature": 5.0},
        {"name": "x", "max_tokens": "many"},
        {"name": "x", "max_tokens": 99999},
        {"name": "x", "model": "not-a-real-model"},
    ],
)
async def test_invalid_input_returns_400(session, payload):
    with pytest.raises(HTTPException) as exc:
        await create_custom_character(
            body=payload, token={"sub": "1"}, db=session
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_valid_input_creates_character(session):
    result = await create_custom_character(
        body={"name": "小助手", "temperature": 0.5, "max_tokens": 200},
        token={"sub": "1"},
        db=session,
    )

    assert result["message"] == "角色创建成功"
