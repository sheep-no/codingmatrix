import hashlib
import io
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile

import app.api.v1.file_upload as file_upload


class _Result:
    def __init__(self, value=None):
        self._value = value

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value


class _DB:
    def __init__(self, results=()):
        self._results = list(results)
        self.added = []
        self.commits = 0
        self.refreshes = 0
        self.rolled_back = 0

    async def execute(self, statement):
        if self._results:
            return self._results.pop(0)
        return _Result()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        self.refreshes += 1
        obj.id = 1
        obj.created_at = "2026-01-01T00:00:00"

    async def rollback(self):
        self.rolled_back += 1


def _upload(name="a.txt", content=b"hello"):
    return UploadFile(filename=name, file=io.BytesIO(content))


def _file_record(**overrides):
    base = {
        "id": 5,
        "filename": "a.txt",
        "file_path": "/tmp/a.txt",
        "file_size": 5,
        "content_type": "text/plain",
        "created_at": "2026-01-01T00:00:00",
    }
    base.update(overrides)
    record = SimpleNamespace(**base)
    record.to_dict = lambda: {
        "id": record.id,
        "filename": record.filename,
        "file_size": record.file_size,
        "content_type": record.content_type,
        "created_at": record.created_at,
        "download_url": f"/api/v1/files/{record.id}/download",
    }
    return record


def test_chunk_metadata_loads_existing_and_defaults(tmp_path):
    meta_dir = tmp_path / "fid"
    meta_dir.mkdir()
    (meta_dir / "metadata.json").write_text('{"uploaded_chunks": [0, 2]}', encoding="utf-8")
    loaded = file_upload.ChunkMetadata.load("fid", 3, base_dir=tmp_path)
    assert loaded.uploaded_chunks == [0, 2]
    assert loaded.is_complete() is False

    missing = file_upload.ChunkMetadata.load("absent", 2, base_dir=tmp_path)
    assert missing.uploaded_chunks == []


def test_chunk_metadata_is_complete_requires_exact_set():
    meta = file_upload.ChunkMetadata("f", 2, [0, 1, 1])
    assert meta.is_complete() is False
    meta = file_upload.ChunkMetadata("f", 2, [1, 0])
    assert meta.is_complete() is True


def test_cleanup_stale_user_chunks_removes_old_dirs(tmp_path):
    user_dir = tmp_path / "7"
    user_dir.mkdir()
    stale = user_dir / "old"
    stale.mkdir()
    (stale / "chunk_0").write_bytes(b"x")
    fresh = user_dir / "new"
    fresh.mkdir()

    old = time.time() - file_upload.CHUNK_TTL_SECONDS - 100
    Path(stale).touch()
    import os
    os.utime(stale, (old, old))

    file_upload._cleanup_stale_user_chunks(user_dir)
    assert not stale.exists()
    assert fresh.exists()

    file_upload._cleanup_stale_user_chunks(tmp_path / "absent")


def test_cleanup_stale_user_chunks_swallows_oserror(tmp_path, monkeypatch):
    user_dir = tmp_path / "7"
    user_dir.mkdir()
    entry = user_dir / "broken"
    entry.mkdir()

    class _BrokenEntry:
        name = "broken"

        def is_dir(self):
            return True

        def stat(self):
            raise OSError("denied")

        def __str__(self):
            return "broken"

    monkeypatch.setattr(Path, "iterdir", lambda self: iter([entry]))
    monkeypatch.setattr(Path, "is_dir", lambda self: True)

    def broken_stat(self, *args, **kwargs):
        raise OSError("denied")

    monkeypatch.setattr(Path, "stat", broken_stat)
    file_upload._cleanup_stale_user_chunks(user_dir)


def test_validate_file_upload_rejects_empty_oversized_and_bad_extension():
    empty = _upload(content=b"")
    with pytest.raises(HTTPException) as exc:
        file_upload.validate_file_upload(empty)
    assert exc.value.status_code == 400

    oversized = _upload(content=b"xxxx")
    with patch.object(file_upload, "MAX_FILE_SIZE", 3):
        with pytest.raises(HTTPException) as exc:
            file_upload.validate_file_upload(oversized)
    assert exc.value.status_code == 413

    bad = _upload(name="evil.exe")
    with pytest.raises(HTTPException) as exc:
        file_upload.validate_file_upload(bad)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_upload_returns_existing_duplicate(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(file_upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(file_upload, "validate_file_upload", lambda file: None)
    monkeypatch.setattr(file_upload, "validate_file_path", lambda p, n: ("text/plain", "a.txt"))
    existing = _file_record()
    db = _DB([_Result(existing)])

    result = await file_upload.upload_file(_upload(), None, {"sub": "1"}, db)

    assert result.id == 5
    assert db.added == []


@pytest.mark.asyncio
async def test_upload_rejects_stream_exceeding_limit(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(file_upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(file_upload, "validate_file_upload", lambda file: None)
    monkeypatch.setattr(file_upload, "MAX_FILE_SIZE", 3)

    with pytest.raises(HTTPException) as exc:
        await file_upload.upload_file(_upload(content=b"0123456789"), None, {"sub": "1"}, _DB())

    assert exc.value.status_code == 413
    assert [p for p in upload_dir.rglob("*") if p.is_file()] == []


@pytest.mark.asyncio
async def test_upload_maps_validation_errors_and_cleans_temp(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(file_upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(file_upload, "validate_file_upload", lambda file: None)
    monkeypatch.setattr(
        file_upload, "validate_file_path",
        lambda p, n: (_ for _ in ()).throw(ValueError("bad content")),
    )

    with pytest.raises(HTTPException) as exc:
        await file_upload.upload_file(_upload(), None, {"sub": "1"}, _DB())

    assert exc.value.status_code == 500
    assert [p for p in upload_dir.rglob("*") if p.is_file()] == []


@pytest.mark.asyncio
async def test_upload_reraises_http_exception(tmp_path, monkeypatch):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()
    monkeypatch.setattr(file_upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(
        file_upload, "validate_file_upload",
        lambda file: (_ for _ in ()).throw(HTTPException(status_code=400, detail="bad")),
    )

    with pytest.raises(HTTPException) as exc:
        await file_upload.upload_file(_upload(), None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_download_missing_record_and_physical_file(tmp_path, monkeypatch):
    with pytest.raises(HTTPException) as exc:
        await file_upload.download_file(5, {"sub": "1"}, _DB([_Result(None)]))
    assert exc.value.status_code == 404

    missing = _file_record(file_path=str(tmp_path / "gone.txt"))
    with pytest.raises(HTTPException) as exc:
        await file_upload.download_file(5, {"sub": "1"}, _DB([_Result(missing)]))
    assert exc.value.status_code == 404
    assert exc.value.detail == "文件已丢失"


@pytest.mark.asyncio
async def test_download_streams_file(tmp_path):
    target = tmp_path / "a.txt"
    target.write_bytes(b"hello")
    record = _file_record(file_path=str(target), content_type=None)

    response = await file_upload.download_file(5, {"sub": "1"}, _DB([_Result(record)]))

    assert response.media_type == "application/octet-stream"
    assert "a.txt" in response.headers["Content-Disposition"]


@pytest.mark.asyncio
async def test_init_chunked_rejects_bad_sizes():
    for size in (0, file_upload.MAX_FILE_SIZE + 1):
        with pytest.raises(HTTPException) as exc:
            await file_upload.init_chunked_upload(
                "a.txt", size, "hash", None, {"sub": "1"}, _DB()
            )
        assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_init_chunked_returns_existing_file(tmp_path, monkeypatch):
    chunks = tmp_path / ".chunks"
    monkeypatch.setattr(file_upload, "CHUNKS_DIR", chunks)
    existing = _file_record()
    result = await file_upload.init_chunked_upload(
        "a.txt", 10, "hash", 3, {"sub": "1"}, _DB([_Result(existing)])
    )
    assert result["status"] == "exists"
    assert result["file_id"] == "5"


@pytest.mark.asyncio
async def test_init_chunked_resumes_existing_metadata(tmp_path, monkeypatch):
    chunks = tmp_path / ".chunks"
    monkeypatch.setattr(file_upload, "CHUNKS_DIR", chunks)
    monkeypatch.setattr(file_upload, "_cleanup_stale_user_chunks", lambda p: None)
    class _FixedUUID:
        def __str__(self):
            return "fid"

    monkeypatch.setattr(file_upload.uuid, "uuid4", lambda: _FixedUUID())

    meta_dir = chunks / "1" / "fid"
    meta_dir.mkdir(parents=True)
    (meta_dir / "metadata.json").write_text('{"uploaded_chunks": [0]}', encoding="utf-8")

    result = await file_upload.init_chunked_upload(
        "a.txt", file_upload.CHUNK_SIZE + 1, "hash", None, {"sub": "1"}, _DB()
    )
    assert result["status"] == "new"
    assert result["total_chunks"] == 2
    assert result["uploaded_chunks"] == [0]


@pytest.mark.asyncio
async def test_upload_chunk_validates_counts_and_size(tmp_path, monkeypatch):
    chunks = tmp_path / ".chunks"
    monkeypatch.setattr(file_upload, "CHUNKS_DIR", chunks)

    with pytest.raises(HTTPException) as exc:
        await file_upload.upload_chunk("fid", 0, _upload(), 0, {"sub": "1"})
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await file_upload.upload_chunk("fid", 0, _upload(), file_upload.MAX_TOTAL_CHUNKS + 1, {"sub": "1"})
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await file_upload.upload_chunk("fid", 2, _upload(), 2, {"sub": "1"})
    assert exc.value.status_code == 400

    monkeypatch.setattr(file_upload, "CHUNK_SIZE", 2)
    with pytest.raises(HTTPException) as exc:
        await file_upload.upload_chunk("fid", 0, _upload(content=b"abc"), 1, {"sub": "1"})
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_upload_chunk_persists_and_reports_complete(tmp_path, monkeypatch):
    chunks = tmp_path / ".chunks"
    monkeypatch.setattr(file_upload, "CHUNKS_DIR", chunks)
    result = await file_upload.upload_chunk("fid", 0, _upload(content=b"abc"), 1, {"sub": "1"})
    assert result["status"] == "success"
    assert result["is_complete"] is True
    assert (chunks / "1" / "fid" / "chunk_0").read_bytes() == b"abc"


@pytest.mark.asyncio
async def test_merge_rejects_bad_extension_and_size(tmp_path, monkeypatch):
    chunks = tmp_path / ".chunks"
    monkeypatch.setattr(file_upload, "CHUNKS_DIR", chunks)

    with pytest.raises(HTTPException) as exc:
        await file_upload.merge_chunks("fid", "bad.exe", "hash", 5, None, None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as exc:
        await file_upload.merge_chunks("fid", "a.txt", "hash", 0, None, None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 413


def _prepare_chunks(tmp_path, monkeypatch, *, uploaded=(0,), chunks=(b"hello",), total=1):
    upload_dir = tmp_path / "uploads"
    chunks_dir = upload_dir / ".chunks"
    chunk_dir = chunks_dir / "1" / "fid"
    chunk_dir.mkdir(parents=True)
    for index, payload in enumerate(chunks):
        (chunk_dir / f"chunk_{index}").write_bytes(payload)
    (chunk_dir / "metadata.json").write_text(
        f'{{"file_id": "fid", "total_chunks": {total}, "uploaded_chunks": {list(uploaded)}}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(file_upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(file_upload, "CHUNKS_DIR", chunks_dir)
    return upload_dir, chunk_dir


@pytest.mark.asyncio
async def test_merge_requires_metadata(tmp_path, monkeypatch):
    chunks = tmp_path / ".chunks"
    monkeypatch.setattr(file_upload, "CHUNKS_DIR", chunks)
    with pytest.raises(HTTPException) as exc:
        await file_upload.merge_chunks("fid", "a.txt", "hash", 5, None, None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_merge_rejects_incomplete_chunks(tmp_path, monkeypatch):
    _prepare_chunks(tmp_path, monkeypatch, uploaded=(0,), chunks=(b"a", b"b"), total=2)
    with pytest.raises(HTTPException) as exc:
        await file_upload.merge_chunks("fid", "a.txt", "hash", 2, None, None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 400
    assert "分片不完整" in exc.value.detail


@pytest.mark.asyncio
async def test_merge_detects_missing_chunk_file(tmp_path, monkeypatch):
    upload_dir, chunk_dir = _prepare_chunks(tmp_path, monkeypatch, uploaded=(0, 1), chunks=(b"a",), total=2)
    with pytest.raises(HTTPException) as exc:
        await file_upload.merge_chunks("fid", "a.txt", "hash", 2, None, None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 500
    assert "丢失" in exc.value.detail


@pytest.mark.asyncio
async def test_merge_rejects_size_mismatch(tmp_path, monkeypatch):
    _prepare_chunks(tmp_path, monkeypatch, chunks=(b"hello",))
    with pytest.raises(HTTPException) as exc:
        await file_upload.merge_chunks("fid", "a.txt", "hash", 4, None, None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 400
    assert "大小与声明不一致" in exc.value.detail


@pytest.mark.asyncio
async def test_merge_rejects_hash_mismatch(tmp_path, monkeypatch):
    _prepare_chunks(tmp_path, monkeypatch, chunks=(b"hello",))
    with pytest.raises(HTTPException) as exc:
        await file_upload.merge_chunks("fid", "a.txt", "deadbeef", 5, None, None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 500
    assert "文件校验失败" in exc.value.detail


@pytest.mark.asyncio
async def test_merge_rejects_deep_content_validation(tmp_path, monkeypatch):
    _prepare_chunks(tmp_path, monkeypatch, chunks=(b"hello",))
    digest = hashlib.sha256(b"hello").hexdigest()
    monkeypatch.setattr(
        file_upload, "validate_file_path",
        lambda p, n: (_ for _ in ()).throw(ValueError("evil")),
    )
    with pytest.raises(HTTPException) as exc:
        await file_upload.merge_chunks("fid", "a.txt", digest, 5, None, None, {"sub": "1"}, _DB())
    assert exc.value.status_code == 400
    assert "文件内容校验失败" in exc.value.detail


@pytest.mark.asyncio
async def test_merge_success_cleans_chunks_and_returns_record(tmp_path, monkeypatch):
    upload_dir, chunk_dir = _prepare_chunks(tmp_path, monkeypatch, chunks=(b"hello",))
    digest = hashlib.sha256(b"hello").hexdigest()
    monkeypatch.setattr(file_upload, "validate_file_path", lambda p, n: ("text/plain", n))

    class _OkDB(_DB):
        async def refresh(self, obj):
            self.refreshes += 1
            obj.id = 9
            from datetime import datetime
            obj.created_at = datetime(2026, 1, 1)

    db = _OkDB()
    result = await file_upload.merge_chunks(
        "fid", "a.txt", digest, 5, "text/plain", 3, {"sub": "1"}, db
    )

    assert result["success"] is True
    assert result["file"]["id"] == 9
    assert not chunk_dir.exists()
    assert db.commits == 1
