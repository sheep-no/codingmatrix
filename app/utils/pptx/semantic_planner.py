"""Stable semantic slide planning and content capacity budgeting."""

from dataclasses import dataclass, field
from typing import Any, Iterable

from app.schema.ppt_outline import OutlineDraft, OutlineSlide


SLIDE_TYPES = (
    "cover", "agenda", "section", "key_points", "image_text", "data",
    "comparison", "timeline", "process", "summary", "closing",
)

LAYOUTS_BY_TYPE = {
    "cover": ("title_slide", "center_focus"),
    "agenda": ("content_only", "two_column"),
    "section": ("title_slide", "center_focus"),
    "key_points": ("content_only", "two_column"),
    "image_text": ("content_with_image", "two_column"),
    "data": ("content_only", "center_focus"),
    "comparison": ("two_column", "content_only"),
    "timeline": ("two_column", "content_only"),
    "process": ("two_column", "center_focus"),
    "summary": ("center_focus", "content_only"),
    "closing": ("title_slide", "center_focus"),
}

CAPACITY_BY_TYPE = {
    "cover": {"max_items": 1, "max_title_chars": 40, "max_body_chars": 80},
    "agenda": {"max_items": 6, "max_title_chars": 32, "max_body_chars": 240},
    "section": {"max_items": 1, "max_title_chars": 32, "max_body_chars": 120},
    "key_points": {"max_items": 6, "max_title_chars": 32, "max_body_chars": 360},
    "image_text": {"max_items": 4, "max_title_chars": 32, "max_body_chars": 260},
    "data": {"max_items": 8, "max_title_chars": 32, "max_body_chars": 300},
    "comparison": {"max_items": 6, "max_title_chars": 32, "max_body_chars": 300},
    "timeline": {"max_items": 6, "max_title_chars": 32, "max_body_chars": 280},
    "process": {"max_items": 6, "max_title_chars": 32, "max_body_chars": 280},
    "summary": {"max_items": 4, "max_title_chars": 32, "max_body_chars": 240},
    "closing": {"max_items": 1, "max_title_chars": 32, "max_body_chars": 120},
}


@dataclass(frozen=True)
class CapacityBudget:
    max_items: int
    max_title_chars: int
    max_body_chars: int
    title_chars: int
    body_chars: int
    item_count: int

    @property
    def exceeded(self) -> bool:
        return (
            self.title_chars > self.max_title_chars
            or self.body_chars > self.max_body_chars
            or self.item_count > self.max_items
        )


@dataclass(frozen=True)
class SlidePlan:
    slide_id: str
    position: int
    slide_type: str
    key_message: str
    layout_candidates: tuple[str, ...]
    capacity: CapacityBudget
    content_blocks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    adjustment_reason: str | None = None


def infer_slide_type(slide: OutlineSlide) -> str:
    """Map legacy or semantic slide labels to the supported type set."""
    candidate = (slide.slide_type or "").lower().replace("-", "_")
    aliases = {
        "title": "cover", "title_slide": "cover", "toc": "agenda",
        "content": "key_points", "bullet": "key_points", "image": "image_text",
        "chart": "data", "end": "closing", "thank_you": "closing",
    }
    if candidate in SLIDE_TYPES:
        return candidate
    if candidate in aliases:
        return aliases[candidate]
    combined = f"{slide.title} {slide.key_message}".lower()
    for keyword, slide_type in (("对比", "comparison"), ("流程", "process"), ("时间", "timeline"), ("数据", "data")):
        if keyword in combined:
            return slide_type
    return "key_points"


def _capacity(slide: OutlineSlide, slide_type: str) -> CapacityBudget:
    rules = CAPACITY_BY_TYPE[slide_type]
    body = "\n".join(block.content for block in slide.content_blocks)
    return CapacityBudget(
        max_items=rules["max_items"],
        max_title_chars=rules["max_title_chars"],
        max_body_chars=rules["max_body_chars"],
        title_chars=len(slide.title),
        body_chars=len(body),
        item_count=len(slide.content_blocks),
    )


def plan_outline(outline: OutlineDraft, planner_version: str = "1.0") -> list[SlidePlan]:
    """Create a deterministic plan while preserving slide and block order."""
    del planner_version  # Reserved for persistence and future planner versions.
    plans = []
    previous_layout: str | None = None
    repeated_layouts = 0
    for slide in sorted(outline.slides, key=lambda item: (item.position, item.id)):
        slide_type = infer_slide_type(slide)
        candidates = list(LAYOUTS_BY_TYPE[slide_type])
        if candidates[0] == previous_layout and repeated_layouts >= 2:
            candidates.append(candidates.pop(0))
        selected = candidates[0]
        repeated_layouts = repeated_layouts + 1 if selected == previous_layout else 1
        previous_layout = selected
        plans.append(SlidePlan(
            slide_id=slide.id,
            position=slide.position,
            slide_type=slide_type,
            key_message=slide.key_message,
            layout_candidates=tuple(candidates),
            capacity=_capacity(slide, slide_type),
            content_blocks=tuple(block.model_dump(mode="json") for block in slide.content_blocks),
            adjustment_reason=("页面类型已兼容映射" if slide_type != slide.slide_type else None),
        ))
    return plans


def split_content_blocks(blocks: Iterable[dict[str, Any]], max_items: int) -> list[list[dict[str, Any]]]:
    """Split blocks in source order for pages that exceed item capacity."""
    block_list = list(blocks)
    return [block_list[index:index + max_items] for index in range(0, len(block_list), max_items)] or [[]]
