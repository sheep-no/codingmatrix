"""上传在 DB 写入失败时不得遗留孤儿文件。

文件先 `os.replace` 落盘、再写 DB；原实现 commit 失败只回滚事务，
磁盘上的文件不会删除，长期会累积无主文件。
"""

import io

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy.exc import SQLAlchemyError

import app.api.v1.file_upload as file_upload


class _DB:
    def __init__(self):
        self.rolled_back = False
        self.added = []

    async def execute(self, statement):
        class _Result:
            def scalar(self):
                return None

        return _Result()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        raise SQLAlchemyError("db down")

    async def refresh(self, obj):
        raise AssertionError("refresh should not run after failed commit")

    async def rollback(self):
        self.rolled_back = True


@pytest.mark.asyncio
async def test_upload_removes_orphan_file_when_commit_fails(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    monkeypatch.setattr(file_upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(file_upload, "validate_file_upload", lambda file: None)
    monkeypatch.setattr(
        file_upload,
        "validate_file_path",
        lambda path, name: ("text/plain", "a.txt"),
    )

    db = _DB()
    file = UploadFile(filename="a.txt", file=io.BytesIO(b"hello world"))

    with pytest.raises(HTTPException) as error:
        await file_upload.upload_file(
            file=file, conversation_id=None, token={"sub": "1"}, db=db
        )

    assert error.value.status_code == 500
    assert db.rolled_back is True

    stored = [p for p in upload_dir.rglob("*") if p.is_file()]
    assert stored == [], f"commit 失败后仍残留文件: {stored}"


@pytest.mark.asyncio
async def test_upload_keeps_file_when_commit_succeeds(monkeypatch, tmp_path):
    upload_dir = tmp_path / "uploads"
    upload_dir.mkdir()

    monkeypatch.setattr(file_upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(file_upload, "validate_file_upload", lambda file: None)
    monkeypatch.setattr(
        file_upload,
        "validate_file_path",
        lambda path, name: ("text/plain", "a.txt"),
    )

    class _OkDB(_DB):
        async def commit(self):
            return None

        async def refresh(self, obj):
            obj.id = 1
            obj.created_at = "2026-01-01T00:00:00"
            obj.to_dict = lambda: {
                "id": 1,
                "filename": "a.txt",
                "file_size": 11,
                "content_type": "text/plain",
                "created_at": "2026-01-01T00:00:00",
                "download_url": "/api/v1/files/1/download",
            }

    db = _OkDB()
    file = UploadFile(filename="a.txt", file=io.BytesIO(b"hello world"))

    result = await file_upload.upload_file(
        file=file, conversation_id=None, token={"sub": "1"}, db=db
    )

    assert result.id == 1
    stored = [p for p in upload_dir.rglob("*") if p.is_file()]
    assert len(stored) == 1


@pytest.mark.asyncio
async def test_merge_removes_merged_file_when_commit_fails(monkeypatch, tmp_path):
    """分片合并同样必须在 DB 失败时清理已合并的孤儿文件。"""
    upload_dir = tmp_path / "uploads"
    chunks_dir = upload_dir / ".chunks"
    file_id = "merge-1"
    chunk_dir = chunks_dir / "1" / file_id
    chunk_dir.mkdir(parents=True)
    (chunk_dir / "chunk_0").write_bytes(b"hello")
    (chunk_dir / "metadata.json").write_text(
        '{"file_id": "merge-1", "total_chunks": 1, "uploaded_chunks": [0]}'
    )

    monkeypatch.setattr(file_upload, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(file_upload, "CHUNKS_DIR", chunks_dir)
    monkeypatch.setattr(file_upload, "validate_file_path", lambda path, name: ("text/plain", name))
    monkeypatch.setattr(
        file_upload.ChunkMetadata,
        "load",
        classmethod(
            lambda cls, fid, total, base_dir=None: cls(fid, total, [0], base_dir=base_dir)
        ),
    )

    db = _DB()
    import hashlib

    actual_hash = hashlib.sha256(b"hello").hexdigest()

    with pytest.raises(SQLAlchemyError):
        await file_upload.merge_chunks(
            file_id=file_id,
            filename="a.txt",
            file_hash=actual_hash,
            file_size=5,
            content_type="text/plain",
            conversation_id=None,
            token={"sub": "1"},
            db=db,
        )

    assert db.rolled_back is True
    merged = [p for p in upload_dir.rglob("*") if p.is_file() and ".chunks" not in str(p)]
    assert merged == [], f"commit 失败后仍残留合并文件: {merged}"
