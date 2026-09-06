"""Deterministic orchestration stage and terminal-state transitions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from .models import OrchestrationStage, OrchestrationState, OrchestrationStatus, utc_now


class InvalidOrchestrationTransition(RuntimeError):
    """Raised when a lifecycle transition violates the state graph."""


class OrchestrationRevisionConflict(RuntimeError):
    """Raised when a transition was created from an obsolete revision."""


ALLOWED_TRANSITIONS = {
    OrchestrationStage.CREATED: OrchestrationStage.PLANNING,
    OrchestrationStage.PLANNING: OrchestrationStage.SCHEDULING,
    OrchestrationStage.SCHEDULING: OrchestrationStage.GENERATING,
    OrchestrationStage.GENERATING: OrchestrationStage.PERSISTING,
    OrchestrationStage.PERSISTING: OrchestrationStage.VALIDATING,
    OrchestrationStage.VALIDATING: OrchestrationStage.FINALIZING,
}


def _validate_event(
    state: OrchestrationState,
    event_id: str,
    expected_revision: int,
) -> bool:
    if not event_id:
        raise ValueError("event_id must be non-empty")
    if event_id in state.applied_event_ids:
        return False
    if expected_revision != state.revision:
        raise OrchestrationRevisionConflict(
            f"expected revision {expected_revision}, current revision {state.revision}"
        )
    if state.status.is_terminal:
        raise InvalidOrchestrationTransition(
            f"task is already terminal with status {state.status.value}"
        )
    return True


def _updated_state(state: OrchestrationState, **updates: Any) -> OrchestrationState:
    values = state.model_dump(mode="python")
    values.update(updates)
    return OrchestrationState.model_validate(values)


def advance_state(
    state: OrchestrationState,
    target_stage: OrchestrationStage,
    *,
    event_id: str,
    expected_revision: int,
    resume_cursor: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
) -> OrchestrationState:
    """Advance exactly one lifecycle stage and persist its idempotency key."""
    if not _validate_event(state, event_id, expected_revision):
        return state

    expected_target = ALLOWED_TRANSITIONS.get(state.stage)
    if target_stage != expected_target:
        raise InvalidOrchestrationTransition(
            f"cannot transition from {state.stage.value} to {target_stage.value}"
        )

    timestamp = occurred_at or utc_now()
    return _updated_state(
        state,
        stage=target_stage,
        revision=state.revision + 1,
        stage_started_at=timestamp,
        last_activity_at=timestamp,
        resume_cursor=resume_cursor,
        applied_event_ids=(*state.applied_event_ids, event_id),
        metadata={**state.metadata, **(metadata or {})},
    )


def terminate_state(
    state: OrchestrationState,
    status: OrchestrationStatus,
    *,
    event_id: str,
    expected_revision: int,
    diagnostic: Optional[Dict[str, Any]] = None,
    occurred_at: Optional[datetime] = None,
) -> OrchestrationState:
    """Set the task's single terminal status and terminal event identifier."""
    if not _validate_event(state, event_id, expected_revision):
        return state
    if not status.is_terminal:
        raise InvalidOrchestrationTransition("terminal transition requires a terminal status")
    if status is OrchestrationStatus.COMPLETED and state.stage is not OrchestrationStage.FINALIZING:
        raise InvalidOrchestrationTransition("completed is only valid from finalizing")

    timestamp = occurred_at or utc_now()
    diagnostics = state.diagnostics
    if diagnostic is not None:
        diagnostics = (*diagnostics, diagnostic)
    return _updated_state(
        state,
        status=status,
        revision=state.revision + 1,
        last_activity_at=timestamp,
        resume_cursor=None,
        terminal_event_id=event_id,
        applied_event_ids=(*state.applied_event_ids, event_id),
        diagnostics=diagnostics,
    )
