import inspect


def test_scheduler_registers_worker_lease_recovery_job():
    from app.db.scheduler import recover_expired_tasks_task, scheduler

    assert inspect.iscoroutinefunction(recover_expired_tasks_task)
    assert scheduler.get_job("worker_lease_recovery") is not None
