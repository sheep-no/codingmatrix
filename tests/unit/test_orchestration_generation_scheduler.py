"""Structured-concurrency tests for GenerationScheduler."""

import asyncio
from pathlib import Path

import pytest

from app.agent.orchestration import (
    ArtifactCommitter,
    ExecutionBudget,
    GeneratedContent,
    GenerationNodeStatus,
    GenerationScheduleStatus,
    GenerationScheduler,
    build_file_plan,
)
from app.agent.shared_context import SharedContext
from app.agent.contract_index import ContractIndex


def make_scheduler(tmp_path: Path, *, max_concurrent: int = 2, max_retries: int = 0):
    context = SharedContext("generate files", tmp_path)
    committer = ArtifactCommitter(tmp_path, context, task_id="task-1")
    return GenerationScheduler(
        committer,
        max_concurrent=max_concurrent,
        max_retries=max_retries,
    )


def make_budget(
    *,
    task_seconds: float = 1.0,
    stage_seconds: float = 1.0,
    file_seconds: float = 0.5,
) -> ExecutionBudget:
    file_seconds = min(file_seconds, stage_seconds)
    model_call_seconds = min(file_seconds, 0.5)
    return ExecutionBudget(
        task_seconds=task_seconds,
        stage_seconds=stage_seconds,
        file_seconds=file_seconds,
        model_call_seconds=model_call_seconds,
    )


@pytest.mark.asyncio
async def test_scheduler_generates_dependencies_in_topological_order(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    plan = build_file_plan(
        [
            {"path": "service.py", "dependencies": ["model.py"]},
            {"path": "model.py"},
        ],
        requested_paths=["service.py", "model.py"],
    )
    observed: list[tuple[str, tuple[str, ...]]] = []

    async def generator(context):
        observed.append((context.file_path, tuple(sorted(context.upstream_contents))))
        return GeneratedContent(
            content=f"# {context.file_path}\n",
            model_name="test-model",
        )

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-1",
        stage_id="stage-1",
    )

    assert result.status is GenerationScheduleStatus.COMPLETED
    assert observed == [("model.py", ()), ("service.py", ("model.py",))]
    assert all(node.status is GenerationNodeStatus.COMPLETED for node in result.nodes.values())
    assert result.stats.max_parallelism == 1
    assert scheduler.active_task_count == 0


@pytest.mark.asyncio
async def test_scheduler_shares_one_frozen_contract_snapshot_with_all_files(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    contracts = ContractIndex.build([
        {
            "name": "inventory.entry",
            "kind": "file",
            "owner": "main.py",
            "schema": {"exports": ["application"]},
        },
        {
            "name": "PATCH /inventory",
            "kind": "api",
            "owner": "routes.py",
            "schema": {
                "method": "PATCH",
                "path": "/inventory",
                "serialization_guidance": "Encode domain values before sending JSON.",
            },
        },
    ])
    plan = build_file_plan(
        [
            {
                "path": "model.py",
                "language": "python",
                "contract_refs": ["inventory.entry"],
                "contract": {"framework": "fastapi", "runtime": "python"},
            },
            {
                "path": "service.py",
                "language": "python",
                "dependencies": ["model.py"],
                "contract_refs": ["inventory.entry"],
                "contract": {"framework": "fastapi", "runtime": "python"},
            },
        ],
        requested_paths=["model.py", "service.py"],
    )
    observed = []

    async def generator(context):
        observed.append(context)
        return GeneratedContent(content=f"# {context.file_path}\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-contracts",
        stage_id="stage-contracts",
        contract_index=contracts,
    )

    assert result.status is GenerationScheduleStatus.COMPLETED
    assert [item.file_path for item in observed] == ["model.py", "service.py"]
    assert all(item.contract_index is contracts for item in observed)
    assert all(item.technology.model_dump(mode="json") == {
        "language": "python", "framework": "fastapi", "runtime": "python"
    } for item in observed)
    assert all(item.http_contracts[0].schema["serialization_guidance"]
               == "Encode domain values before sending JSON." for item in observed)
    assert all(item.cross_file_contracts[0].schema["exports"] == ["application"]
               for item in observed)
    assert all(item.test_generation_contract.discovery == "declared_test_files" for item in observed)
    assert all(item.test_generation_contract.execution == "profile_command" for item in observed)
    assert all(item.test_generation_contract.dependencies == "declared_contracts" for item in observed)
    assert all(item.test_generation_contract.serialization == "framework_defined" for item in observed)


@pytest.mark.asyncio
async def test_scheduler_rejects_unknown_contract_before_commit(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    plan = build_file_plan(
        [{"path": "main.py", "contract_refs": ["missing.contract"]}],
        requested_paths=["main.py"],
    )

    async def generator(context):
        return GeneratedContent(content="VALUE = 1\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-missing-contract",
        stage_id="stage-missing-contract",
        contract_index=ContractIndex.build(()),
    )

    assert result.status is GenerationScheduleStatus.FAILED
    assert result.nodes["main.py"].diagnostics[0].code == "operation_contract_missing"
    assert not (tmp_path / "main.py").exists()


@pytest.mark.asyncio
async def test_scheduler_drains_fast_completion_events_before_deadlock(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path, max_concurrent=4)
    paths = [f"step-{index}.py" for index in range(20)]
    plan = build_file_plan(
        [
            {"path": path, "dependencies": [paths[index - 1]] if index else []}
            for index, path in enumerate(paths)
        ],
        requested_paths=paths,
    )

    async def generator(context):
        return GeneratedContent(content=f"# {context.file_path}\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-fast-chain",
        stage_id="stage-fast-chain",
    )

    assert result.status is GenerationScheduleStatus.COMPLETED
    assert all(node.status is GenerationNodeStatus.COMPLETED for node in result.nodes.values())


@pytest.mark.asyncio
async def test_scheduler_runs_independent_files_concurrently(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path, max_concurrent=2)
    plan = build_file_plan(
        [{"path": "a.py"}, {"path": "b.py"}],
        requested_paths=["a.py", "b.py"],
    )
    started = 0
    peak = 0
    lock = asyncio.Lock()

    async def generator(context):
        nonlocal started, peak
        async with lock:
            started += 1
            peak = max(peak, started)
        await asyncio.sleep(0.02)
        async with lock:
            started -= 1
        return GeneratedContent(content=f"# {context.file_path}\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-1",
        stage_id="stage-1",
    )

    assert result.success is True
    assert peak == 2
    assert result.stats.max_parallelism == 2
    assert scheduler.active_task_count == 0


@pytest.mark.asyncio
async def test_failed_upstream_blocks_all_descendants(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    plan = build_file_plan(
        [
            {"path": "root.py"},
            {"path": "child.py", "dependencies": ["root.py"]},
            {"path": "grandchild.py", "dependencies": ["child.py"]},
        ],
        requested_paths=["root.py", "child.py", "grandchild.py"],
    )
    called: list[str] = []

    async def generator(context):
        called.append(context.file_path)
        if context.file_path == "root.py":
            raise RuntimeError("model failed")
        return GeneratedContent(content="# generated\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-1",
        stage_id="stage-1",
    )

    assert result.status is GenerationScheduleStatus.FAILED
    assert called == ["root.py"]
    assert result.nodes["root.py"].status is GenerationNodeStatus.FAILED
    assert result.nodes["child.py"].status is GenerationNodeStatus.BLOCKED
    assert result.nodes["grandchild.py"].status is GenerationNodeStatus.BLOCKED
    assert result.stats.blocked_files == 2
    assert result.blocked_nodes == ("child.py", "grandchild.py")
    assert [diagnostic.code for diagnostic in result.root_causes] == ["generation_failed"]
    assert scheduler.active_task_count == 0


@pytest.mark.asyncio
async def test_file_timeout_cancels_file_and_blocks_downstream(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    plan = build_file_plan(
        [{"path": "slow.py"}, {"path": "dependent.py", "dependencies": ["slow.py"]}],
        requested_paths=["slow.py", "dependent.py"],
    )
    cancelled = asyncio.Event()

    async def generator(context):
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return GeneratedContent(content="# done\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(file_seconds=0.02),
        task_id="task-1",
        stage_id="stage-1",
    )

    assert result.status is GenerationScheduleStatus.TIMED_OUT
    assert result.nodes["slow.py"].status is GenerationNodeStatus.TIMED_OUT
    assert result.nodes["dependent.py"].status is GenerationNodeStatus.BLOCKED
    assert [diagnostic.code for diagnostic in result.timeouts] == ["file_timeout"]
    assert result.blocked_nodes == ("dependent.py",)
    assert cancelled.is_set()
    assert scheduler.active_task_count == 0


@pytest.mark.asyncio
async def test_stage_timeout_reclaims_all_active_tasks(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path, max_concurrent=2)
    plan = build_file_plan(
        [{"path": "a.py"}, {"path": "b.py"}],
        requested_paths=["a.py", "b.py"],
    )
    cancelled = 0

    async def generator(context):
        nonlocal cancelled
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled += 1
            raise
        return GeneratedContent(content="# done\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(stage_seconds=0.02, task_seconds=0.1, file_seconds=0.5),
        task_id="task-1",
        stage_id="stage-1",
    )

    assert result.status is GenerationScheduleStatus.TIMED_OUT
    assert cancelled == 2
    assert all(
        node.status is GenerationNodeStatus.TIMED_OUT for node in result.nodes.values()
    ), {path: node.status for path, node in result.nodes.items()}
    assert scheduler.active_task_count == 0


@pytest.mark.asyncio
async def test_user_cancellation_reclaims_tasks_and_marks_nodes_cancelled(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path, max_concurrent=2)
    plan = build_file_plan(
        [{"path": "a.py"}, {"path": "b.py"}],
        requested_paths=["a.py", "b.py"],
    )
    cancel_event = asyncio.Event()

    async def generator(context):
        await asyncio.sleep(1)
        return GeneratedContent(content="# done\n", model_name="model")

    task = asyncio.create_task(
        scheduler.run(
            plan,
            generator,
            make_budget(),
            task_id="task-1",
            stage_id="stage-1",
            cancel_event=cancel_event,
        )
    )
    await asyncio.sleep(0.01)
    cancel_event.set()
    result = await task

    assert result.status is GenerationScheduleStatus.CANCELLED
    assert all(node.status is GenerationNodeStatus.CANCELLED for node in result.nodes.values())
    assert scheduler.active_task_count == 0


@pytest.mark.asyncio
async def test_transient_generation_failure_uses_retry_budget(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path, max_retries=1)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])
    attempts = 0

    async def generator(context):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary")
        return GeneratedContent(content="print('ok')\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-1",
        stage_id="stage-1",
    )

    assert result.status is GenerationScheduleStatus.COMPLETED
    assert result.nodes["main.py"].attempts == 2
    assert attempts == 2


@pytest.mark.asyncio
async def test_validation_failure_retries_with_diagnostic_feedback(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path, max_retries=1)
    plan = build_file_plan([{"path": "main.py"}], requested_paths=["main.py"])
    observed_feedback = []

    async def generator(context):
        observed_feedback.append(context.previous_diagnostics)
        if context.attempt == 1:
            return GeneratedContent(
                content="invalid\n",
                model_name="model",
                validation_passed=False,
                diagnostics=("missing required route",),
            )
        return GeneratedContent(content="print('ok')\n", model_name="model")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-1",
        stage_id="stage-1",
    )

    assert result.status is GenerationScheduleStatus.COMPLETED
    assert result.nodes["main.py"].attempts == 2
    assert observed_feedback == [(), ("missing required route",)]


@pytest.mark.asyncio
async def test_scheduler_converges_cycle_to_blocked_without_waiting_forever(tmp_path: Path) -> None:
    scheduler = make_scheduler(tmp_path)
    plan = build_file_plan(
        [
            {"path": "a.py", "dependencies": ["b.py"]},
            {"path": "b.py", "dependencies": ["a.py"]},
        ],
        requested_paths=["a.py", "b.py"],
    )

    async def generator(context):
        raise AssertionError(f"cycle node was incorrectly scheduled: {context.file_path}")

    result = await scheduler.run(
        plan,
        generator,
        make_budget(),
        task_id="task-1",
        stage_id="stage-1",
    )

    assert result.status is GenerationScheduleStatus.FAILED
    assert all(node.status is GenerationNodeStatus.BLOCKED for node in result.nodes.values())
    assert scheduler.active_task_count == 0
