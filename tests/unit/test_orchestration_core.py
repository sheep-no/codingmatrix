"""Checkpoint and recovery tests for Orchestrator Core."""

import json

import pytest
from pydantic import ValidationError

from app.agent.orchestration import (
    ARTIFACT_CONSISTENCY_FAILED,
    ArtifactConsistencyResult,
    ArtifactDiagnostic,
    ExecutionBudget,
    OrchestrationCheckpointStore,
    OrchestrationCommand,
    OrchestrationStage,
    OrchestrationStatus,
    OrchestratorCore,
    StageResult,
)
from app.agent.orchestration.generation_scheduler import (
    GenerationNodeResult,
    GenerationScheduleResult,
    GenerationScheduleStats,
    GenerationScheduleStatus,
    GenerationNodeStatus,
)


def make_command() -> OrchestrationCommand:
    return OrchestrationCommand(
        task_id="task-1",
        session_id="session-1",
        mode="traditional",
        request={"requirement": "create an app"},
    )


async def advance_to_finalizing(core: OrchestratorCore, revision: int) -> int:
    for stage in (
        OrchestrationStage.SCHEDULING,
        OrchestrationStage.GENERATING,
        OrchestrationStage.PERSISTING,
        OrchestrationStage.VALIDATING,
        OrchestrationStage.FINALIZING,
    ):
        result = await core.advance(
            "task-1",
            stage,
            event_id=f"task-1:{revision + 1}:{stage.value}",
            expected_revision=revision,
        )
        revision = result.state.revision
    return revision


@pytest.mark.asyncio
async def test_run_creates_planning_checkpoint_and_resume_restores_it(tmp_path) -> None:
    store = OrchestrationCheckpointStore(tmp_path)
    core = OrchestratorCore(store)

    started = await core.run(make_command())
    restored = await OrchestratorCore(OrchestrationCheckpointStore(tmp_path)).resume("task-1")

    assert started.resumed is False
    assert started.state.stage is OrchestrationStage.PLANNING
    assert started.state.revision == 1
    assert started.state.resume_cursor == "planning"
    assert restored.resumed is True
    assert restored.state == started.state


@pytest.mark.asyncio
async def test_run_existing_task_uses_checkpoint_engine_version(tmp_path) -> None:
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    original = await core.run(make_command())
    changed_command = make_command().model_copy(update={"engine_version": "core-v2"})

    resumed = await core.run(changed_command)

    assert resumed.resumed is True
    assert resumed.state.engine_version == original.state.engine_version == "core-v1"


@pytest.mark.asyncio
async def test_run_persists_creation_budget_across_checkpoint_reload(tmp_path) -> None:
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    command = make_command().model_copy(
        update={
            "budgets": ExecutionBudget(
                task_seconds=60,
                stage_seconds=40,
                file_seconds=20,
                model_call_seconds=10,
            )
        }
    )

    started = await core.run(command)
    restored = await OrchestratorCore(OrchestrationCheckpointStore(tmp_path)).resume("task-1")

    assert started.state.budgets == command.budgets
    assert restored.state.budgets == command.budgets


@pytest.mark.asyncio
async def test_advance_persists_revision_cursor_and_metadata(tmp_path) -> None:
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    started = await core.run(make_command())

    advanced = await core.advance(
        "task-1",
        OrchestrationStage.SCHEDULING,
        event_id="task-1:2:scheduling",
        expected_revision=started.state.revision,
        resume_cursor="schedule-files",
        metadata={"plan_version": 1},
    )
    restored = await core.resume("task-1")

    assert advanced.state.revision == 2
    assert restored.state.stage is OrchestrationStage.SCHEDULING
    assert restored.state.resume_cursor == "schedule-files"
    assert restored.state.metadata["plan_version"] == 1


@pytest.mark.asyncio
async def test_cancel_is_idempotent_across_checkpoint_reload(tmp_path) -> None:
    store = OrchestrationCheckpointStore(tmp_path)
    core = OrchestratorCore(store)
    started = await core.run(make_command())

    cancelled = await core.cancel(
        "task-1",
        "user requested cancellation",
        event_id="terminal-cancel",
        expected_revision=started.state.revision,
    )
    duplicate = await OrchestratorCore(OrchestrationCheckpointStore(tmp_path)).cancel(
        "task-1",
        "user requested cancellation",
        event_id="terminal-cancel",
        expected_revision=started.state.revision,
    )

    assert cancelled.state.status is OrchestrationStatus.CANCELLED
    assert duplicate.state == cancelled.state
    assert duplicate.state.revision == 2
    assert duplicate.state.terminal_event_id == "terminal-cancel"


@pytest.mark.asyncio
async def test_completed_status_requires_successful_artifact_gate(tmp_path) -> None:
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    started = await core.run(make_command())
    revision = await advance_to_finalizing(core, started.state.revision)

    with pytest.raises(ValueError, match="artifact consistency evidence"):
        await core.finish(
            "task-1",
            OrchestrationStatus.COMPLETED,
            event_id="terminal-completed",
            expected_revision=revision,
        )

    consistency = ArtifactConsistencyResult(
        success=True,
        planned_paths=("main.py",),
        manifest_paths=("main.py",),
        completed_paths=("main.py",),
        disk_paths=("main.py",),
    )
    completed = await core.finish(
        "task-1",
        OrchestrationStatus.COMPLETED,
        event_id="terminal-completed",
        expected_revision=revision,
        artifact_consistency=consistency,
    )

    assert completed.state.status is OrchestrationStatus.COMPLETED


@pytest.mark.asyncio
async def test_failed_artifact_gate_converges_task_to_failed(tmp_path) -> None:
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    started = await core.run(make_command())
    revision = await advance_to_finalizing(core, started.state.revision)
    consistency = ArtifactConsistencyResult(
        success=False,
        planned_paths=("main.py",),
        manifest_paths=(),
        completed_paths=(),
        disk_paths=(),
        diagnostic=ArtifactDiagnostic(
            code=ARTIFACT_CONSISTENCY_FAILED,
            message="missing artifact",
            path="main.py",
        ),
    )

    failed = await core.finish(
        "task-1",
        OrchestrationStatus.COMPLETED,
        event_id="terminal-consistency-failed",
        expected_revision=revision,
        artifact_consistency=consistency,
    )

    assert failed.state.status is OrchestrationStatus.FAILED
    assert failed.state.diagnostics[-1]["code"] == ARTIFACT_CONSISTENCY_FAILED


@pytest.mark.asyncio
async def test_finish_schedule_maps_timeout_to_single_terminal_state(tmp_path) -> None:
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    started = await core.run(make_command())
    schedule = GenerationScheduleResult(
        status=GenerationScheduleStatus.TIMED_OUT,
        nodes={"main.py": GenerationNodeResult(path="main.py", status=GenerationNodeStatus.TIMED_OUT)},
        stats=GenerationScheduleStats(
            total_files=1,
            completed_files=0,
            failed_files=0,
            timed_out_files=1,
            cancelled_files=0,
            blocked_files=0,
            max_parallelism=1,
        ),
    )

    result = await core.finish_schedule(
        "task-1", schedule, event_id="terminal-timeout", expected_revision=started.state.revision
    )

    assert result.state.status is OrchestrationStatus.TIMED_OUT
    assert result.state.diagnostics[-1]["code"] == "generation_schedule.timed_out"


@pytest.mark.asyncio
async def test_resume_rejects_unknown_task(tmp_path) -> None:
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))

    with pytest.raises(KeyError, match="task not found"):
        await core.resume("missing")


@pytest.mark.asyncio
async def test_checkpoint_rejects_unknown_schema_version(tmp_path) -> None:
    path = tmp_path / "task-1.json"
    path.write_text('{"schema_version":99,"state":{}}', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported orchestration checkpoint"):
        await OrchestrationCheckpointStore(tmp_path).load_latest("task-1")


@pytest.mark.asyncio
async def test_checkpoint_rejects_inconsistent_terminal_payload(tmp_path) -> None:
    state = (await OrchestratorCore(OrchestrationCheckpointStore(tmp_path)).run(make_command())).state
    payload = {
        "schema_version": 1,
        "state": {
            **state.model_dump(mode="json"),
            "status": "failed",
            "terminal_event_id": None,
        },
    }
    (tmp_path / "task-1.json").write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValidationError, match="terminal state requires"):
        await OrchestrationCheckpointStore(tmp_path).load_latest("task-1")


def test_contracts_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs"):
        OrchestrationCommand.model_validate(
            {
                **make_command().model_dump(),
                "unexpected": True,
            }
        )

    with pytest.raises(ValidationError, match="Extra inputs"):
        StageResult(
            stage=OrchestrationStage.PLANNING,
            event_id="event-1",
            unexpected=True,
        )
