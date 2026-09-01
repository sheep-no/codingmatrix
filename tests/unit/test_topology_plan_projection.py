"""Tests for deriving legacy scheduling state from a frozen plan."""

import pytest

from app.agent.generation_plan import GenerationPlan
from app.agent.topology_scheduler import FileStatus, TopologyScheduler


@pytest.mark.asyncio
async def test_topology_scheduler_builds_nodes_and_ready_queue_from_plan() -> None:
    plan = GenerationPlan.build([
        {"path": "service.py", "dependencies": ["model.py"]},
        {"path": "model.py"},
    ])
    scheduler = TopologyScheduler()

    scheduler.build_from_generation_plan(plan)
    ready = await scheduler.initialize_ready_queue()

    assert ready == ["model.py"]
    assert scheduler.nodes["service.py"].dependency_count == 1
    assert scheduler.adjacency["service.py"] == {"model.py"}
    assert scheduler.nodes["model.py"].status is FileStatus.READY
