"""Auditable context assembly for generation and repair stages."""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any, Iterable, Mapping, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field

from app.agent.retrieval.models import RetrievalResult


class ContextSource(str, Enum):
    REQUIREMENT = "requirement"
    PLAN = "generation_plan"
    INTERFACE = "interface_registry"
    DEPENDENCY = "dependency_map"
    PROFILE = "framework_profile"
    RETRIEVAL = "retrieval"
    MEMORY = "memory"
    SKILL = "skill"
    FEEDBACK = "feedback"


class ContextItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: ContextSource
    source_id: str = Field(min_length=1)
    content: str = Field(min_length=1)
    priority: int = Field(default=50, ge=0, le=100)
    scope: str = "project"
    metadata: Mapping[str, Any] = Field(default_factory=dict)
    content_hash: str = Field(min_length=64, max_length=64)


class ContextEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    file_path: Optional[str] = None
    items: Tuple[ContextItem, ...] = ()
    context_hash: str = Field(min_length=64, max_length=64)
    redacted_count: int = Field(default=0, ge=0)


class SkillPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    stage: str = Field(min_length=1)
    priority: int = Field(default=50, ge=0, le=100)
    languages: Tuple[str, ...] = ()
    frameworks: Tuple[str, ...] = ()
    hard_constraints: Tuple[str, ...] = ()
    validation_rules: Tuple[str, ...] = ()


class MCPToolDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1)
    capability: str = Field(min_length=1)
    read_scopes: Tuple[str, ...] = ()
    write_scopes: Tuple[str, ...] = ()
    project_scope: Optional[str] = None
    dependencies: Tuple[str, ...] = ()
    timeout_seconds: int = Field(default=60, ge=1, le=600)
    audited: bool = True

    def allows(self, operation: str, scope: str) -> bool:
        allowed = self.write_scopes if operation == "write" else self.read_scopes
        return scope in allowed


class ContextAssembler:
    """Order, deduplicate, redact, and hash context from controlled sources."""

    def __init__(self, *, max_chars: int = 24000) -> None:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        self.max_chars = max_chars

    def assemble(
        self,
        *,
        task_id: str,
        stage: str,
        file_path: Optional[str] = None,
        items: Iterable[Mapping[str, Any] | ContextItem] = (),
        retrieval: Optional[RetrievalResult] = None,
        memory_entries: Iterable[Any] = (),
        mcp_tools: Optional[Mapping[str, Mapping[str, Any]]] = None,
    ) -> ContextEnvelope:
        candidates = [self._coerce(item) for item in items]
        if retrieval is not None:
            candidates.extend(
                self._item(
                    ContextSource.RETRIEVAL,
                    chunk.source_id,
                    chunk.content,
                    priority=min(100, max(0, int(chunk.score * 100))),
                    scope=str(chunk.metadata.get("project_scope", "project")),
                    metadata={"source_type": chunk.source_type, "retrieval_hash": chunk.content_hash},
                )
                for chunk in retrieval.chunks
            )
        candidates.extend(
            self._item(
                ContextSource.MEMORY,
                str(getattr(entry, "id", None) or index),
                str(getattr(entry, "content", "")),
                priority=min(100, max(0, int(float(getattr(entry, "importance", 0.5)) * 100))),
                scope=str(getattr(entry, "metadata", {}).get("project_scope", "project")),
                metadata={"memory_type": getattr(entry, "type", "unknown")},
            )
            for index, entry in enumerate(memory_entries)
            if str(getattr(entry, "content", "")).strip()
        )
        candidates.extend(
            self._item(
                ContextSource.SKILL if details.get("kind") == "skill" else ContextSource.FEEDBACK,
                name,
                json.dumps(details, ensure_ascii=False, sort_keys=True, default=str),
                priority=int(details.get("priority", 60)),
                scope=str(details.get("project_scope", "project")),
                metadata={"capability": details.get("capability", "mcp")},
            )
            for name, details in (mcp_tools or {}).items()
        )
        ordered = sorted(candidates, key=lambda item: (-item.priority, item.source.value, item.source_id))
        selected = []
        seen = set()
        used_chars = 0
        redacted_count = 0
        for item in ordered:
            if item.content_hash in seen:
                continue
            redacted, count = _redact_secrets(item.content)
            redacted_count += count
            remaining = self.max_chars - used_chars
            if remaining <= 0:
                break
            content = redacted[:remaining]
            if not content.strip():
                continue
            normalized = self._item(
                item.source, item.source_id, content, priority=item.priority,
                scope=item.scope, metadata=item.metadata,
            )
            selected.append(normalized)
            seen.add(normalized.content_hash)
            used_chars += len(content)
        payload = [item.model_dump(mode="json") for item in selected]
        return ContextEnvelope(
            task_id=task_id,
            stage=stage,
            file_path=file_path,
            items=tuple(selected),
            context_hash=_hash({"task_id": task_id, "stage": stage, "file_path": file_path, "items": payload}),
            redacted_count=redacted_count,
        )

    def _coerce(self, item: Mapping[str, Any] | ContextItem) -> ContextItem:
        if isinstance(item, ContextItem):
            return item
        return self._item(
            ContextSource(item["source"]), str(item["source_id"]), str(item["content"]),
            priority=int(item.get("priority", 50)), scope=str(item.get("scope", "project")),
            metadata=dict(item.get("metadata", {})),
        )

    @staticmethod
    def _item(
        source: ContextSource, source_id: str, content: str, *, priority: int,
        scope: str, metadata: Mapping[str, Any],
    ) -> ContextItem:
        return ContextItem(
            source=source, source_id=source_id, content=content, priority=priority,
            scope=scope, metadata=metadata, content_hash=_hash(content),
        )


_SECRET_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|token|password|secret)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)bearer\s+[a-z0-9._~+/-]+=*"),
)


def _redact_secrets(content: str) -> tuple[str, int]:
    count = 0
    for pattern in _SECRET_PATTERNS:
        content, replacements = pattern.subn("[REDACTED]", content)
        count += replacements
    return content, count


def _hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = ["ContextAssembler", "ContextEnvelope", "ContextItem", "ContextSource", "MCPToolDescriptor", "SkillPolicy"]
