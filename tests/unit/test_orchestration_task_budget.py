"""任务级预算必须从 Core 透传到调度器。"""

from datetime import timedelta

import pytest

from app.agent.orchestration import (
    ArtifactCommitter,
    ExecutionBudget,
    GenerationScheduler,
    GenerationScheduleStatus,
    build_file_plan,
)
from app.agent.orchestration.core import _elapsed_since
from app.agent.orchestration.models import utc_now
from app.agent.shared_context import SharedContext


def test_elapsed_since_handles_missing_and_invalid_values():
    assert _elapsed_since(None) == 0.0
    assert _elapsed_since("not-a-timestamp") == 0.0


def test_elapsed_since_measures_task_age():
    started = utc_now() - timedelta(seconds=30)

    assert 29 <= _elapsed_since(started.isoformat()) < 60


@pytest.mark.asyncio
async def test_scheduler_times_out_when_task_budget_is_already_spent(tmp_path):
    context = SharedContext("task", tmp_path)
    scheduler = GenerationScheduler(
        ArtifactCommitter(tmp_path, context, task_id="task-budget"),
    )
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    async def generator(_context):
        raise AssertionError("generator must not run once the task budget is gone")

    result = await scheduler.run(
        plan,
        generator,
        ExecutionBudget(
            task_seconds=10,
            stage_seconds=10,
            file_seconds=5,
            model_call_seconds=5,
        ),
        task_id="task-budget",
        stage_id="stage-budget",
        task_elapsed_seconds=11,
    )

    assert result.status is GenerationScheduleStatus.TIMED_OUT
