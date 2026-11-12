"""GenerationScheduler 分支补充：技术契约、预算边界与失败诊断。"""

import asyncio
from pathlib import Path

import pytest

from app.agent.contract_index import ContractIndex
from app.agent.orchestration import (
    ArtifactCommitter,
    ExecutionBudget,
    GeneratedContent,
    GenerationNodeStatus,
    GenerationScheduleStatus,
    GenerationScheduler,
    build_file_plan,
)
from app.agent.orchestration.generation_scheduler import (
    test_contract_for_technology as build_test_contract,
)
from app.agent.orchestration.artifact_committer import ArtifactDiagnostic
from app.agent.shared_context import SharedContext
from app.agent.workflow_ir import TechnologyProfile


def _scheduler(tmp_path: Path, *, max_concurrent: int = 2, max_retries: int = 0):
    context = SharedContext("generate files", tmp_path)
    committer = ArtifactCommitter(tmp_path, context, task_id="task-branch")
    return GenerationScheduler(committer, max_concurrent=max_concurrent, max_retries=max_retries)


def _budget(*, task: float = 1.0, stage: float = 1.0, file: float = 0.5) -> ExecutionBudget:
    file = min(file, stage)
    return ExecutionBudget(
        task_seconds=task,
        stage_seconds=stage,
        file_seconds=file,
        model_call_seconds=min(file, 0.5),
    )


@pytest.mark.parametrize(
    "technology, expected",
    [
        (TechnologyProfile(language="Python", framework="FastAPI", runtime="py"), {"runner": "pytest", "client": "framework_test_client"}),
        (TechnologyProfile(language="python", framework="flask", runtime="py"), {"runner": "pytest", "client": "application_test_client"}),
        (TechnologyProfile(language="TypeScript", framework="", runtime="node"), {"runner": "jest_or_vitest"}),
        (TechnologyProfile(language="javascript", framework="", runtime="node"), {"runner": "jest_or_vitest"}),
        (TechnologyProfile(language="Go", framework="", runtime="go"), {"runner": "go_test"}),
        (TechnologyProfile(language="Java", framework="", runtime="jvm"), {"runner": "junit"}),
        (TechnologyProfile(language="Rust", framework="", runtime="bin"), {"runner": "cargo_test"}),
        (TechnologyProfile(language="ruby", framework="", runtime="mri"), {}),
    ],
)
def test_build_test_contract_selects_stack_rules(technology, expected):
    assert build_test_contract(technology).stack_rules == expected


def test_scheduler_constructor_rejects_invalid_limits(tmp_path):
    context = SharedContext("task", tmp_path)
    committer = ArtifactCommitter(tmp_path, context, task_id="t")

    with pytest.raises(ValueError, match="max_concurrent"):
        GenerationScheduler(committer, max_concurrent=0)
    with pytest.raises(ValueError, match="max_retries"):
        GenerationScheduler(committer, max_retries=-1)


@pytest.mark.asyncio
async def test_run_returns_timed_out_when_stage_budget_exhausted(tmp_path):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    async def generator(context):
        raise AssertionError("must not run")

    result = await scheduler.run(
        plan,
        generator,
        _budget(stage=0.1, task=0.1),
        task_id="task-budget",
        stage_id="stage-budget",
        task_elapsed_seconds=0.2,
    )

    assert result.status is GenerationScheduleStatus.TIMED_OUT
    assert result.nodes["main.py"].status is GenerationNodeStatus.TIMED_OUT


@pytest.mark.asyncio
async def test_run_converts_unexpected_scheduler_cancellation(tmp_path):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    async def generator(context):
        await asyncio.sleep(1)
        return GeneratedContent(content="x", model_name="m")

    task = asyncio.create_task(
        scheduler.run(
            plan,
            generator,
            _budget(),
            task_id="task-cancel",
            stage_id="stage-cancel",
        )
    )
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert scheduler.nodes["main.py"].status is GenerationNodeStatus.CANCELLED
    assert scheduler.active_task_count == 0


@pytest.mark.asyncio
async def test_generator_must_return_generated_content(tmp_path):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    async def generator(context):
        return "not a GeneratedContent"

    result = await scheduler.run(
        plan, generator, _budget(), task_id="task-type", stage_id="stage-type"
    )

    assert result.status is GenerationScheduleStatus.FAILED
    assert "GeneratedContent" in result.nodes["main.py"].diagnostics[-1].message


@pytest.mark.asyncio
async def test_validation_failure_without_diagnostics_uses_default_feedback(tmp_path):
    scheduler = _scheduler(tmp_path, max_retries=0)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    async def generator(context):
        return GeneratedContent(
            content="bad",
            model_name="m",
            validation_passed=False,
        )

    result = await scheduler.run(
        plan, generator, _budget(), task_id="task-val", stage_id="stage-val"
    )

    assert result.nodes["main.py"].status is GenerationNodeStatus.FAILED
    assert result.nodes["main.py"].diagnostics[0].code == "generation_validation_failed"


@pytest.mark.asyncio
async def test_protocol_validation_failure_is_reported(tmp_path):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    async def generator(context):
        return GeneratedContent(content="", model_name="m")

    result = await scheduler.run(
        plan, generator, _budget(), task_id="task-proto", stage_id="stage-proto"
    )

    assert result.nodes["main.py"].diagnostics[-1].code == "protocol_validation_failed"


@pytest.mark.asyncio
async def test_commit_failure_records_diagnostic_and_fails_node(tmp_path, monkeypatch):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    class _CommitResult:
        success = False
        diagnostic = ArtifactDiagnostic(code="commit_failed", message="disk full", path="main.py")
        completion_event = None

    monkeypatch.setattr(scheduler.committer, "commit", lambda *args, **kwargs: _CommitResult())

    async def generator(context):
        return GeneratedContent(content="ok", model_name="m")

    result = await scheduler.run(
        plan, generator, _budget(), task_id="task-commit", stage_id="stage-commit"
    )

    assert result.nodes["main.py"].status is GenerationNodeStatus.FAILED
    assert result.nodes["main.py"].diagnostics[-1].code == "commit_failed"


@pytest.mark.asyncio
async def test_model_timeout_diagnostic_marks_node_timed_out(tmp_path):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    class ModelTimeout(Exception):
        diagnostic = {"code": "model_timeout", "message": "model went away"}

    async def generator(context):
        raise ModelTimeout()

    result = await scheduler.run(
        plan, generator, _budget(), task_id="task-model", stage_id="stage-model"
    )

    assert result.nodes["main.py"].status is GenerationNodeStatus.TIMED_OUT
    assert result.timeouts[0].code == "model_timeout"


@pytest.mark.asyncio
async def test_truncation_diagnostics_are_classified(tmp_path):
    scheduler = _scheduler(tmp_path, max_retries=0)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    class Truncated(Exception):
        diagnostic = {"code": "response_truncated", "message": "output cut"}

    async def generator(context):
        raise Truncated()

    result = await scheduler.run(
        plan, generator, _budget(), task_id="task-trunc", stage_id="stage-trunc"
    )

    assert result.truncations
    assert result.status is GenerationScheduleStatus.FAILED


@pytest.mark.asyncio
async def test_unexpected_exception_records_generation_failed(tmp_path):
    scheduler = _scheduler(tmp_path, max_retries=0)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    async def generator(context):
        raise RuntimeError("kaboom")

    result = await scheduler.run(
        plan, generator, _budget(), task_id="task-err", stage_id="stage-err"
    )

    diagnostic = result.nodes["main.py"].diagnostics[-1]
    assert diagnostic.code == "generation_failed"
    assert diagnostic.details == {"attempt": 1}


def test_derive_status_without_nodes_is_completed(tmp_path):
    scheduler = _scheduler(tmp_path)
    scheduler.nodes = {}

    assert scheduler._derive_status() is GenerationScheduleStatus.COMPLETED


@pytest.mark.asyncio
async def test_cancelled_node_status_derives_cancelled_result(tmp_path):
    scheduler = _scheduler(tmp_path)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])

    async def generator(context):
        return GeneratedContent(content="ok", model_name="m")

    await scheduler.run(
        plan, generator, _budget(), task_id="task-derive", stage_id="stage-derive"
    )
    # Simulate a node left cancelled by a converging stage timeout.
    scheduler.nodes["main.py"].status = GenerationNodeStatus.CANCELLED
    assert scheduler._derive_status() is GenerationScheduleStatus.CANCELLED

    scheduler.nodes["main.py"].status = GenerationNodeStatus.TIMED_OUT
    assert scheduler._derive_status() is GenerationScheduleStatus.TIMED_OUT

    scheduler.nodes["main.py"].status = GenerationNodeStatus.FAILED
    assert scheduler._derive_status() is GenerationScheduleStatus.FAILED
