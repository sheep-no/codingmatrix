"""知识库上传的边界与阻塞防护。

超大文件必须在写入过程中被拦下且不留残留文件；
非法分块参数必须在磁盘操作前返回 400；
分块器本身不得因重叠参数而原地打转。
"""

import io

import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.api.v1 import aicloud_knowledge as knowledge
from app.utils.aicloud.knowledge_processor import chunk_text


def test_chunk_text_rejects_non_positive_chunk_size():
    with pytest.raises(ValueError, match="chunk_size"):
        chunk_text("内容", chunk_size=0)


def test_chunk_text_terminates_when_overlap_not_smaller_than_size():
    chunks = chunk_text("a" * 100, chunk_size=10, chunk_overlap=10)

    assert chunks
    assert all(chunk.content for chunk in chunks)


def _upload(payload: bytes, filename: str = "doc.txt") -> UploadFile:
    return UploadFile(file=io.BytesIO(payload), filename=filename, size=len(payload))


async def _call_upload(monkeypatch, tmp_path, payload, **overrides):
    monkeypatch.setattr(knowledge, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(knowledge, "check_aicloud_permission", _noop_permission)
    params = {"chunk_size": 500, "chunk_overlap": 50}
    params.update(overrides)
    return await knowledge.upload_document(
        file=_upload(payload),
        collection="default",
        description=None,
        tags=None,
        db=_fake_db(),
        user_id=1,
        **params,
    )


async def _noop_permission(user_id, db):
    return None


def _fake_db():
    db = type("FakeDb", (), {})()
    added = []
    db.add = added.append

    async def commit():
        return None

    db.commit = commit
    db.added = added
    return db


@pytest.mark.asyncio
async def test_oversized_upload_is_rejected_without_leaving_file(monkeypatch, tmp_path):
    monkeypatch.setattr(knowledge, "MAX_DOCUMENT_SIZE", 1024, raising=False)

    with pytest.raises(HTTPException) as error:
        await _call_upload(monkeypatch, tmp_path, b"x" * 4096)

    assert error.value.status_code == 400
    assert "文件过大" in error.value.detail
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [
    {"chunk_size": 0},
    {"chunk_size": -1},
    {"chunk_overlap": -1},
    {"chunk_size": 50, "chunk_overlap": 50},
])
async def test_invalid_chunk_params_rejected_before_writing(monkeypatch, tmp_path, overrides):
    with pytest.raises(HTTPException) as error:
        await _call_upload(monkeypatch, tmp_path, b"content", **overrides)

    assert error.value.status_code == 400
    assert "分块参数" in error.value.detail
    assert list(tmp_path.iterdir()) == []
