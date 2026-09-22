"""TSK25：BaseTask 回调在异步上下文中也必须把通知送达。

回调原用 `asyncio.run`，一旦调用方已有运行中的事件循环（异步 worker、内联
测试），会抛 running-loop 并只记一条错误日志，WebSocket 通知静默丢失。
"""

import pytest

from app.tasks.base import BaseTask


class _RecordingWS:
    def __init__(self):
        self.calls = []

    async def send_task_update(self, user_id, task_id, payload):
        self.calls.append((user_id, task_id, payload))


class _DummyTask(BaseTask):
    abstract = True


def _task_with_ws():
    task = _DummyTask()
    ws = _RecordingWS()
    task._ws_manager = ws
    return task, ws


@pytest.mark.asyncio
async def test_on_success_notifies_inside_running_loop():
    task, ws = _task_with_ws()

    task.on_success({"ok": True}, "task-1", (), {"user_id": 7})

    assert ws.calls == [(7, "task-1", {"status": "SUCCESS", "result": {"ok": True}})]


@pytest.mark.asyncio
async def test_on_failure_notifies_inside_running_loop():
    task, ws = _task_with_ws()

    task.on_failure(RuntimeError("boom"), "task-2", (), {"user_id": 9}, None)

    assert ws.calls == [(9, "task-2", {"status": "FAILURE", "error": "boom"})]


def test_on_success_notifies_without_running_loop():
    task, ws = _task_with_ws()

    task.on_success("done", "task-3", (), {"user_id": 3})

    assert ws.calls == [(3, "task-3", {"status": "SUCCESS", "result": "done"})]
