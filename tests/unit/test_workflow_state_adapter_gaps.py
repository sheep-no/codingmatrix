"""补齐 workflow_state_adapter 的任务映射与制品注册。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import workflow_state_adapter as adapter


@pytest.mark.asyncio
async def test_ensure_workflow_task_reuses_mapping(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        adapter,
        "resolve_compatibility_mapping",
        AsyncMock(return_value=SimpleNamespace(unified_id="task-existing")),
    )
    create = AsyncMock()
    monkeypatch.setattr(adapter, "create_task", create)

    result = await adapter.ensure_workflow_task(db, 7, "wf-1", "req")

    assert result == "task-existing"
    create.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_workflow_task_creates_and_maps(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        adapter, "resolve_compatibility_mapping", AsyncMock(return_value=None)
    )
    create = AsyncMock(return_value=SimpleNamespace(task_id="task-new"))
    upsert = AsyncMock()
    monkeypatch.setattr(adapter, "create_task", create)
    monkeypatch.setattr(adapter, "upsert_compatibility_mapping", upsert)

    result = await adapter.ensure_workflow_task(db, 7, "wf-1", "do it")

    assert result == "task-new"
    create.assert_awaited_once_with(
        db,
        7,
        task_type="workflow",
        task_id="wf-1",
        idempotency_key="workflow:wf-1",
        params={"request": "do it", "module": "workflow"},
    )
    upsert.assert_awaited_once_with(
        db,
        7,
        "workflow",
        "workflow_history",
        "wf-1",
        "task",
        "task-new",
        source_table="workflow_history",
    )


@pytest.mark.asyncio
async def test_register_workflow_artifacts(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        adapter, "ensure_workflow_task", AsyncMock(return_value="task-1")
    )
    create_artifact = AsyncMock(
        side_effect=[SimpleNamespace(id="a1"), SimpleNamespace(id="a2")]
    )
    monkeypatch.setattr(adapter, "create_artifact", create_artifact)

    ids = await adapter.register_workflow_artifacts(
        db,
        7,
        "wf-1",
        [
            {"path": "src/a.py", "version": 2, "content_hash": "h1"},
            {
                "artifact_type": "report",
                "storage_uri": "s3://bucket/b",
                "metadata": {"k": "v"},
            },
        ],
    )

    assert ids == ["a1", "a2"]
    first = create_artifact.await_args_list[0].kwargs
    assert first["artifact_type"] == "generated_file"
    assert first["storage_uri"] == "src/a.py"
    assert first["version"] == 2
    assert first["content_hash"] == "h1"
    assert first["metadata"] == {"source": "workflow"}
    second = create_artifact.await_args_list[1].kwargs
    assert second["artifact_type"] == "report"
    assert second["storage_uri"] == "s3://bucket/b"
    assert second["metadata"] == {"k": "v"}


@pytest.mark.asyncio
async def test_register_workflow_artifacts_falls_back_to_name(monkeypatch):
    db = AsyncMock()
    monkeypatch.setattr(
        adapter, "ensure_workflow_task", AsyncMock(return_value="task-1")
    )
    create_artifact = AsyncMock(return_value=SimpleNamespace(id="a1"))
    monkeypatch.setattr(adapter, "create_artifact", create_artifact)

    await adapter.register_workflow_artifacts(db, 7, "wf-1", [{"name": "out.txt"}])

    assert create_artifact.await_args.kwargs["storage_uri"] == "out.txt"
