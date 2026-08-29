"""Deterministic state merge with revision and event idempotency checks."""

from __future__ import annotations

from dataclasses import replace
from typing import Set

from .models import State, StateDelta


class StateConflictError(RuntimeError):
    """Raised when a delta was produced from an obsolete state revision."""


class StateReducer:
    def __init__(self) -> None:
        self._applied_event_ids: Set[str] = set()

    def apply(self, state: State, delta: StateDelta) -> State:
        if delta.expected_revision != state.revision:
            raise StateConflictError(
                f"expected revision {delta.expected_revision}, current revision {state.revision}"
            )

        new_messages = [
            message for message in delta.messages
            if message.event_id not in self._applied_event_ids
        ]
        for message in new_messages:
            self._applied_event_ids.add(message.event_id)

        if delta.messages and not new_messages:
            return state

        return replace(
            state,
            revision=state.revision + 1,
            status=delta.status if delta.status is not None else state.status,
            messages=[*state.messages, *new_messages],
            planned_changes=[*state.planned_changes, *delta.planned_changes],
            generated_files=[*state.generated_files, *delta.generated_files],
            validation_results=[*state.validation_results, *delta.validation_results],
            pending_actions=(
                list(delta.replace_pending_actions)
                if delta.replace_pending_actions is not None
                else [*state.pending_actions, *delta.pending_actions]
            ),
            errors=[*state.errors, *delta.errors],
            metadata={**state.metadata, **delta.metadata},
        )
