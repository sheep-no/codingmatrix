"""Quality-mode orchestration shared by standard and refined PPT generation."""

from collections.abc import Awaitable, Callable
from typing import Any

from app.utils.pptx.quality import AutoReflowEngine, QualityReport, check_deck


async def run_quality_pipeline(
    slides: list[dict[str, Any]],
    quality_mode: str = "standard",
    vision_reviewer: Callable[[dict[str, Any]], Awaitable[list[dict[str, Any]]]] | None = None,
) -> tuple[list[dict[str, Any]], QualityReport]:
    """Run deterministic QA first and optionally append visual review."""
    report = check_deck(slides)
    fixed_slides = list(slides)
    reflow = AutoReflowEngine()
    for index, slide in enumerate(fixed_slides):
        slide_id = str(slide.get("id", slide.get("slide_id", "unknown")))
        issues = [issue for issue in report.issues if issue.slide_id == slide_id]
        if issues:
            fixed_slides[index] = reflow.reflow(slide, issues, report)

    if quality_mode == "refined" and vision_reviewer:
        try:
            for slide in fixed_slides:
                visual_issues = await vision_reviewer(slide)
                report.issues.extend(visual_issues)
                if any(
                    issue.get("confidence") is not None and float(issue["confidence"]) < 0.6
                    for issue in visual_issues
                ):
                    report.issues.append({
                        "issue_type": "vision_review_low_confidence",
                        "severity": "low",
                        "slide_id": slide.get("id", slide.get("slide_id")),
                        "message": "视觉复审置信度较低，建议人工复核",
                    })
        except Exception as exc:
            report.issues.append({
                "issue_type": "vision_review_unavailable",
                "severity": "medium",
                "message": "视觉复审服务不可用，已降级为标准模式",
                "error": str(exc),
            })
    return fixed_slides, report
