"""长周期定时任务必须在进程启动后不久先执行一次。

APScheduler 对未指定 start_date 的 IntervalTrigger 把首次触发排在
``now + interval``；调度容器每次发版重建，重启周期远短于 7/10 天，
文件清理/归档因此几乎永不执行。
"""

import importlib
from datetime import datetime, timedelta

scheduler = importlib.import_module("app.db.scheduler")

LONG_INTERVAL_JOB_IDS = (
    "chat_archive",
    "file_cleanup",
    "task_cleanup",
    "log_cleanup",
    "project_retention_sweep",
    "unified_state_retention",
    "generated_asset_retention",
)


def _pending_jobs():
    return {entry[0].id: entry[0] for entry in scheduler.scheduler._pending_jobs}


def test_long_interval_jobs_start_soon_after_boot():
    jobs = _pending_jobs()

    for job_id in LONG_INTERVAL_JOB_IDS:
        trigger = jobs[job_id].trigger
        now = datetime.now(trigger.timezone)
        assert trigger.start_date is not None, job_id
        assert trigger.start_date <= now + timedelta(minutes=5), job_id


def test_long_interval_is_preserved():
    jobs = _pending_jobs()

    assert jobs["file_cleanup"].trigger.interval == timedelta(days=7)
    assert jobs["chat_archive"].trigger.interval == timedelta(days=10)
