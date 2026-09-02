"""Immutable hierarchical execution budgets for orchestration work."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

class ExecutionBudgetExhausted(TimeoutError):
    """Raised when a budget scope has no wall-clock time remaining."""

    def __init__(self, scope: str) -> None:
        super().__init__(f"{scope} execution budget is exhausted")
        self.scope = scope


class ExecutionBudget(BaseModel):
    """Maximum wall-clock durations for nested orchestration scopes."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    task_seconds: float = Field(gt=0)
    stage_seconds: float = Field(gt=0)
    file_seconds: float = Field(gt=0)
    model_call_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_scope_order(self) -> "ExecutionBudget":
        if self.file_seconds > self.stage_seconds:
            raise ValueError("file_seconds must be less than or equal to stage_seconds")
        if self.stage_seconds > self.task_seconds:
            raise ValueError("stage_seconds must be less than or equal to task_seconds")
        if self.model_call_seconds > self.file_seconds:
            raise ValueError("model_call_seconds must be less than or equal to file_seconds")
        return self

    def remaining_model_seconds(
        self,
        *,
        task_elapsed_seconds: float = 0.0,
        stage_elapsed_seconds: float = 0.0,
        file_elapsed_seconds: float = 0.0,
        model_elapsed_seconds: float = 0.0,
    ) -> float:
        elapsed: Dict[str, float] = {
            "task": task_elapsed_seconds,
            "stage": stage_elapsed_seconds,
            "file": file_elapsed_seconds,
            "model_call": model_elapsed_seconds,
        }
        if any(value < 0 for value in elapsed.values()):
            raise ValueError("elapsed durations must be non-negative")

        remaining: Tuple[Tuple[str, float], ...] = (
            ("task", self.task_seconds - task_elapsed_seconds),
            ("stage", self.stage_seconds - stage_elapsed_seconds),
            ("file", self.file_seconds - file_elapsed_seconds),
            ("model_call", self.model_call_seconds - model_elapsed_seconds),
        )
        scope, seconds = min(remaining, key=lambda item: item[1])
        if seconds <= 0:
            raise ExecutionBudgetExhausted(scope)
        return seconds

    def model_deadline(
        self,
        *,
        started_at: datetime | None = None,
        task_elapsed_seconds: float = 0.0,
        stage_elapsed_seconds: float = 0.0,
        file_elapsed_seconds: float = 0.0,
    ) -> datetime:
        started = started_at or datetime.now(timezone.utc)
        seconds = self.remaining_model_seconds(
            task_elapsed_seconds=task_elapsed_seconds,
            stage_elapsed_seconds=stage_elapsed_seconds,
            file_elapsed_seconds=file_elapsed_seconds,
        )
        return started + timedelta(seconds=seconds)
