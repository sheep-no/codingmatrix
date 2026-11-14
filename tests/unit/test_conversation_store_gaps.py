"""conversation_store 同步回填、压缩与错误分支补测。"""

import asyncio
import json
import logging
import time

import pytest

from app.agent import conversation_store as module
from app.agent.conversation_store import ConversationStore


class _FakeRedis:
    def __init__(self):
        self.data = {}
        self.fail_get = False
        self.fail_setex = False
        self.fail_delete = False
        self.fail_exists = False
        self.fail_script = False
        self.deleted = []

    def get(self, key):
        if self.fail_get:
            raise RuntimeError("get failed")
        return self.data.get(key)

    def setex(self, key, ttl, value):
        if self.fail_setex:
            raise RuntimeError("setex failed")
        self.data[key] = value

    def delete(self, key):
        self.deleted.append(key)
        if self.fail_delete:
            raise RuntimeError("delete failed")
        self.data.pop(key, None)

    def exists(self, key):
        if self.fail_exists:
            raise RuntimeError("exists failed")
        return 1 if key in self.data else 0

    def register_script(self, script):
        def run(keys, args):
            if self.fail_script:
                raise RuntimeError("script failed")
            key = keys[0]
            raw = self.data.get(key)
            existing = json.loads(raw) if raw else (
                json.loads(args[2]) if args[2] else []
            )
            existing.append(json.loads(args[0]))
            self.data[key] = json.dumps(existing, ensure_ascii=False)
            return len(existing)

        return run


@pytest.fixture
def store(monkeypatch):
    fake = _FakeRedis()
    instance = ConversationStore.__new__(ConversationStore)
    instance.redis = fake
    instance._append_lock = asyncio.Lock()
    return instance


def test_get_history_returns_redis_hit(store):
    payload = [{"role": "user", "content": "hi"}]
    store.redis.data[store._key("s")] = json.dumps(payload)
    assert store.get_history("s") == payload


def test_get_history_redis_error_falls_back(store):
    store.redis.fail_get = True
    assert store.get_history("s") == []


def test_get_history_db_miss_with_user(store, monkeypatch):
    async def empty(session_id, user_id):
        return []

    monkeypatch.setattr(store, "_load_from_db_async", empty)
    assert store.get_history("s", "u") == []


def test_get_history_db_hit_backfills_redis(store, monkeypatch):
    messages = [{"role": "user", "content": "from db"}]

    async def load(session_id, user_id):
        return messages

    monkeypatch.setattr(store, "_load_from_db_async", load)
    result = store.get_history("s", "u")

    assert result == messages
    assert json.loads(store.redis.data[store._key("s")]) == messages


def test_load_from_db_sync_returns_empty_when_loop_running(store):
    async def scenario():
        return store._load_from_db_sync("s", "u")

    assert asyncio.run(scenario()) == []


def test_load_from_db_sync_runs_loop(monkeypatch):
    store = ConversationStore.__new__(ConversationStore)
    store.redis = _FakeRedis()

    async def load(session_id, user_id):
        return [{"role": "user", "content": "x"}]

    monkeypatch.setattr(store, "_load_from_db_async", load)
    assert store._load_from_db_sync("s", "u") == [{"role": "user", "content": "x"}]


def test_load_from_db_sync_handles_error(monkeypatch):
    store = ConversationStore.__new__(ConversationStore)

    def boom():
        raise RuntimeError("loop broken")

    monkeypatch.setattr(asyncio, "get_event_loop", boom)
    assert store._load_from_db_sync("s", "u") == []


def test_save_to_redis_error_logged(store):
    store.redis.fail_setex = True
    store._save_to_redis("s", [{"role": "user", "content": "x"}])


def test_append_to_redis_error_returns_minus_one(store):
    store.redis.fail_script = True
    assert store._append_to_redis("s", {"role": "user", "content": "x"}) == -1


def test_append_to_redis_seed_on_miss(store):
    count = store._append_to_redis(
        "s", {"role": "user", "content": "new"},
        [{"role": "user", "content": "old"}],
    )
    stored = json.loads(store.redis.data[store._key("s")])
    assert count == 2
    assert [m["content"] for m in stored] == ["old", "new"]


async def test_append_message_returns_false_when_db_fails(store, monkeypatch):
    async def fail(*args, **kwargs):
        return False

    monkeypatch.setattr(store, "_save_message_to_db", fail)
    assert await store.append_message("s", "u", "user", "x") is False
    assert store._key("s") not in store.redis.data


async def test_append_message_seed_error_continues(store, monkeypatch):
    store.redis.fail_exists = True

    async def ok(*args, **kwargs):
        return True

    monkeypatch.setattr(store, "_save_message_to_db", ok)
    assert await store.append_message("s", "u", "user", "x") is True


async def test_append_message_seeds_from_db_when_missing(store, monkeypatch):
    seeded = [{"role": "user", "content": "history"}]

    async def load(session_id, user_id):
        return seeded

    async def ok(*args, **kwargs):
        return True

    monkeypatch.setattr(store, "_load_from_db_async", load)
    monkeypatch.setattr(store, "_save_message_to_db", ok)

    await store.append_message("s", "u", "user", "new")

    stored = json.loads(store.redis.data[store._key("s")])
    assert [m["content"] for m in stored] == ["history", "new"]


async def test_get_history_async_redis_hit(store):
    payload = [{"role": "assistant", "content": "ai"}]
    store.redis.data[store._key("s")] = json.dumps(payload)
    assert await store.get_history_async("s") == payload


async def test_get_history_async_redis_error_falls_back(store, monkeypatch):
    store.redis.fail_get = True

    async def load(session_id, user_id):
        return [{"role": "user", "content": "db"}]

    monkeypatch.setattr(store, "_load_from_db_async", load)
    result = await store.get_history_async("s", "u")
    assert result == [{"role": "user", "content": "db"}]


async def test_get_history_async_without_user_returns_empty(store):
    assert await store.get_history_async("s") == []


async def test_clear_history_without_user_skips_db(store):
    store.redis.data[store._key("s")] = "[]"
    await store.clear_history("s")
    assert store._key("s") not in store.redis.data


async def test_clear_history_logs_db_and_redis_failures(store, monkeypatch):
    store.redis.fail_delete = True

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Capture()
    module.logger.addHandler(handler)

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "app.db.models":
            raise RuntimeError("db down")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)
    try:
        await store.clear_history("s", "u")
    finally:
        module.logger.removeHandler(handler)

    assert any("Failed to clear DB" in r.getMessage() for r in records)
    assert any("Failed to clear Redis" in r.getMessage() for r in records)


async def test_compress_returns_when_under_limit(store):
    messages = [{"role": "user", "content": "short"}]
    result = await store.compress_history("s", "u", messages, lambda *a: None)
    assert result == messages


async def test_compress_success_replaces_old_messages(store, monkeypatch):
    messages = [
        {"role": "user", "content": "长" * 2000},
        {"role": "assistant", "content": "回" * 2000},
        {"role": "user", "content": "最近"},
        {"role": "assistant", "content": "回复"},
        {"role": "user", "content": "最新"},
    ]
    appended = []
    cleared = []

    async def fake_llm(system, text):
        return "摘要内容"

    async def fake_clear(session_id, user_id):
        cleared.append((session_id, user_id))

    async def fake_append(session_id, user_id, role, content):
        appended.append((role, content))
        return True

    monkeypatch.setattr(store, "clear_history", fake_clear)
    monkeypatch.setattr(store, "append_message", fake_append)

    result = await store.compress_history("s", "u", messages, fake_llm, max_tokens=10)

    assert result[0]["role"] == "system"
    assert "摘要内容" in result[0]["content"]
    assert cleared == [("s", "u")]
    assert appended[0] == ("system", "[历史对话摘要]\n摘要内容")


async def test_compress_failure_falls_back_to_truncation(store):
    messages = [
        {"role": "user", "content": "长" * 2000},
        {"role": "assistant", "content": "回" * 2000},
    ]

    async def failing_llm(*args):
        raise RuntimeError("llm down")

    result = await store.compress_history("s", "u", messages, failing_llm, max_tokens=10)
    assert result == store.truncate_history(messages)


def test_get_conversation_store_singleton(monkeypatch):
    created = []

    class FakeStore:
        def __init__(self, url):
            created.append(url)

    monkeypatch.setattr(module, "ConversationStore", FakeStore)
    monkeypatch.setattr(module, "_store", None)

    first = module.get_conversation_store()
    second = module.get_conversation_store()

    assert first is second
    assert len(created) == 1
