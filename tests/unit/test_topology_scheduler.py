import asyncio
from types import SimpleNamespace

import pytest

from app.agent.topology_scheduler import FileStatus, TopologyScheduler
from app.core.llm_errors import USER_API_KEY_NOT_FOUND
from app.utils.aicloud.llm_caller import UserAPIKeyNotFoundError


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


@pytest.mark.asyncio
async def test_scheduler_aborts_immediately_on_api_key_expiry():
    scheduler = TopologyScheduler(
        max_concurrent=2, max_retries=2, timeout_per_file=600, heartbeat_timeout=600
    )
    graph = SimpleNamespace(
        nodes={"a.py": object(), "b.py": object()},
        adjacency={"a.py": set(), "b.py": set()},
        reverse_adjacency={"a.py": set(), "b.py": set()},
    )
    scheduler.build_from_dependency_graph(graph)
    attempts = {"a.py": 0, "b.py": 0}

    async def key_expired_generator(file_path, upstream_context, tracker):
        attempts[file_path] += 1
        raise UserAPIKeyNotFoundError()

    result = await asyncio.wait_for(
        scheduler.run(key_expired_generator, global_timeout=7200),
        timeout=1,
    )

    assert result["error_code"] == USER_API_KEY_NOT_FOUND
    assert "API Key" in result["error_message"]
    assert any(count == 1 for count in attempts.values())
    assert all(count <= 1 for count in attempts.values())
    assert scheduler._stop_event.is_set()
    assert all(
        node.status is FileStatus.FAILED for node in scheduler.nodes.values()
    )


@pytest.mark.asyncio
async def test_scheduler_detects_api_key_error_inside_wrapper_chain():
    scheduler = TopologyScheduler(max_retries=2, timeout_per_file=600)
    graph = SimpleNamespace(
        nodes={"main.py": object()},
        adjacency={"main.py": set()},
        reverse_adjacency={"main.py": set()},
    )
    scheduler.build_from_dependency_graph(graph)

    async def wrapped_failure(file_path, upstream_context, tracker):
        try:
            raise UserAPIKeyNotFoundError()
        except UserAPIKeyNotFoundError as exc:
            raise RuntimeError("ReAct LLM call failed") from exc

    result = await asyncio.wait_for(
        scheduler.run(wrapped_failure, global_timeout=7200),
        timeout=1,
    )

    assert result["error_code"] == USER_API_KEY_NOT_FOUND
    assert scheduler.nodes["main.py"].error == "用户 API Key 未找到或已过期，请重新配置"
