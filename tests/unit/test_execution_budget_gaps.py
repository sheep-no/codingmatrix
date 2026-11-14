"""execution_budget 层级校验、耗尽与截止时间补测。"""

from datetime import datetime, timedelta, timezone

import pytest

from app.agent.orchestration.budget import ExecutionBudget, ExecutionBudgetExhausted


def _budget(**overrides):
    values = dict(task_seconds=100, stage_seconds=50, file_seconds=20, model_call_seconds=10)
    values.update(overrides)
    return ExecutionBudget(**values)


def test_scope_order_validation():
    with pytest.raises(ValueError, match="file_seconds"):
        _budget(file_seconds=60)
    with pytest.raises(ValueError, match="stage_seconds"):
        _budget(stage_seconds=200)
    with pytest.raises(ValueError, match="model_call_seconds"):
        _budget(model_call_seconds=30)


def test_negative_elapsed_rejected():
    with pytest.raises(ValueError, match="non-negative"):
        _budget().remaining_model_seconds(task_elapsed_seconds=-1)


def test_remaining_uses_smallest_scope():
    budget = _budget()

    assert budget.remaining_model_seconds() == 10
    assert budget.remaining_model_seconds(model_elapsed_seconds=4) == 6


def test_exhausted_scope_reported():
    with pytest.raises(ExecutionBudgetExhausted) as info:
        _budget().remaining_model_seconds(stage_elapsed_seconds=50)

    assert info.value.scope == "stage"
    assert "stage" in str(info.value)


def test_model_deadline_uses_started_at():
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    deadline = _budget().model_deadline(started_at=started)

    assert deadline == started + timedelta(seconds=10)


def test_model_deadline_defaults_to_now():
    before = datetime.now(timezone.utc)
    deadline = _budget().model_deadline()
    assert deadline > before


def test_model_deadline_respects_elapsed():
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    deadline = _budget().model_deadline(
        started_at=started, task_elapsed_seconds=95
    )

    assert deadline == started + timedelta(seconds=5)
