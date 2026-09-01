"""Dependency-aware structured concurrency for generated artifacts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Awaitable, Callable, Dict, Mapping, Optional, Set, Tuple

from pydantic import BaseModel, ConfigDict, Field

from .artifact_committer import (
    ArtifactCommitter,
    ArtifactCompletionEvent,
    ArtifactDiagnostic,
)
from .budget import ExecutionBudget
from .plan import GenerationPlan, PlannedFile


class GenerationNodeStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"

    @property
    def is_terminal(self) -> bool:
        return self in {
            GenerationNodeStatus.COMPLETED,
            GenerationNodeStatus.FAILED,
            GenerationNodeStatus.TIMED_OUT,
            GenerationNodeStatus.CANCELLED,
            GenerationNodeStatus.BLOCKED,
        }


class GenerationScheduleStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class GeneratedContent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    model_name: str = Field(min_length=1)
    validation_passed: bool = True
    diagnostics: Tuple[str, ...] = ()


@dataclass(frozen=True)
class FileGenerationContext:
    task_id: str
    stage_id: str
    planned_file: PlannedFile
    upstream_contents: Mapping[str, str]
    attempt: int
    cancel_event: Optional[asyncio.Event]

    @property
    def file_path(self) -> str:
        return self.planned_file.path


class GenerationNodeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    path: str = Field(min_length=1)
    status: GenerationNodeStatus
    attempts: int = Field(default=0, ge=0)
    diagnostics: Tuple[ArtifactDiagnostic, ...] = ()
    completion_event: Optional[ArtifactCompletionEvent] = None


class GenerationScheduleStats(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    total_files: int = Field(ge=0)
    completed_files: int = Field(ge=0)
    failed_files: int = Field(ge=0)
    timed_out_files: int = Field(ge=0)
    cancelled_files: int = Field(ge=0)
    blocked_files: int = Field(ge=0)
    max_parallelism: int = Field(ge=0)


class GenerationScheduleResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: GenerationScheduleStatus
    nodes: Dict[str, GenerationNodeResult]
    completion_events: Tuple[ArtifactCompletionEvent, ...] = ()
    stats: GenerationScheduleStats

    @property
    def success(self) -> bool:
        return self.status is GenerationScheduleStatus.COMPLETED


Generator = Callable[[FileGenerationContext], Awaitable[GeneratedContent]]


@dataclass
class _MutableNode:
    planned_file: PlannedFile
    status: GenerationNodeStatus = GenerationNodeStatus.PENDING
    attempts: int = 0
    diagnostics: Tuple[ArtifactDiagnostic, ...] = ()
    completion_event: Optional[ArtifactCompletionEvent] = None


class GenerationScheduler:
    """Generate, commit, and release plan nodes under hierarchical budgets."""

    def __init__(
        self,
        committer: ArtifactCommitter,
        *,
        max_concurrent: int = 5,
        max_retries: int = 2,
    ) -> None:
        if max_concurrent < 1:
            raise ValueError("max_concurrent must be positive")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        self.committer = committer
        self.max_concurrent = max_concurrent
        self.max_retries = max_retries
        self.nodes: Dict[str, _MutableNode] = {}
        self._active_tasks: Set[asyncio.Task[None]] = set()
        self._max_parallelism = 0
        self._termination_status: Optional[GenerationNodeStatus] = None

    @property
    def active_task_count(self) -> int:
        return sum(not task.done() for task in self._active_tasks)

    async def run(
        self,
        plan: GenerationPlan,
        generator: Generator,
        budget: ExecutionBudget,
        *,
        task_id: str,
        stage_id: str,
        cancel_event: Optional[asyncio.Event] = None,
        task_elapsed_seconds: float = 0.0,
    ) -> GenerationScheduleResult:
        self._initialize(plan)
        remaining_stage_seconds = min(
            budget.stage_seconds,
            budget.task_seconds - task_elapsed_seconds,
        )
        if remaining_stage_seconds <= 0:
            self._converge_unfinished(GenerationNodeStatus.TIMED_OUT, "stage budget exhausted")
            return self._result(GenerationScheduleStatus.TIMED_OUT)

        schedule_task = asyncio.create_task(
            self._run_graph(
                plan,
                generator,
                budget,
                task_id=task_id,
                stage_id=stage_id,
                cancel_event=cancel_event,
            ),
            name=f"generation-scheduler:{task_id}:{stage_id}",
        )
        cancel_watcher = (
            asyncio.create_task(cancel_event.wait(), name=f"generation-cancel:{task_id}")
            if cancel_event is not None
            else None
        )
        try:
            async with asyncio.timeout(remaining_stage_seconds):
                if cancel_watcher is None:
                    await schedule_task
                else:
                    done, _ = await asyncio.wait(
                        {schedule_task, cancel_watcher},
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if cancel_watcher in done:
                        self._termination_status = GenerationNodeStatus.CANCELLED
                        schedule_task.cancel()
                        await asyncio.gather(schedule_task, return_exceptions=True)
                        self._converge_unfinished(
                            GenerationNodeStatus.CANCELLED,
                            "generation cancelled by request",
                        )
                        return self._result(GenerationScheduleStatus.CANCELLED)
                    await schedule_task
        except TimeoutError:
            self._termination_status = GenerationNodeStatus.TIMED_OUT
            schedule_task.cancel()
            await asyncio.gather(schedule_task, return_exceptions=True)
            self._converge_unfinished(
                GenerationNodeStatus.TIMED_OUT,
                "generation stage wall-clock budget exceeded",
            )
            return self._result(GenerationScheduleStatus.TIMED_OUT)
        except asyncio.CancelledError:
            self._termination_status = GenerationNodeStatus.CANCELLED
            schedule_task.cancel()
            await asyncio.gather(schedule_task, return_exceptions=True)
            self._converge_unfinished(
                GenerationNodeStatus.CANCELLED,
                "generation scheduler task was cancelled",
            )
            raise
        finally:
            if cancel_watcher is not None:
                cancel_watcher.cancel()
                await asyncio.gather(cancel_watcher, return_exceptions=True)
            self._active_tasks.clear()

        return self._result(self._derive_status())

    def _initialize(self, plan: GenerationPlan) -> None:
        self.nodes = {item.path: _MutableNode(planned_file=item) for item in plan.files}
        self._active_tasks.clear()
        self._max_parallelism = 0
        self._termination_status = None

    async def _run_graph(
        self,
        plan: GenerationPlan,
        generator: Generator,
        budget: ExecutionBudget,
        *,
        task_id: str,
        stage_id: str,
        cancel_event: Optional[asyncio.Event],
    ) -> None:
        reverse_dependencies: Dict[str, Set[str]] = {path: set() for path in self.nodes}
        for item in plan.files:
            for dependency in item.dependencies:
                reverse_dependencies[dependency].add(item.path)

        ready = sorted(
            path for path, node in self.nodes.items() if not node.planned_file.dependencies
        )
        for path in ready:
            self.nodes[path].status = GenerationNodeStatus.READY
        completion_queue: asyncio.Queue[str] = asyncio.Queue()
        loop = asyncio.get_running_loop()

        async with asyncio.TaskGroup() as task_group:
            while not all(node.status.is_terminal for node in self.nodes.values()):
                while ready and self.active_task_count < self.max_concurrent:
                    path = ready.pop(0)
                    node = self.nodes[path]
                    if node.status is not GenerationNodeStatus.READY:
                        continue
                    node.status = GenerationNodeStatus.RUNNING
                    task = task_group.create_task(
                        self._execute_node(
                            node,
                            generator,
                            budget,
                            task_id=task_id,
                            stage_id=stage_id,
                            cancel_event=cancel_event,
                            completion_queue=completion_queue,
                            loop=loop,
                        ),
                        name=f"generate:{path}",
                    )
                    self._active_tasks.add(task)
                    task.add_done_callback(self._active_tasks.discard)
                    self._max_parallelism = max(self._max_parallelism, self.active_task_count)

                if self.active_task_count == 0:
                    unresolved = [
                        path for path, node in self.nodes.items() if not node.status.is_terminal
                    ]
                    if unresolved:
                        self._block_paths(
                            unresolved,
                            code="scheduler_deadlock",
                            message="dependency graph has no runnable nodes",
                        )
                    break

                completed_path = await completion_queue.get()
                completed_node = self.nodes[completed_path]
                if completed_node.status is GenerationNodeStatus.COMPLETED:
                    for downstream in sorted(reverse_dependencies[completed_path]):
                        downstream_node = self.nodes[downstream]
                        if downstream_node.status is not GenerationNodeStatus.PENDING:
                            continue
                        if all(
                            self.nodes[dependency].status is GenerationNodeStatus.COMPLETED
                            for dependency in downstream_node.planned_file.dependencies
                        ):
                            downstream_node.status = GenerationNodeStatus.READY
                            ready.append(downstream)
                    ready.sort()
                else:
                    self._block_descendants(completed_path, reverse_dependencies)

    async def _execute_node(
        self,
        node: _MutableNode,
        generator: Generator,
        budget: ExecutionBudget,
        *,
        task_id: str,
        stage_id: str,
        cancel_event: Optional[asyncio.Event],
        completion_queue: asyncio.Queue[str],
        loop: asyncio.AbstractEventLoop,
    ) -> None:
        file_deadline = loop.time() + budget.file_seconds
        path = node.planned_file.path
        try:
            for attempt in range(1, self.max_retries + 2):
                node.attempts = attempt
                remaining = file_deadline - loop.time()
                if remaining <= 0:
                    self._fail_node(
                        node,
                        GenerationNodeStatus.TIMED_OUT,
                        "file_timeout",
                        "file generation wall-clock budget exceeded",
                    )
                    break
                try:
                    context = FileGenerationContext(
                        task_id=task_id,
                        stage_id=stage_id,
                        planned_file=node.planned_file,
                        upstream_contents=MappingProxyType({
                            dependency: self.committer.shared_context.get_file_content(dependency) or ""
                            for dependency in node.planned_file.dependencies
                        }),
                        attempt=attempt,
                        cancel_event=cancel_event,
                    )
                    async with asyncio.timeout(remaining):
                        generated = await generator(context)
                    if not isinstance(generated, GeneratedContent):
                        raise TypeError("generator must return GeneratedContent")

                    commit_result = self.committer.commit(
                        path,
                        generated.content,
                        model_name=generated.model_name,
                    )
                    if not commit_result.success:
                        node.status = GenerationNodeStatus.FAILED
                        if commit_result.diagnostic is not None:
                            node.diagnostics = (*node.diagnostics, commit_result.diagnostic)
                        break

                    node.completion_event = commit_result.completion_event
                    self.committer.shared_context.update_file_validation(
                        path,
                        generated.validation_passed,
                        list(generated.diagnostics),
                    )
                    if generated.validation_passed:
                        node.status = GenerationNodeStatus.COMPLETED
                    else:
                        self._fail_node(
                            node,
                            GenerationNodeStatus.FAILED,
                            "generation_validation_failed",
                            "generated artifact failed required validation",
                        )
                    break
                except TimeoutError:
                    self._fail_node(
                        node,
                        GenerationNodeStatus.TIMED_OUT,
                        "file_timeout",
                        "file generation wall-clock budget exceeded",
                    )
                    break
                except asyncio.CancelledError:
                    termination_status = self._termination_status or GenerationNodeStatus.CANCELLED
                    self._fail_node(
                        node,
                        termination_status,
                        termination_status.value,
                        "file generation was cancelled or its scheduler was stopped",
                    )
                    break
                except Exception as exc:
                    node.diagnostics = (
                        *node.diagnostics,
                        ArtifactDiagnostic(
                            code="generation_failed",
                            message=str(exc),
                            path=path,
                            details={"attempt": attempt},
                        ),
                    )
                    if attempt > self.max_retries:
                        node.status = GenerationNodeStatus.FAILED
                        break
        finally:
            await completion_queue.put(path)

    def _block_descendants(
        self,
        source: str,
        reverse_dependencies: Mapping[str, Set[str]],
    ) -> None:
        pending = list(reverse_dependencies[source])
        while pending:
            path = pending.pop()
            node = self.nodes[path]
            if node.status in {GenerationNodeStatus.PENDING, GenerationNodeStatus.READY}:
                self._fail_node(
                    node,
                    GenerationNodeStatus.BLOCKED,
                    "generation_blocked",
                    f"upstream artifact {source} is unavailable",
                )
                pending.extend(reverse_dependencies[path])

    def _block_paths(self, paths: list[str], *, code: str, message: str) -> None:
        for path in paths:
            self._fail_node(self.nodes[path], GenerationNodeStatus.BLOCKED, code, message)

    def _converge_unfinished(self, status: GenerationNodeStatus, message: str) -> None:
        for node in self.nodes.values():
            scheduler_cancelled_node = (
                status is GenerationNodeStatus.TIMED_OUT
                and node.status is GenerationNodeStatus.CANCELLED
                and self._termination_status is GenerationNodeStatus.TIMED_OUT
            )
            if not node.status.is_terminal or scheduler_cancelled_node:
                self._fail_node(node, status, status.value, message)

    @staticmethod
    def _fail_node(
        node: _MutableNode,
        status: GenerationNodeStatus,
        code: str,
        message: str,
    ) -> None:
        node.status = status
        node.diagnostics = (
            *node.diagnostics,
            ArtifactDiagnostic(
                code=code,
                message=message,
                path=node.planned_file.path,
            ),
        )

    def _derive_status(self) -> GenerationScheduleStatus:
        statuses = {node.status for node in self.nodes.values()}
        if statuses == {GenerationNodeStatus.COMPLETED}:
            return GenerationScheduleStatus.COMPLETED
        if GenerationNodeStatus.CANCELLED in statuses:
            return GenerationScheduleStatus.CANCELLED
        if GenerationNodeStatus.TIMED_OUT in statuses:
            return GenerationScheduleStatus.TIMED_OUT
        return GenerationScheduleStatus.FAILED

    def _result(self, status: GenerationScheduleStatus) -> GenerationScheduleResult:
        node_results = {
            path: GenerationNodeResult(
                path=path,
                status=node.status,
                attempts=node.attempts,
                diagnostics=node.diagnostics,
                completion_event=node.completion_event,
            )
            for path, node in sorted(self.nodes.items())
        }
        completion_events = tuple(
            node.completion_event
            for node in self.nodes.values()
            if node.completion_event is not None
        )
        counts = {status: 0 for status in GenerationNodeStatus}
        for node in self.nodes.values():
            counts[node.status] += 1
        return GenerationScheduleResult(
            status=status,
            nodes=node_results,
            completion_events=completion_events,
            stats=GenerationScheduleStats(
                total_files=len(self.nodes),
                completed_files=counts[GenerationNodeStatus.COMPLETED],
                failed_files=counts[GenerationNodeStatus.FAILED],
                timed_out_files=counts[GenerationNodeStatus.TIMED_OUT],
                cancelled_files=counts[GenerationNodeStatus.CANCELLED],
                blocked_files=counts[GenerationNodeStatus.BLOCKED],
                max_parallelism=self._max_parallelism,
            ),
        )
