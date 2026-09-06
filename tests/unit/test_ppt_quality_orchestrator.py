import pytest

from app.services.ppt_quality_orchestrator import run_quality_pipeline


@pytest.mark.asyncio
async def test_refined_mode_contains_standard_quality_checks():
    seen = []

    async def reviewer(slide):
        seen.append(slide["id"])
        return [{"issue_type": "visual_balance", "slide_id": slide["id"]}]

    slides, report = await run_quality_pipeline(
        [{"id": "slide-1", "layout": "content_only", "elements": []}],
        "refined",
        reviewer,
    )
    assert slides[0]["id"] == "slide-1"
    assert seen == ["slide-1"]
    assert any(issue.get("issue_type") == "visual_balance" for issue in report.issues)


@pytest.mark.asyncio
async def test_refined_mode_degrades_when_vision_review_fails():
    async def reviewer(_slide):
        raise RuntimeError("service unavailable")

    _, report = await run_quality_pipeline(
        [{"id": "slide-1", "layout": "content_only", "elements": []}],
        "refined",
        reviewer,
    )
    assert any(issue["issue_type"] == "vision_review_unavailable" for issue in report.issues)


@pytest.mark.asyncio
async def test_refined_mode_marks_low_confidence_for_manual_review():
    async def reviewer(_slide):
        return [{"issue_type": "visual_balance", "confidence": 0.42}]

    _, report = await run_quality_pipeline(
        [{"id": "slide-1", "layout": "content_only", "elements": []}],
        "refined",
        reviewer,
    )
    assert any(issue["issue_type"] == "vision_review_low_confidence" for issue in report.issues)


@pytest.mark.asyncio
async def test_refined_mode_marks_confidence_below_seventy_percent():
    async def reviewer(_slide):
        return [{"issue_type": "visual_balance", "confidence": 0.65}]

    _, report = await run_quality_pipeline(
        [{"id": "slide-1", "layout": "content_only", "elements": []}],
        "refined",
        reviewer,
    )
    assert any(issue["issue_type"] == "vision_review_low_confidence" for issue in report.issues)


@pytest.mark.asyncio
async def test_pipeline_returns_reflowed_slide_artifact():
    source_slides = [{
            "id": "slide-1",
            "layout": "content_only",
            "safe_margin": 0.5,
            "elements": [{"id": "title", "type": "text", "left": 0.1, "top": 0.1, "width": 4, "height": 1}],
        }]
    slides, report = await run_quality_pipeline(
        source_slides,
        "standard",
    )
    assert slides[0] is not source_slides[0]
    assert slides[0]["elements"][0]["left"] == 0.5
    assert slides[0]["elements"][0]["top"] == 0.5
    assert report.reflow_attempts["slide-1"] == 1
