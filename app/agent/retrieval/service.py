"""Fan-out retrieval service with provenance, deduplication, and degradation."""

from __future__ import annotations

import inspect
from typing import Any, Awaitable, Callable, Dict, Iterable, List, Protocol

from .models import RetrievalChunk, RetrievalRequest, RetrievalResult


class Retriever(Protocol):
    source_type: str

    async def retrieve(self, request: RetrievalRequest) -> Iterable[Any]: ...


class CallableRetriever:
    """Adapt an existing sync or async source search function."""

    def __init__(self, source_type: str, search: Callable[..., Any]) -> None:
        if not source_type:
            raise ValueError("source_type must not be empty")
        self.source_type = source_type
        self._search = search

    async def retrieve(self, request: RetrievalRequest) -> Iterable[Any]:
        value = self._search(request)
        if inspect.isawaitable(value):
            value = await value
        return value or []


class RetrievalService:
    def __init__(self, retrievers: Iterable[Retriever] = ()) -> None:
        self._retrievers = list(retrievers)

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        selected = [
            retriever for retriever in self._retrievers
            if not request.source_filters
            or retriever.source_type in request.source_filters
        ]
        chunks: Dict[str, RetrievalChunk] = {}
        errors: List[Dict[str, Any]] = []

        for retriever in selected:
            try:
                raw_items = await retriever.retrieve(request)
                for item in raw_items:
                    chunk = self._normalize(item, retriever.source_type)
                    if not chunk or not self._in_scope(chunk, request):
                        continue
                    current = chunks.get(chunk.content_hash)
                    if current is None or chunk.score > current.score:
                        chunks[chunk.content_hash] = chunk
            except Exception as exc:
                errors.append({
                    "source": retriever.source_type,
                    "code": "retrieval.source_unavailable",
                    "message": str(exc),
                    "retryable": True,
                })

        ranked = sorted(chunks.values(), key=lambda chunk: chunk.score, reverse=True)
        return RetrievalResult(
            chunks=ranked[:request.limit],
            degraded=bool(errors),
            fallback_mode="partial_source_failure" if errors else None,
            errors=errors,
        )

    @staticmethod
    def _in_scope(chunk: RetrievalChunk, request: RetrievalRequest) -> bool:
        metadata = chunk.metadata
        project = metadata.get("project_scope")
        session = metadata.get("session_scope")
        return (
            (request.project_scope is None or project in (None, request.project_scope))
            and (request.session_scope is None or session in (None, request.session_scope))
        )

    @staticmethod
    def _normalize(item: Any, source_type: str) -> RetrievalChunk | None:
        if isinstance(item, RetrievalChunk):
            return item
        if isinstance(item, str):
            return RetrievalChunk(content=item, source_type=source_type, source_id="unknown")
        if isinstance(item, dict):
            data = dict(item)
            data.setdefault("source_type", source_type)
            data.setdefault("source_id", str(data.get("id", "unknown")))
            data.setdefault("content", "")
            data.setdefault("score", 0.0)
            data.setdefault("metadata", {})
            return RetrievalChunk(**{
                key: data[key]
                for key in ("content", "source_type", "source_id", "score", "metadata", "retrieved_at", "content_hash")
                if key in data
            }) if data["content"] else None
        return None
