"""流式 LLM 信号量必须在取消 / aclose 后释放。"""

import asyncio

import pytest

from app.utils.aicloud.llm_caller import (
    LLMCallError,
    _acquire_llm_semaphores,
    _iter_stream_holding_semaphore,
)


@pytest.mark.asyncio
async def test_aclose_releases_semaphores():
    global_sem = asyncio.Semaphore(1)
    model_sem = asyncio.Semaphore(1)
    await _acquire_llm_semaphores(global_sem, model_sem)

    async def inner():
        yield "chunk-1"
        await asyncio.sleep(60)
        yield "chunk-2"

    stream = _iter_stream_holding_semaphore(inner(), global_sem, model_sem)
    assert await stream.__anext__() == "chunk-1"
    await stream.aclose()
    await stream.aclose()
    assert global_sem._value == 1
    assert model_sem._value == 1


@pytest.mark.asyncio
async def test_cancel_during_iterate_releases():
    global_sem = asyncio.Semaphore(1)
    model_sem = asyncio.Semaphore(1)
    await _acquire_llm_semaphores(global_sem, model_sem)

    async def inner():
        yield "chunk-1"
        await asyncio.sleep(60)
        yield "chunk-2"

    async def consume():
        stream = _iter_stream_holding_semaphore(inner(), global_sem, model_sem)
        try:
            async for _ in stream:
                pass
        finally:
            stream.release_now()
            await stream.aclose()

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert global_sem._value == 1
    assert model_sem._value == 1


@pytest.mark.asyncio
async def test_release_now_is_sync_and_idempotent():
    global_sem = asyncio.Semaphore(1)
    model_sem = asyncio.Semaphore(1)
    await _acquire_llm_semaphores(global_sem, model_sem)

    async def inner():
        yield "chunk-1"
        await asyncio.sleep(60)
        yield "chunk-2"

    stream = _iter_stream_holding_semaphore(inner(), global_sem, model_sem)
    assert await stream.__anext__() == "chunk-1"
    stream.release_now()
    stream.release_now()
    assert global_sem._value == 1
    assert model_sem._value == 1


@pytest.mark.asyncio
async def test_acquire_cancel_releases_global_while_waiting_model():
    global_sem = asyncio.Semaphore(1)
    model_sem = asyncio.Semaphore(1)
    await model_sem.acquire()

    async def waiter():
        await _acquire_llm_semaphores(global_sem, model_sem, timeout=5)

    task = asyncio.create_task(waiter())
    await asyncio.sleep(0.05)
    assert global_sem._value == 0
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert global_sem._value == 1
    model_sem.release()
    assert model_sem._value == 1


@pytest.mark.asyncio
async def test_timeout_waiting_model_releases_global():
    global_sem = asyncio.Semaphore(1)
    model_sem = asyncio.Semaphore(0)
    with pytest.raises(LLMCallError) as exc:
        await _acquire_llm_semaphores(global_sem, model_sem, timeout=0.05)
    assert exc.value.status_code == 503
    assert global_sem._value == 1


@pytest.mark.asyncio
async def test_exhausted_stream_releases():
    global_sem = asyncio.Semaphore(1)
    model_sem = asyncio.Semaphore(1)
    await _acquire_llm_semaphores(global_sem, model_sem)

    async def inner():
        yield "a"
        yield "b"

    chunks = [item async for item in _iter_stream_holding_semaphore(inner(), global_sem, model_sem)]
    assert chunks == ["a", "b"]
    assert global_sem._value == 1
    assert model_sem._value == 1
