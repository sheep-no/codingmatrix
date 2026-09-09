"""Deterministic manifests and pixel comparisons for PPT preview baselines."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def build_baseline_manifest(slides: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a stable, reviewable manifest from semantic slide metadata."""
    normalized = []
    for index, slide in enumerate(slides, start=1):
        metadata = slide.get("render_metadata", {})
        normalized.append({
            "index": index,
            "id": str(slide.get("id", f"slide-{index}")),
            "slide_type": metadata.get("slide_type", slide.get("slide_type", slide.get("type", "key_points"))),
            "layout": slide.get("layout", metadata.get("layout")),
            "token_version": metadata.get("token_version", "1.0"),
            "element_count": len(slide.get("elements", [])),
            "grid": metadata.get("grid", {}),
        })
    payload = json.dumps(normalized, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return {"version": "1", "slide_count": len(normalized), "slides": normalized, "sha256": hashlib.sha256(payload.encode()).hexdigest()}


def write_baseline_manifest(path: str | Path, slides: list[dict[str, Any]]) -> dict[str, Any]:
    """Write a baseline manifest and return the generated content."""
    manifest = build_baseline_manifest(slides)
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(manifest, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    return manifest


def compare_baseline_manifest(expected: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    """Return a compact diff summary suitable for CI output."""
    expected_slides = expected.get("slides", [])
    actual_slides = actual.get("slides", [])
    changed = []
    for index in range(max(len(expected_slides), len(actual_slides))):
        before = expected_slides[index] if index < len(expected_slides) else None
        after = actual_slides[index] if index < len(actual_slides) else None
        if before != after:
            changed.append({"index": index + 1, "expected": before, "actual": after})
    return {"matches": not changed and expected.get("slide_count") == actual.get("slide_count"), "changed_slides": changed}


def compare_images(expected_path: str | Path, actual_path: str | Path, threshold: float = 0.01) -> dict[str, Any]:
    """Compare two rendered pages and report the changed pixel ratio."""
    from PIL import Image, ImageChops

    expected = Image.open(expected_path).convert("RGB")
    actual = Image.open(actual_path).convert("RGB")
    if expected.size != actual.size:
        return {"matches": False, "changed_ratio": 1.0, "reason": "image_size_mismatch", "expected_size": expected.size, "actual_size": actual.size}
    diff = ImageChops.difference(expected, actual)
    changed = sum(1 for pixel in diff.getdata() if pixel != (0, 0, 0))
    total = expected.width * expected.height
    ratio = changed / total if total else 0.0
    return {"matches": ratio <= threshold, "changed_ratio": ratio, "threshold": threshold}
