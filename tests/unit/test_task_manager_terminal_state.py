import pytest

from app.utils.task_manager import TaskManager, TaskStatus


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", [TaskStatus.FAILED.value, TaskStatus.CANCELLED.value])
async def test_execute_task_preserves_terminal_status(monkeypatch, terminal_status):
    manager = TaskManager()
    task_info = {"task_id": "task-1", "status": TaskStatus.PENDING.value, "result": {}}
    saved = []

    async def get_task(_task_id):
        return task_info

    async def save_task(_task_id, value):
        task_info.update(value)
        saved.append(value.copy())

    async def task_func(task_id):
        task_info["status"] = terminal_status

    monkeypatch.setattr(manager, "_get_task_from_redis", get_task)
    monkeypatch.setattr(manager, "_save_task_to_redis", save_task)
    manager._running_tasks["task-1"] = object()

    await manager._execute_task("task-1", task_func, {})

    assert task_info["status"] == terminal_status
    assert task_info.get("completed_at")
