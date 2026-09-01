"""Lifecycle coordinator for versioned orchestration state."""

from __future__ import annotations

from typing import Any, Dict, Optional

from .artifact_committer import ArtifactConsistencyResult
from .generation_scheduler import GenerationScheduleResult, GenerationScheduleStatus
from .models import (
    OrchestrationCommand,
    OrchestrationResult,
    OrchestrationStage,
    OrchestrationState,
    OrchestrationStatus,
)
from .state_machine import advance_state, terminate_state
from .store import OrchestrationStore


class OrchestratorCore:
    """Create, transition, terminate, and resume orchestration tasks."""

    def __init__(self, store: OrchestrationStore) -> None:
        self.store = store

    async def run(self, command: OrchestrationCommand) -> OrchestrationResult:
        existing = await self.store.load_latest(command.task_id)
        if existing is not None:
            return OrchestrationResult(state=existing, resumed=True)

        created = OrchestrationState(
            task_id=command.task_id,
            session_id=command.session_id,
            engine_version=command.engine_version,
            mode=command.mode,
            budgets=command.budgets,
            metadata={"request": command.request},
        )
        state = advance_state(
            created,
            OrchestrationStage.PLANNING,
            event_id=f"{command.task_id}:1:planning",
            expected_revision=0,
            resume_cursor=OrchestrationStage.PLANNING.value,
        )
        await self.store.save(state)
        return OrchestrationResult(state=state)

    async def advance(
        self,
        task_id: str,
        target_stage: OrchestrationStage,
        *,
        event_id: str,
        expected_revision: int,
        resume_cursor: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> OrchestrationResult:
        state = await self._require_state(task_id)
        updated = advance_state(
            state,
            target_stage,
            event_id=event_id,
            expected_revision=expected_revision,
            resume_cursor=resume_cursor,
            metadata=metadata,
        )
        if updated is not state:
            await self.store.save(updated)
        return OrchestrationResult(state=updated)

    async def finish(
        self,
        task_id: str,
        status: OrchestrationStatus,
        *,
        event_id: str,
        expected_revision: int,
        diagnostic: Optional[Dict[str, Any]] = None,
        artifact_consistency: Optional[ArtifactConsistencyResult] = None,
    ) -> OrchestrationResult:
        state = await self._require_state(task_id)
        if status is OrchestrationStatus.COMPLETED:
            if artifact_consistency is None:
                raise ValueError("completed status requires artifact consistency evidence")
            if not artifact_consistency.success:
                status = OrchestrationStatus.FAILED
                diagnostic = artifact_consistency.diagnostic.model_dump(mode="json")
        updated = terminate_state(
            state,
            status,
            event_id=event_id,
            expected_revision=expected_revision,
            diagnostic=diagnostic,
        )
        if updated is not state:
            await self.store.save(updated)
        return OrchestrationResult(state=updated)

    async def finish_schedule(
        self,
        task_id: str,
        schedule: GenerationScheduleResult,
        *,
        event_id: str,
        expected_revision: int,
        artifact_consistency: Optional[ArtifactConsistencyResult] = None,
    ) -> OrchestrationResult:
        """Map one scheduler result to the single task terminal transition."""
        if schedule.status is GenerationScheduleStatus.COMPLETED:
            return await self.finish(
                task_id,
                OrchestrationStatus.COMPLETED,
                event_id=event_id,
                expected_revision=expected_revision,
                artifact_consistency=artifact_consistency,
            )
        status = {
            GenerationScheduleStatus.CANCELLED: OrchestrationStatus.CANCELLED,
            GenerationScheduleStatus.TIMED_OUT: OrchestrationStatus.TIMED_OUT,
        }.get(schedule.status, OrchestrationStatus.FAILED)
        diagnostic = {
            "code": f"generation_schedule.{schedule.status.value}",
            "message": f"generation schedule ended with status {schedule.status.value}",
            "details": {"nodes": {path: node.status.value for path, node in schedule.nodes.items()}},
        }
        return await self.finish(
            task_id,
            status,
            event_id=event_id,
            expected_revision=expected_revision,
            diagnostic=diagnostic,
        )

    async def resume(self, task_id: str) -> OrchestrationResult:
        return OrchestrationResult(state=await self._require_state(task_id), resumed=True)

    async def cancel(
        self,
        task_id: str,
        reason: str,
        *,
        event_id: str,
        expected_revision: int,
    ) -> OrchestrationResult:
        return await self.finish(
            task_id,
            OrchestrationStatus.CANCELLED,
            event_id=event_id,
            expected_revision=expected_revision,
            diagnostic={"code": "orchestration.cancelled", "message": reason},
        )

    async def _require_state(self, task_id: str) -> OrchestrationState:
        state = await self.store.load_latest(task_id)
        if state is None:
            raise KeyError(f"orchestration task not found: {task_id}")
        return state
