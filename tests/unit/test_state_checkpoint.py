"""Checkpoint persistence and legacy migration tests."""

from app.agent.state import CheckpointStore, State


def test_checkpoint_round_trip(tmp_path) -> None:
    store = CheckpointStore(tmp_path)
    state = State(
        session_id="session-1",
        task_id="task-1",
        revision=3,
        status="waiting_local_validation",
        generated_files=[{"path": "main.py", "hash": "abc"}],
        pending_actions=[{"type": "run_tests"}],
    )

    store.save(state)

    first_load = store.load("task-1")
    second_load = store.load("task-1")

    assert first_load.to_dict() == state.to_dict()
    assert second_load.to_dict() == first_load.to_dict()


def test_legacy_session_payload_is_migrated(tmp_path) -> None:
    path = tmp_path / "legacy-task.json"
    path.write_text(
        '{"session_id":"session-1","requirement":"demo",'
        '"file_plan":[{"path":"main.py"}],'
        '"file_statuses":{"main.py":{"status":"completed"}},'
        '"warnings":["legacy warning"]}',
        encoding="utf-8",
    )
    state = CheckpointStore(tmp_path).load("legacy-task")

    assert state.task_id == "session-1"
    assert state.planned_changes == [{"path": "main.py"}]
    assert state.generated_files[0]["status"] == "completed"
    assert state.errors[0]["code"] == "legacy.warning"


def test_unsupported_checkpoint_version_is_rejected(tmp_path) -> None:
    path = tmp_path / "task-1.json"
    path.write_text('{"schema_version":99,"state":{}}', encoding="utf-8")

    try:
        CheckpointStore(tmp_path).load("task-1")
    except ValueError as exc:
        assert "unsupported checkpoint schema version" in str(exc)
    else:
        raise AssertionError("unsupported checkpoint version was accepted")


def test_checkpoint_rejects_path_traversal(tmp_path) -> None:
    store = CheckpointStore(tmp_path)

    for task_id in ("../outside", "nested/task", ""):
        try:
            store.path_for(task_id)
        except ValueError:
            continue
        raise AssertionError(f"unsafe task id was accepted: {task_id!r}")
