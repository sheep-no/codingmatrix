"""Tests for legacy Agent and progress event adapters."""

from app.agent.adapters import legacy_result_to_delta, progress_event_to_message, spec_first_result_to_delta


def test_legacy_result_maps_files_validation_and_failure() -> None:
    delta = legacy_result_to_delta(
        {"success": False, "files": {"main.py": "print(1)"}, "errors": ["failed"]},
        session_id="s1", task_id="t1", revision=2, node="generate",
    )

    assert delta.status == "failed"
    assert delta.generated_files == [{"path": "main.py", "content": "print(1)"}]
    assert delta.errors[0]["code"] == "legacy.error"
    assert delta.messages[0].type == "generate.completed"


def test_progress_event_maps_json_and_generates_stable_identity() -> None:
    message = progress_event_to_message(
        '{"type":"file_generated","path":"main.py"}',
        session_id="s1", task_id="t1", revision=3, sequence=4,
    )

    assert message.type == "file_generated"
    assert message.payload == {"path": "main.py"}
    assert message.event_id == "t1:3:4"


def test_spec_first_adapter_preserves_stage_artifact() -> None:
    delta = spec_first_result_to_delta(
        {"file_plan": [{"path": "main.py"}], "openapi": {}},
        revision=1,
        stage="specification",
    )

    assert delta.planned_changes == [{"path": "main.py"}]
    assert delta.metadata["spec_artifacts"]["openapi"] == {}
