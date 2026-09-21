"""TSK7/TSK11/TSK12：app/tasks/base.py 的输入契约加固。

- TSK7：ProgressCallback.update 不再透传越界进度
- TSK11：handle_task_result 对非 dict 大结果不再抛 AttributeError
- TSK12：parse_priority 对非字符串输入落默认档，而非抛 AttributeError
"""

import os

import pytest

from app.tasks.base import ProgressCallback, handle_task_result, parse_priority


class _FakeWSManager:
    def __init__(self):
        self.payloads = []

    async def send_task_update(self, user_id, task_id, payload):
        self.payloads.append(payload)


@pytest.mark.asyncio
async def test_progress_clamped_to_range():
    ws = _FakeWSManager()
    callback = ProgressCallback(task_id="t1", user_id=1, ws_manager=ws)

    await callback.update(150, "over")
    await callback.update(-20, "under")

    assert [p["progress"] for p in ws.payloads] == [100, 0]
    assert callback._last_progress == 0


@pytest.mark.asyncio
async def test_progress_without_ws_manager_still_clamps():
    callback = ProgressCallback(task_id="t2", user_id=1)
    await callback.update(999)
    assert callback._last_progress == 100


def test_handle_task_result_non_dict_large_result():
    processed = handle_task_result(["x" * 2000], max_size=100)

    assert processed["stored"] == "file"
    assert processed["path"].endswith("unknown.json")
    if os.path.exists(processed["path"]):
        os.remove(processed["path"])


def test_parse_priority_non_string_falls_back():
    assert parse_priority(None) == 5
    assert parse_priority(3) == 5
    assert parse_priority("HIGH") == 8
    assert parse_priority("unknown") == 5
