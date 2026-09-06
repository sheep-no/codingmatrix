import asyncio

import pytest

from app.services.image_resource_service import GenerationConcurrencyLimiter


@pytest.mark.asyncio
async def test_user_limit_allows_only_configured_parallel_work():
    limiter = GenerationConcurrencyLimiter(global_limit=4, user_limit=1)
    active = 0
    maximum_active = 0
    release = asyncio.Event()

    async def work():
        nonlocal active, maximum_active
        async with limiter.user_slot(7):
            active += 1
            maximum_active = max(maximum_active, active)
            await release.wait()
            active -= 1

    first = asyncio.create_task(work())
    await asyncio.sleep(0)
    second = asyncio.create_task(work())
    await asyncio.sleep(0)
    assert maximum_active == 1

    release.set()
    await asyncio.gather(first, second)
    assert maximum_active == 1


@pytest.mark.asyncio
async def test_user_limit_is_independent_between_users():
    limiter = GenerationConcurrencyLimiter(global_limit=2, user_limit=1)
    entered = asyncio.Event()
    release = asyncio.Event()
    active_users = set()

    async def work(user_id):
        async with limiter.user_slot(user_id):
            active_users.add(user_id)
            entered.set()
            await release.wait()

    first = asyncio.create_task(work(1))
    second = asyncio.create_task(work(2))
    await entered.wait()
    await asyncio.sleep(0)
    assert active_users == {1, 2}

    release.set()
    await asyncio.gather(first, second)


@pytest.mark.asyncio
async def test_user_slot_releases_after_cancelled_work():
    limiter = GenerationConcurrencyLimiter(global_limit=1, user_limit=1)
    started = asyncio.Event()

    async def cancelled_work():
        async with limiter.user_slot(7):
            started.set()
            await asyncio.sleep(60)

    task = asyncio.create_task(cancelled_work())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    async with limiter.user_slot(7):
        assert True
