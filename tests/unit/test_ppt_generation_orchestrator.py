import pytest

from app.services.ppt_generation_orchestrator import PPTGenerationOrchestrator


STAGES = ("planning", "assets", "rendering", "rule_qa", "reflow", "vision_qa")


@pytest.mark.asyncio
async def test_runs_stages_in_order_and_emits_progress():
    seen = []
    events = []

    async def handler(context, stage):
        seen.append(stage)
        context["last"] = stage
        return context

    result = await PPTGenerationOrchestrator(
        {stage: lambda context, stage=stage: handler(context, stage) for stage in STAGES},
        progress_callback=events.append,
    ).run({})

    assert result.status == "completed"
    assert seen == list(STAGES)
    assert [event["stage"] for event in events if event["status"] == "started"] == [*STAGES, "completed"]
    assert events[-1] == {"stage": "completed", "status": "completed", "progress": 1.0}


@pytest.mark.asyncio
async def test_cancellation_returns_cancelled_without_running_following_stage():
    seen = []
    checks = 0

    def cancel_check():
        nonlocal checks
        checks += 1
        return checks >= 3

    async def handler(context, stage):
        seen.append(stage)
        return context

    result = await PPTGenerationOrchestrator(
        {stage: lambda context, stage=stage: handler(context, stage) for stage in STAGES},
        cancel_check=cancel_check,
    ).run({})

    assert result.status == "cancelled"
    assert result.stage == "assets"
    assert seen == ["planning"]


@pytest.mark.asyncio
async def test_recovery_starts_at_requested_stage():
    seen = []

    async def handler(context, stage):
        seen.append(stage)
        return context

    result = await PPTGenerationOrchestrator(
        {stage: lambda context, stage=stage: handler(context, stage) for stage in STAGES}
    ).run({"planned": True}, start_stage="rendering")

    assert result.status == "completed"
    assert seen == ["rendering", "rule_qa", "reflow", "vision_qa"]


@pytest.mark.asyncio
async def test_failure_returns_failed_stage_and_error_for_recovery():
    seen = []

    async def failing_handler(context):
        seen.append("rendering")
        raise RuntimeError("render failed")

    result = await PPTGenerationOrchestrator(
        {"rendering": failing_handler}
    ).run({}, start_stage="rendering")

    assert result.status == "failed"
    assert result.stage == "rendering"
    assert result.error == "render failed"
    assert seen == ["rendering"]
