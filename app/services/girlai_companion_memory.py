"""Consent-aware persistence for GirlAI companion memories."""

from datetime import datetime
from typing import Iterable

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat_history import UserPreference
from app.schema.girl_companion import MemoryCandidate


class CompanionMemoryNotFoundError(LookupError):
    """Raised when a memory is absent or owned by another user."""


class CompanionMemoryStateError(ValueError):
    """Raised when a memory transition is invalid."""


class CompanionMemoryService:
    """Manage candidate, confirmed and deleted companion memories."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_candidates(
        self,
        user_id: int,
        candidates: Iterable[MemoryCandidate],
    ) -> list[UserPreference]:
        created: list[UserPreference] = []
        seen_keys: set[str] = set()
        for candidate in candidates:
            if candidate.key in seen_keys:
                continue
            seen_keys.add(candidate.key)
            result = await self.db.execute(
                select(UserPreference).where(
                    and_(
                        UserPreference.user_id == user_id,
                        UserPreference.preference_key == candidate.key,
                        UserPreference.status != "deleted",
                    )
                )
            )
            existing_records = list(result.scalars().all())
            existing = next(
                (record for record in existing_records if record.status == "confirmed"),
                existing_records[0] if existing_records else None,
            )
            if existing and existing.status == "confirmed":
                continue
            confidence = round(candidate.confidence * 100)
            if existing:
                existing.preference_value = candidate.value
                existing.confidence = confidence
                existing.source = candidate.source[:20]
                existing.status = "candidate"
                existing.consent_source = "system_derived"
                existing.visibility = "conversation_only"
                existing.updated_at = datetime.utcnow()
                created.append(existing)
                continue
            memory = UserPreference(
                user_id=user_id,
                preference_key=candidate.key,
                preference_value=candidate.value,
                confidence=confidence,
                source=candidate.source[:20],
                status="candidate",
                consent_source="system_derived",
                visibility="conversation_only",
            )
            self.db.add(memory)
            created.append(memory)
        await self.db.flush()
        return created

    async def list_memories(
        self,
        user_id: int,
        *,
        limit: int = 20,
        offset: int = 0,
        status: str | None = None,
    ) -> tuple[list[UserPreference], int]:
        filters = [UserPreference.user_id == user_id, UserPreference.status != "deleted"]
        if status:
            filters.append(UserPreference.status == status)
        total_result = await self.db.execute(
            select(func.count(UserPreference.id)).where(and_(*filters))
        )
        result = await self.db.execute(
            select(UserPreference)
            .where(and_(*filters))
            .order_by(UserPreference.updated_at.desc(), UserPreference.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), int(total_result.scalar_one())

    async def confirm(
        self,
        user_id: int,
        memory_id: str,
        *,
        key: str | None = None,
        value: str | None = None,
        visibility: str = "companion_allowed",
    ) -> UserPreference:
        memory = await self._get_owned(user_id, memory_id)
        if memory.status == "deleted":
            raise CompanionMemoryStateError("已删除的记忆无法确认")
        if key is not None:
            memory.preference_key = key
        if value is not None:
            memory.preference_value = value
        memory.status = "confirmed"
        memory.consent_source = "user_confirmed"
        memory.visibility = visibility
        memory.updated_at = datetime.utcnow()
        await self.db.flush()
        return memory

    async def soft_delete(self, user_id: int, memory_id: str) -> UserPreference:
        memory = await self._get_owned(user_id, memory_id)
        memory.status = "deleted"
        memory.visibility = "conversation_only"
        memory.updated_at = datetime.utcnow()
        await self.db.flush()
        return memory

    async def get_authorized(self, user_id: int, *, limit: int = 10) -> list[UserPreference]:
        result = await self.db.execute(
            select(UserPreference)
            .where(
                and_(
                    UserPreference.user_id == user_id,
                    UserPreference.status == "confirmed",
                    UserPreference.visibility == "companion_allowed",
                )
            )
            .order_by(UserPreference.confidence.desc(), UserPreference.updated_at.desc())
            .limit(limit)
        )
        memories = list(result.scalars().all())
        used_at = datetime.utcnow()
        for memory in memories:
            memory.last_used_at = used_at
        return memories

    async def _get_owned(self, user_id: int, memory_id: str) -> UserPreference:
        result = await self.db.execute(
            select(UserPreference).where(
                and_(UserPreference.id == memory_id, UserPreference.user_id == user_id)
            )
        )
        memory = result.scalar_one_or_none()
        if memory is None:
            raise CompanionMemoryNotFoundError(memory_id)
        return memory


__all__ = [
    "CompanionMemoryNotFoundError",
    "CompanionMemoryService",
    "CompanionMemoryStateError",
]
