"""Serializable contracts for the orchestration lifecycle."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .budget import ExecutionBudget


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def default_execution_budget() -> ExecutionBudget:
    return ExecutionBudget(
        task_seconds=900,
        stage_seconds=600,
        file_seconds=180,
        model_call_seconds=120,
    )


class OrchestrationStage(str, Enum):
    CREATED = "created"
    PLANNING = "planning"
    SCHEDULING = "scheduling"
    GENERATING = "generating"
    PERSISTING = "persisting"
    VALIDATING = "validating"
    FINALIZING = "finalizing"


class OrchestrationStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"

    @property
    def is_terminal(self) -> bool:
        return self is not OrchestrationStatus.RUNNING


class OrchestrationCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    request: Dict[str, Any] = Field(default_factory=dict)
    engine_version: str = Field(default="core-v1", min_length=1)
    budgets: ExecutionBudget = Field(default_factory=default_execution_budget)


class OrchestrationState(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = Field(default=1, ge=1)
    task_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    engine_version: str = Field(min_length=1)
    mode: str = Field(min_length=1)
    stage: OrchestrationStage = OrchestrationStage.CREATED
    status: OrchestrationStatus = OrchestrationStatus.RUNNING
    revision: int = Field(default=0, ge=0)
    stage_started_at: datetime = Field(default_factory=utc_now)
    last_activity_at: datetime = Field(default_factory=utc_now)
    resume_cursor: Optional[str] = None
    terminal_event_id: Optional[str] = None
    applied_event_ids: Tuple[str, ...] = ()
    diagnostics: Tuple[Dict[str, Any], ...] = ()
    metadata: Dict[str, Any] = Field(default_factory=dict)
    budgets: ExecutionBudget = Field(default_factory=default_execution_budget)

    @model_validator(mode="after")
    def validate_terminal_state(self) -> "OrchestrationState":
        if self.status.is_terminal and not self.terminal_event_id:
            raise ValueError("terminal state requires terminal_event_id")
        if not self.status.is_terminal and self.terminal_event_id:
            raise ValueError("running state cannot have terminal_event_id")
        if self.terminal_event_id and self.terminal_event_id not in self.applied_event_ids:
            raise ValueError("terminal_event_id must be an applied event")
        if self.revision != len(self.applied_event_ids):
            raise ValueError("revision must equal the number of applied events")
        if len(set(self.applied_event_ids)) != len(self.applied_event_ids):
            raise ValueError("applied_event_ids must be unique")
        return self


class StageResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage: OrchestrationStage
    event_id: str = Field(min_length=1)
    next_stage: Optional[OrchestrationStage] = None
    resume_cursor: Optional[str] = None
    diagnostics: Tuple[Dict[str, Any], ...] = ()
    metadata: Dict[str, Any] = Field(default_factory=dict)


class OrchestrationResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state: OrchestrationState
    resumed: bool = False

    @property
    def is_terminal(self) -> bool:
        return self.state.status.is_terminal
