import asyncio
from types import SimpleNamespace

import pytest

from app.agent.topology_scheduler import FileStatus, TopologyScheduler


@pytest.mark.asyncio
async def test_scheduler_applies_per_file_timeout_and_reaches_failed_state():
    scheduler = TopologyScheduler(timeout_per_file=0.01, heartbeat_timeout=10)
    graph = SimpleNamespace(
        nodes={"main.py": object()},
        adjacency={"main.py": set()},
        reverse_adjacency={"main.py": set()},
    )
    scheduler.build_from_dependency_graph(graph)

    async def stuck_generator(file_path, upstream_context, tracker):
        await asyncio.sleep(1)
        return ""

    result = await scheduler.run(stuck_generator, global_timeout=1)

    assert result["success"] is False
    assert result["failed_files"] == ["main.py"]
    assert scheduler.nodes["main.py"].status is FileStatus.FAILED


@pytest.mark.asyncio
async def test_scheduler_reports_incomplete_nodes_as_failure_after_stop():
    cancel_event = asyncio.Event()
    scheduler = TopologyScheduler(
        timeout_per_file=10,
        heartbeat_timeout=10,
        cancel_event=cancel_event,
    )
    graph = SimpleNamespace(
        nodes={"main.py": object()},
        adjacency={"main.py": set()},
        reverse_adjacency={"main.py": set()},
    )
    scheduler.build_from_dependency_graph(graph)

    async def stuck_generator(file_path, upstream_context, tracker):
        await asyncio.sleep(1)
        return ""

    async def stop_scheduler():
        await asyncio.sleep(0.01)
        cancel_event.set()

    stopper = asyncio.create_task(stop_scheduler())
    result = await scheduler.run(stuck_generator, global_timeout=1)
    await stopper

    assert result["success"] is False
    assert scheduler.nodes["main.py"].status is FileStatus.FAILED
