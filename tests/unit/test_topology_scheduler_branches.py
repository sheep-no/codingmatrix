"""TopologyScheduler 全分支回归：心跳、调度循环、重试与上下游传播。"""

import asyncio
from types import SimpleNamespace

import pytest

from app.agent import topology_scheduler as ts
from app.agent.topology_scheduler import FileStatus, TopologyScheduler


def _graph(nodes, adjacency=None, reverse=None):
    adjacency = adjacency or {}
    reverse = reverse or {}
    return SimpleNamespace(
        nodes={name: object() for name in nodes},
        adjacency=adjacency,
        reverse_adjacency=reverse,
    )


def _scheduler(**kwargs):
    return TopologyScheduler(
        max_concurrent=kwargs.pop("max_concurrent", 5),
        max_retries=kwargs.pop("max_retries", 0),
        timeout_per_file=kwargs.pop("timeout_per_file", 5),
        heartbeat_timeout=kwargs.pop("heartbeat_timeout", 5),
        **kwargs,
    )


class TestHeartbeatTracker:
    def test_touch_and_elapsed(self, monkeypatch):
        clock = {"now": 100.0}
        monkeypatch.setattr(ts.time, "time", lambda: clock["now"])

        tracker = ts.HeartbeatTracker(timeout=10)
        assert tracker.is_alive() is True

        clock["now"] = 106.0
        assert tracker.elapsed() == pytest.approx(6.0)
        tracker.touch()
        assert tracker.elapsed() == pytest.approx(0.0)

        clock["now"] = 117.0
        assert tracker.is_alive() is False


class TestBuildState:
    def test_build_from_dependency_graph_counts_dependencies(self):
        scheduler = _scheduler()
        graph = _graph(
            ["a", "b"],
            adjacency={"a": set(), "b": {"a"}},
            reverse={"a": {"b"}},
        )

        scheduler.build_from_dependency_graph(graph)

        assert scheduler.stats.total_files == 2
        assert scheduler.nodes["b"].dependency_count == 1
        assert scheduler.adjacency["b"] == {"a"}
        assert scheduler.reverse_adjacency["a"] == {"b"}

    def test_build_from_generation_plan(self):
        scheduler = _scheduler()
        plan = SimpleNamespace(
            files=[
                SimpleNamespace(path="a.py", dependencies=[]),
                SimpleNamespace(path="b.py", dependencies=["a.py"]),
            ]
        )

        scheduler.build_from_generation_plan(plan)

        assert scheduler.stats.total_files == 2
        assert scheduler.nodes["b.py"].dependency_count == 1
        assert scheduler.reverse_adjacency["a.py"] == {"b.py"}
        assert scheduler.adjacency["a.py"] == set()

    def test_build_from_generation_plan_rejects_outside_dependency(self):
        scheduler = _scheduler()
        plan = SimpleNamespace(
            files=[SimpleNamespace(path="a.py", dependencies=["ghost.py"])]
        )

        with pytest.raises(ValueError, match="outside the frozen node set"):
            scheduler.build_from_generation_plan(plan)

    @pytest.mark.asyncio
    async def test_initialize_ready_queue_only_zero_dependency(self):
        scheduler = _scheduler()
        scheduler.build_from_generation_plan(
            SimpleNamespace(
                files=[
                    SimpleNamespace(path="a.py", dependencies=[]),
                    SimpleNamespace(path="b.py", dependencies=["a.py"]),
                ]
            )
        )

        ready = await scheduler.initialize_ready_queue()

        assert ready == ["a.py"]
        assert scheduler.nodes["a.py"].status is FileStatus.READY
        assert scheduler.nodes["b.py"].status is FileStatus.PENDING
        assert scheduler.ready_queue.qsize() == 1


class TestRun:
    @pytest.mark.asyncio
    async def test_run_generates_dependencies_in_order(self):
        scheduler = _scheduler(cancel_event=asyncio.Event())
        scheduler.build_from_generation_plan(
            SimpleNamespace(
                files=[
                    SimpleNamespace(path="a.py", dependencies=[]),
                    SimpleNamespace(path="b.py", dependencies=["a.py"]),
                ]
            )
        )
        seen = []

        async def generator(file_path, upstream_context, tracker):
            seen.append((file_path, dict(upstream_context)))
            return f"content-{file_path}"

        result = await scheduler.run(generator)

        assert result["success"] is True
        assert result["generated_files"] == {
            "a.py": "content-a.py",
            "b.py": "content-b.py",
        }
        assert seen[0][0] == "a.py"
        assert seen[1][0] == "b.py"
        assert seen[1][1] == {"a.py": "content-a.py"}
        assert scheduler.stats.max_parallelism >= 1
        assert scheduler.stats.avg_parallelism > 0

    @pytest.mark.asyncio
    async def test_run_reports_progress_events(self):
        scheduler = _scheduler()
        scheduler.build_from_dependency_graph(_graph(["main.py"]))
        events = []

        async def generator(file_path, upstream_context, tracker):
            return "ok"

        def progress(event, file_path, completed, total):
            events.append((event, file_path, completed, total))

        result = await scheduler.run(generator, progress_callback=progress)

        assert result["success"] is True
        assert events[0] == ("start", "main.py", 0, 1)
        assert events[-1] == ("completed", "main.py", 1, 1)

    @pytest.mark.asyncio
    async def test_run_detects_deadlock(self):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode("a.py", 1)
        scheduler.nodes["b.py"] = ts.ScheduleNode("b.py", 1)
        scheduler.adjacency["a.py"] = {"b.py"}
        scheduler.adjacency["b.py"] = {"a.py"}
        scheduler.stats.total_files = 2

        async def generator(file_path, upstream_context, tracker):
            return "never"

        result = await scheduler.run(generator, global_timeout=2)

        assert result["success"] is False
        assert set(result["failed_files"]) == {"a.py", "b.py"}

    @pytest.mark.asyncio
    async def test_run_global_timeout_fails_ready_nodes(self):
        scheduler = _scheduler()
        scheduler.build_from_dependency_graph(_graph(["main.py"]))

        async def generator(file_path, upstream_context, tracker):
            return "never"

        result = await scheduler.run(generator, global_timeout=-1)

        assert result["success"] is False
        assert result["failed_files"] == ["main.py"]
        assert scheduler.nodes["main.py"].error == "调度器在任务完成前停止"

    @pytest.mark.asyncio
    async def test_run_handles_cancelled_task(self, monkeypatch):
        scheduler = _scheduler()
        scheduler.build_from_dependency_graph(_graph(["main.py"]))

        async def cancelled(file_path, generator, progress_callback=None):
            scheduler._stop_event.set()
            raise asyncio.CancelledError

        monkeypatch.setattr(scheduler, "_generate_file_with_retry", cancelled)

        async def generator(file_path, upstream_context, tracker):
            return "never"

        result = await scheduler.run(generator)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_run_handles_task_exception(self, monkeypatch):
        scheduler = _scheduler()
        scheduler.build_from_dependency_graph(_graph(["main.py"]))

        async def boom(file_path, generator, progress_callback=None):
            scheduler._stop_event.set()
            raise RuntimeError("task boom")

        monkeypatch.setattr(scheduler, "_generate_file_with_retry", boom)

        async def generator(file_path, upstream_context, tracker):
            return "never"

        result = await scheduler.run(generator)

        assert result["success"] is False

    @pytest.mark.asyncio
    async def test_run_partial_failure_blocks_downstream(self):
        scheduler = _scheduler(max_retries=0)
        scheduler.build_from_generation_plan(
            SimpleNamespace(
                files=[
                    SimpleNamespace(path="a.py", dependencies=[]),
                    SimpleNamespace(path="b.py", dependencies=["a.py"]),
                    SimpleNamespace(path="c.py", dependencies=["b.py"]),
                ]
            )
        )

        async def generator(file_path, upstream_context, tracker):
            if file_path == "a.py":
                return "bad"
            return "ok"

        async def fake_retry(file_path, gen, progress_callback=None):
            node = scheduler.nodes[file_path]
            if file_path == "a.py":
                node.status = FileStatus.FAILED
                scheduler.stats.failed_files += 1
                await scheduler._block_downstream(file_path)
                return
            node.status = FileStatus.COMPLETED
            scheduler.completed_files[file_path] = "ok"
            scheduler.stats.completed_files += 1
            await scheduler._trigger_downstream(file_path)

        scheduler._generate_file_with_retry = fake_retry
        result = await scheduler.run(generator)

        assert result["success"] is False
        assert scheduler.nodes["b.py"].status is FileStatus.BLOCKED
        assert scheduler.nodes["c.py"].status is FileStatus.FAILED

    @pytest.mark.asyncio
    async def test_run_exits_when_only_terminal_nodes_remain(self, monkeypatch):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode(
            "a.py", 0, status=FileStatus.COMPLETED
        )
        scheduler._stop_event.clear()

        calls = {"n": 0}

        def should_stop():
            calls["n"] += 1
            return calls["n"] > 2

        monkeypatch.setattr(scheduler, "_should_stop", should_stop)

        async def generator(file_path, upstream_context, tracker):
            return "never"

        result = await scheduler.run(generator)

        assert result["success"] is True
        assert calls["n"] >= 2

    @pytest.mark.asyncio
    async def test_run_waits_while_generating(self):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode(
            "a.py", 1, status=FileStatus.GENERATING
        )

        async def finish_later():
            await asyncio.sleep(0.05)
            scheduler.nodes["a.py"].status = FileStatus.COMPLETED

        finisher = asyncio.create_task(finish_later())

        async def generator(file_path, upstream_context, tracker):
            return "never"

        result = await scheduler.run(generator, global_timeout=5)
        await finisher

        assert result["success"] is True

    @pytest.mark.asyncio
    async def test_run_breaks_when_queue_reports_empty(self, monkeypatch):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode("a.py", 0, status=FileStatus.READY)

        class _RacyQueue:
            def qsize(self):
                return 1

            async def put(self, item):
                return None

            def get_nowait(self):
                raise asyncio.QueueEmpty

        scheduler.ready_queue = _RacyQueue()

        calls = {"n": 0}

        def should_stop():
            calls["n"] += 1
            return calls["n"] > 1

        monkeypatch.setattr(scheduler, "_should_stop", should_stop)

        async def generator(file_path, upstream_context, tracker):
            return "never"

        result = await scheduler.run(generator)

        assert result["success"] is False
        assert scheduler.nodes["a.py"].status is FileStatus.FAILED


class TestGenerateWithRetry:
    @pytest.mark.asyncio
    async def test_success_marks_completed_and_triggers_downstream(self):
        scheduler = _scheduler()
        scheduler.build_from_generation_plan(
            SimpleNamespace(
                files=[
                    SimpleNamespace(path="a.py", dependencies=[]),
                    SimpleNamespace(path="b.py", dependencies=["a.py"]),
                ]
            )
        )

        async def generator(file_path, upstream_context, tracker):
            tracker.touch()
            return "code"

        await scheduler._generate_file_with_retry("a.py", generator)

        assert scheduler.nodes["a.py"].status is FileStatus.COMPLETED
        assert scheduler.nodes["b.py"].status is FileStatus.READY
        assert scheduler.ready_queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_exception_retries_then_succeeds(self):
        scheduler = _scheduler(max_retries=1)
        scheduler.build_from_dependency_graph(_graph(["a.py"]))
        attempts = {"n": 0}

        async def generator(file_path, upstream_context, tracker):
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("transient")
            return "ok"

        await scheduler._generate_file_with_retry("a.py", generator)

        assert attempts["n"] == 2
        assert scheduler.nodes["a.py"].status is FileStatus.COMPLETED
        assert scheduler.nodes["a.py"].retry_count == 1

    @pytest.mark.asyncio
    async def test_timeout_retries_and_fails(self):
        scheduler = _scheduler(max_retries=0, timeout_per_file=0.01)
        scheduler.build_from_dependency_graph(_graph(["a.py"]))
        events = []

        async def generator(file_path, upstream_context, tracker):
            await asyncio.sleep(1)
            return "never"

        def progress(event, file_path, completed, total):
            events.append(event)

        await scheduler._generate_file_with_retry("a.py", generator, progress)

        assert scheduler.nodes["a.py"].status is FileStatus.FAILED
        assert scheduler.nodes["a.py"].retry_count == 1
        assert events == ["start", "failed"]

    @pytest.mark.asyncio
    async def test_cancellation_marks_error_and_reraises(self):
        scheduler = _scheduler(max_retries=1)
        scheduler.build_from_dependency_graph(_graph(["a.py"]))

        async def generator(file_path, upstream_context, tracker):
            raise asyncio.CancelledError

        with pytest.raises(asyncio.CancelledError):
            await scheduler._generate_file_with_retry("a.py", generator)

        assert scheduler.nodes["a.py"].error == "任务被取消"
        assert scheduler.nodes["a.py"].retry_count == 1


class TestRunWithHeartbeat:
    @pytest.mark.asyncio
    async def test_without_tracker_creates_one(self):
        scheduler = _scheduler()

        async def work():
            return "done"

        assert await scheduler._run_with_heartbeat(work(), "a.py") == "done"

    @pytest.mark.asyncio
    async def test_dead_tracker_raises_timeout(self, monkeypatch):
        scheduler = _scheduler()
        tracker = ts.HeartbeatTracker(timeout=-1)

        async def slow():
            await asyncio.sleep(10)
            return "never"

        async def immediate_timeout(awaitable, timeout=None):
            if hasattr(awaitable, "close"):
                awaitable.close()
            raise asyncio.TimeoutError

        monkeypatch.setattr(ts.asyncio, "wait_for", immediate_timeout)

        with pytest.raises(asyncio.TimeoutError, match="心跳超时"):
            await scheduler._run_with_heartbeat(slow(), "a.py", tracker)

    @pytest.mark.asyncio
    async def test_cancellation_cancels_inner_task(self):
        scheduler = _scheduler()
        started = asyncio.Event()

        async def slow():
            started.set()
            await asyncio.sleep(10)
            return "never"

        outer = asyncio.create_task(
            scheduler._run_with_heartbeat(slow(), "a.py", ts.HeartbeatTracker())
        )
        await started.wait()
        outer.cancel()

        with pytest.raises(asyncio.CancelledError):
            await outer

    @pytest.mark.asyncio
    async def test_alive_tracker_keeps_waiting(self, monkeypatch):
        scheduler = _scheduler()
        tracker = ts.HeartbeatTracker(timeout=1000)
        calls = {"n": 0}
        real_wait_for = asyncio.wait_for

        async def flaky_wait_for(awaitable, timeout=None):
            calls["n"] += 1
            if calls["n"] == 1:
                if hasattr(awaitable, "close"):
                    awaitable.close()
                raise asyncio.TimeoutError
            return await real_wait_for(awaitable, timeout=timeout)

        monkeypatch.setattr(ts.asyncio, "wait_for", flaky_wait_for)

        async def work():
            return "done"

        assert await scheduler._run_with_heartbeat(
            work(), "a.py", tracker
        ) == "done"
        assert calls["n"] >= 2

    @pytest.mark.asyncio
    async def test_task_finishing_during_continue_returns_result(self, monkeypatch):
        scheduler = _scheduler()
        tracker = ts.HeartbeatTracker(timeout=1000)

        async def fast():
            return "done"

        async def fake_wait_for(awaitable, timeout=None):
            if hasattr(awaitable, "close"):
                awaitable.close()
            await asyncio.sleep(0)
            await asyncio.sleep(0)
            raise asyncio.TimeoutError

        monkeypatch.setattr(ts.asyncio, "wait_for", fake_wait_for)

        assert await scheduler._run_with_heartbeat(
            fast(), "a.py", tracker
        ) == "done"


class TestDownstreamPropagation:
    @pytest.mark.asyncio
    async def test_trigger_pending_reaches_zero(self):
        scheduler = _scheduler()
        scheduler.nodes["b.py"] = ts.ScheduleNode("b.py", 1)
        scheduler.reverse_adjacency["a.py"] = {"b.py"}

        await scheduler._trigger_downstream("a.py")

        assert scheduler.nodes["b.py"].status is FileStatus.READY
        assert scheduler.nodes["b.py"].dependency_count == 0
        assert scheduler.stats.schedule_log[-1]["event"] == "triggered"

    @pytest.mark.asyncio
    async def test_trigger_pending_keeps_count(self):
        scheduler = _scheduler()
        scheduler.nodes["b.py"] = ts.ScheduleNode("b.py", 2)
        scheduler.reverse_adjacency["a.py"] = {"b.py"}

        await scheduler._trigger_downstream("a.py")

        assert scheduler.nodes["b.py"].status is FileStatus.PENDING
        assert scheduler.nodes["b.py"].dependency_count == 1

    @pytest.mark.asyncio
    async def test_trigger_skips_unknown_and_terminal_nodes(self):
        scheduler = _scheduler()
        scheduler.nodes["done.py"] = ts.ScheduleNode("done.py", 0, status=FileStatus.COMPLETED)
        scheduler.reverse_adjacency["a.py"] = {"missing.py", "done.py"}

        await scheduler._trigger_downstream("a.py")

        assert scheduler.nodes["done.py"].status is FileStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_trigger_unblocks_when_all_dependencies_completed(self):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode("a.py", 0, status=FileStatus.COMPLETED)
        scheduler.nodes["b.py"] = ts.ScheduleNode("b.py", 1, status=FileStatus.BLOCKED)
        scheduler.adjacency["b.py"] = {"a.py"}
        scheduler.reverse_adjacency["a.py"] = {"b.py"}

        await scheduler._trigger_downstream("a.py")

        assert scheduler.nodes["b.py"].status is FileStatus.READY

    @pytest.mark.asyncio
    async def test_trigger_keeps_blocked_when_dependency_pending(self):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode("a.py", 0, status=FileStatus.COMPLETED)
        scheduler.nodes["c.py"] = ts.ScheduleNode("c.py", 1, status=FileStatus.PENDING)
        scheduler.nodes["b.py"] = ts.ScheduleNode("b.py", 2, status=FileStatus.BLOCKED)
        scheduler.adjacency["b.py"] = {"a.py", "c.py"}
        scheduler.reverse_adjacency["a.py"] = {"b.py"}

        await scheduler._trigger_downstream("a.py")

        assert scheduler.nodes["b.py"].status is FileStatus.BLOCKED

    @pytest.mark.asyncio
    async def test_trigger_unblocks_with_missing_dependency_entry(self):
        scheduler = _scheduler()
        scheduler.nodes["b.py"] = ts.ScheduleNode("b.py", 1, status=FileStatus.BLOCKED)
        scheduler.adjacency["b.py"] = {"ghost.py"}
        scheduler.reverse_adjacency["a.py"] = {"b.py"}

        await scheduler._trigger_downstream("a.py")

        assert scheduler.nodes["b.py"].status is FileStatus.READY

    @pytest.mark.asyncio
    async def test_block_downstream_states(self):
        scheduler = _scheduler()
        scheduler.nodes["ready.py"] = ts.ScheduleNode("ready.py", 0, status=FileStatus.READY)
        scheduler.nodes["pending.py"] = ts.ScheduleNode("pending.py", 0, status=FileStatus.PENDING)
        scheduler.nodes["done.py"] = ts.ScheduleNode("done.py", 0, status=FileStatus.COMPLETED)
        scheduler.reverse_adjacency["a.py"] = {
            "missing.py",
            "ready.py",
            "pending.py",
            "done.py",
        }

        await scheduler._block_downstream("a.py")

        assert scheduler.nodes["ready.py"].status is FileStatus.BLOCKED
        assert scheduler.nodes["pending.py"].status is FileStatus.BLOCKED
        assert scheduler.nodes["done.py"].status is FileStatus.COMPLETED
        assert scheduler.stats.schedule_log[-1]["event"] == "blocked"

    @pytest.mark.asyncio
    async def test_block_downstream_without_matches_is_silent(self):
        scheduler = _scheduler()
        scheduler.nodes["done.py"] = ts.ScheduleNode("done.py", 0, status=FileStatus.COMPLETED)
        scheduler.reverse_adjacency["a.py"] = {"done.py"}
        before = len(scheduler.stats.schedule_log)

        await scheduler._block_downstream("a.py")

        assert len(scheduler.stats.schedule_log) == before


class TestIntrospection:
    def test_build_upstream_context_only_completed(self):
        scheduler = _scheduler()
        scheduler.adjacency["b.py"] = {"a.py", "c.py"}
        scheduler.completed_files["a.py"] = "code-a"

        assert scheduler._build_upstream_context("b.py") == {"a.py": "code-a"}

    def test_should_stop_honours_event(self):
        scheduler = _scheduler()
        scheduler._stop_event.set()
        assert scheduler._should_stop() is True

    def test_should_stop_with_actionable_nodes(self):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode("a.py", 0)
        assert scheduler._should_stop() is False

    def test_should_stop_logs_blocked_nodes(self):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode("a.py", 1, status=FileStatus.BLOCKED)
        assert scheduler._should_stop() is True

    @pytest.mark.asyncio
    async def test_cancel_sets_event_and_cancels_tasks(self):
        scheduler = _scheduler()
        task = asyncio.create_task(asyncio.sleep(10))
        scheduler._running_tasks.add(task)

        scheduler.cancel()
        await asyncio.gather(task, return_exceptions=True)

        assert scheduler._stop_event.is_set() is True
        assert task.cancelled() is True

    def test_get_stats_counts_blocked(self):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode("a.py", 1, status=FileStatus.BLOCKED)
        scheduler.stats.total_files = 1
        scheduler.stats.avg_parallelism = 1.234

        stats = scheduler.get_stats()

        assert stats["blocked_files"] == 1
        assert stats["avg_parallelism"] == 1.23
        assert stats["interface_errors"] == 0

    def test_file_status_helpers(self):
        scheduler = _scheduler()
        scheduler.nodes["a.py"] = ts.ScheduleNode("a.py", 0, status=FileStatus.READY)

        assert scheduler.get_file_status("a.py") is FileStatus.READY
        assert scheduler.get_file_status("missing.py") is None
        assert scheduler.is_file_ready("a.py") is True
        assert scheduler.is_file_ready("missing.py") is False

    def test_log_schedule_entry_shape(self):
        scheduler = _scheduler()

        scheduler._log_schedule("completed", ["a.py"], source="b.py", error="e")

        entry = scheduler.stats.schedule_log[-1]
        assert entry["event"] == "completed"
        assert entry["files"] == ["a.py"]
        assert entry["source"] == "b.py"
        assert entry["error"] == "e"
        assert isinstance(entry["timestamp"], float)
