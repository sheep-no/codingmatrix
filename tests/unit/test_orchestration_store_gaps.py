"""OrchestrationCheckpointStore 校验分支补测。"""

import json

import pytest

from app.agent.orchestration.models import OrchestrationState
from app.agent.orchestration.store import (
    CURRENT_ORCHESTRATION_SCHEMA_VERSION,
    OrchestrationCheckpointStore,
)


def _state(task_id="task-1"):
    return OrchestrationState(
        task_id=task_id,
        session_id="session-1",
        engine_version="core-v1",
        mode="traditional",
    )


@pytest.mark.parametrize("task_id", ["", "../escape", "nested/name"])
def test_path_for_rejects_unsafe_task_ids(tmp_path, task_id):
    store = OrchestrationCheckpointStore(tmp_path)
    with pytest.raises(ValueError, match="simple non-empty file name"):
        store.path_for(task_id)


@pytest.mark.asyncio
async def test_load_latest_returns_none_when_absent(tmp_path):
    store = OrchestrationCheckpointStore(tmp_path)
    assert await store.load_latest("missing") is None


@pytest.mark.asyncio
async def test_load_latest_rejects_unsupported_schema(tmp_path):
    store = OrchestrationCheckpointStore(tmp_path)
    path = store.path_for("task-1")
    path.write_text(json.dumps({"schema_version": 99, "state": {}}), encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported orchestration checkpoint schema"):
        await store.load_latest("task-1")


@pytest.mark.asyncio
async def test_load_latest_rejects_missing_state_object(tmp_path):
    store = OrchestrationCheckpointStore(tmp_path)
    path = store.path_for("task-1")
    path.write_text(
        json.dumps({"schema_version": CURRENT_ORCHESTRATION_SCHEMA_VERSION, "state": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="must contain a state object"):
        await store.load_latest("task-1")


@pytest.mark.asyncio
async def test_save_then_load_roundtrips_state(tmp_path):
    store = OrchestrationCheckpointStore(tmp_path)
    state = _state()

    await store.save(state)

    assert await store.load_latest("task-1") == state
    assert not list(tmp_path.glob("*.tmp"))
