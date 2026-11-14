"""spec_first_adapter 与 event_adapter 的全分支补测。"""

import pytest

from app.agent.adapters.event_adapter import progress_event_to_message
from app.agent.adapters.spec_first_adapter import spec_first_result_to_delta


@pytest.mark.parametrize(
    ("stage", "key"),
    [
        ("requirements", "spec_artifacts"),
        ("specification", "spec_artifacts"),
        ("dependency_graph", "graph_artifact"),
        ("topology_schedule", "topology_artifact"),
        ("review", "stage_artifact"),
    ],
)
def test_spec_first_result_routes_artifacts_by_stage(stage, key):
    delta = spec_first_result_to_delta({"payload": 1}, revision=4, stage=stage)

    assert delta.metadata["spec_first_stage"] == stage
    assert delta.metadata[key] == {"payload": 1}
    assert delta.expected_revision == 4
    assert delta.status == "generated"


def test_spec_first_result_only_plans_changes_for_specification():
    plan = [{"path": "a.py"}]

    assert spec_first_result_to_delta(
        {"file_plan": plan}, revision=1, stage="specification"
    ).planned_changes == plan
    assert spec_first_result_to_delta(
        {"file_plan": plan}, revision=1, stage="requirements"
    ).planned_changes == []


def test_spec_first_result_rejects_non_dict():
    with pytest.raises(TypeError, match="must be a dictionary"):
        spec_first_result_to_delta([], revision=1, stage="specification")


@pytest.mark.parametrize(
    ("event", "expected_type", "payload"),
    [
        ('{"type": "file_generated", "path": "a.py"}', "file_generated", {"path": "a.py"}),
        ("plain text progress", "progress", {"message": "plain text progress"}),
        ({"type": "custom", "value": 1}, "custom", {"value": 1}),
        ({"value": 2}, "progress", {"value": 2}),
        (123, "progress", {"value": "123"}),
    ],
)
def test_progress_event_normalizes_input(event, expected_type, payload):
    message = progress_event_to_message(
        event, session_id="s", task_id="t", revision=2, sequence=7
    )

    assert message.type == expected_type
    assert message.payload == payload
    assert message.event_id == "t:2:7"
    assert message.source == "legacy_progress"
    assert message.schema_version == 1


def test_progress_event_does_not_mutate_input_dict():
    event = {"type": "custom", "value": 1}

    message = progress_event_to_message(
        event, session_id="s", task_id="t", revision=1, sequence=1
    )

    assert event == {"type": "custom", "value": 1}
    assert message.payload == {"value": 1}
