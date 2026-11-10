"""知识库语义检索必须限制单次加载与返回数量。

检索在 Python 侧全量计算余弦相似度，原实现把用户所有分块一次读入内存，
且 `top_k` 无上界，超大知识库可造成内存放大。
"""

import pytest
from pydantic import ValidationError

import app.api.v1.aicloud_knowledge as knowledge_api


def test_top_k_is_bounded():
    with pytest.raises(ValidationError):
        knowledge_api.KnowledgeSearchRequest(query="x", top_k=0)
    with pytest.raises(ValidationError):
        knowledge_api.KnowledgeSearchRequest(query="x", top_k=500)

    assert knowledge_api.KnowledgeSearchRequest(query="x", top_k=50).top_k == 50


def test_search_chunk_load_is_capped():
    """候选分块查询必须带上限，避免整库读入内存。"""
    from sqlalchemy import select

    from app.models.aicloud_knowledge import AicloudKnowledgeChunk

    query = select(AicloudKnowledgeChunk).where(
        AicloudKnowledgeChunk.user_id == 1
    ).order_by(AicloudKnowledgeChunk.created_at.desc()).limit(
        knowledge_api.MAX_SEARCH_CHUNKS
    )

    sql = str(query.compile(compile_kwargs={"literal_binds": True}))
    assert "LIMIT" in sql.upper()
    assert str(knowledge_api.MAX_SEARCH_CHUNKS) in sql
    assert knowledge_api.MAX_SEARCH_CHUNKS > 0


@pytest.mark.asyncio
async def test_search_query_applies_limit(monkeypatch):
    """端点构造的 chunk 查询必须真的带 limit，而不是只定义了常量。"""
    captured = {}

    class _FakeResult:
        def scalars(self):
            return self

        def all(self):
            return []

    class _FakeDB:
        async def execute(self, statement):
            captured.setdefault("statements", []).append(str(statement))
            return _FakeResult()

    async def _allow(user_id, db):
        return None

    async def _embedding(text, model=None):
        return [1.0, 0.0]

    monkeypatch.setattr(knowledge_api, "check_aicloud_permission", _allow)
    monkeypatch.setattr(knowledge_api, "get_embedding", _embedding)

    request = knowledge_api.KnowledgeSearchRequest(query="hello", top_k=5)
    result = await knowledge_api.search_knowledge(
        request=request, db=_FakeDB(), user_id=1
    )

    assert result["results"] == []
    chunk_stmt = captured["statements"][0]
    assert "LIMIT" in chunk_stmt.upper()
