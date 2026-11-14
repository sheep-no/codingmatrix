"""CompanionMemoryService 剩余分支补测。"""

import pytest

from app.schema.girl_companion import MemoryCandidate
from app.services.girlai_companion_memory import (
    CompanionMemoryNotFoundError,
    CompanionMemoryService,
    CompanionMemoryStateError,
)


@pytest.mark.asyncio
async def test_new_candidate_updates_existing_pending_memory(test_db, test_user):
    service = CompanionMemoryService(test_db)
    first = (
        await service.create_candidates(
            test_user.id,
            [MemoryCandidate(key="work", value="旧值", confidence=0.5, source="conversation")],
        )
    )[0]

    updated = await service.create_candidates(
        test_user.id,
        [
            MemoryCandidate(
                key="work",
                value="新值",
                confidence=0.9,
                source="a-very-long-extraction-source-name",
            )
        ],
    )

    assert [memory.id for memory in updated] == [first.id]
    assert updated[0].preference_value == "新值"
    assert updated[0].confidence == 90
    assert updated[0].source == "a-very-long-extracti"
    assert updated[0].status == "candidate"
    assert updated[0].consent_source == "system_derived"
    assert updated[0].visibility == "conversation_only"


@pytest.mark.asyncio
async def test_confirm_rejects_deleted_memory(test_db, test_user):
    service = CompanionMemoryService(test_db)
    memory = (
        await service.create_candidates(
            test_user.id,
            [MemoryCandidate(key="work", value="开发平台", confidence=0.8)],
        )
    )[0]
    await service.soft_delete(test_user.id, memory.id)

    with pytest.raises(CompanionMemoryStateError, match="已删除的记忆无法确认"):
        await service.confirm(test_user.id, memory.id)


@pytest.mark.asyncio
async def test_confirm_applies_key_and_value_overrides(test_db, test_user):
    service = CompanionMemoryService(test_db)
    memory = (
        await service.create_candidates(
            test_user.id,
            [MemoryCandidate(key="work", value="开发平台", confidence=0.8)],
        )
    )[0]

    confirmed = await service.confirm(
        test_user.id,
        memory.id,
        key="job",
        value="AI 平台",
        visibility="conversation_only",
    )

    assert confirmed.preference_key == "job"
    assert confirmed.preference_value == "AI 平台"
    assert confirmed.visibility == "conversation_only"


@pytest.mark.asyncio
async def test_get_owned_raises_for_missing_memory(test_db, test_user):
    service = CompanionMemoryService(test_db)

    with pytest.raises(CompanionMemoryNotFoundError):
        await service._get_owned(test_user.id, "missing-id")
