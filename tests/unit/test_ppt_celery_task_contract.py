def test_ppt_celery_task_is_registered_with_json_arguments():
    import inspect

    from app.tasks.ppt_tasks import generate_ppt

    assert generate_ppt.name == "app.tasks.ppt_tasks.generate_ppt"
    assert "request_data" in inspect.signature(generate_ppt.run).parameters


def test_ppt_celery_task_has_retry_configuration():
    from app.tasks.ppt_tasks import generate_ppt

    assert generate_ppt.max_retries == 3
    assert generate_ppt.acks_late is True


def test_ppt_celery_task_uses_unified_progress_services():
    from pathlib import Path

    source = Path("app/tasks/ppt_tasks.py").read_text(encoding="utf-8")
    assert "transition_task" in source
    assert "append_task_event" in source


def test_ppt_celery_progress_adapter_supports_message_only_updates():
    from pathlib import Path

    source = Path("app/tasks/ppt_tasks.py").read_text(encoding="utf-8")
    assert "kwargs.get(\"progress\", last_progress)" in source
    assert "original_update(progress_value, message)" in source
