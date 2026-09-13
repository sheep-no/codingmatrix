"""Dynamic file changes for feature and incremental generation."""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .project_snapshot import ProjectSnapshot


class ChangeAction(str, Enum):
    ADD = "add"
    MODIFY = "modify"
    DELETE = "delete"
    RENAME = "rename"


class FileChange(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    action: ChangeAction
    owner: str = ""
    reason: str = ""
    dependencies: tuple[str, ...] = ()
    previous_path: str | None = None


def collapse_change_items(
    changes: Iterable[Mapping[str, object] | FileChange],
    *,
    known_paths: Iterable[str] | None = None,
) -> list[dict[str, object]]:
    """Merge duplicate paths so one file appears once in a change plan."""
    known = {str(path) for path in (known_paths or ())}
    ordered: list[str] = []
    by_path: dict[str, dict[str, object]] = {}
    for raw in changes:
        item = raw.model_dump(mode="json") if isinstance(raw, FileChange) else dict(raw)
        path = str(item.get("path") or "").strip()
        if not path:
            continue
        if path not in by_path:
            ordered.append(path)
            by_path[path] = item
            continue
        by_path[path] = _merge_change_dicts(by_path[path], item, known)
    return [by_path[path] for path in ordered]


def _merge_change_dicts(
    first: Mapping[str, object],
    second: Mapping[str, object],
    known_paths: set[str],
) -> dict[str, object]:
    merged = dict(first)
    action = _merge_actions(
        str(first.get("action") or "modify"),
        str(second.get("action") or "modify"),
        str(first.get("path") or ""),
        known_paths,
    )
    merged["action"] = action
    reasons: list[str] = []
    for source in (first, second):
        for key in ("reason", "description"):
            value = str(source.get(key) or "").strip()
            if value and value not in reasons:
                reasons.append(value)
    if reasons:
        merged["reason"] = "; ".join(reasons)
        if first.get("description") or second.get("description"):
            merged["description"] = merged["reason"]
    dependencies: list[str] = []
    for source in (first, second):
        extra = source.get("dependencies") or source.get("depends_on") or ()
        for value in extra:
            text = str(value)
            if text and text not in dependencies:
                dependencies.append(text)
    if dependencies:
        merged["dependencies"] = dependencies
    if not merged.get("previous_path") and second.get("previous_path"):
        merged["previous_path"] = second.get("previous_path")
    if not merged.get("owner") and second.get("owner"):
        merged["owner"] = second.get("owner")
    return merged


def _merge_actions(first: str, second: str, path: str, known_paths: set[str]) -> str:
    if first == second:
        return first
    if "delete" in (first, second):
        return "delete"
    if path in known_paths:
        return "modify"
    if "add" in (first, second):
        return "add"
    return second


def expand_change_plan_for_missing_exports(
    changes: Iterable[Mapping[str, object] | FileChange],
    *,
    output_dir: Path,
    language_adapter: Any,
    known_files: Iterable[str],
) -> list[dict[str, object]]:
    """Add provider files whose currently imported symbols are missing on disk."""
    known = [str(path).replace("\\", "/") for path in known_files]
    existing = collapse_change_items(changes, known_paths=known)
    if language_adapter is None:
        return existing
    known_set = set(known)
    deleted = {
        str(item.get("path") or "").replace("\\", "/")
        for item in existing
        if str(item.get("action") or "") == "delete"
    }
    root = Path(output_dir)
    try:
        root_resolved = root.resolve()
    except OSError:
        return existing

    contents: dict[str, str] = {}
    for path in known:
        if path in deleted:
            continue
        target = root / path
        try:
            resolved = target.resolve()
            if not resolved.is_file() or not resolved.is_relative_to(root_resolved):
                continue
            contents[path] = resolved.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            continue

    definitions: dict[str, set[str]] = {}
    for path, content in contents.items():
        try:
            defs = language_adapter.extract_definitions(content) or {}
        except Exception:
            defs = {}
        definitions[path] = {str(name) for name in defs}

    missing_by_provider: dict[str, dict[str, set[str]]] = {}
    for importer, content in contents.items():
        try:
            imports = language_adapter.parse_imports(content, importer) or ()
        except Exception:
            continue
        for info in imports:
            symbols = [
                str(symbol)
                for symbol in (getattr(info, "symbols", None) or ())
                if symbol and symbol != "*"
            ]
            if not symbols:
                continue
            try:
                candidates = language_adapter.resolve_import_to_file(info, importer) or ()
            except Exception:
                continue
            provider = ""
            for candidate in candidates:
                normalized = str(candidate).replace("\\", "/")
                if normalized in known_set and normalized not in deleted:
                    provider = normalized
                    break
            if not provider:
                continue
            defined = definitions.get(provider, set())
            absent = [symbol for symbol in symbols if symbol not in defined]
            if not absent:
                continue
            bucket = missing_by_provider.setdefault(provider, {})
            for symbol in absent:
                bucket.setdefault(symbol, set()).add(importer)

    extras: list[dict[str, object]] = []
    for provider, symbol_importers in missing_by_provider.items():
        symbols = sorted(symbol_importers)
        importers = sorted({
            importer
            for names in symbol_importers.values()
            for importer in names
        })
        extra: dict[str, object] = {
            "action": "modify" if provider in known_set else "add",
            "path": provider,
            "reason": (
                f"provide missing export {', '.join(symbols)} "
                f"imported by {', '.join(importers)}"
            ),
        }
        infer = getattr(language_adapter, "infer_file_type", None)
        if callable(infer):
            try:
                extra["file_type"] = infer(provider)
            except Exception:
                pass
        extras.append(extra)
    if not extras:
        return existing
    return collapse_change_items([*existing, *extras], known_paths=known)


class ChangePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    base_revision: str = Field(min_length=1)
    version: int = Field(default=1, ge=1)
    changes: tuple[FileChange, ...] = ()
    digest: str = Field(min_length=64, max_length=64)

    @classmethod
    def build(
        cls,
        snapshot: ProjectSnapshot,
        changes: Iterable[Mapping[str, object] | FileChange],
        *,
        version: int = 1,
    ) -> "ChangePlan":
        collapsed = collapse_change_items(changes, known_paths=snapshot.hashes())
        normalized = tuple(
            item if isinstance(item, FileChange) else FileChange(
                path=str(item["path"]),
                action=ChangeAction(str(item.get("action", "modify"))),
                owner=str(item.get("owner", "")),
                reason=str(item.get("reason", "")),
                dependencies=tuple(str(value) for value in item.get("dependencies", ())),
                previous_path=str(item["previous_path"]) if item.get("previous_path") else None,
            )
            for item in collapsed
        )
        paths = [item.path for item in normalized]
        if len(paths) != len(set(paths)):
            raise ValueError("change plan paths must be unique")
        known = set(snapshot.hashes())
        for item in normalized:
            if item.action is ChangeAction.MODIFY and item.path not in known:
                raise ValueError(f"modified file is absent from snapshot: {item.path}")
            if item.action is ChangeAction.DELETE and item.path not in known:
                raise ValueError(f"deleted file is absent from snapshot: {item.path}")
            if item.action is ChangeAction.RENAME and item.previous_path not in known:
                raise ValueError(f"renamed source is absent from snapshot: {item.previous_path}")
        payload = {
            "base_revision": snapshot.revision,
            "version": version,
            "changes": [item.model_dump(mode="json") for item in normalized],
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return cls(base_revision=snapshot.revision, version=version, changes=normalized, digest=digest)

    @property
    def affected_files(self) -> tuple[str, ...]:
        return tuple(sorted({item.path for item in self.changes} | {
            item.previous_path for item in self.changes if item.previous_path
        }))

    def verify_untouched(self, snapshot: ProjectSnapshot, current: ProjectSnapshot) -> tuple[str, ...]:
        """Return files whose content changed outside the declared change scope."""
        before = snapshot.hashes()
        after = current.hashes()
        affected = set(self.affected_files)
        return tuple(sorted(
            path for path in set(before) | set(after)
            if path not in affected and before.get(path) != after.get(path)
        ))


__all__ = [
    "ChangeAction",
    "ChangePlan",
    "FileChange",
    "collapse_change_items",
    "expand_change_plan_for_missing_exports",
]
