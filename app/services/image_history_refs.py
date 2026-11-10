"""Helpers for persisting generated image history references safely."""

from __future__ import annotations

from pathlib import Path


def filename_from_reference(reference: object) -> str | None:
    """Return the generated-image filename for a local path or data URL.

    Historical rows may contain base64 data URLs or absolute paths. New rows
    only persist the filename so the database row stays small and the file can
    be resolved against the configured output directory.
    """

    if not isinstance(reference, str):
        return None
    value = reference.strip()
    if not value or value.startswith("data:"):
        return None
    name = Path(value.split("?", 1)[0]).name
    return name or None


def normalize_image_references(references: object) -> list[str]:
    """Keep only resolvable generated-image filenames."""

    if not isinstance(references, (list, tuple)):
        return []
    normalized: list[str] = []
    for reference in references:
        name = filename_from_reference(reference)
        if name:
            normalized.append(name)
    return normalized


def resolve_reference(reference: object, root: str | Path) -> Path | None:
    """Resolve a history reference to a file inside ``root``."""

    name = filename_from_reference(reference)
    if not name:
        return None
    base = Path(root).resolve()
    target = (base / name).resolve()
    if target.parent != base:
        return None
    return target
