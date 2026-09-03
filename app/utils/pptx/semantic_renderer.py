"""Deterministic semantic rendering metadata and asset rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


SLIDE_TYPES = (
    "cover", "agenda", "section", "key_points", "image_text", "data",
    "comparison", "timeline", "process", "summary", "closing",
)


@dataclass(frozen=True)
class ImagePlacement:
    width: float
    height: float
    crop_left: float = 0.0
    crop_top: float = 0.0
    fallback: bool = False


def normalize_slide_type(slide_type: str | None) -> str:
    value = (slide_type or "key_points").strip().lower()
    aliases = {"title": "cover", "content": "key_points", "chart": "data", "end": "closing"}
    return aliases.get(value, value if value in SLIDE_TYPES else "key_points")


def build_render_metadata(slide: dict[str, Any], *, token_version: str = "1.0") -> dict[str, Any]:
    """Return stable renderer metadata consumed by rendering and quality checks."""
    slide_type = normalize_slide_type(slide.get("slide_type", slide.get("type")))
    blocks = slide.get("content_blocks") or slide.get("blocks") or []
    return {
        "slide_id": str(slide.get("id", slide.get("slide_id", "unknown"))),
        "slide_type": slide_type,
        "token_version": token_version,
        "hierarchy": {"title": 32, "key_message": 24, "body": 14},
        "grid": {"margin": 0.5, "gutter": 0.25, "safe_area": 0.5},
        "content_block_count": len(blocks),
        "chart_type": select_chart_type(slide.get("data")) if slide_type == "data" else None,
        "source_placeholder": "数据来源：待补充" if slide_type == "data" else None,
    }


def fit_image(original_width: float, original_height: float, box_width: float, box_height: float, *, available: bool = True) -> ImagePlacement:
    """Fit an image into a box while preserving its aspect ratio."""
    if not available or original_width <= 0 or original_height <= 0:
        return ImagePlacement(box_width, box_height, fallback=True)
    scale = max(box_width / original_width, box_height / original_height)
    rendered_width = original_width * scale
    rendered_height = original_height * scale
    return ImagePlacement(
        rendered_width,
        rendered_height,
        crop_left=max(0.0, (rendered_width - box_width) / 2),
        crop_top=max(0.0, (rendered_height - box_height) / 2),
    )


def select_chart_type(data: Any) -> str:
    """Choose a chart from the relationship represented by structured data."""
    if not isinstance(data, dict):
        return "bar"
    relationship = str(data.get("relationship", "comparison")).lower()
    if relationship in {"trend", "time", "timeline"}:
        return "line"
    if relationship in {"share", "composition", "part_to_whole"}:
        return "donut"
    if relationship in {"correlation", "distribution"}:
        return "scatter"
    return "bar"
