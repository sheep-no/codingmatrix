import asyncio

import pytest

from app.services.image_resource_service import get_or_create_generation


@pytest.mark.asyncio
async def test_singleflight_runs_owner_once_for_concurrent_requests():
    started = asyncio.Event()
    release = asyncio.Event()
    calls = 0

    async def owner():
        nonlocal calls
        calls += 1
        started.set()
        await release.wait()
        return {"path": "/tmp/generated.png"}

    first = asyncio.create_task(
        get_or_create_generation(fingerprint="same", owner=owner)
    )
    await started.wait()
    second = asyncio.create_task(
        get_or_create_generation(fingerprint="same", owner=owner)
    )
    release.set()

    assert await asyncio.gather(first, second) == [
        {"path": "/tmp/generated.png"},
        {"path": "/tmp/generated.png"},
    ]
    assert calls == 1


@pytest.mark.asyncio
async def test_singleflight_removes_failed_task_for_retry():
    calls = 0

    async def owner():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("provider failed")
        return "recovered"

    with pytest.raises(RuntimeError, match="provider failed"):
        await get_or_create_generation(fingerprint="retry", owner=owner)

    assert await get_or_create_generation(fingerprint="retry", owner=owner) == "recovered"
    assert calls == 2
