"""知识库向量化失败的处理回归（KP2/KP3）。

零向量占位会让余弦相似度恒为 0，检索仍把它当作有效结果返回，属静默的垃圾检索；
全部向量化失败时文档还会被标记为 completed。这里约束三点：
1. `embed_chunks` 跳过失败/空向量的块，不写入零向量；
2. `search_similar_chunks` 丢弃相似度非正的块；
3. 上传端点在全失败时标记 failed，且 chunk_count 与实际入库数一致。
"""
import io

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import select

import app.api.v1.aicloud_knowledge as knowledge_api
import app.utils.aicloud.knowledge_processor as kp
from app.models.aicloud_knowledge import AicloudKnowledgeChunk, AicloudKnowledgeDoc


def _chunk(content: str, index: int = 0) -> kp.DocumentChunk:
    return kp.DocumentChunk(
        content=content,
        chunk_index=index,
        metadata={},
        content_hash=kp.compute_content_hash(content),
    )


@pytest.mark.asyncio
async def test_embed_chunks_skips_failed_embedding_without_zero_vector(monkeypatch):
    async def _embedding(text, model=None):
        if text == "原文":
            return [1.0, 0.0]
        raise RuntimeError("provider down")

    monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", _embedding)

    results = await kp.embed_chunks([_chunk("原文"), _chunk("坏块", 1)])

    assert [chunk.content for chunk, _ in results] == ["原文"]
    assert all(vector != [0.0] * 768 for _, vector in results)


@pytest.mark.asyncio
async def test_embed_chunks_treats_empty_vector_as_failure(monkeypatch):
    async def _embedding(text, model=None):
        return []

    monkeypatch.setattr("app.utils.AiCodeUtil.get_embedding", _embedding)

    assert await kp.embed_chunks([_chunk("原文")]) == []


def test_search_drops_zero_similarity_chunks():
    """零向量（历史占位数据）不能再占用 top_k 名额。"""
    good = _chunk("相关")
    polluted = _chunk("历史占位", 1)

    matches = kp.search_similar_chunks(
        [1.0, 0.0],
        [(good, [1.0, 0.0]), (polluted, [0.0] * 768)],
        top_k=5,
    )

    assert [(chunk.content, score) for chunk, score in matches] == [("相关", 1.0)]


def test_search_drops_length_mismatch_vectors():
    """维度不符的向量相似度恒为 0，不能作为检索结果返回。"""
    mismatched = _chunk("维度不符")

    assert kp.search_similar_chunks([1.0, 0.0], [(mismatched, [1.0, 0.0, 0.0])]) == []


async def _allow_permission(user_id, db):
    return None


def _upload(filename: str = "a.txt") -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(b"hello"))


async def _call_upload(db, filename: str, user_id: int = 1):
    return await knowledge_api.upload_document(
        file=_upload(filename),
        collection="default",
        description=None,
        tags=None,
        chunk_size=500,
        chunk_overlap=50,
        db=db,
        user_id=user_id,
    )


def _patch_upload_pipeline(monkeypatch, tmp_path, embed_result):
    async def _permission(user_id, db):
        return None

    async def _embed(chunks, model=None):
        return embed_result

    monkeypatch.setattr(knowledge_api, "check_aicloud_permission", _permission)
    monkeypatch.setattr(knowledge_api, "KNOWLEDGE_STORAGE_PATH", str(tmp_path))
    monkeypatch.setattr(knowledge_api, "parse_document", lambda path: "正文内容" * 20)
    monkeypatch.setattr(
        knowledge_api,
        "chunk_text",
        lambda text, **kwargs: [_chunk("块一"), _chunk("块二", 1)],
    )
    monkeypatch.setattr(knowledge_api, "embed_chunks", _embed)


@pytest.mark.asyncio
async def test_upload_marks_failed_when_no_chunk_can_be_embedded(test_db, monkeypatch, tmp_path):
    _patch_upload_pipeline(monkeypatch, tmp_path, embed_result=[])

    with pytest.raises(HTTPException) as error:
        await _call_upload(test_db, "all-failed.txt")

    assert error.value.status_code == 500

    doc = (
        await test_db.execute(
            select(AicloudKnowledgeDoc).where(AicloudKnowledgeDoc.filename == "all-failed.txt")
        )
    ).scalars().one()
    assert doc.status == "failed"
    assert doc.error_message

    stored = (
        await test_db.execute(
            select(AicloudKnowledgeChunk).where(AicloudKnowledgeChunk.doc_id == doc.id)
        )
    ).scalars().all()
    assert stored == []


@pytest.mark.asyncio
async def test_upload_chunk_count_matches_stored_chunks_on_partial_failure(
    test_db, monkeypatch, tmp_path
):
    _patch_upload_pipeline(monkeypatch, tmp_path, embed_result=[(_chunk("块一"), [1.0, 0.0])])

    response = await _call_upload(test_db, "partial.txt")

    assert response["chunk_count"] == 1

    doc = (
        await test_db.execute(
            select(AicloudKnowledgeDoc).where(AicloudKnowledgeDoc.filename == "partial.txt")
        )
    ).scalars().one()
    assert doc.status == "completed"
    assert doc.chunk_count == 1

    stored = (
        await test_db.execute(
            select(AicloudKnowledgeChunk).where(AicloudKnowledgeChunk.doc_id == doc.id)
        )
    ).scalars().all()
    assert len(stored) == 1
    assert stored[0].embedding_model == kp.DEFAULT_EMBEDDING_MODEL
