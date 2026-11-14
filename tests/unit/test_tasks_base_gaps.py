"""tasks.base WebSocket 通知、结果落盘与参数解析补测。"""

import json

import pytest

from app.tasks import base


class _WS:
    def __init__(self):
        self.calls = []

    async def send_task_update(self, user_id, task_id, payload):
        self.calls.append((user_id, task_id, payload))


class _Task(base.BaseTask):
    request = type("Request", (), {"retries": 0, "id": "t1"})()

    def __init__(self, ws):
        self._ws_manager = ws

    def update_state(self, **kwargs):
        self.updated = kwargs


async def test_progress_callback_clamps_and_sends():
    ws = _WS()
    callback = base.ProgressCallback("t1", 7, ws)

    await callback.update(150, "too high")
    await callback.update(-5, "too low")

    assert callback._last_progress == 0
    assert [item[2]["progress"] for item in ws.calls] == [100, 0]


async def test_progress_callback_without_manager_or_user():
    callback = base.ProgressCallback("t1", 0, None)
    await callback.update(50, "ok")
    assert callback._last_progress == 50


def test_ws_manager_property_caches_instance():
    task = _Task(None)
    task._ws_manager = "cached"
    assert task.ws_manager == "cached"


def test_ws_manager_property_loads_default():
    task = _Task(None)
    assert task.ws_manager is base.__dict__.get("ws_manager", task.ws_manager)


def test_get_progress_callback_returns_callback():
    task = _Task(_WS())
    callback = task._get_progress_callback("t1", "9")
    assert isinstance(callback, base.ProgressCallback)
    assert callback.user_id == 9


def test_on_failure_notifies(monkeypatch):
    ws = _WS()
    task = _Task(ws)

    task.on_failure(RuntimeError("boom"), "t1", (), {"user_id": 3}, None)

    assert ws.calls[0][2]["status"] == "FAILURE"
    assert ws.calls[0][2]["error"] == "boom"


def test_on_failure_swallows_notification_error(monkeypatch):
    task = _Task(_WS())

    def boom(coro):
        coro.close()
        raise RuntimeError("loop gone")

    monkeypatch.setattr(base, "_run_coroutine_sync", boom)

    task.on_failure(RuntimeError("x"), "t1", (), None, None)


def test_on_success_notifies():
    ws = _WS()
    task = _Task(ws)

    task.on_success({"ok": True}, "t1", (), {"user_id": 4})

    assert ws.calls[0][2] == {"status": "SUCCESS", "result": {"ok": True}}


def test_on_retry_updates_state(monkeypatch):
    task = _Task(_WS())
    monkeypatch.setattr(type(task), "request", type("R", (), {"retries": 2, "id": "t1"})())
    task.max_retries = 5

    task.on_retry(RuntimeError("x"), "t1", (), {}, None)

    assert task.updated["state"] == "RETRYING"
    assert task.updated["meta"]["retry_count"] == 2


def test_on_timeout_notifies(monkeypatch):
    task = _Task(_WS())
    seen = []

    def fake_run(coro):
        seen.append(coro)
        coro.close()
        return None

    monkeypatch.setattr(base, "_run_coroutine_sync", fake_run)

    task.on_timeout(True, 30)
    assert seen


async def test_notify_failure_requires_manager_and_user():
    await base.BaseTask()._notify_failure("t1", 0, "err")
    await base.BaseTask()._notify_success("t1", 0, "result")
    await base.BaseTask()._notify_timeout("t1")


def test_run_coroutine_sync_in_thread_when_loop_running():
    async def inner():
        return 42

    async def outer():
        return base._run_coroutine_sync(inner())

    import asyncio

    assert asyncio.run(outer()) == 42


def test_handle_task_result_inline():
    assert base.handle_task_result({"a": 1})["stored"] == "inline"


def test_handle_task_result_stores_large_payload(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = {"task_id": "abc/../def", "data": "x" * 2000}

    handled = base.handle_task_result(result, max_size=10)

    assert handled["stored"] == "file"
    assert handled["path"].endswith("abcdef.json")
    with open(handled["path"], encoding="utf-8") as handle:
        assert json.load(handle)["data"] == "x" * 2000


def test_handle_task_result_sanitizes_to_unknown(monkeypatch):
    monkeypatch.setattr(base.os, "makedirs", lambda *a, **k: None)
    monkeypatch.setattr(base.os.path, "dirname", lambda _: "/tmp")
    opened = {}

    class _File:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def write(self, _data):
            return None

    def fake_open(path, *args, **kwargs):
        opened["path"] = path
        return _File()

    monkeypatch.setattr(base, "open", fake_open, raising=False)

    handled = base.handle_task_result({"task_id": "///", "data": "y" * 100}, max_size=1)

    assert handled["path"] == "/tmp/task_results/unknown.json"


def test_parse_priority_and_timeout():
    assert base.parse_priority("HIGH") == 8
    assert base.parse_priority("unknown") == 5
    assert base.parse_priority(3) == 5
    assert base.parse_timeout(None) == 300
    assert base.parse_timeout(1) == 30
    assert base.parse_timeout(99999) == 3600


def test_on_success_swallows_notification_error(monkeypatch):
    task = _Task(_WS())

    def boom(coro):
        coro.close()
        raise RuntimeError("notify failed")

    monkeypatch.setattr(base, "_run_coroutine_sync", boom)
    task.on_success("ok", "t1", (), None)


def test_on_timeout_swallows_notification_error(monkeypatch):
    task = _Task(_WS())

    def boom(coro):
        coro.close()
        raise RuntimeError("notify failed")

    monkeypatch.setattr(base, "_run_coroutine_sync", boom)
    task.on_timeout(True, 30)
