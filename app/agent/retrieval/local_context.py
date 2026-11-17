"""Deterministic local retrieval for the legacy generation prompt path.

The retrieval service in this package accepts pluggable sources. This module
provides the local, network-free sources used by every per-file prompt so the
legacy chain consumes the same retrieval contract as the core adapters.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

ASCII_WORD_RE = re.compile(r"[a-zA-Z0-9_]+")
CJK_SEG_RE = re.compile(r"[\u4e00-\u9fff]+")

MAX_CHUNK_CHARS = 400
MAX_TOTAL_CHARS = 1600
MAX_CHUNKS = 4


def _tokenize(text: str) -> set[str]:
    tokens = {word.lower() for word in ASCII_WORD_RE.findall(text) if len(word) > 2}
    for segment in CJK_SEG_RE.findall(text):
        if len(segment) == 1:
            tokens.add(segment)
        else:
            tokens.update(segment[index:index + 2] for index in range(len(segment) - 1))
    return tokens


def _compact_json(value: Any, limit: int) -> str:
    if isinstance(value, str):
        return value[:limit]
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        rendered = str(value)
    return rendered[:limit]


def _iter_sources(
    project_context: Mapping[str, Any],
    file_plan: Iterable[Any],
) -> Iterable[tuple[str, str]]:
    architecture = project_context.get("architecture") or {}
    if not isinstance(architecture, Mapping):
        architecture = {}
    yield "architecture", _compact_json({
        key: architecture.get(key)
        for key in ("project_type", "tech_stack", "database", "api_endpoints", "framework", "language")
        if architecture.get(key)
    }, 600)
    api_contract = project_context.get("api_contract")
    if api_contract:
        yield "api_contract", _compact_json(api_contract, 600)
    profile = project_context.get("profile")
    if profile:
        yield "framework_profile", _compact_json(profile, 600)
    for item in file_plan:
        if not isinstance(item, Mapping):
            continue
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        description = str(item.get("description") or "").strip()
        yield f"file_plan:{path}", f"{path} {description}".strip()


def retrieve_local_chunks(
    file_path: str,
    project_context: Mapping[str, Any],
    file_plan: Iterable[Any] = (),
    *,
    limit: int = MAX_CHUNKS,
) -> list[dict[str, Any]]:
    """Rank local context sources for one target file.

    Returns compact chunks with provenance so the prompt can cite where each
    snippet came from. An empty corpus or empty query yields an empty list.
    """
    if limit < 1:
        return []
    architecture = project_context.get("architecture") or {}
    if not isinstance(architecture, Mapping):
        architecture = {}
    target_description = ""
    normalized = (file_path or "").replace("\\", "/")
    for item in file_plan:
        if isinstance(item, Mapping) and str(item.get("path") or "").replace("\\", "/") == normalized:
            target_description = str(item.get("description") or "")
            break
    query = " ".join(part for part in (
        normalized,
        target_description,
        str(project_context.get("requirement") or "")[:500],
    ) if part)
    query_terms = _tokenize(query)
    if not query_terms:
        return []

    scored: list[tuple[float, str, str]] = []
    seen_contents: set[str] = set()
    for source_id, content in _iter_sources(project_context, file_plan):
        normalized_content = content.strip()
        if not normalized_content or normalized_content in seen_contents:
            continue
        content_terms = _tokenize(normalized_content)
        if not content_terms:
            continue
        score = len(query_terms & content_terms) / len(query_terms)
        if score <= 0:
            continue
        seen_contents.add(normalized_content)
        scored.append((score, source_id, normalized_content))

    scored.sort(key=lambda entry: (-entry[0], entry[1]))
    chunks: list[dict[str, Any]] = []
    used_chars = 0
    for score, source_id, content in scored[:limit]:
        remaining = MAX_TOTAL_CHARS - used_chars
        if remaining <= 0:
            break
        snippet = content[:min(MAX_CHUNK_CHARS, remaining)]
        used_chars += len(snippet)
        chunks.append({
            "source": source_id,
            "content": snippet,
            "score": round(score, 3),
        })
    return chunks
