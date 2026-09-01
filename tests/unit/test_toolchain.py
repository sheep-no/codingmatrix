import pytest

from app.agent.toolchain import CommandSpec, ToolchainAction, detect_toolchain


def test_toolchain_detects_parameterized_python_commands(tmp_path):
    (tmp_path / "requirements.txt").write_text("pytest\n", encoding="utf-8")

    plan = detect_toolchain(tmp_path)

    assert plan.status == "detected"
    assert plan.for_action(ToolchainAction.TEST).command == ("python3", "-m", "pytest")
    assert plan.for_action(ToolchainAction.TEST).shell is False


@pytest.mark.parametrize("command", [("bash", "run.sh"), ("npm", "test", "&&", "npm", "build")])
def test_toolchain_rejects_shell_execution(command):
    with pytest.raises(ValueError):
        CommandSpec(action=ToolchainAction.TEST, command=command)


def test_toolchain_marks_unknown_workspace_unsupported(tmp_path):
    assert detect_toolchain(tmp_path).status == "unsupported"
