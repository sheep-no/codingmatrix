"""Tests for strict Orchestrator Core lifecycle transitions."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.agent.orchestration import (
    InvalidOrchestrationTransition,
    OrchestrationRevisionConflict,
    OrchestrationStage,
    OrchestrationState,
    OrchestrationStatus,
    advance_state,
    terminate_state,
)


STAGE_SEQUENCE = [
    OrchestrationStage.CREATED,
    OrchestrationStage.PLANNING,
    OrchestrationStage.SCHEDULING,
    OrchestrationStage.GENERATING,
    OrchestrationStage.PERSISTING,
    OrchestrationStage.VALIDATING,
    OrchestrationStage.FINALIZING,
]


def make_state() -> OrchestrationState:
    return OrchestrationState(
        task_id="task-1",
        session_id="session-1",
        engine_version="core-v1",
        mode="traditional",
    )


def advance_to(target: OrchestrationStage) -> OrchestrationState:
    state = make_state()
    for stage in STAGE_SEQUENCE[1:]:
        state = advance_state(
            state,
            stage,
            event_id=f"event-{state.revision + 1}",
            expected_revision=state.revision,
        )
        if stage is target:
            break
    return state


def test_all_declared_stage_transitions_advance_revision() -> None:
    state = make_state()
    timestamp = datetime(2026, 8, 31, 10, 0, tzinfo=timezone.utc)

    for target in STAGE_SEQUENCE[1:]:
        previous_revision = state.revision
        state = advance_state(
            state,
            target,
            event_id=f"event-{previous_revision + 1}",
            expected_revision=previous_revision,
            occurred_at=timestamp,
        )

        assert state.stage is target
        assert state.revision == previous_revision + 1
        assert state.last_activity_at == timestamp
        assert state.stage_started_at == timestamp


def test_stage_transition_rejects_skipped_stage() -> None:
    with pytest.raises(InvalidOrchestrationTransition, match="created to scheduling"):
        advance_state(
            make_state(),
            OrchestrationStage.SCHEDULING,
            event_id="event-1",
            expected_revision=0,
        )


def test_stage_transition_rejects_stale_revision() -> None:
    with pytest.raises(OrchestrationRevisionConflict, match="expected revision 3"):
        advance_state(
            make_state(),
            OrchestrationStage.PLANNING,
            event_id="event-1",
            expected_revision=3,
        )


def test_duplicate_event_is_idempotent_after_revision_changes() -> None:
    state = advance_state(
        make_state(),
        OrchestrationStage.PLANNING,
        event_id="event-1",
        expected_revision=0,
    )

    duplicate = advance_state(
        state,
        OrchestrationStage.PLANNING,
        event_id="event-1",
        expected_revision=0,
    )

    assert duplicate is state
    assert duplicate.revision == 1


@pytest.mark.parametrize(
    "status",
    [
        OrchestrationStatus.FAILED,
        OrchestrationStatus.TIMED_OUT,
        OrchestrationStatus.CANCELLED,
    ],
)
def test_failure_terminal_statuses_are_allowed_from_active_stage(
    status: OrchestrationStatus,
) -> None:
    state = advance_to(OrchestrationStage.GENERATING)

    terminal = terminate_state(
        state,
        status,
        event_id="terminal-1",
        expected_revision=state.revision,
        diagnostic={"code": status.value},
    )

    assert terminal.status is status
    assert terminal.terminal_event_id == "terminal-1"
    assert terminal.resume_cursor is None
    assert terminal.diagnostics == ({"code": status.value},)


def test_completed_requires_finalizing_stage() -> None:
    with pytest.raises(InvalidOrchestrationTransition, match="only valid from finalizing"):
        terminate_state(
            advance_to(OrchestrationStage.GENERATING),
            OrchestrationStatus.COMPLETED,
            event_id="terminal-1",
            expected_revision=3,
        )


def test_terminal_state_preserves_first_terminal_event() -> None:
    state = advance_to(OrchestrationStage.FINALIZING)
    completed = terminate_state(
        state,
        OrchestrationStatus.COMPLETED,
        event_id="terminal-1",
        expected_revision=state.revision,
    )

    duplicate = terminate_state(
        completed,
        OrchestrationStatus.COMPLETED,
        event_id="terminal-1",
        expected_revision=state.revision,
    )
    assert duplicate is completed

    with pytest.raises(InvalidOrchestrationTransition, match="already terminal"):
        terminate_state(
            completed,
            OrchestrationStatus.FAILED,
            event_id="terminal-2",
            expected_revision=completed.revision,
        )


def test_state_validation_rejects_inconsistent_revision() -> None:
    with pytest.raises(ValidationError, match="number of applied events"):
        OrchestrationState(
            task_id="task-1",
            session_id="session-1",
            engine_version="core-v1",
            mode="traditional",
            revision=1,
        )
