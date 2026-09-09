"""Quality-mode orchestration shared by standard and refined PPT generation."""

from collections.abc import Awaitable, Callable
from typing import Any

from app.utils.pptx.quality import AutoReflowEngine, QualityReport, check_deck

VISION_CONFIDENCE_THRESHOLD = 0.70


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

    if quality_mode == "refined":
        await append_visual_review(fixed_slides, report, vision_reviewer)
    return fixed_slides, report


async def append_visual_review(slides, report, vision_reviewer=None):
    """Append review findings without rerunning reflow on the rendered deck."""
    try:
        if vision_reviewer is None:
            raise RuntimeError("视觉复审服务未配置")
        for slide in slides:
            visual_issues = await vision_reviewer(slide)
            report.issues.extend(visual_issues)
            if any(
                issue.get("confidence") is not None and float(issue["confidence"]) < VISION_CONFIDENCE_THRESHOLD
                for issue in visual_issues
            ):
                report.issues.append({
                    "issue_type": "vision_review_low_confidence",
                    "severity": "low",
                    "slide_id": slide.get("id", slide.get("slide_id")),
                    "message": "视觉复审置信度较低，建议人工复核",
                })
    except Exception:
        report.issues.append({
            "issue_type": "vision_review_unavailable",
            "severity": "medium",
            "message": "视觉复审未完成，已保留标准检查结果；请检查用户模型凭据、渲染依赖或模型服务。",
        })


async def review_rendered_deck(pptx_path, slides, report, api_key_token, user_id, slide_count=None):
    """Review actual PDF pixels using the existing user-authenticated vision service."""
    import asyncio
    import base64
    import json
    import subprocess
    from app.api.v1.aiGeneratorPptx import _content_slides_for_total

    pdf_path = pptx_path.with_suffix(".pdf")
    prepared = False
    rendered_slides = _content_slides_for_total(slides, slide_count)

    async def reviewer(slide):
        nonlocal prepared
        if not api_key_token:
            raise RuntimeError("需要用户视觉模型凭据")
        if not pptx_path.is_file():
            raise RuntimeError("当前输出格式不支持成品视觉复审")
        if not prepared:
            from app.api.v1.aiGeneratorPptx import _convert_pptx_to_pdf

            await _convert_pptx_to_pdf(pptx_path, pdf_path)
            prepared = True
        page = slide["rendered_page"]
        rendered = await asyncio.to_thread(
            subprocess.run,
            ["pdftoppm", "-f", str(page), "-l", str(page), "-singlefile", "-scale-to", "1280", "-png", str(pdf_path)],
            capture_output=True, check=True, timeout=30,
        )
        if not rendered.stdout.startswith(b"\x89PNG"):
            raise RuntimeError("页面渲染失败")
        from app.agent.models import DEFAULT_VISUAL_MODEL
        from app.utils.vision import _call_vision_model
        from httpx import Timeout

        response = await _call_vision_model(
            image_base64="data:image/png;base64," + base64.b64encode(rendered.stdout).decode("ascii"),
            prompt='检查此成品幻灯片的文本溢出、重叠、对比度和图片变形。仅返回 JSON 对象：{"issues": [{"issue_type": "text_overflow", "severity": "high", "message": "具体问题", "confidence": 0.9}]}。无问题返回 {"issues": []}。',
            model=DEFAULT_VISUAL_MODEL, timeout=Timeout(60),
            api_key_token=api_key_token, user_id=user_id,
        )
        payload = json.loads(response)
        issues = payload["issues"]
        if not isinstance(issues, list):
            raise ValueError("Invalid visual review")
        findings = []
        for issue in issues:
            if not isinstance(issue, dict) or not issue.get("issue_type") or not issue.get("message"):
                raise ValueError("Invalid visual issue")
            confidence = float(issue.get("confidence", 0))
            if not 0 <= confidence <= 1 or issue.get("severity") not in {"low", "medium", "high"}:
                raise ValueError("Invalid visual confidence or severity")
            findings.append({**issue, "slide_id": slide["id"], "confidence": confidence})
        return findings

    # Include the generated cover, which is absent from the semantic slide list.
    cover = {"id": "__cover__", "rendered_page": 1}
    await append_visual_review([
        cover,
        *({**slide, "rendered_page": index + 2} for index, slide in enumerate(rendered_slides)),
    ], report, reviewer)
