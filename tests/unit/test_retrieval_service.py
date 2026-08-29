"""Tests for unified retrieval contracts and source fan-out."""

import pytest

from app.agent.retrieval import CallableRetriever, RetrievalChunk, RetrievalRequest, RetrievalService


@pytest.mark.asyncio
async def test_retrieval_deduplicates_by_content_hash_and_keeps_best_score() -> None:
    async def first(_request):
        return [RetrievalChunk("same context", "memory", "m-1", score=0.4)]

    async def second(_request):
        return [RetrievalChunk("same context", "knowledge", "k-1", score=0.9)]

    result = await RetrievalService([
        CallableRetriever("memory", first),
        CallableRetriever("knowledge", second),
    ]).retrieve(RetrievalRequest("context", limit=5))

    assert len(result.chunks) == 1
    assert result.chunks[0].score == 0.9
    assert result.chunks[0].source_type == "knowledge"


@pytest.mark.asyncio
async def test_retrieval_returns_degraded_result_for_source_failure() -> None:
    async def broken(_request):
        raise RuntimeError("index unavailable")

    result = await RetrievalService([CallableRetriever("vector", broken)]).retrieve(
        RetrievalRequest("query")
    )

    assert result.degraded is True
    assert result.fallback_mode == "partial_source_failure"
    assert result.errors[0]["code"] == "retrieval.source_unavailable"


def test_retrieval_request_validates_query_and_limit() -> None:
    with pytest.raises(ValueError):
        RetrievalRequest(" ")
    with pytest.raises(ValueError):
        RetrievalRequest("query", limit=0)


@pytest.mark.asyncio
async def test_retrieval_filters_sources_and_scopes_and_applies_limit() -> None:
    def memory_source(_request):
        return [
            {"content": "project context", "id": "p", "score": 0.8,
             "metadata": {"project_scope": "project-1"}},
            {"content": "other project", "id": "o", "score": 1.0,
             "metadata": {"project_scope": "project-2"}},
        ]

    async def knowledge_source(_request):
        return ["knowledge context"]

    result = await RetrievalService([
        CallableRetriever("memory", memory_source),
        CallableRetriever("knowledge", knowledge_source),
    ]).retrieve(
        RetrievalRequest(
            "context",
            project_scope="project-1",
            source_filters=["memory"],
            limit=1,
        )
    )

    assert [chunk.content for chunk in result.chunks] == ["project context"]
    assert result.degraded is False


@pytest.mark.asyncio
async def test_retrieval_normalizes_strings_and_preserves_provenance() -> None:
    result = await RetrievalService([
        CallableRetriever("memory", lambda _request: ["plain context"]),
    ]).retrieve(RetrievalRequest("context"))

    assert result.chunks[0].source_type == "memory"
    assert result.chunks[0].source_id == "unknown"
    assert len(result.chunks[0].content_hash) == 64


@pytest.mark.asyncio
async def test_retrieval_keeps_successful_sources_when_one_returns_empty() -> None:
    async def empty(_request):
        return None

    async def successful(_request):
        return [{"content": "available", "score": 0.2, "source_id": "s-1"}]

    result = await RetrievalService([
        CallableRetriever("empty", empty),
        CallableRetriever("memory", successful),
    ]).retrieve(RetrievalRequest("context"))

    assert result.degraded is False
    assert result.chunks[0].source_id == "s-1"
