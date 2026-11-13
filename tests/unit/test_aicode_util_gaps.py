"""补齐 AiCodeUtil 的连接池、磁盘缓存与缓存失效分支。"""

import json
import time

import pytest
from fastapi import HTTPException

import app.utils.AiCodeUtil as aicu


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = "upstream error"

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, closed=False):
        self.is_closed = closed
        self.closed_count = 0

    async def aclose(self):
        self.closed_count += 1
        self.is_closed = True

    async def post(self, *args, **kwargs):
        return _FakeResponse({"data": [{"embedding": [0.5]}]})


@pytest.fixture
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(aicu, "_embedding_cache_dir", tmp_path)
    aicu._embedding_memory_cache.clear()
    aicu._embedding_memory_expiry.clear()
    yield tmp_path
    aicu._embedding_memory_cache.clear()
    aicu._embedding_memory_expiry.clear()


class TestSharedHttpClient:
    async def test_creates_then_reuses_client(self, monkeypatch):
        created = []

        def factory(**kwargs):
            client = _FakeClient()
            created.append(client)
            return client

        monkeypatch.setattr(aicu, "_http_client", None)
        monkeypatch.setattr(aicu.httpx, "AsyncClient", factory)

        first = await aicu.get_http_client()
        second = await aicu.get_http_client()

        assert first is second
        assert len(created) == 1
        monkeypatch.setattr(aicu, "_http_client", None)

    async def test_closed_client_is_replaced(self, monkeypatch):
        closed = _FakeClient(closed=True)
        replacement = _FakeClient()
        monkeypatch.setattr(aicu, "_http_client", closed)
        monkeypatch.setattr(aicu.httpx, "AsyncClient", lambda **kwargs: replacement)

        assert await aicu.get_http_client() is replacement
        monkeypatch.setattr(aicu, "_http_client", None)

    async def test_close_open_client(self, monkeypatch):
        client = _FakeClient()
        monkeypatch.setattr(aicu, "_http_client", client)

        await aicu.close_http_client()

        assert client.closed_count == 1
        assert aicu._http_client is None

    async def test_close_skips_missing_or_closed_client(self, monkeypatch):
        monkeypatch.setattr(aicu, "_http_client", None)
        await aicu.close_http_client()

        client = _FakeClient(closed=True)
        monkeypatch.setattr(aicu, "_http_client", client)
        await aicu.close_http_client()

        assert client.closed_count == 0
        monkeypatch.setattr(aicu, "_http_client", None)


class TestDiskCache:
    def test_missing_file_returns_none(self, cache_dir):
        assert aicu._load_embedding_from_disk("missing") is None

    def test_fresh_entry_loaded(self, cache_dir):
        (cache_dir / "fresh.json").write_text(
            json.dumps({"vector": [1, 2], "timestamp": time.time()}),
            encoding="utf-8",
        )

        assert aicu._load_embedding_from_disk("fresh") == [1, 2]

    def test_expired_entry_returns_none(self, cache_dir):
        (cache_dir / "old.json").write_text(
            json.dumps({"vector": [1], "timestamp": 0}),
            encoding="utf-8",
        )

        assert aicu._load_embedding_from_disk("old") is None

    def test_corrupt_file_returns_none(self, cache_dir):
        (cache_dir / "bad.json").write_text("{not json", encoding="utf-8")

        assert aicu._load_embedding_from_disk("bad") is None

    def test_save_writes_payload(self, cache_dir):
        aicu._save_embedding_to_disk("key", [0.1, 0.2])

        payload = json.loads((cache_dir / "key.json").read_text(encoding="utf-8"))
        assert payload["vector"] == [0.1, 0.2]
        assert payload["timestamp"] > 0

    def test_save_failure_is_swallowed(self, cache_dir, monkeypatch):
        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr("builtins.open", boom)
        aicu._save_embedding_to_disk("key", [0.1])

    def test_cleanup_removes_expired_and_ignores_bad_files(self, cache_dir):
        expired = cache_dir / "expired.json"
        expired.write_text(json.dumps({"vector": [1], "timestamp": 0}), encoding="utf-8")
        fresh = cache_dir / "fresh.json"
        fresh.write_text(json.dumps({"vector": [2], "timestamp": time.time()}), encoding="utf-8")
        corrupt = cache_dir / "corrupt.json"
        corrupt.write_text("{bad", encoding="utf-8")

        aicu._clean_expired_disk_cache()

        assert not expired.exists()
        assert fresh.exists()
        assert corrupt.exists()


class TestGetEmbeddingCachePaths:
    async def test_memory_cache_hit_moves_to_end(self, cache_dir):
        key = aicu._get_embedding_cache_key("cached", aicu.DEFAULT_EMBEDDING_MODEL)
        aicu._embedding_memory_cache[key] = [9.0]
        aicu._embedding_memory_expiry[key] = time.time() + 60

        assert await aicu.get_embedding("cached") == [9.0]
        assert aicu._embedding_memory_cache[key] == [9.0]

    async def test_expired_memory_entry_removed_before_disk_lookup(self, cache_dir, monkeypatch):
        key = aicu._get_embedding_cache_key("stale", aicu.DEFAULT_EMBEDDING_MODEL)
        aicu._embedding_memory_cache[key] = [1.0]
        aicu._embedding_memory_expiry[key] = 0
        monkeypatch.setattr(aicu, "_load_embedding_from_disk", lambda cache_key: None)

        with pytest.raises(HTTPException):
            await aicu.get_embedding("stale")

        assert key not in aicu._embedding_memory_cache
        assert key not in aicu._embedding_memory_expiry

    async def test_expired_memory_entry_without_expiry_record(self, cache_dir, monkeypatch):
        key = aicu._get_embedding_cache_key("orphan", aicu.DEFAULT_EMBEDDING_MODEL)
        aicu._embedding_memory_cache[key] = [1.0]
        aicu._embedding_memory_expiry.pop(key, None)
        monkeypatch.setattr(aicu, "_load_embedding_from_disk", lambda cache_key: None)

        with pytest.raises(HTTPException):
            await aicu.get_embedding("orphan")

        assert key not in aicu._embedding_memory_cache

    async def test_disk_cache_hit_populates_memory(self, cache_dir, monkeypatch):
        monkeypatch.setattr(aicu, "_load_embedding_from_disk", lambda cache_key: [3.0, 4.0])

        assert await aicu.get_embedding("disk") == [3.0, 4.0]

        key = aicu._get_embedding_cache_key("disk", aicu.DEFAULT_EMBEDDING_MODEL)
        assert aicu._embedding_memory_cache[key] == [3.0, 4.0]
        assert aicu._embedding_memory_expiry[key] > time.time()

    async def test_non_200_response_raises_http_exception(self, cache_dir, monkeypatch):
        monkeypatch.setattr(aicu.settings, "SILICONFLOW_API_KEY", "sk-test")
        monkeypatch.setattr(aicu, "_load_embedding_from_disk", lambda cache_key: None)
        client = _FakeClient()

        async def failing_post(*args, **kwargs):
            return _FakeResponse({}, status_code=502)

        client.post = failing_post
        monkeypatch.setattr(aicu, "get_http_client", _async_return(client))

        with pytest.raises(HTTPException) as raised:
            await aicu.get_embedding("boom")

        assert raised.value.status_code == 502


def _async_return(value):
    async def wrapper():
        return value

    return wrapper
