"""Celery 信号写路径的状态归一化与终态守卫回归测试。

覆盖 P1：`task_postrun`/`task_failure`/`task_retry` 传入的是 Celery 原生状态
（FAILURE/RETRY/REVOKED），直接落库会写入 `failure`/`retry`/`revoked` 这类词表外
取值，使 retry/recover/cancel 端点与终态判定失效；同时 `acks_late` 重投递会让
终态任务被改回运行中。
"""

from datetime import datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.celery_app import (
    _sync_notify_failure,
    _sync_notify_retry,
    _sync_update_task_status,
)
from app.models.task import (
    CELERY_STATE_TO_TASK_STATUS,
    TERMINAL_TASK_STATUSES,
    Task,
    TaskStatus,
)


@pytest.fixture
def task_db(tmp_path, monkeypatch):
    """文件型 SQLite，供 worker 侧新建的同步 engine 复用同一份数据。"""
    url = f"sqlite:///{tmp_path / 'tasks.db'}"
    engine = create_engine(url)
    Task.__table__.create(engine)
    monkeypatch.setenv("DATABASE_URL", url)
    yield engine
    engine.dispose()


def _insert_task(engine, task_id="t1", **overrides):
    fields = {
        "task_type": "ppt_generate",
        "user_id": 1,
        "status": TaskStatus.PENDING.value,
        "retry_count": 0,
    }
    fields.update(overrides)
    with Session(engine) as session:
        session.add(Task(task_id=task_id, **fields))
        session.commit()


def _read_task(engine, task_id="t1"):
    with Session(engine) as session:
        row = session.execute(
            select(
                Task.status,
                Task.retry_count,
                Task.error_message,
                Task.started_at,
                Task.completed_at,
            ).where(Task.task_id == task_id)
        ).one()
    return {
        "status": row[0],
        "retry_count": row[1],
        "error_message": row[2],
        "started_at": row[3],
        "completed_at": row[4],
    }


@pytest.mark.parametrize(
    "celery_state,expected",
    [
        ("FAILURE", TaskStatus.FAILED.value),
        ("RETRY", TaskStatus.RETRYING.value),
        ("REVOKED", TaskStatus.CANCELLED.value),
        ("started", TaskStatus.RUNNING.value),
    ],
)
def test_postrun_celery_state_is_normalized_before_persist(task_db, celery_state, expected):
    """写路径必须与读路径同口径，禁止落库 failure/retry/revoked。"""
    _insert_task(task_db, status=TaskStatus.PENDING.value)

    _sync_update_task_status("t1", celery_state.lower())

    assert _read_task(task_db)["status"] == expected


def test_notify_failure_writes_failed_and_error(task_db):
    _insert_task(task_db, status=TaskStatus.RUNNING.value)

    _sync_notify_failure("t1", "boom")

    record = _read_task(task_db)
    assert record["status"] == TaskStatus.FAILED.value
    assert record["error_message"] == "boom"
    assert record["completed_at"] is not None


def test_notify_retry_writes_retrying_and_increments_count(task_db):
    _insert_task(task_db, status=TaskStatus.RUNNING.value, retry_count=0)

    _sync_notify_retry("t1", "transient")

    record = _read_task(task_db)
    assert record["status"] == TaskStatus.RETRYING.value
    assert record["retry_count"] == 1
    assert record["completed_at"] is None


def test_failed_task_can_be_retried_and_recovered_by_api_predicates(task_db):
    """落库状态必须命中 retry/recover 端点要求的 `failed`。"""
    _insert_task(task_db, status=TaskStatus.RUNNING.value)

    _sync_update_task_status("t1", "failure")

    assert _read_task(task_db)["status"] == "failed"


def test_unknown_celery_state_keeps_persisted_status(task_db):
    _insert_task(task_db, status=TaskStatus.RUNNING.value)

    _sync_update_task_status("t1", "somefuturestate")

    assert _read_task(task_db)["status"] == TaskStatus.RUNNING.value


def test_terminal_status_is_not_overwritten_by_late_failure(task_db):
    """迟到/重投递的失败信号不得把已成功任务改成失败。"""
    _insert_task(task_db, status=TaskStatus.SUCCESS.value)

    _sync_notify_failure("t1", "late boom")

    record = _read_task(task_db)
    assert record["status"] == TaskStatus.SUCCESS.value
    assert record["error_message"] is None


def test_terminal_status_is_not_reset_to_running_by_redelivery(task_db):
    """acks_late 重投递触发 task_prerun 时不得把终态任务改回运行中。"""
    started = datetime(2026, 1, 1, 0, 0, 0)
    _insert_task(
        task_db,
        status=TaskStatus.SUCCESS.value,
        started_at=started,
        completed_at=started,
    )

    _sync_update_task_status("t1", "running")

    record = _read_task(task_db)
    assert record["status"] == TaskStatus.SUCCESS.value
    assert record["started_at"] == started


def test_matching_terminal_status_write_is_idempotent(task_db):
    """failure 信号重复到达时状态不变且不报错。"""
    _insert_task(task_db, status=TaskStatus.FAILED.value)

    _sync_notify_failure("t1", "again")

    assert _read_task(task_db)["status"] == TaskStatus.FAILED.value


def test_missing_task_is_a_noop(task_db):
    _sync_update_task_status("does-not-exist", "running")

    with Session(task_db) as session:
        assert session.execute(select(Task)).scalars().all() == []


def test_shared_map_covers_vocabulary_and_is_single_source():
    """映射值必须落在任务表词表内，且 API 读路径与 worker 写路径共用同一份。"""
    from app.api.v1 import task_queue
    from app.services import unified_state_service

    declared = {member.value for member in TaskStatus}
    assert set(CELERY_STATE_TO_TASK_STATUS.values()) <= declared
    assert TaskStatus.RETRYING.value in declared
    assert task_queue._CELERY_STATE_TO_STATUS is CELERY_STATE_TO_TASK_STATUS
    assert unified_state_service.TERMINAL_TASK_STATUSES is TERMINAL_TASK_STATUSES
    assert TERMINAL_TASK_STATUSES == {"success", "failed", "cancelled"}
