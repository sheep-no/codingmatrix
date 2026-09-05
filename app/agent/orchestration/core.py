"""Lifecycle coordinator for versioned orchestration state."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Dict, Optional

from app.agent.shared_context import SharedContext

from .artifact_committer import (
    ArtifactConsistencyResult,
    ArtifactDiagnostic,
    ArtifactCommitter,
    ArtifactConsistencyResult,
    check_artifact_success_gate,
)
from .adapters import GenerationRequest
from .generation_scheduler import GenerationScheduleResult, GenerationScheduleStatus, GenerationScheduler
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

    async def execute(
        self,
        command: OrchestrationCommand,
        adapter: Any,
        *,
        output_dir: Path,
        shared_context: SharedContext,
        cancel_event: Optional[asyncio.Event] = None,
        max_concurrent: int = 5,
    ) -> OrchestrationResult:
        """Run an adapter through the complete Core lifecycle and success gate."""
        started = await self.run(command)
        if started.resumed and started.state.status.is_terminal:
            return started
        if started.resumed and started.state.stage is not OrchestrationStage.PLANNING:
            return await self.finish(
                command.task_id,
                OrchestrationStatus.FAILED,
                event_id=f"{command.task_id}:{started.state.revision + 1}:resume_failed",
                expected_revision=started.state.revision,
                diagnostic={
                    "code": "orchestration.resume_stage_unsupported",
                    "message": f"cannot resume execution from stage {started.state.stage.value}",
                },
            )
        if cancel_event is not None and cancel_event.is_set():
            return await self.cancel(
                command.task_id,
                "generation was cancelled before planning",
                event_id=f"{command.task_id}:{started.state.revision + 1}:cancelled",
                expected_revision=started.state.revision,
            )

        request = command.request
        try:
            plan = await adapter.create_plan(GenerationRequest(
                requirement=str(request.get("requirement", "")),
                task_id=command.task_id,
                session_id=command.session_id,
                metadata=request,
            ))
        except asyncio.CancelledError:
            return await self.cancel(
                command.task_id,
                "planning was cancelled",
                event_id=f"{command.task_id}:2:cancelled",
                expected_revision=started.state.revision,
            )
        except Exception as exc:
            return await self.finish(
                command.task_id,
                OrchestrationStatus.FAILED,
                event_id=f"{command.task_id}:2:planning_failed",
                expected_revision=started.state.revision,
                diagnostic={
                    "code": "orchestration.planning_failed",
                    "message": str(exc),
                },
            )
        state = (await self.advance(
            command.task_id,
            OrchestrationStage.SCHEDULING,
            event_id=f"{command.task_id}:2:scheduling",
            expected_revision=started.state.revision,
            metadata={"plan_paths": [item.path for item in plan.files]},
        )).state
        state = (await self.advance(
            command.task_id,
            OrchestrationStage.GENERATING,
            event_id=f"{command.task_id}:3:generating",
            expected_revision=state.revision,
        )).state

        committer = ArtifactCommitter(
            output_dir,
            shared_context,
            task_id=command.task_id,
        )
        schedule = await GenerationScheduler(
            committer,
            max_concurrent=max_concurrent,
        ).run(
            plan,
            adapter.generate_file,
            command.budgets,
            task_id=command.task_id,
            stage_id=f"{command.task_id}:generating",
            cancel_event=cancel_event,
        )
        state = (await self.advance(
            command.task_id,
            OrchestrationStage.PERSISTING,
            event_id=f"{command.task_id}:4:persisting",
            expected_revision=state.revision,
            metadata={"schedule": schedule.model_dump(mode="json")},
        )).state
        state = (await self.advance(
            command.task_id,
            OrchestrationStage.VALIDATING,
            event_id=f"{command.task_id}:5:validating",
            expected_revision=state.revision,
        )).state
        transaction = None
        change_plan = getattr(adapter, "change_plan", None)
        if schedule.status is GenerationScheduleStatus.COMPLETED and change_plan is not None:
            from .file_transaction import IncrementalFileTransaction

            transaction = IncrementalFileTransaction(
                output_dir,
                change_plan,
                transaction_id=command.task_id,
            )
            transaction.stage()
        consistency = check_artifact_success_gate(
            plan,
            shared_context.get_artifact_manifest(),
            [event for event in schedule.completion_events if event is not None],
            output_dir,
            preserved_paths=getattr(adapter, "preserved_paths", ()),
        ) if schedule.status is GenerationScheduleStatus.COMPLETED else None
        if consistency is not None:
            architecture = getattr(adapter, "_project_context", {}).get("architecture", {})
            language = str(architecture.get("language", "")).lower()
            from app.agent.framework_profiles import DEFAULT_PROFILES
            from app.agent.framework_profiles.validation import validate_project_profile

            framework = str(architecture.get("framework", ""))
            profile = DEFAULT_PROFILES.validation_profile(language, framework)
            if profile is not None:
                validation = await validate_project_profile(output_dir, profile)
                if not validation["passed"]:
                    consistency = ArtifactConsistencyResult(
                        success=False,
                        planned_paths=consistency.planned_paths,
                        manifest_paths=consistency.manifest_paths,
                        completed_paths=consistency.completed_paths,
                        disk_paths=consistency.disk_paths,
                        diagnostic=ArtifactDiagnostic(
                            code="project.validation_failed",
                            message="project profile validation failed",
                            details=validation,
                        ),
                    )
        snapshot = getattr(adapter, "_project_context", {}).get("base_snapshot")
        if consistency is not None and change_plan is not None and snapshot is not None:
            from app.agent.project_snapshot import ProjectSnapshot

            untouched = change_plan.verify_untouched(
                ProjectSnapshot.model_validate(snapshot),
                ProjectSnapshot.scan(output_dir, revision="after-generation"),
            )
            if untouched:
                consistency = ArtifactConsistencyResult(
                    success=False,
                    planned_paths=consistency.planned_paths,
                    manifest_paths=consistency.manifest_paths,
                    completed_paths=consistency.completed_paths,
                    disk_paths=consistency.disk_paths,
                    diagnostic=ArtifactDiagnostic(
                        code="incremental.untouched_file_changed",
                        message="files outside the incremental change plan changed",
                        details={"paths": list(untouched)},
                    ),
                )
        if transaction is not None:
            if consistency is not None and consistency.success:
                transaction.commit()
            else:
                transaction.rollback()
        state = (await self.advance(
            command.task_id,
            OrchestrationStage.FINALIZING,
            event_id=f"{command.task_id}:6:finalizing",
            expected_revision=state.revision,
        )).state
        return await self.finish_schedule(
            command.task_id,
            schedule,
            event_id=f"{command.task_id}:7:{schedule.status.value}",
            expected_revision=state.revision,
            artifact_consistency=consistency,
        )

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
            if artifact_consistency is not None and artifact_consistency.success:
                scheduled_paths = tuple(sorted(event.path for event in schedule.completion_events))
                if scheduled_paths != artifact_consistency.completed_paths:
                    return await self.finish(
                        task_id,
                        OrchestrationStatus.FAILED,
                        event_id=event_id,
                        expected_revision=expected_revision,
                        diagnostic={
                            "code": "orchestration.schedule_artifact_mismatch",
                            "message": "scheduler completion events do not match artifact evidence",
                            "details": {
                                "scheduled_paths": scheduled_paths,
                                "artifact_paths": artifact_consistency.completed_paths,
                            },
                        },
                    )
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
            "details": {
                "nodes": {
                    path: {
                        "status": node.status.value,
                        "attempts": node.attempts,
                        "diagnostics": [
                            item.model_dump(mode="json") for item in node.diagnostics
                        ],
                    }
                    for path, node in schedule.nodes.items()
                }
            },
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
