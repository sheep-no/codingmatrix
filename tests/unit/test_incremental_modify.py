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
