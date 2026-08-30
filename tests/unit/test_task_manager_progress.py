import json

import pytest

from app.utils.task_manager import TaskManager, TaskStatus


@pytest.mark.asyncio
async def test_update_progress_preserves_status_result_and_error(monkeypatch):
    manager = TaskManager()
    task_info = {
        "task_id": "task-1",
        "status": TaskStatus.RUNNING.value,
        "result": {},
        "error_message": None,
    }
    saved = {}

    async def get_task(_task_id):
        return task_info

    async def save_task(task_id, value):
        saved[task_id] = value.copy()

    monkeypatch.setattr(manager, "_get_task_from_redis", get_task)
    monkeypatch.setattr(manager, "_save_task_to_redis", save_task)

    await manager.update_progress(
        "task-1",
        100,
        "PPT 生成完成",
        status="completed",
        result_data=json.dumps({"ppt_id": "task-1"}),
        error_message="ignored when empty",
    )

    assert saved["task-1"]["status"] == "success"
    assert saved["task-1"]["result"] == {"ppt_id": "task-1"}
    assert saved["task-1"]["error_message"] == "ignored when empty"
