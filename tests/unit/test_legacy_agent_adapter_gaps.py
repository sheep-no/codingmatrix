"""legacy_agent_adapter 状态、文件与错误归一化补测。"""

from app.agent.adapters.legacy_agent_adapter import legacy_result_to_delta


def _delta(result):
    return legacy_result_to_delta(result, session_id="s1", task_id="t1", revision=3)


def test_non_dict_result_wrapped():
    delta = _delta("done")
    assert delta.status == "completed"
    assert delta.errors == []


def test_explicit_terminal_statuses_are_preserved():
    assert _delta({"status": "failed"}).status == "failed"
    assert _delta({"status": "partial_success"}).status == "partial_success"
    assert _delta({"status": "completed"}).status == "completed"


def test_validation_not_runnable_is_partial():
    delta = _delta({"validation": {"runnable": False}})
    assert delta.status == "partial_success"
    assert delta.validation_results == [{"runnable": False}]


def test_validation_non_dict_is_ignored():
    assert _delta({"validation": "ok"}).validation_results == []


def test_success_false_is_failed():
    assert _delta({"success": False}).status == "failed"


def test_generated_files_dict_is_converted():
    delta = _delta({
        "generated_files": {
            "a.py": {"content": "A = 1"},
            "b.py": "B = 2",
        }
    })

    assert {item["path"] for item in delta.generated_files} == {"a.py", "b.py"}


def test_files_list_filters_non_dict():
    delta = _delta({"files": ["x", {"path": "a.py"}]})
    assert delta.generated_files == [{"path": "a.py"}]


def test_files_non_list_returns_empty():
    assert _delta({"files": "not-a-list"}).generated_files == []


def test_string_errors_become_error_entries():
    delta = _delta({"errors": "boom"})
    assert delta.errors == [
        {"code": "legacy.error", "message": "boom", "retryable": False, "details": {}}
    ]


def test_dict_errors_pass_through():
    delta = _delta({"errors": [{"code": "x"}]})
    assert delta.errors == [{"code": "x"}]


def test_non_list_errors_are_empty():
    assert _delta({"errors": {"code": "x"}}).errors == []


def test_message_envelope_fields():
    delta = _delta({"success": True})
    message = delta.messages[0]
    assert message.event_id == "t1:3:legacy_agent"
    assert message.sequence == 4
    assert message.type == "legacy_agent.completed"
    assert delta.metadata == {"legacy_node": "legacy_agent"}
