"""Lifecycle coordinator for versioned orchestration state."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from pathlib import Path
from typing import Any, Dict, Mapping, Optional

from app.agent.shared_context import SharedContext
from app.agent.workflow_ir import (
    ModelPolicy,
    TechnologyProfile,
    WorkflowIR,
    WorkflowNode,
    WorkflowNodeKind,
)

from .artifact_committer import (
    ArtifactConsistencyResult,
    ArtifactDiagnostic,
    ArtifactCommitter,
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


logger = logging.getLogger(__name__)


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
            logger.exception(
                "Orchestration planning failed | task_id=%s | mode=%s",
                command.task_id,
                command.mode,
            )
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
        transaction = None
        change_plan = getattr(adapter, "change_plan", None)
        if change_plan is not None:
            from .file_transaction import IncrementalFileTransaction

            transaction = IncrementalFileTransaction(
                output_dir,
                change_plan,
                transaction_id=command.task_id,
            )
            try:
                transaction.stage()
            except Exception as exc:
                return await self.finish(
                    command.task_id,
                    OrchestrationStatus.FAILED,
                    event_id=f"{command.task_id}:2:transaction_failed",
                    expected_revision=started.state.revision,
                    diagnostic={
                        "code": "incremental.transaction_stage_failed",
                        "message": str(exc),
                    },
                )

        try:
            result = await self._execute_frozen_plan(
                command,
                adapter,
                plan,
                output_dir=output_dir,
                shared_context=shared_context,
                cancel_event=cancel_event,
                max_concurrent=max_concurrent,
                expected_revision=started.state.revision,
            )
        except BaseException:
            if transaction is not None:
                transaction.rollback()
            raise
        if transaction is not None:
            if result.state.status is OrchestrationStatus.COMPLETED:
                transaction.commit()
            else:
                transaction.rollback()
        return result

    async def _execute_frozen_plan(
        self,
        command: OrchestrationCommand,
        adapter: Any,
        plan: Any,
        *,
        output_dir: Path,
        shared_context: SharedContext,
        cancel_event: Optional[asyncio.Event],
        max_concurrent: int,
        expected_revision: int,
    ) -> OrchestrationResult:
        """Schedule one frozen plan after any incremental transaction is staged."""
        model_routing = adapter._model_assignment_payload() if hasattr(adapter, "_model_assignment_payload") else {}
        workflow_ir = _build_workflow_ir(
            command,
            plan,
            getattr(adapter, "contract_index", None),
            model_routing=model_routing,
            technology=_technology_metadata(command, adapter, plan),
        )
        state = (await self.advance(
            command.task_id,
            OrchestrationStage.SCHEDULING,
            event_id=f"{command.task_id}:2:scheduling",
            expected_revision=expected_revision,
            metadata={
                "plan_paths": [item.path for item in plan.files],
                "contract_digest": getattr(getattr(adapter, "contract_index", None), "digest", None),
                "workflow_ir": workflow_ir.model_dump(mode="json"),
                "workflow_digest": workflow_ir.digest,
                "model_routing": model_routing,
            },
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
            contract_index=getattr(adapter, "contract_index", None),
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
        change_plan = getattr(adapter, "change_plan", None)
        consistency = check_artifact_success_gate(
            plan,
            shared_context.get_artifact_manifest(),
            [event for event in schedule.completion_events if event is not None],
            output_dir,
            preserved_paths=getattr(adapter, "preserved_paths", ()),
        ) if schedule.status is GenerationScheduleStatus.COMPLETED else None
        candidate_hashes = {
            path: hashlib.sha256((output_dir / path).read_bytes()).hexdigest()
            for path in sorted({item.path for item in plan.files} | set(getattr(adapter, "preserved_paths", ())))
            if (output_dir / path).is_file()
        }
        # Project tests and runtime checks are local Agent Host actions.
        # Core only gates on cloud syntax, contracts, and artifact integrity.
        validation = {"status": "waiting_local_validation"}
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
        state = (await self.advance(
            command.task_id,
            OrchestrationStage.FINALIZING,
            event_id=f"{command.task_id}:6:finalizing",
            expected_revision=state.revision,
            metadata={"candidate_hashes": candidate_hashes, "candidate_validation": validation},
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


def _build_workflow_ir(
    command: OrchestrationCommand,
    plan: Any,
    contract_index: Any,
    *,
    model_routing: Optional[Dict[str, str]] = None,
    technology: Optional[Dict[str, str]] = None,
) -> WorkflowIR:
    """Project the frozen generation plan into a callable-free workflow graph."""
    routing = model_routing or {}
    stack = technology or {}
    role_models = {
        "architect": routing.get("architect_model"),
        "frontend": routing.get("frontend_model"),
        "backend": routing.get("backend_model"),
        "reviewer": routing.get("reviewer_model"),
        "fallback": routing.get("fallback_model"),
    }
    nodes = [WorkflowNode(
        node_id="plan",
        kind=WorkflowNodeKind.PLAN,
        handler_ref="orchestration.plan",
        agent_role="architect",
        model_policy=ModelPolicy(
            preferred_models=tuple(model for model in (role_models["architect"],) if model),
        ),
        budget_scope="stage",
    )]
    for planned_file in plan.files:
        role = str(getattr(planned_file, "role", "") or "").lower()
        selected_model = role_models.get(role) or role_models.get("fallback")
        contract = getattr(planned_file, "contract", {}) or {}
        provided_symbols = _contract_values(contract, "exports", "provided_symbols")
        required_symbols = _contract_values(contract, "imports", "required_symbols")
        required_fixtures = _contract_values(contract, "fixtures", "required_fixtures")
        node_language = str(getattr(planned_file, "language", "") or stack.get("language", ""))
        node_framework = str(contract.get("framework") or stack.get("framework", ""))
        node_runtime = str(contract.get("runtime") or stack.get("runtime", ""))
        nodes.append(WorkflowNode(
            node_id=f"file:{planned_file.path}",
            kind=WorkflowNodeKind.GENERATE,
            handler_ref="orchestration.generate_file",
            depends_on=("plan", *(f"file:{dependency}" for dependency in planned_file.dependencies)),
            agent_role=role or None,
            input_refs=tuple(planned_file.contract_refs),
            output_refs=(planned_file.path,),
            provided_symbols=provided_symbols,
            required_symbols=required_symbols,
            required_fixtures=required_fixtures,
            technology=TechnologyProfile(
                language=node_language,
                framework=node_framework,
                runtime=node_runtime,
            ),
            model_policy=ModelPolicy(
                preferred_models=tuple(model for model in (selected_model,) if model),
            ),
            budget_scope="file",
        ))
    return WorkflowIR.build(
        workflow_id=command.task_id,
        name=f"{command.mode}-generation",
        mode=command.mode,
        language=stack.get("language", ""),
        framework=stack.get("framework", ""),
        runtime=stack.get("runtime", ""),
        languages=tuple(stack.get("languages", ())),
        frameworks=tuple(stack.get("frameworks", ())),
        runtimes=tuple(stack.get("runtimes", ())),
        entry_node="plan",
        nodes=tuple(nodes),
        generation_plan=plan,
        contract_index=contract_index,
        budgets=command.budgets,
    )


def _technology_metadata(command: OrchestrationCommand, adapter: Any, plan: Any) -> Dict[str, Any]:
    project_plan = getattr(adapter, "project_plan", None)
    request = command.request
    languages = _technology_values(
        getattr(project_plan, "language", None),
        *(getattr(item, "language", None) for item in getattr(plan, "files", ())),
        request.get("languages", ()),
        request.get("language"),
    )
    frameworks = _technology_values(
        getattr(project_plan, "framework", None),
        *(getattr(item, "contract", {}).get("framework") for item in getattr(plan, "files", ())),
        request.get("frameworks", ()),
        request.get("framework"),
    )
    runtimes = _technology_values(
        getattr(project_plan, "runtime", None),
        *(getattr(item, "contract", {}).get("runtime") for item in getattr(plan, "files", ())),
        request.get("runtimes", ()),
        request.get("runtime"),
    )
    return {
        "language": languages[0] if languages else "",
        "framework": frameworks[0] if frameworks else "",
        "runtime": runtimes[0] if runtimes else "",
        "languages": languages,
        "frameworks": frameworks,
        "runtimes": runtimes,
    }


def _technology_values(*values: Any) -> tuple[str, ...]:
    flattened: list[str] = []
    for value in values:
        if isinstance(value, (list, tuple, set)):
            flattened.extend(str(item).strip() for item in value if str(item).strip())
        elif value is not None and str(value).strip():
            flattened.append(str(value).strip())
    return tuple(dict.fromkeys(flattened))


def _contract_values(contract: Any, *keys: str) -> tuple[str, ...]:
    """Read language-neutral symbol facts from a contract declaration."""
    if not isinstance(contract, Mapping):
        return ()
    for key in keys:
        values = contract.get(key)
        if isinstance(values, str):
            return (values,)
        if isinstance(values, (list, tuple, set)):
            return tuple(sorted({str(value) for value in values if str(value)}))
    return ()
