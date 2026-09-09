import pytest

from app.schema.girl_companion import MemoryCandidate
from app.services.girlai_companion_context import build_companion_context
from app.services.girlai_companion_memory import (
    CompanionMemoryNotFoundError,
    CompanionMemoryService,
)


@pytest.mark.asyncio
async def test_memory_requires_confirmation_and_stops_retrieval_after_delete(test_db, test_user):
    service = CompanionMemoryService(test_db)
    candidates = await service.create_candidates(
        test_user.id,
        [MemoryCandidate(key="work", value="开发平台", confidence=0.87)],
    )
    memory = candidates[0]

    assert memory.status == "candidate"
    assert memory.visibility == "conversation_only"
    assert await service.get_authorized(test_user.id) == []

    confirmed = await service.confirm(
        test_user.id,
        memory.id,
        value="开发 AI 平台",
        visibility="companion_allowed",
    )
    authorized = await service.get_authorized(test_user.id)

    assert confirmed.status == "confirmed"
    assert confirmed.consent_source == "user_confirmed"
    assert confirmed.preference_value == "开发 AI 平台"
    assert [item.id for item in authorized] == [memory.id]
    assert authorized[0].last_used_at is not None
    confirmed_context = build_companion_context(
        character={"name": "姬"},
        user_prompt="继续",
        memories=[
            {
                "key": item.preference_key,
                "value": item.preference_value,
                "status": item.status,
                "visibility": item.visibility,
            }
            for item in authorized
        ],
    )
    assert "开发 AI 平台" in confirmed_context.prompt

    await service.soft_delete(test_user.id, memory.id)

    authorized_after_delete = await service.get_authorized(test_user.id)
    assert authorized_after_delete == []
    deleted_context = build_companion_context(
        character={"name": "姬"}, user_prompt="继续", memories=authorized_after_delete
    )
    assert "开发 AI 平台" not in deleted_context.prompt
    visible, total = await service.list_memories(test_user.id)
    assert visible == []
    assert total == 0


@pytest.mark.asyncio
async def test_memory_operations_hide_other_users_records(test_db, test_user):
    service = CompanionMemoryService(test_db)
    memory = (
        await service.create_candidates(
            test_user.id,
            [MemoryCandidate(key="hobby", value="阅读", confidence=0.9)],
        )
    )[0]

    with pytest.raises(CompanionMemoryNotFoundError):
        await service.confirm(test_user.id + 1, memory.id)

    with pytest.raises(CompanionMemoryNotFoundError):
        await service.soft_delete(test_user.id + 1, memory.id)


@pytest.mark.asyncio
async def test_candidate_does_not_overwrite_confirmed_memory(test_db, test_user):
    service = CompanionMemoryService(test_db)
    memory = (
        await service.create_candidates(
            test_user.id,
            [MemoryCandidate(key="name", value="小明", confidence=0.8)],
        )
    )[0]
    await service.confirm(test_user.id, memory.id)

    created = await service.create_candidates(
        test_user.id,
        [MemoryCandidate(key="name", value="另一个名字", confidence=0.95)],
    )

    assert created == []
    assert memory.preference_value == "小明"


@pytest.mark.asyncio
async def test_duplicate_candidates_create_one_pending_memory(test_db, test_user):
    service = CompanionMemoryService(test_db)

    created = await service.create_candidates(
        test_user.id,
        [
            MemoryCandidate(key="location", value="杭州", confidence=0.7),
            MemoryCandidate(key="location", value="杭州", confidence=0.9),
        ],
    )

    assert len(created) == 1
    memories, total = await service.list_memories(test_user.id, status="candidate")
    assert total == 1
    assert memories[0].preference_value == "杭州"
