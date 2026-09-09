"""Checkpoint and recovery tests for Orchestrator Core."""

import asyncio
import json
from pathlib import Path

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
    GeneratedContent,
    GenerationNodeResult,
    GenerationScheduleResult,
    GenerationScheduleStats,
    GenerationScheduleStatus,
    GenerationNodeStatus,
)
from app.agent.orchestration.plan import build_file_plan
from app.agent.shared_context import SharedContext


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
async def test_execute_runs_adapter_through_artifact_success_gate(tmp_path) -> None:
    class Adapter:
        async def create_plan(self, request):
            return build_file_plan([
                {"path": "main.py", "description": "entry point"},
                {"path": "tests/test_main.py", "description": "test", "depends_on": ["main.py"]},
            ])

        async def generate_file(self, context):
            content = "def main():\n    return 1\n" if context.file_path == "main.py" else "def test_main():\n    assert True\n"
            return GeneratedContent(content=content, model_name="test-model")

    output_dir = Path(tmp_path) / "generated"
    shared_context = SharedContext("create an app", output_dir)
    core = OrchestratorCore(OrchestrationCheckpointStore(Path(tmp_path) / "checkpoints"))
    result = await core.execute(
        OrchestrationCommand(
            task_id="execute-task",
            session_id="execute-session",
            mode="traditional",
            request={"requirement": "create an app"},
        ),
        Adapter(),
        output_dir=output_dir,
        shared_context=shared_context,
    )

    assert result.state.status is OrchestrationStatus.COMPLETED, result.state.model_dump()
    assert result.state.stage is OrchestrationStage.FINALIZING
    assert (output_dir / "main.py").exists()
    assert (output_dir / "tests/test_main.py").exists()


@pytest.mark.asyncio
async def test_execute_persists_workflow_ir_for_frozen_plan(tmp_path) -> None:
    class Adapter:
        def _model_assignment_payload(self):
            return {
                "architect_model": "planner-model",
                "backend_model": "code-model",
                "fallback_model": "fallback-model",
            }

        async def create_plan(self, request):
            return build_file_plan([
                {
                    "path": "main.ts",
                    "language": "typescript",
                    "contract": {
                        "exports": ["app"],
                        "fixtures": ["client"],
                        "framework": "express",
                        "runtime": "node",
                    },
                },
                {
                    "path": "service.go",
                    "language": "go",
                    "depends_on": ["main.ts"],
                    "contract": {"framework": "gin", "runtime": "go"},
                },
            ])

        async def generate_file(self, context):
            return GeneratedContent(content="VALUE = 1\n", model_name="test-model")

    output_dir = Path(tmp_path) / "generated"
    core = OrchestratorCore(OrchestrationCheckpointStore(Path(tmp_path) / "checkpoints"))
    result = await core.execute(
        OrchestrationCommand(
            task_id="workflow-ir-task",
            session_id="workflow-ir-session",
            mode="traditional",
            request={
                "requirement": "create an app",
                "language": "typescript",
                "framework": "express",
                "runtime": "node",
                "languages": ["typescript", "go"],
                "frameworks": ["express", "gin"],
                "runtimes": ["node", "go"],
            },
        ),
        Adapter(),
        output_dir=output_dir,
        shared_context=SharedContext("create an app", output_dir),
    )

    workflow = result.state.metadata["workflow_ir"]
    assert result.state.metadata["workflow_digest"] == workflow["digest"]
    assert result.state.metadata["model_routing"]["backend_model"] == "code-model"
    assert (workflow["language"], workflow["framework"], workflow["runtime"]) == (
        "typescript", "express", "node"
    )
    assert workflow["languages"] == ["typescript", "go"]
    assert workflow["frameworks"] == ["express", "gin"]
    assert workflow["runtimes"] == ["node", "go"]
    model_by_node = {node["node_id"]: node["model_policy"] for node in workflow["nodes"]}
    assert model_by_node["plan"]["preferred_models"] == ["planner-model"]
    assert model_by_node["file:main.ts"]["preferred_models"] == ["fallback-model"]
    assert model_by_node["file:main.ts"] is not None
    main_node = next(node for node in workflow["nodes"] if node["node_id"] == "file:main.ts")
    assert main_node["provided_symbols"] == ["app"]
    assert main_node["required_fixtures"] == ["client"]
    assert main_node["technology"] == {
        "language": "typescript", "framework": "express", "runtime": "node"
    }
    go_node = next(node for node in workflow["nodes"] if node["node_id"] == "file:service.go")
    assert go_node["technology"] == {
        "language": "go", "framework": "gin", "runtime": "go"
    }
    assert {node["node_id"] for node in workflow["nodes"]} == {
        "plan", "file:main.ts", "file:service.go"
    }


@pytest.mark.asyncio
async def test_execute_converges_planning_failure_to_terminal_state(tmp_path) -> None:
    class Adapter:
        async def create_plan(self, request):
            raise ValueError("invalid frozen plan")

    core = OrchestratorCore(OrchestrationCheckpointStore(Path(tmp_path) / "checkpoints"))
    result = await core.execute(
        OrchestrationCommand(
            task_id="planning-failure",
            session_id="execute-session",
            mode="incremental",
            request={"requirement": "change a file"},
        ),
        Adapter(),
        output_dir=Path(tmp_path) / "generated",
        shared_context=SharedContext("change a file", Path(tmp_path) / "generated"),
    )

    assert result.state.status is OrchestrationStatus.FAILED
    assert result.state.diagnostics[-1]["code"] == "orchestration.planning_failed"


@pytest.mark.asyncio
async def test_execute_resumes_from_planning_checkpoint(tmp_path) -> None:
    class Adapter:
        async def create_plan(self, request):
            return build_file_plan([{"path": "main.py"}])

        async def generate_file(self, context):
            return GeneratedContent(content="VALUE = 1\n", model_name="test-model")

    output_dir = Path(tmp_path) / "generated"
    core = OrchestratorCore(OrchestrationCheckpointStore(Path(tmp_path) / "checkpoints"))
    command = OrchestrationCommand(
        task_id="resume-planning",
        session_id="resume-session",
        mode="spec_first",
        request={"requirement": "build an app"},
    )
    await core.run(command)

    result = await core.execute(
        command,
        Adapter(),
        output_dir=output_dir,
        shared_context=SharedContext("build an app", output_dir),
    )

    assert result.state.status is OrchestrationStatus.COMPLETED
    assert (output_dir / "main.py").exists()


@pytest.mark.asyncio
async def test_execute_honors_cancellation_before_planning(tmp_path) -> None:
    class Adapter:
        async def create_plan(self, request):
            raise AssertionError("planning must not run after cancellation")

    cancel_event = asyncio.Event()
    cancel_event.set()
    core = OrchestratorCore(OrchestrationCheckpointStore(Path(tmp_path) / "checkpoints"))
    result = await core.execute(
        OrchestrationCommand(
            task_id="cancel-before-planning",
            session_id="cancel-session",
            mode="incremental",
            request={"requirement": "change an app"},
        ),
        Adapter(),
        output_dir=Path(tmp_path) / "generated",
        shared_context=SharedContext("change an app", Path(tmp_path) / "generated"),
        cancel_event=cancel_event,
    )

    assert result.state.status is OrchestrationStatus.CANCELLED


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
        nodes={
            "main.py": GenerationNodeResult(
                path="main.py",
                status=GenerationNodeStatus.TIMED_OUT,
                attempts=2,
                diagnostics=(ArtifactDiagnostic(
                    code="file_timeout",
                    message="file generation wall-clock budget exceeded",
                    path="main.py",
                ),),
            )
        },
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
    node_details = result.state.diagnostics[-1]["details"]["nodes"]["main.py"]
    assert node_details["status"] == "timed_out"
    assert node_details["attempts"] == 2
    assert node_details["diagnostics"][0]["code"] == "file_timeout"


@pytest.mark.asyncio
async def test_finish_schedule_rejects_mismatched_artifact_evidence(tmp_path) -> None:
    core = OrchestratorCore(OrchestrationCheckpointStore(tmp_path))
    started = await core.run(make_command())
    schedule = GenerationScheduleResult(
        status=GenerationScheduleStatus.COMPLETED,
        nodes={"main.py": GenerationNodeResult(path="main.py", status=GenerationNodeStatus.COMPLETED)},
        stats=GenerationScheduleStats(
            total_files=1,
            completed_files=1,
            failed_files=0,
            timed_out_files=0,
            cancelled_files=0,
            blocked_files=0,
            max_parallelism=1,
        ),
    )
    evidence = ArtifactConsistencyResult(
        success=True,
        planned_paths=("main.py",),
        manifest_paths=("main.py",),
        completed_paths=("other.py",),
        disk_paths=("main.py",),
    )

    result = await core.finish_schedule(
        "task-1", schedule, event_id="terminal-mismatch", expected_revision=started.state.revision,
        artifact_consistency=evidence,
    )

    assert result.state.status is OrchestrationStatus.FAILED
    assert result.state.diagnostics[-1]["code"] == "orchestration.schedule_artifact_mismatch"


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
