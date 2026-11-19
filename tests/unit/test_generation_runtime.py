import asyncio

import pytest

from app.services.generation_runtime import GenerationRuntime
from app.utils.dynamic_concurrent import ConcurrentLimitManager


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.hashes = {}

    def set(self, key, value, nx=False, ex=None, px=None):
        if nx and key in self.values:
            return False
        self.values[key] = str(value)
        return True

    def get(self, key):
        return self.values.get(key)

    def delete(self, key):
        self.values.pop(key, None)
        self.hashes.pop(key, None)

    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[str(field)] = str(value)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def hexists(self, key, field):
        return str(field) in self.hashes.get(key, {})

    def hdel(self, key, *fields):
        members = self.hashes.get(key, {})
        for field in fields:
            members.pop(str(field), None)

    def expire(self, key, seconds):
        return True

    def incr(self, key):
        self.values[key] = str(int(self.values.get(key, 0)) + 1)

    def decr(self, key):
        self.values[key] = str(int(self.values.get(key, 0)) - 1)


@pytest.mark.asyncio
async def test_cancel_signal_crosses_runtime_instances():
    client = FakeRedis()
    watcher_runtime = GenerationRuntime(
        client, enabled=True, watch_interval=0.01
    )
    signal_runtime = GenerationRuntime(client, enabled=True)
    event = asyncio.Event()
    watcher_runtime.register_cancel_event("sess-1", event)

    signal_runtime.request_cancel("sess-1")
    await asyncio.wait_for(event.wait(), timeout=1.0)

    assert watcher_runtime.is_cancel_requested("sess-1") is True
    watcher_runtime.release_cancel_event("sess-1", event)
    assert signal_runtime.is_cancel_requested("sess-1") is False


@pytest.mark.asyncio
async def test_cancel_stays_local_without_redis():
    runtime = GenerationRuntime(enabled=False)
    event = asyncio.Event()
    runtime.register_cancel_event("sess-2", event)

    runtime.request_cancel("sess-2")

    assert event.is_set()
    assert runtime.is_cancel_requested("sess-2") is False


@pytest.mark.asyncio
async def test_user_lock_serializes_two_workers():
    client = FakeRedis()
    first = GenerationRuntime(client, enabled=True)
    second = GenerationRuntime(client, enabled=True)
    entered = asyncio.Event()
    release = asyncio.Event()

    async def holder():
        async with first.user_lock("42"):
            entered.set()
            await release.wait()

    async def contender():
        async with second.user_lock("42"):
            return True

    holder_task = asyncio.create_task(holder())
    await entered.wait()
    contender_task = asyncio.create_task(contender())
    await asyncio.sleep(0.05)
    assert not contender_task.done()

    release.set()
    await asyncio.wait_for(holder_task, timeout=1.0)
    assert await asyncio.wait_for(contender_task, timeout=1.0) is True
    assert client.values == {}


@pytest.fixture
def reset_concurrent_manager():
    ConcurrentLimitManager._instance = None
    yield
    ConcurrentLimitManager._instance = None


def test_concurrent_manager_reads_redis_sessions(reset_concurrent_manager):
    client = FakeRedis()
    manager = ConcurrentLimitManager(redis_client=client)
    manager.register_session("free", "sess-1")

    # Simulate another worker inspecting the shared counter.
    ConcurrentLimitManager._instance = None
    other_worker = ConcurrentLimitManager(redis_client=client)

    assert other_worker.get_active_count("free") == 1
    assert other_worker.can_create_session("free") is False


def test_concurrent_manager_unregisters_redis_session(reset_concurrent_manager):
    client = FakeRedis()
    manager = ConcurrentLimitManager(redis_client=client)
    manager.register_session("premium", "sess-1")
    manager.unregister_session("premium", "sess-1")

    assert manager.get_active_count("premium") == 0


def test_concurrent_manager_supports_legacy_counter_mode(reset_concurrent_manager):
    client = FakeRedis()
    manager = ConcurrentLimitManager(redis_client=client)
    manager.register_session("basic")
    manager.register_session("basic")

    assert manager.get_active_count("basic") == 2
    manager.unregister_session("basic")
    manager.unregister_session("basic")
    assert manager.get_active_count("basic") == 0


def test_concurrent_manager_drops_expired_redis_leases(reset_concurrent_manager):
    client = FakeRedis()
    manager = ConcurrentLimitManager(redis_client=client)
    manager.register_session("free", "dead-worker-session")
    client.hset(
        manager._active_key("free"),
        "dead-worker-session",
        int(0),
    )

    ConcurrentLimitManager._instance = None
    other_worker = ConcurrentLimitManager(redis_client=client)

    assert other_worker.get_active_count("free") == 0
    assert "dead-worker-session" not in client.hashes[manager._active_key("free")]
