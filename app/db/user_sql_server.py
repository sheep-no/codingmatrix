from typing import Optional

from pydantic import EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.models.user import User


async def get_user_by_email(db: AsyncSession, email: EmailStr) -> Optional[User]:
    res = await db.execute(select(User).where(User.email == email)
                           .options(selectinload(User.permission)))
    return res.scalar_one_or_none()


async def check_email_exists(db: AsyncSession, email: EmailStr) -> bool:
    result = await db.execute(
        select(User.id).where(User.email == email).limit(1)
    )
    return result.scalar_one_or_none() is not None
