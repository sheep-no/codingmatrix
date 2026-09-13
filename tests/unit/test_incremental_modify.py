import inspect
from pathlib import Path

from app.agent.generation_plan import add_profile_components
from app.agent.orchestrator_files import FilesMixin
from app.agent.orchestrator_generation.incremental_modify import IncrementalModifyMixin


def test_select_engineer_does_not_accept_force_model():
    params = inspect.signature(FilesMixin._select_engineer).parameters
    assert "force_model" not in params


def test_simple_change_does_not_pass_force_model():
    source = Path("app/agent/orchestrator_generation/incremental_modify.py").read_text(encoding="utf-8")
    assert "force_model=" not in source


def test_incremental_strict_plan_keeps_architect_files_only():
    context = {"capability_policy": {"component_file_plan": [
        {"path": "app/command.py", "component": "command"},
    ]}}
    change_plan = [
        {"action": "modify", "path": "greet.py", "reason": "add whisper"},
        {"action": "modify", "path": "main.py", "reason": "import whisper"},
    ]
    plan = add_profile_components(
        [change for change in change_plan if change.get("path")],
        context,
        policy="strict",
        requested_paths=[change["path"] for change in change_plan],
    )
    assert {item.path for item in plan.files} == {"greet.py", "main.py"}


def test_add_action_is_simple_change():
    mixin = IncrementalModifyMixin()
    assert mixin._is_simple_change({"action": "add", "path": "app/command.py"}) is True
    assert mixin._is_simple_change({"action": "modify", "path": "greet.py", "reason": "add whisper"}) is False


class _FileEventHarness(IncrementalModifyMixin):
    def __init__(self):
        self.file_events = []
        self.diff_events = []

    def _report_file_event(self, *args, **kwargs):
        self.file_events.append((args, kwargs))

    def _report_file_diff_event(self, *args, **kwargs):
        self.diff_events.append((args, kwargs))


def test_legacy_incremental_emits_file_and_diff_events():
    harness = _FileEventHarness()
    original = "def greet(name):\n    return f'Hello, {name}'\n"
    updated = original + "\ndef whisper(name):\n    return f'Hello, {name}...'\n"
    harness._emit_generated_file_events(
        "greet.py",
        updated,
        {"action": "modify", "reason": "add whisper", "file_type": "utils"},
        original,
    )
    assert harness.file_events == [
        (("greet.py", updated, "add whisper", "utils"), {"operation": "modify"}),
    ]
    assert harness.diff_events == [
        (("greet.py", original, updated), {"operation": "modify"}),
    ]


def test_legacy_incremental_skips_diff_when_content_unchanged():
    harness = _FileEventHarness()
    content = "print('hello')\n"
    harness._emit_generated_file_events(
        "main.py",
        content,
        {"action": "add", "description": "entry", "file_type": "entry"},
        "",
    )
    assert harness.file_events == [
        (("main.py", content, "entry", "entry"), {"operation": "create"}),
    ]
    assert harness.diff_events == []
