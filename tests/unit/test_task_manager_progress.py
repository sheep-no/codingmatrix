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


@pytest.mark.asyncio
async def test_get_task_info_async_falls_back_to_memory_when_redis_misses(monkeypatch):
    """创建时 Redis 不可用 -> 任务只在内存；Redis 恢复后键不存在仍应能查到。"""
    manager = TaskManager()
    manager._tasks["task-memory"] = {
        "task_id": "task-memory",
        "status": TaskStatus.RUNNING.value,
    }

    class _RedisWithoutKey:
        async def get(self, _key):
            return None

    async def get_redis():
        return _RedisWithoutKey()

    monkeypatch.setattr(manager, "_get_redis", get_redis)

    task_info = await manager.get_task_info_async("task-memory")

    assert task_info is not None
    assert task_info["status"] == TaskStatus.RUNNING.value
    manager._tasks.pop("task-memory", None)
