"""TaskManager 的 Redis 回退、任务生命周期、进度、取消与清理测试。"""

import asyncio
import json

import pytest

import app.utils.task_manager as tm
from app.utils.task_manager import TaskManager, TaskStatus


class FakeRedis:
    def __init__(self, fail_on=None):
        self.store = {}
        self.sets = {}
        self.expires = {}
        self.published = []
        self.deleted = []
        self.fail_on = set(fail_on or [])

    def _maybe_fail(self, operation):
        if operation in self.fail_on:
            raise RuntimeError(f"{operation} failed")

    async def set(self, key, value, ex=None):
        self._maybe_fail("set")
        self.store[key] = value
        if ex is not None:
            self.expires[key] = ex

    async def get(self, key):
        self._maybe_fail("get")
        return self.store.get(key)

    async def sadd(self, key, value):
        self._maybe_fail("sadd")
        self.sets.setdefault(key, set()).add(value)

    async def smembers(self, key):
        self._maybe_fail("smembers")
        return self.sets.get(key, set())

    async def srem(self, key, value):
        self._maybe_fail("srem")
        self.sets.get(key, set()).discard(value)

    async def expire(self, key, ttl):
        self._maybe_fail("expire")
        self.expires[key] = ttl

    async def publish(self, channel, payload):
        self._maybe_fail("publish")
        self.published.append((channel, payload))

    async def delete(self, key):
        self._maybe_fail("delete")
        self.deleted.append(key)
        self.store.pop(key, None)

    async def scan_iter(self, match=None):
        self._maybe_fail("scan_iter")
        prefix = (match or "").rstrip("*")
        for key in list(self.store):
            if key.startswith(prefix):
                yield key


@pytest.fixture
def manager(monkeypatch):
    # 绕过单例，避免实例方法替换泄漏到其它测试。
    instance = object.__new__(TaskManager)
    instance._redis = FakeRedis()
    instance._tasks = {}
    instance._running_tasks = {}
    instance._cleanup_task = None
    monkeypatch.setattr(instance, "_ensure_started", _noop)
    return instance


async def _noop():
    return None


class TestSingleton:
    def test_same_instance(self):
        assert TaskManager() is TaskManager()

    def test_concurrent_creation_returns_winner(self, monkeypatch):
        winner = object()

        class Lock:
            def __enter__(self):
                TaskManager._instance = winner

            def __exit__(self, *_args):
                return False

        monkeypatch.setattr(TaskManager, "_instance", None)
        monkeypatch.setattr(TaskManager, "_instance_lock", Lock())

        assert TaskManager() is winner

    def test_attributes_initialized(self):
        instance = TaskManager()

        assert hasattr(instance, "_tasks")
        assert hasattr(instance, "_running_tasks")

    @pytest.mark.asyncio
    async def test_get_redis_lazy(self, monkeypatch):
        instance = TaskManager()
        instance._redis = None
        created = []

        def fake_from_url(url, decode_responses):
            created.append(url)
            return object()

        monkeypatch.setattr(tm.redis, "from_url", fake_from_url)

        first = await instance._get_redis()
        second = await instance._get_redis()

        assert len(created) == 1
        assert first is second
        instance._redis = None

    @pytest.mark.asyncio
    async def test_get_redis_double_check_returns_existing(self, monkeypatch):
        instance = object.__new__(TaskManager)
        instance._redis = None
        winner = object()

        class Lock:
            def __enter__(self):
                instance._redis = winner

            def __exit__(self, *_args):
                return False

        monkeypatch.setattr(instance, "_instance_lock", Lock(), raising=False)

        assert await instance._get_redis() is winner


class TestCleanupLoop:
    @pytest.mark.asyncio
    async def test_ensure_started_creates_task(self, manager, monkeypatch):
        created = []
        monkeypatch.setattr(
            tm.asyncio, "create_task", lambda coro: created.append(coro) or _FakeTask()
        )
        manager._cleanup_task = None

        await TaskManager._ensure_started(manager)

        assert len(created) == 1
        created[0].close()

    @pytest.mark.asyncio
    async def test_ensure_started_replaces_done_task(self, manager, monkeypatch):
        class DoneTask:
            def done(self):
                return True

        created = []
        manager._cleanup_task = DoneTask()
        monkeypatch.setattr(
            tm.asyncio, "create_task", lambda coro: created.append(coro) or _FakeTask()
        )

        await TaskManager._ensure_started(manager)

        assert len(created) == 1
        created[0].close()

    @pytest.mark.asyncio
    async def test_ensure_started_keeps_running_task(self, manager, monkeypatch):
        class RunningTask:
            def done(self):
                return False

        existing = RunningTask()
        manager._cleanup_task = existing
        calls = []
        monkeypatch.setattr(tm.asyncio, "create_task", lambda coro: calls.append(coro))

        await TaskManager._ensure_started(manager)

        assert manager._cleanup_task is existing
        assert calls == []

    @pytest.mark.asyncio
    async def test_loop_cancelled_breaks(self, manager, monkeypatch):
        calls = []

        async def fake_sleep(_seconds):
            calls.append(1)
            raise asyncio.CancelledError()

        monkeypatch.setattr(tm.asyncio, "sleep", fake_sleep)

        await manager._cleanup_loop()

        assert calls == [1]

    @pytest.mark.asyncio
    async def test_loop_error_logged(self, manager, monkeypatch):
        errors = []
        calls = []

        async def fake_sleep(_seconds):
            calls.append(1)
            if len(calls) > 1:
                raise asyncio.CancelledError()
            raise RuntimeError("boom")

        async def fake_cleanup(days=7):
            return None

        monkeypatch.setattr(tm.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(manager, "cleanup_old_tasks", fake_cleanup)
        monkeypatch.setattr(tm.logger, "error", lambda message: errors.append(message))

        await manager._cleanup_loop()

        assert errors == ["清理任务失败: boom"]

    @pytest.mark.asyncio
    async def test_loop_runs_cleanup_then_cancels(self, manager, monkeypatch):
        calls = []

        async def fake_sleep(_seconds):
            calls.append("sleep")
            if len(calls) > 1:
                raise asyncio.CancelledError()

        async def fake_cleanup(days=7):
            calls.append(("cleanup", days))

        monkeypatch.setattr(tm.asyncio, "sleep", fake_sleep)
        monkeypatch.setattr(manager, "cleanup_old_tasks", fake_cleanup)

        await manager._cleanup_loop()

        assert calls == ["sleep", ("cleanup", 7), "sleep"]


class _FakeTask:
    def close(self):
        pass

    def done(self):
        return False


class TestCreateTask:
    @pytest.mark.asyncio
    async def test_creates_in_redis_and_memory(self, manager, monkeypatch):
        executed = []

        def fake_create_task(coro):
            executed.append(coro)
            return _FakeTask()

        async def fake_sql_create(_info):
            return None

        async def func(task_id):
            return {"ok": True}

        monkeypatch.setattr(tm.asyncio, "create_task", fake_create_task)
        monkeypatch.setattr(manager, "_persist_sql_create", fake_sql_create)

        task_id = await manager.create_task("demo", 7, func, params={"a": 1})

        assert task_id in manager._running_tasks
        assert f"task:{task_id}" in manager._redis.store
        assert task_id in manager._redis.sets["user_tasks:7"]
        saved = json.loads(manager._redis.store[f"task:{task_id}"])
        assert saved["status"] == TaskStatus.PENDING.value
        assert saved["params"] == {"a": 1}
        assert saved["progress_message"] == "等待中..."
        executed[0].close()

    @pytest.mark.asyncio
    async def test_redis_failure_falls_back_to_memory(self, manager, monkeypatch):
        warnings = []
        manager._redis = FakeRedis(fail_on={"set"})
        monkeypatch.setattr(tm.asyncio, "create_task", lambda coro: _close(coro))
        monkeypatch.setattr(manager, "_persist_sql_create", _noop_info)
        monkeypatch.setattr(tm.logger, "warning", lambda message: warnings.append(message))

        task_id = await manager.create_task("demo", 1, _func, params=None, input_file_id=5)

        assert manager._tasks[task_id]["input_file_id"] == 5
        assert any("Redis 存储失败" in message for message in warnings)

    @pytest.mark.asyncio
    async def test_sql_create_failure_logged(self, manager, monkeypatch):
        warnings = []
        monkeypatch.setattr(tm.asyncio, "create_task", lambda coro: _close(coro))
        monkeypatch.setattr(tm.logger, "warning", lambda *a: warnings.append(a))

        task_id = await manager.create_task("demo", 1, _func)

        assert task_id
        assert any("统一任务 SQL 创建失败" in str(a) for a in warnings)


def _close(coro):
    coro.close()
    return _FakeTask()


async def _noop_info(_info):
    return None


async def _func(task_id):
    return {}


class TestExecuteTask:
    @pytest.mark.asyncio
    async def test_success_updates_status(self, manager):
        info = {"task_id": "t", "status": TaskStatus.PENDING.value, "result": {}}
        saved = []

        async def get_task(_id):
            return info

        async def save(_id, value):
            info.update(value)
            saved.append(value.copy())

        async def func(task_id):
            return {"value": 1}

        manager._get_task_from_redis = get_task
        manager._save_task_to_redis = save
        manager._running_tasks["t"] = object()
        manager._persist_sql_update = _noop_info

        await manager._execute_task("t", func, {})

        assert info["status"] == TaskStatus.SUCCESS.value
        assert info["result"] == {"value": 1}
        assert info["progress"] == 100
        assert "t" not in manager._running_tasks

    @pytest.mark.asyncio
    async def test_terminal_status_preserved(self, manager):
        pending = {"task_id": "t", "status": TaskStatus.PENDING.value, "result": {}}
        failed = {
            "task_id": "t",
            "status": TaskStatus.FAILED.value,
            "result": {},
        }
        reads = iter([dict(pending), dict(failed)])
        saved = []

        async def get_task(_id):
            return next(reads)

        async def save(_id, value):
            saved.append(value.copy())

        async def func(task_id):
            return {}

        manager._get_task_from_redis = get_task
        manager._save_task_to_redis = save
        manager._running_tasks["t"] = object()
        manager._persist_sql_update = _noop_info

        await manager._execute_task("t", func, {})

        assert saved[-1]["status"] == TaskStatus.FAILED.value
        assert saved[-1]["completed_at"]
        assert [entry["status"] for entry in saved] == ["running", "failed"]

    @pytest.mark.asyncio
    async def test_cancelled_marks_cancelled(self, manager):
        info = {"task_id": "t", "status": TaskStatus.RUNNING.value, "result": {}}

        async def get_task(_id):
            return info

        async def save(_id, value):
            info.update(value)

        async def func(task_id):
            raise asyncio.CancelledError()

        manager._get_task_from_redis = get_task
        manager._running_tasks["t"] = object()
        manager._persist_sql_update = _noop_info

        await manager._execute_task("t", func, {})

        assert info["status"] == TaskStatus.CANCELLED.value

    @pytest.mark.asyncio
    async def test_failure_records_error(self, manager, monkeypatch):
        info = {"task_id": "t", "status": TaskStatus.RUNNING.value, "result": {}}
        errors = []

        async def get_task(_id):
            return info

        async def save(_id, value):
            info.update(value)

        async def func(task_id):
            raise ValueError("bad input")

        manager._get_task_from_redis = get_task
        manager._running_tasks["t"] = object()
        manager._persist_sql_update = _noop_info
        monkeypatch.setattr(tm.logger, "error", lambda *a, **k: errors.append(a))

        await manager._execute_task("t", func, {})

        assert info["status"] == TaskStatus.FAILED.value
        assert info["error_message"] == "bad input"
        assert "失败：bad input" in info["progress_message"]

    @pytest.mark.asyncio
    async def test_missing_task_info_does_not_crash(self, manager, monkeypatch):
        manager._running_tasks["t"] = object()
        warnings = []
        monkeypatch.setattr(tm.logger, "warning", lambda *a: warnings.append(a[0]))

        await manager._execute_task("t", _func, {})

        assert "t" not in manager._running_tasks
        assert warnings == ["任务状态不存在，跳过执行 | task_id=t"]

    @pytest.mark.asyncio
    async def test_finally_tolerates_absent_running_entry(self, manager):
        info = {"task_id": "t", "status": TaskStatus.PENDING.value, "result": {}}

        async def get_task(_id):
            return info

        async def save(_id, value):
            pass

        manager._get_task_from_redis = get_task
        manager._persist_sql_update = _noop_info

        await manager._execute_task("t", _func, {})

        assert "t" not in manager._running_tasks


class TestRedisAccess:
    @pytest.mark.asyncio
    async def test_get_task_read_failure_falls_back(self, manager, monkeypatch):
        manager._redis = FakeRedis(fail_on={"get"})
        manager._tasks["t"] = {"task_id": "t"}
        warnings = []
        monkeypatch.setattr(tm.logger, "warning", lambda message: warnings.append(message))

        assert await manager._get_task_from_redis("t") == {"task_id": "t"}
        assert warnings == ["Redis 读取失败: get failed"]

    @pytest.mark.asyncio
    async def test_save_publishes_event(self, manager):
        info = {"task_id": "t", "status": "running"}

        await manager._save_task_to_redis("t", info)

        assert manager._redis.published[0][0] == "task_events:t"
        assert json.loads(manager._redis.store["task:t"]) == info

    @pytest.mark.asyncio
    async def test_save_failure_keeps_memory(self, manager, monkeypatch):
        manager._redis = FakeRedis(fail_on={"set"})
        info = {"task_id": "t"}
        warnings = []
        monkeypatch.setattr(tm.logger, "warning", lambda message: warnings.append(message))

        await manager._save_task_to_redis("t", info)

        assert manager._tasks["t"] is info
        assert warnings == ["Redis 保存失败: set failed"]


class TestSyncInfo:
    def test_running_task_in_memory(self, manager):
        manager._running_tasks["t"] = object()
        manager._tasks["t"] = {"task_id": "t"}

        assert manager.get_task_info("t") == {"task_id": "t"}

    def test_running_task_without_snapshot(self, manager):
        manager._running_tasks["t"] = object()

        assert manager.get_task_info("t") is None

    def test_unknown_task_returns_none(self, manager):
        assert manager.get_task_info("absent") is None

    @pytest.mark.asyncio
    async def test_async_restores_datetimes(self, manager):
        manager._redis.store["task:t"] = json.dumps(
            {
                "task_id": "t",
                "created_at": "2026-01-02T03:04:05",
                "started_at": "bad-date",
                "completed_at": None,
            }
        )

        info = await manager.get_task_info_async("t")

        assert info["created_at"].year == 2026
        assert info["started_at"] == "bad-date"
        assert info["completed_at"] is None

    @pytest.mark.asyncio
    async def test_async_missing_returns_none(self, manager):
        assert await manager.get_task_info_async("absent") is None


class TestUpdateProgress:
    @pytest.mark.asyncio
    async def test_ignored_for_terminal_task(self, manager):
        manager._redis.store["task:t"] = json.dumps(
            {"task_id": "t", "status": TaskStatus.SUCCESS.value}
        )
        saved = []
        manager._save_task_to_redis = lambda *a: saved.append(a)

        await manager.update_progress("t", 50)

        assert saved == []

    @pytest.mark.asyncio
    async def test_clamps_and_parses_json_result(self, manager):
        manager._redis.store["task:t"] = json.dumps(
            {"task_id": "t", "status": TaskStatus.RUNNING.value}
        )
        saved = []

        async def save(_id, value):
            saved.append(value.copy())

        manager._save_task_to_redis = save

        await manager.update_progress(
            "t", 150, "done", status="completed", result_data='{"a": 1}', error_message="e"
        )

        assert saved[0]["progress"] == 100
        assert saved[0]["status"] == TaskStatus.SUCCESS.value
        assert saved[0]["result"] == {"a": 1}
        assert saved[0]["error_message"] == "e"

    @pytest.mark.asyncio
    async def test_negative_progress_and_dict_result(self, manager):
        manager._redis.store["task:t"] = json.dumps(
            {"task_id": "t", "status": TaskStatus.PENDING.value}
        )
        saved = []

        async def save(_id, value):
            saved.append(value.copy())

        manager._save_task_to_redis = save

        await manager.update_progress("t", -5, result_data={"b": 2}, status="failed")

        assert saved[0]["progress"] == 0
        assert saved[0]["status"] == "failed"
        assert saved[0]["result"] == {"b": 2}

    @pytest.mark.asyncio
    async def test_error_message_without_result(self, manager):
        manager._redis.store["task:t"] = json.dumps(
            {"task_id": "t", "status": TaskStatus.RUNNING.value}
        )
        saved = []

        async def save(_id, value):
            saved.append(value.copy())

        manager._save_task_to_redis = save

        await manager.update_progress("t", 10, error_message="boom")

        assert saved[0]["error_message"] == "boom"
        assert "result" not in saved[0]

    @pytest.mark.asyncio
    async def test_invalid_json_result_kept_raw(self, manager):
        manager._redis.store["task:t"] = json.dumps(
            {"task_id": "t", "status": TaskStatus.RUNNING.value}
        )
        saved = []

        async def save(_id, value):
            saved.append(value.copy())

        manager._save_task_to_redis = save

        await manager.update_progress("t", 10, result_data="{not json")

        assert saved[0]["result"] == "{not json"

    @pytest.mark.asyncio
    async def test_missing_task_is_noop(self, manager):
        calls = []
        manager._save_task_to_redis = lambda *a: calls.append(a)

        await manager.update_progress("absent", 10)

        assert calls == []


class TestCancel:
    @pytest.mark.asyncio
    async def test_cancel_running(self, manager):
        class Cancellable:
            cancelled = False

            def cancel(self):
                self.cancelled = True

        task = Cancellable()
        manager._running_tasks["t"] = task

        assert await manager.cancel_task("t") is True
        assert task.cancelled is True

    @pytest.mark.asyncio
    async def test_cancel_missing(self, manager):
        assert await manager.cancel_task("absent") is False


class TestUserTasks:
    @pytest.mark.asyncio
    async def test_filters_by_status_and_sorts(self, manager):
        manager._redis.sets["user_tasks:1"] = {"a", "b", "c"}
        manager._redis.store["task:a"] = json.dumps(
            {"task_id": "a", "status": "success", "created_at": "2026-01-01"}
        )
        manager._redis.store["task:b"] = json.dumps(
            {"task_id": "b", "status": "failed", "created_at": "2026-02-01"}
        )
        manager._redis.store["task:c"] = json.dumps(
            {"task_id": "c", "status": "success", "created_at": "2026-03-01"}
        )

        tasks = await manager.get_user_tasks(1, status="success")

        assert [t["task_id"] for t in tasks] == ["c", "a"]

    @pytest.mark.asyncio
    async def test_limit(self, manager):
        manager._redis.sets["user_tasks:1"] = {"a", "b"}
        manager._redis.store["task:a"] = json.dumps({"task_id": "a", "created_at": "1"})
        manager._redis.store["task:b"] = json.dumps({"task_id": "b", "created_at": "2"})

        assert len(await manager.get_user_tasks(1, limit=1)) == 1

    @pytest.mark.asyncio
    async def test_redis_error_returns_empty(self, manager, monkeypatch):
        manager._redis = FakeRedis(fail_on={"smembers"})
        errors = []
        monkeypatch.setattr(tm.logger, "error", lambda message: errors.append(message))

        assert await manager.get_user_tasks(1) == []
        assert errors == ["获取用户任务列表失败: smembers failed"]


class TestCleanupOldTasks:
    @pytest.mark.asyncio
    async def test_expired_task_deleted_and_unlinked(self, manager):
        manager._redis.store["task:old"] = json.dumps(
            {
                "task_id": "old",
                "user_id": 3,
                "completed_at": "2000-01-01T00:00:00",
            }
        )
        manager._redis.sets["user_tasks:3"] = {"old"}

        await manager.cleanup_old_tasks(days=1)

        assert "task:old" not in manager._redis.store
        assert manager._redis.sets["user_tasks:3"] == set()

    @pytest.mark.asyncio
    async def test_recent_task_kept(self, manager):
        from app.core.time import utcnow_naive

        manager._redis.store["task:new"] = json.dumps(
            {
                "task_id": "new",
                "completed_at": utcnow_naive().isoformat(),
            }
        )

        await manager.cleanup_old_tasks(days=1)

        assert "task:new" in manager._redis.store

    @pytest.mark.asyncio
    async def test_invalid_completed_at_skipped(self, manager):
        manager._redis.store["task:weird"] = json.dumps(
            {"task_id": "weird", "completed_at": "not-a-date"}
        )

        await manager.cleanup_old_tasks()

        assert "task:weird" in manager._redis.store

    @pytest.mark.asyncio
    async def test_task_without_completed_at_kept(self, manager):
        manager._redis.store["task:running"] = json.dumps({"task_id": "running"})

        await manager.cleanup_old_tasks()

        assert "task:running" in manager._redis.store

    @pytest.mark.asyncio
    async def test_empty_value_skipped(self, manager):
        manager._redis.store["task:empty"] = ""

        await manager.cleanup_old_tasks()

        assert manager._redis.deleted == []

    @pytest.mark.asyncio
    async def test_no_user_id_still_deletes(self, manager):
        manager._redis.store["task:old"] = json.dumps(
            {"task_id": "old", "completed_at": "2000-01-01T00:00:00"}
        )

        await manager.cleanup_old_tasks()

        assert "task:old" not in manager._redis.store

    @pytest.mark.asyncio
    async def test_redis_error_logged(self, manager, monkeypatch):
        manager._redis = FakeRedis(fail_on={"scan_iter"})
        errors = []
        monkeypatch.setattr(tm.logger, "error", lambda message: errors.append(message))

        await manager.cleanup_old_tasks()

        assert errors == ["清理过期任务失败: scan_iter failed"]


class _FakeSessionContext:
    def __init__(self, db):
        self.db = db

    async def __aenter__(self):
        return self.db

    async def __aexit__(self, *_args):
        return False


class _FakeDb:
    def __init__(self):
        self.committed = False

    async def commit(self):
        self.committed = True


class TestSqlPersistence:
    @pytest.mark.asyncio
    async def test_create_writes_row(self, manager, monkeypatch):
        db = _FakeDb()
        captured = []
        import app.db.database as database
        import app.services.unified_state_service as state

        async def create(session, user_id, task_type, **kwargs):
            captured.append((session, user_id, task_type, kwargs))

        monkeypatch.setattr(database, "async_session", lambda: _FakeSessionContext(db))
        monkeypatch.setattr(state, "create_task", create)

        await manager._persist_sql_create(
            {
                "task_id": "t",
                "user_id": "7",
                "task_type": "demo",
                "session_id": "s",
                "idempotency_key": "k",
                "params": None,
                "input_file_id": 3,
            }
        )

        assert db.committed is True
        assert captured[0][1:3] == (7, "demo")
        assert captured[0][3]["params"] == {}
        assert captured[0][3]["input_file_id"] == 3

    @pytest.mark.asyncio
    async def test_create_failure_logged(self, manager, monkeypatch):
        warnings = []
        import app.db.database as database

        def broken():
            raise RuntimeError("db down")

        monkeypatch.setattr(database, "async_session", broken)
        monkeypatch.setattr(tm.logger, "warning", lambda *a: warnings.append(a))

        await manager._persist_sql_create({"task_id": "t", "user_id": 1, "task_type": "x"})

        assert "统一任务 SQL 创建失败" in warnings[0][0]

    @pytest.mark.asyncio
    async def test_update_transitions_and_appends_event(self, manager, monkeypatch):
        db = _FakeDb()
        calls = []
        import app.db.database as database
        import app.services.unified_state_service as state

        async def transition(session, task_id, user_id, status, **kwargs):
            calls.append(("transition", task_id, user_id, status, kwargs))

        async def append(session, task_id, user_id, event, **kwargs):
            calls.append(("append", task_id, user_id, event, kwargs))

        monkeypatch.setattr(database, "async_session", lambda: _FakeSessionContext(db))
        monkeypatch.setattr(state, "transition_task", transition)
        monkeypatch.setattr(state, "append_task_event", append)

        await manager._persist_sql_update(
            {
                "task_id": "t",
                "user_id": 2,
                "status": "success",
                "progress": 100,
                "progress_message": "完成",
                "result": {},
                "error_message": None,
            }
        )

        assert db.committed is True
        assert calls[0][3] == "success"
        assert calls[0][4]["result"] is None
        assert calls[1][3] == "task.updated"
        assert calls[1][4]["payload"]["result"] == {}

    @pytest.mark.asyncio
    async def test_update_failure_logged(self, manager, monkeypatch):
        warnings = []
        import app.db.database as database

        def broken():
            raise RuntimeError("db down")

        monkeypatch.setattr(database, "async_session", broken)
        monkeypatch.setattr(tm.logger, "warning", lambda *a: warnings.append(a))

        await manager._persist_sql_update({"task_id": "t", "user_id": 1, "status": "failed"})

        assert "统一任务 SQL 更新失败" in warnings[0][0]


class TestReconcile:
    @pytest.mark.asyncio
    async def test_missing_snapshot_returns_none(self, manager):
        assert await manager.reconcile_task("absent") is None

    @pytest.mark.asyncio
    async def test_consistent_report_returned(self, manager, monkeypatch):
        manager._redis.store["task:t"] = json.dumps({"task_id": "t", "user_id": "5"})
        db = _FakeDb()
        import app.db.database as database
        import app.services.unified_state_service as state

        async def compare(session, task_id, user_id, snapshot):
            assert user_id == 5
            return {"task_id": task_id, "consistent": True}

        monkeypatch.setattr(database, "async_session", lambda: _FakeSessionContext(db))
        monkeypatch.setattr(state, "compare_task_snapshot", compare)

        report = await manager.reconcile_task("t")

        assert report == {"task_id": "t", "consistent": True}
        assert db.committed is True

    @pytest.mark.asyncio
    async def test_compare_failure_returns_report(self, manager, monkeypatch):
        manager._redis.store["task:t"] = json.dumps({"task_id": "t", "user_id": 1})
        warnings = []
        import app.db.database as database

        def broken():
            raise RuntimeError("db down")

        monkeypatch.setattr(database, "async_session", broken)
        monkeypatch.setattr(tm.logger, "warning", lambda *a: warnings.append(a))

        report = await manager.reconcile_task("t")

        assert report["consistent"] is False
        assert report["error"] == "db down"
        assert "统一任务状态核对失败" in warnings[0][0]
