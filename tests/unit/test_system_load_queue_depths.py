"""SystemLoadMonitor 模型队列深度采集的行为回归。

覆盖两点：阻塞的 Celery inspect 调用必须在工作线程执行；active 与
reserved 中同一 task id 只计一次。
"""

import asyncio
import threading

import app.celery_app as celery_module
from app.utils.system_load import SystemLoadMonitor


class _FakeInspect:
    def __init__(self, active, reserved, thread_log):
        self._active = active
        self._reserved = reserved
        self._thread_log = thread_log

    def active(self):
        self._thread_log.append(threading.get_ident())
        return self._active

    def reserved(self):
        self._thread_log.append(threading.get_ident())
        return self._reserved


def _install_fake_celery(monkeypatch, active, reserved, thread_log):
    class _FakeControl:
        def inspect(self, timeout=None):
            thread_log.append(threading.get_ident())
            return _FakeInspect(active, reserved, thread_log)

    class _FakeCelery:
        control = _FakeControl()

    monkeypatch.setattr(celery_module, "celery_app", _FakeCelery())


def test_queue_depth_collection_runs_off_event_loop(monkeypatch):
    thread_log = []
    _install_fake_celery(
        monkeypatch,
        active={"worker-1": [{"id": "t1", "args": [{"model": "gpt-4"}]}]},
        reserved={},
        thread_log=thread_log,
    )
    main_thread = threading.get_ident()
    monitor = SystemLoadMonitor()

    depths = asyncio.run(monitor._get_model_queue_depths())

    assert depths == {"gpt-4": 1}
    assert thread_log, "未观察到 Celery inspect 调用"
    assert all(tid != main_thread for tid in thread_log)


def test_queue_depth_deduplicates_tasks_seen_in_active_and_reserved(monkeypatch):
    shared_task = {"id": "dup-task", "args": [{"model": "gpt-4"}]}
    _install_fake_celery(
        monkeypatch,
        active={"worker-1": [dict(shared_task)]},
        reserved={"worker-1": [dict(shared_task)]},
        thread_log=[],
    )
    monitor = SystemLoadMonitor()

    depths = asyncio.run(monitor._get_model_queue_depths())

    assert depths == {"gpt-4": 1}


def test_queue_depth_counts_distinct_tasks_separately(monkeypatch):
    _install_fake_celery(
        monkeypatch,
        active={"worker-1": [{"id": "a", "args": [{"model": "gpt-4"}]}]},
        reserved={"worker-1": [{"id": "b", "args": [{"model": "claude"}]}]},
        thread_log=[],
    )
    monitor = SystemLoadMonitor()

    depths = asyncio.run(monitor._get_model_queue_depths())

    assert depths == {"gpt-4": 1, "claude": 1}
