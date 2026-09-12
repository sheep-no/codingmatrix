import inspect


def test_scheduler_registers_worker_lease_recovery_job():
    from app.db.scheduler import recover_expired_tasks_task, scheduler

    assert inspect.iscoroutinefunction(recover_expired_tasks_task)
    assert scheduler.get_job("worker_lease_recovery") is not None


def test_scheduler_registers_generated_asset_retention_job():
    from app.db.scheduler import cleanup_generated_assets_task, scheduler

    assert inspect.iscoroutinefunction(cleanup_generated_assets_task)
    job = scheduler.get_job("generated_asset_retention")
    assert job is not None
