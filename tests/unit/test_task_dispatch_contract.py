"""Celery 任务派发契约回归。

覆盖三类真实缺陷：
1. 业务参数必须以 ``kwargs=`` 下发，否则会被当作 AMQP 消息属性丢弃；
2. 重试/恢复必须保存新的 Celery ID，不能复用旧标识；
3. 隔离测试运行器必须在事件循环内 await，不能再次 asyncio.run。
"""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class _FakeResult:
    def __init__(self, record):
        self._record = record

    def scalar_one_or_none(self):
        return self._record


class _FakeDB:
    """Minimal AsyncSession stand-in for the task-queue endpoints."""

    def __init__(self, record=None):
        self._record = record
        self.added = []
        self.commits = 0

    def add(self, obj):
        self.added.append(obj)

    async def execute(self, stmt):
        return _FakeResult(self._record)

    async def commit(self):
        self.commits += 1

    async def refresh(self, obj):
        obj.created_at = None


def _record(**overrides):
    base = {
        "task_id": "biz-task-1",
        "user_id": 7,
        "task_type": "code_generate",
        "status": "failed",
        "retry_count": 1,
        "error_message": "boom",
        "progress": 10,
        "priority": 5,
        "timeout": 300,
        "max_retries": 3,
        "result": None,
        "parent_task_id": None,
        "created_at": None,
        "started_at": None,
        "completed_at": None,
        "celery_task_id": "old-celery-id",
        "params": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_create_task_sends_business_kwargs():
    from app.api.v1 import task_queue
    from app.schema.task_schema import TaskCreateRequest, TaskTypeEnum

    captured = {}

    def fake_send_task(name, **options):
        captured["name"] = name
        captured["options"] = options
        return MagicMock(id="celery-created")

    body = TaskCreateRequest(
        task_type=TaskTypeEnum.CODE_GENERATE,
        params={"prompt": "hello", "language": "go"},
    )
    db = _FakeDB()

    with patch.object(task_queue.celery_app, "send_task", side_effect=fake_send_task):
        response = await task_queue.create_task(body, {"sub": "7"}, db)

    assert captured["name"] == "app.tasks.code_tasks.generate_code"
    sent = captured["options"]["kwargs"]
    assert sent["task_id"] == response.task_id
    assert sent["user_id"] == 7
    assert sent["prompt"] == "hello"
    assert sent["language"] == "go"
    # 业务参数不应再被当作顶层 AMQP 选项发送。
    assert "prompt" not in captured["options"]


@pytest.mark.asyncio
async def test_retry_task_uses_new_celery_id_and_business_kwargs():
    from app.api.v1 import task_queue

    record = _record(
        task_type="modify_with_test",
        params={"requirement": "fix it", "target_files": ["a.py"], "max_retry_loops": 2},
    )
    db = _FakeDB(record)
    captured = {}

    def fake_send_task(name, **options):
        captured["name"] = name
        captured["options"] = options
        return MagicMock(id="celery-retried")

    with patch.object(task_queue.celery_app, "send_task", side_effect=fake_send_task):
        response = await task_queue.retry_task("biz-task-1", {"sub": "7"}, db)

    assert captured["name"] == "app.tasks.code_tasks.modify_with_test"
    # 旧 Celery ID 不再作为新消息标识复用。
    assert "task_id" not in captured["options"]
    assert record.celery_task_id == "celery-retried"
    assert response.celery_task_id == "celery-retried"
    sent = captured["options"]["kwargs"]
    assert sent["task_id"] == "biz-task-1"
    assert sent["requirement"] == "fix it"
    assert sent["target_files"] == ["a.py"]
    assert sent["max_retry_loops"] == 2


@pytest.mark.asyncio
async def test_recover_task_sends_kwargs_and_tracks_new_celery_id():
    from app.api.v1 import task_queue

    record = _record(task_type="project_generate", params={"requirement": "build a service"})
    record.status = "failed"
    db = _FakeDB(record)
    captured = {}

    def fake_send_task(name, **options):
        captured["name"] = name
        captured["options"] = options
        return MagicMock(id="celery-recovered")

    with patch.object(task_queue, "get_owned_task", AsyncMock(return_value=record)), \
            patch.object(task_queue, "transition_task", AsyncMock()), \
            patch.object(task_queue, "append_task_event", AsyncMock()), \
            patch.object(task_queue.celery_app, "send_task", side_effect=fake_send_task):
        await task_queue.recover_task("biz-task-1", {"sub": "7"}, db)

    assert captured["name"] == "app.tasks.project_tasks.generate_project"
    assert record.celery_task_id == "celery-recovered"
    sent = captured["options"]["kwargs"]
    assert sent["task_id"] == "biz-task-1"
    assert sent["user_id"] == 7
    assert sent["requirement"] == "build a service"


@pytest.mark.asyncio
async def test_run_tests_awaits_isolated_runner_inside_event_loop():
    import app.tasks.code_tasks as code_tasks

    class FakeTestResult:
        success = True
        logs = "ok"
        passed = 1
        failed = 0
        total_tests = 1

    class FakeRunner:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run_tests(self, test_paths):
            assert test_paths == ["tests/unit/test_x.py"]
            return FakeTestResult()

    with patch("app.agent.test_runner.IsolatedTestRunner", FakeRunner):
        # 该调用发生在事件循环内，旧实现内部的 asyncio.run 会失败并退化。
        result = await code_tasks._run_tests(["tests/unit/test_x.py"])

    assert result["success"] is True
    assert result["passed"] == 1
    assert result["total"] == 1


def test_task_type_contract_matches_implemented_tasks():
    from app.schema.task_schema import TaskTypeEnum

    assert TaskTypeEnum("modify_with_test") is TaskTypeEnum.MODIFY_WITH_TEST
    assert TaskTypeEnum("ppt_generate") is TaskTypeEnum.PPT_GENERATE
    # 没有对应 Celery 实现的任务类型不应出现在请求契约里。
    with pytest.raises(ValueError):
        TaskTypeEnum("file_process")
    assert "file_process" not in {member.value for member in TaskTypeEnum}


def test_build_task_kwargs_covers_every_supported_type():
    from app.api.v1.task_queue import TASK_NAMES, _build_task_kwargs
    from app.schema.task_schema import TaskTypeEnum

    assert {member.value for member in TaskTypeEnum} == set(TASK_NAMES)
    assert _build_task_kwargs("ppt_generate", "t1", 1, {"slide_count": 3}) == {
        "task_id": "t1",
        "user_id": 1,
        "request_data": {"slide_count": 3},
    }


@pytest.mark.asyncio
async def test_create_task_offloads_send_task_off_event_loop_thread():
    import threading

    from app.api.v1 import task_queue
    from app.schema.task_schema import TaskCreateRequest, TaskTypeEnum

    loop_thread = threading.get_ident()
    seen = {}

    def fake_send_task(name, **options):
        seen["thread"] = threading.get_ident()
        return MagicMock(id="celery-created")

    body = TaskCreateRequest(
        task_type=TaskTypeEnum.CODE_GENERATE,
        params={"prompt": "hello", "language": "go"},
    )

    with patch.object(task_queue.celery_app, "send_task", side_effect=fake_send_task):
        await task_queue.create_task(body, {"sub": "7"}, _FakeDB())

    assert seen["thread"] != loop_thread


@pytest.mark.asyncio
async def test_retry_task_offloads_send_task_off_event_loop_thread():
    import threading

    from app.api.v1 import task_queue

    loop_thread = threading.get_ident()
    seen = {}

    def fake_send_task(name, **options):
        seen["thread"] = threading.get_ident()
        return MagicMock(id="celery-retried")

    record = _record(task_type="code_generate", params={"prompt": "again"})

    with patch.object(task_queue.celery_app, "send_task", side_effect=fake_send_task):
        await task_queue.retry_task("biz-task-1", {"sub": "7"}, _FakeDB(record))

    assert seen["thread"] != loop_thread


@pytest.mark.asyncio
async def test_get_task_offloads_celery_result_read_off_event_loop_thread():
    import threading

    from app.api.v1 import task_queue

    loop_thread = threading.get_ident()
    seen = {}

    class _FakeAsyncResult:
        state = "STARTED"
        info = None

    def fake_async_result(task_id):
        seen["thread"] = threading.get_ident()
        seen["task_id"] = task_id
        return _FakeAsyncResult()

    record = _record(
        status="running", celery_task_id="celery-running", progress_message="",
    )

    with patch.object(task_queue, "get_owned_task", AsyncMock(return_value=record)), \
            patch.object(task_queue.celery_app, "AsyncResult", side_effect=fake_async_result):
        await task_queue.get_task("biz-task-1", {"sub": "7"}, _FakeDB(record))

    assert seen["task_id"] == "celery-running"
    assert seen["thread"] != loop_thread


@pytest.mark.asyncio
async def test_cancel_task_offloads_revoke_off_event_loop_thread():
    import threading

    from app.api.v1 import task_queue

    loop_thread = threading.get_ident()
    seen = {}

    def fake_revoke(*args, **kwargs):
        seen["thread"] = threading.get_ident()
        seen["args"] = args

    record = _record(status="running", celery_task_id="celery-running")

    with patch.object(task_queue, "append_task_event", AsyncMock()), \
            patch.object(task_queue.celery_app.control, "revoke", side_effect=fake_revoke):
        await task_queue.cancel_task("biz-task-1", {"sub": "7"}, _FakeDB(record))

    assert seen["args"] == ("celery-running",)
    assert seen["thread"] != loop_thread
