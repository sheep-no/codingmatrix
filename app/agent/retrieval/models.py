"""Serializable request and result models for project context retrieval."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    project_scope: Optional[str] = None
    session_scope: Optional[str] = None
    source_filters: List[str] = field(default_factory=list)
    limit: int = 5

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query must not be empty")
        if self.limit < 1:
            raise ValueError("limit must be greater than zero")


@dataclass(frozen=True)
class RetrievalChunk:
    content: str
    source_type: str
    source_id: str
    score: float = 0.0
    content_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    retrieved_at: str = field(default_factory=_utc_now)

    def __post_init__(self) -> None:
        if not self.content_hash:
            object.__setattr__(
                self,
                "content_hash",
                hashlib.sha256(self.content.encode("utf-8")).hexdigest(),
            )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalResult:
    chunks: List[RetrievalChunk] = field(default_factory=list)
    degraded: bool = False
    fallback_mode: Optional[str] = None
    errors: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "chunks": [chunk.to_dict() for chunk in self.chunks],
            "degraded": self.degraded,
            "fallback_mode": self.fallback_mode,
            "errors": list(self.errors),
        }
