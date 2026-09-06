import pytest

from app.agent.toolchain import CommandSpec, ToolchainAction, ToolchainRunner, detect_toolchain


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


@pytest.mark.asyncio
async def test_toolchain_runner_executes_parameter_array_without_shell(tmp_path):
    spec = CommandSpec(
        action=ToolchainAction.INSPECT,
        command=("python3", "-c", "print('signature')"),
        timeout_seconds=5,
    )

    result = await ToolchainRunner().run(spec, tmp_path)

    assert result == (0, "signature\n", "")


@pytest.mark.asyncio
async def test_toolchain_runner_rejects_unallowlisted_executable(tmp_path):
    spec = CommandSpec(action=ToolchainAction.INSPECT, command=("rm", "-f", "data"))

    with pytest.raises(ValueError, match="allowlisted"):
        await ToolchainRunner().run(spec, tmp_path)


def test_toolchain_uses_project_install_for_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='demo'\n", encoding="utf-8")

    plan = detect_toolchain(tmp_path)

    assert plan.for_action(ToolchainAction.INSTALL).command == ("python3", "-m", "pip", "install", ".")
